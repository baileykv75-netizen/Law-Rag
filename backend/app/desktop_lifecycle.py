from __future__ import annotations

import os
import threading
import webbrowser
from dataclasses import dataclass
from typing import Callable, Protocol

from PIL import Image, ImageDraw


class ServerLike(Protocol):
    should_exit: bool

    def run(self) -> object: ...


@dataclass
class TrayHandle:
    icon: object
    thread: threading.Thread

    def stop(self) -> None:
        stop = getattr(self.icon, "stop", None)
        if callable(stop):
            stop()
        if self.thread.is_alive() and self.thread is not threading.current_thread():
            self.thread.join(timeout=2.0)


@dataclass(frozen=True)
class DesktopLifecycleProbe:
    platform: str
    tray_supported: bool
    pystray_available: bool
    detail: str


def _tray_image() -> Image.Image:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((5, 5, 59, 59), radius=13, fill=(30, 41, 59, 255))
    draw.rectangle((18, 16, 46, 20), fill=(255, 255, 255, 255))
    draw.rectangle((18, 28, 42, 32), fill=(255, 255, 255, 255))
    draw.rectangle((18, 40, 36, 44), fill=(255, 255, 255, 255))
    return image


def probe_desktop_lifecycle() -> DesktopLifecycleProbe:
    if os.name != "nt":
        return DesktopLifecycleProbe(
            platform=os.name,
            tray_supported=False,
            pystray_available=False,
            detail="System-tray lifecycle is enabled only for the Windows desktop release.",
        )
    try:
        import pystray  # noqa: F401
    except Exception as exc:
        return DesktopLifecycleProbe(
            platform=os.name,
            tray_supported=True,
            pystray_available=False,
            detail=f"pystray could not be imported: {type(exc).__name__}: {exc}",
        )
    return DesktopLifecycleProbe(
        platform=os.name,
        tray_supported=True,
        pystray_available=True,
        detail="Windows system-tray dependency is available.",
    )


def start_system_tray(
    url: str,
    request_shutdown: Callable[[], None],
    *,
    force: bool = False,
    pystray_module=None,
    browser_open: Callable[[str], object] = webbrowser.open,
) -> TrayHandle | None:
    """Start a Windows tray icon without changing provider/pipeline behavior.

    `force` and `pystray_module` exist for deterministic tests. Production
    callers use the Windows-only default path and lazy import so Linux CI and
    non-desktop source environments never require a display server.
    """

    if os.name != "nt" and not force:
        return None

    if pystray_module is None:
        try:
            import pystray as pystray_module
        except Exception as exc:
            raise RuntimeError(f"Windows tray runtime is unavailable: {type(exc).__name__}: {exc}") from exc

    def open_workstation(_icon=None, _item=None) -> None:
        browser_open(url)

    def quit_application(icon=None, _item=None) -> None:
        request_shutdown()
        target = icon if icon is not None else tray_icon
        stop = getattr(target, "stop", None)
        if callable(stop):
            stop()

    menu = pystray_module.Menu(
        pystray_module.MenuItem("Open Law-Rag", open_workstation, default=True),
        pystray_module.MenuItem("Quit Law-Rag", quit_application),
    )
    tray_icon = pystray_module.Icon("Law-Rag", _tray_image(), "Law-Rag", menu)
    thread = threading.Thread(
        target=tray_icon.run,
        name="law-rag-system-tray",
        daemon=True,
    )
    thread.start()
    return TrayHandle(icon=tray_icon, thread=thread)


def _recover_storage_cleanup() -> None:
    """Finish crash-interrupted Stage 17.3 cleanup before serving requests.

    The release launcher always configures LAW_RAG_RUNTIME_DIR. Keeping this a
    no-op when the variable is absent avoids touching a developer/source-tree
    runtime merely because a lifecycle unit test runs.
    """

    if not os.getenv("LAW_RAG_RUNTIME_DIR", "").strip():
        return
    from .storage_management import reconcile_storage_cleanup_transactions

    completed, warnings = reconcile_storage_cleanup_transactions()
    if completed:
        print(f"[Law-Rag] Completed {completed} interrupted storage cleanup transaction(s) after restart.")
    for warning in warnings:
        print(f"[Law-Rag] Storage cleanup recovery warning: {warning}")


def run_server_with_desktop_lifecycle(
    server: ServerLike,
    url: str,
    *,
    enable_tray: bool,
    tray_starter: Callable[[str, Callable[[], None]], TrayHandle | None] = start_system_tray,
    cleanup_recovery: Callable[[], None] = _recover_storage_cleanup,
) -> None:
    """Recover safe cleanup, run the local server, and always tear down the tray."""

    tray: TrayHandle | None = None

    def request_shutdown() -> None:
        server.should_exit = True

    # Cleanup transactions move only Job-owned roots. Recovery must complete
    # before the API begins serving history/results so users never see a
    # half-deleted Job or stale batch reference after a crash.
    cleanup_recovery()

    if enable_tray:
        tray = tray_starter(url, request_shutdown)

    try:
        server.run()
    finally:
        if tray is not None:
            tray.stop()
