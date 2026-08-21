from __future__ import annotations

from app.batch_results import _priority
from app.batch_results_models import SeverityCounts


def _rank(
    *,
    human: bool = False,
    omissions: int = 0,
    disagreements: int = 0,
    critical: int = 0,
    high: int = 0,
    insufficient: int = 0,
    medium: int = 0,
    low: int = 0,
) -> int:
    return _priority(
        SeverityCounts(
            critical=critical,
            high=high,
            medium=medium,
            low=low,
        ),
        human_review=human,
        omissions=omissions,
        material_disagreements=disagreements,
        insufficient_evidence=insufficient,
    )


def test_batch_priority_categories_are_strictly_lexicographic() -> None:
    max_lower = 256

    assert _rank(human=True) > _rank(
        omissions=max_lower,
        disagreements=max_lower,
        critical=max_lower,
        high=max_lower,
        insufficient=max_lower,
        medium=max_lower,
        low=max_lower,
    )
    assert _rank(omissions=1) > _rank(
        disagreements=max_lower,
        critical=max_lower,
        high=max_lower,
        insufficient=max_lower,
        medium=max_lower,
        low=max_lower,
    )
    assert _rank(disagreements=1) > _rank(
        critical=max_lower,
        high=max_lower,
        insufficient=max_lower,
        medium=max_lower,
        low=max_lower,
    )
    assert _rank(critical=1) > _rank(
        high=max_lower,
        insufficient=max_lower,
        medium=max_lower,
        low=max_lower,
    )
    assert _rank(high=1) > _rank(
        insufficient=max_lower,
        medium=max_lower,
        low=max_lower,
    )
    assert _rank(insufficient=1) > _rank(medium=max_lower, low=max_lower)
    assert _rank(medium=1) > _rank(low=max_lower)
