"""Deterministic invariants used as the first evaluation suite."""

from pydantic import BaseModel, ConfigDict

from f1_pitwall.application import PitWallService


class EvaluationResult(BaseModel):
    """One machine-readable evaluation outcome."""

    model_config = ConfigDict(frozen=True)

    name: str
    passed: bool
    detail: str


def run_evaluations(service: PitWallService) -> tuple[EvaluationResult, ...]:
    """Evaluate cutoff safety, determinism, and explainability."""
    lap = min(18, service.dataset.metadata.total_laps)
    driver_id = next(iter(service.dataset.drivers))
    first = service.snapshot(lap)
    second = service.snapshot(lap)
    assessment = service.strategy(lap, driver_id)
    max_seen = max((driver.max_source_lap for driver in first.drivers), default=0)
    return (
        EvaluationResult(
            name="cutoff_safety",
            passed=max_seen <= lap and assessment.max_source_lap <= lap,
            detail=(
                f"Maximum source lap was {max(max_seen, assessment.max_source_lap)} "
                f"at cutoff {lap}."
            ),
        ),
        EvaluationResult(
            name="snapshot_determinism",
            passed=first.snapshot_hash == second.snapshot_hash,
            detail=f"Repeated hash: {first.snapshot_hash}.",
        ),
        EvaluationResult(
            name="strategy_explainability",
            passed=bool(assessment.evidence)
            and all(option.assumptions for option in assessment.options),
            detail=f"Produced {len(assessment.evidence)} evidence statements.",
        ),
    )
