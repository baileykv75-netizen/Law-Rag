from __future__ import annotations

from app.desktop_lifecycle import run_server_with_desktop_lifecycle, start_system_tray


class FakeThread:
    def __init__(self, *, target, name, daemon):
        self.target = target
        self.name = name
        self.daemon = daemon
        self.started = False
        self.joined = False

    def start(self):
        self.started = True

    def is_alive(self):
        return self.started and not self.joined

    def join(self, timeout=None):
        self.joined = True


class FakeMenuItem:
    def __init__(self, text, action, default=False):
        self.text = text
        self.action = action
        self.default = default


class FakeMenu(list):
    def __init__(self, *items):
        super().__init__(items)


class FakeIcon:
    def __init__(self, name, image, title, menu):
        self.name = name
        self.image = image
        self.title = title
        self.menu = menu
        self.run_called = False
        self.stop_called = False

    def run(self):
        self.run_called = True

    def stop(self):
        self.stop_called = True


class FakePystray:
    Menu = FakeMenu
    MenuItem = FakeMenuItem
    Icon = FakeIcon


class FakeServer:
    def __init__(self):
        self.should_exit = False
        self.run_called = False

    def run(self):
        self.run_called = True


def test_tray_menu_opens_local_workstation_and_requests_shutdown(monkeypatch) -> None:
    opened: list[str] = []
    shutdown: list[bool] = []

    monkeypatch.setattr("app.desktop_lifecycle.threading.Thread", FakeThread)
    handle = start_system_tray(
        "http://127.0.0.1:8000/",
        lambda: shutdown.append(True),
        force=True,
        pystray_module=FakePystray,
        browser_open=lambda url: opened.append(url),
    )

    assert handle is not None
    assert handle.thread.started is True
    assert [item.text for item in handle.icon.menu] == ["Open Law-Rag", "Quit Law-Rag"]
    assert handle.icon.menu[0].default is True

    handle.icon.menu[0].action(handle.icon, handle.icon.menu[0])
    assert opened == ["http://127.0.0.1:8000/"]

    handle.icon.menu[1].action(handle.icon, handle.icon.menu[1])
    assert shutdown == [True]
    assert handle.icon.stop_called is True


def test_server_lifecycle_tray_shutdown_sets_uvicorn_should_exit() -> None:
    server = FakeServer()
    events: list[str] = []

    class Handle:
        def stop(self):
            events.append("tray-stop")

    def tray_starter(url, request_shutdown):
        assert url == "http://127.0.0.1:8000/"
        events.append("tray-start")
        request_shutdown()
        return Handle()

    run_server_with_desktop_lifecycle(
        server,
        "http://127.0.0.1:8000/",
        enable_tray=True,
        tray_starter=tray_starter,
    )

    assert server.should_exit is True
    assert server.run_called is True
    assert events == ["tray-start", "tray-stop"]


def test_server_lifecycle_without_tray_preserves_plain_server_path() -> None:
    server = FakeServer()

    def forbidden_tray(*_args, **_kwargs):
        raise AssertionError("tray should not start")

    run_server_with_desktop_lifecycle(
        server,
        "http://127.0.0.1:8000/",
        enable_tray=False,
        tray_starter=forbidden_tray,
    )

    assert server.run_called is True
    assert server.should_exit is False
