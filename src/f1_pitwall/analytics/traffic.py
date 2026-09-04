"""Green-flag pit rejoin and traffic analysis."""

from f1_pitwall.domain import RaceSnapshot, TrafficAnalysis, TrafficRisk


class TrafficAnalyzer:
    """Estimate rejoin order from current gaps and a fixed pit-loss assumption."""

    def analyze(
        self,
        snapshot: RaceSnapshot,
        driver_id: str,
        pit_loss_ms: int = 24_000,
        proximity_ms: int = 3_000,
    ) -> TrafficAnalysis:
        """Return predicted position and nearby cars without mutating race state."""
        target = next(
            (driver for driver in snapshot.drivers if driver.driver_id == driver_id), None
        )
        if target is None:
            raise ValueError(f"driver {driver_id} is not present in the snapshot")
        if target.gap_to_leader_ms is None:
            return TrafficAnalysis(
                driver_id=driver_id,
                assumed_pit_loss_ms=pit_loss_ms,
                predicted_rejoin_position=None,
                nearby_driver_ids=(),
                risk=TrafficRisk.UNKNOWN,
                max_source_lap=target.max_source_lap,
            )

        projected_gap = target.gap_to_leader_ms + pit_loss_ms
        rivals = [
            driver
            for driver in snapshot.drivers
            if driver.driver_id != driver_id and driver.gap_to_leader_ms is not None
        ]
        predicted_position = 1 + sum(
            1 for driver in rivals if (driver.gap_to_leader_ms or 0) < projected_gap
        )
        nearby = tuple(
            driver.driver_id
            for driver in rivals
            if abs((driver.gap_to_leader_ms or 0) - projected_gap) <= proximity_ms
        )
        risk = TrafficRisk.LOW
        if len(nearby) >= 3:
            risk = TrafficRisk.HIGH
        elif nearby:
            risk = TrafficRisk.MEDIUM
        return TrafficAnalysis(
            driver_id=driver_id,
            assumed_pit_loss_ms=pit_loss_ms,
            predicted_rejoin_position=predicted_position,
            nearby_driver_ids=nearby,
            risk=risk,
            max_source_lap=max(driver.max_source_lap for driver in snapshot.drivers),
        )
