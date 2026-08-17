from __future__ import annotations

import threading
import time
from uuid import uuid4


def test_stage12c_pipeline_executor_is_bounded_to_four_workers() -> None:
    import app.pipeline as pipeline

    active = 0
    max_active = 0
    entered_count = 0
    state_lock = threading.Lock()
    four_entered = threading.Event()
    release = threading.Event()

    def fake_run(job_id) -> None:
        nonlocal active, max_active, entered_count
        with state_lock:
            active += 1
            entered_count += 1
            max_active = max(max_active, active)
            if entered_count >= pipeline.PIPELINE_MAX_WORKERS:
                four_entered.set()
        release.wait(timeout=2.0)
        with state_lock:
            active -= 1

    futures = [
        pipeline._EXECUTOR.submit(fake_run, uuid4())
        for _ in range(pipeline.PIPELINE_MAX_WORKERS + 1)
    ]

    assert four_entered.wait(timeout=1.0)
    time.sleep(0.05)
    with state_lock:
        assert active == pipeline.PIPELINE_MAX_WORKERS
        assert max_active == pipeline.PIPELINE_MAX_WORKERS
        assert entered_count == pipeline.PIPELINE_MAX_WORKERS

    release.set()
    for future in futures:
        future.result(timeout=1.0)

    assert max_active == pipeline.PIPELINE_MAX_WORKERS
