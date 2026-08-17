from __future__ import annotations

import threading
import time
from uuid import uuid4


def test_stage12b_serializes_complete_pipeline_execution(monkeypatch) -> None:
    import app.pipeline as pipeline

    active = 0
    max_active = 0
    state_lock = threading.Lock()
    entered = threading.Event()
    release = threading.Event()

    def fake_run(job_id) -> None:
        nonlocal active, max_active
        with state_lock:
            active += 1
            max_active = max(max_active, active)
            entered.set()
        release.wait(timeout=2.0)
        with state_lock:
            active -= 1

    monkeypatch.setattr(pipeline, "_run_pipeline", fake_run)

    first = threading.Thread(target=pipeline._run_pipeline_serialized, args=(uuid4(),))
    second = threading.Thread(target=pipeline._run_pipeline_serialized, args=(uuid4(),))
    first.start()
    assert entered.wait(timeout=1.0)
    second.start()

    time.sleep(0.05)
    with state_lock:
        assert max_active == 1
        assert active == 1

    release.set()
    first.join(timeout=1.0)
    second.join(timeout=1.0)
    assert not first.is_alive()
    assert not second.is_alive()
    assert max_active == 1
