from __future__ import annotations

import errno
import json
import threading

from app.safe_persistence import atomic_write_text, read_text_with_retry


def test_atomic_write_retries_transient_windows_style_sharing_violation(tmp_path, monkeypatch) -> None:
    target = tmp_path / "pipeline.json"
    target.write_text('{"version":0}', encoding="utf-8")

    import app.safe_persistence as persistence

    real_replace = persistence.os.replace
    calls = 0

    def flaky_replace(source, destination):
        nonlocal calls
        calls += 1
        if calls < 4:
            exc = PermissionError(errno.EACCES, "sharing violation")
            exc.winerror = 32
            raise exc
        return real_replace(source, destination)

    monkeypatch.setattr(persistence.os, "replace", flaky_replace)
    monkeypatch.setattr(persistence.time, "sleep", lambda _: None)

    atomic_write_text(target, '{"version":1}')

    assert calls == 4
    assert json.loads(target.read_text(encoding="utf-8")) == {"version": 1}


def test_same_path_concurrent_writers_and_readers_never_observe_partial_json(tmp_path) -> None:
    target = tmp_path / "pipeline.json"
    atomic_write_text(target, json.dumps({"writer": -1, "iteration": -1}))
    errors: list[Exception] = []

    def writer(writer_id: int) -> None:
        try:
            for iteration in range(40):
                atomic_write_text(
                    target,
                    json.dumps({"writer": writer_id, "iteration": iteration}),
                    base_delay_seconds=0.001,
                )
        except Exception as exc:  # pragma: no cover - failure is asserted below
            errors.append(exc)

    def reader() -> None:
        try:
            for _ in range(100):
                payload = json.loads(read_text_with_retry(target, base_delay_seconds=0.001))
                assert isinstance(payload["writer"], int)
                assert isinstance(payload["iteration"], int)
        except Exception as exc:  # pragma: no cover - failure is asserted below
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(index,)) for index in range(4)]
    threads += [threading.Thread(target=reader) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors
    assert all(not thread.is_alive() for thread in threads)
    json.loads(target.read_text(encoding="utf-8"))
