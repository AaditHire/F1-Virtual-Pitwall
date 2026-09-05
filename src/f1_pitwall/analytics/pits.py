"""Observed pit-loss estimates and symmetric pit-timing comparisons."""

from statistics import median

from pydantic import Field

from f1_pitwall.domain import RaceDataset
from f1_pitwall.domain.models import FrozenModel


class PitLossEstimate(FrozenModel):
    pit_loss_ms: int
    sample_count: int
    confidence: float
    max_source_lap: int
    assumption: str


class PitTimingComparison(FrozenModel):
    undercut_gain_ms: float
    overcut_gain_ms: float
    confidence: float = Field(ge=0, le=1)
    assumption: str = "Positive gain favours the named tactic; constant conditions and rival pace."


def calculate_pit_loss(
    dataset: RaceDataset, cutoff_lap: int, fallback_ms: int = 24000
) -> PitLossEstimate:
    """Estimate combined in/out-lap loss against each driver's nearby clean pace."""
    if not 1 <= cutoff_lap <= dataset.metadata.total_laps or fallback_ms <= 0:
        raise ValueError("invalid cutoff or pit loss")
    visible = [lap for lap in dataset.laps if lap.lap_number <= cutoff_lap]
    lookup = {(lap.driver_id, lap.lap_number): lap for lap in visible}
    losses = []
    for lap in visible:
        following = lookup.get((lap.driver_id, lap.lap_number + 1))
        if not lap.pit_in or not following or not following.pit_out:
            continue
        if lap.track_status not in {"", "1"} or following.track_status not in {"", "1"}:
            continue
        times = [
            sample.lap_time_ms
            for sample in visible
            if sample.driver_id == lap.driver_id
            and sample.is_accurate
            and sample.track_status in {"", "1"}
            and not sample.pit_in
            and not sample.pit_out
            and abs(sample.lap_number - lap.lap_number) <= 5
            and sample.lap_time_ms
        ]
        if times and lap.lap_time_ms and following.lap_time_ms:
            loss = lap.lap_time_ms + following.lap_time_ms - 2 * median(times)
            if 5000 <= loss <= 60000:
                losses.append(loss)
    return PitLossEstimate(
        pit_loss_ms=round(median(losses)) if losses else fallback_ms,
        sample_count=len(losses),
        confidence=min(0.85, len(losses) / 8),
        max_source_lap=cutoff_lap,
        assumption="Combined in/out lap excess; fuel/traffic can bias this estimate."
        if losses
        else "No clean observed stops; configured pit-loss assumption.",
    )


def calculate_undercut(
    old_pace_ms: float,
    fresh_pace_ms: float,
    laps: int = 1,
    out_lap_penalty_ms: float = 1800,
    traffic_penalty_ms: float = 0,
    confidence: float = 0.3,
) -> PitTimingComparison:
    """Compare early and delayed stops over the same covered laps and one stop each."""
    if (
        min(old_pace_ms, fresh_pace_ms, laps) <= 0
        or min(out_lap_penalty_ms, traffic_penalty_ms) < 0
    ):
        raise ValueError("invalid pace, horizon or penalties")
    gain = (old_pace_ms - fresh_pace_ms) * laps - out_lap_penalty_ms - traffic_penalty_ms
    return PitTimingComparison(undercut_gain_ms=gain, overcut_gain_ms=-gain, confidence=confidence)


def calculate_overcut(
    old_pace_ms: float,
    fresh_pace_ms: float,
    laps: int = 1,
    out_lap_penalty_ms: float = 1800,
    traffic_penalty_ms: float = 0,
) -> PitTimingComparison:
    """Return both complementary tactics using the same assumptions."""
    return calculate_undercut(
        old_pace_ms, fresh_pace_ms, laps, out_lap_penalty_ms, traffic_penalty_ms
    )
