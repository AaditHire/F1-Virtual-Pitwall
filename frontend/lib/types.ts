export type Metadata = {
  session_id: string;
  event_name: string;
  circuit: string;
  total_laps: number;
  source: string;
};

export type DriverInfo = {
  driver_id: string;
  full_name: string;
  team_name: string;
  team_color: string;
};

export type DriverState = DriverInfo & {
  position: number | null;
  gap_to_leader_ms: number | null;
  interval_ahead_ms: number | null;
  compound: string;
  tyre_age_laps: number | null;
  pit_stop_count: number;
  last_lap_time_ms: number | null;
  status: string;
};

export type Snapshot = {
  cutoff_lap: number;
  total_laps: number;
  drivers: DriverState[];
  snapshot_hash: string;
};

export type StrategyOption = {
  action: string;
  projected_time_ms: number | null;
  delta_to_best_ms: number | null;
  predicted_rejoin_position: number | null;
  traffic_risk: string;
  assumptions: string[];
};

export type Strategy = {
  preferred_action: string;
  confidence: number;
  evidence: string[];
  options: StrategyOption[];
};

export type LapTime = {
  driver_id: string;
  lap_number: number;
  lap_time_ms: number;
  compound: string;
};
