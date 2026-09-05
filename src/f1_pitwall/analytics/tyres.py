"""Transparent tyre pace and degradation estimates."""

from f1_pitwall.domain import RaceDataset, TyreTrend


class TyreAnalyzer:
    """Estimate a linear lap-time trend from visible accurate laps."""

    def __init__(self, dataset: RaceDataset) -> None:
        self._dataset = dataset

    def estimate(self, driver_id: str, cutoff_lap: int, window: int = 8) -> TyreTrend:
        """Fit a least-squares trend to the current stint without future laps."""
        if window <= 0:
            raise ValueError("window must be positive")
        if not 1 <= cutoff_lap <= self._dataset.metadata.total_laps:
            raise ValueError("cutoff_lap is outside this race")
        visible = sorted(
            [
                lap
                for lap in self._dataset.laps
                if lap.driver_id == driver_id and lap.lap_number <= cutoff_lap
            ],
            key=lambda lap: lap.lap_number,
        )
        if not visible:
            raise ValueError(f"no visible laps for {driver_id} at lap {cutoff_lap}")

        latest = visible[-1]
        samples = [
            lap
            for lap in visible
            if lap.stint == latest.stint
            and lap.lap_time_ms is not None
            and lap.is_accurate
            and not lap.pit_in
            and not lap.pit_out
            and lap.track_status in {"", "1"}
        ][-window:]

        if not samples:
            return TyreTrend(
                driver_id=driver_id,
                compound=latest.compound,
                stint=latest.stint,
                sample_count=0,
                pace_ms=None,
                degradation_ms_per_lap=None,
                max_source_lap=latest.source_lap,
            )

        pace = round(sum(lap.lap_time_ms or 0 for lap in samples) / len(samples))
        slope = self._linear_slope(
            [
                (
                    float(lap.tyre_age_laps if lap.tyre_age_laps is not None else index),
                    float(lap.lap_time_ms or 0),
                )
                for index, lap in enumerate(samples)
            ]
        )
        return TyreTrend(
            driver_id=driver_id,
            compound=latest.compound,
            stint=latest.stint,
            sample_count=len(samples),
            pace_ms=pace,
            degradation_ms_per_lap=round(slope, 2) if len(samples) >= 3 else None,
            max_source_lap=max(lap.source_lap for lap in samples),
        )

    @staticmethod
    def _linear_slope(points: list[tuple[float, float]]) -> float:
        if len(points) < 2:
            return 0.0
        mean_x = sum(point[0] for point in points) / len(points)
        mean_y = sum(point[1] for point in points) / len(points)
        denominator = sum((point[0] - mean_x) ** 2 for point in points)
        if denominator == 0:
            return 0.0
        return sum((x - mean_x) * (y - mean_y) for x, y in points) / denominator
