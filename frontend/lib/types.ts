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

export type TyreTrend = {
  driver_id: string;
  compound: string;
  stint: number | null;
  sample_count: number;
  pace_ms: number | null;
  degradation_ms_per_lap: number | null;
  max_source_lap: number;
};

export type TrafficAnalysis = {
  driver_id: string;
  assumed_pit_loss_ms: number;
  predicted_rejoin_position: number | null;
  nearby_driver_ids: string[];
  risk: string;
  max_source_lap: number;
};

export type RadioSignal = {
  text: string;
  categories: string[];
  matched_terms: string[];
};

export type KnowledgeHit = {
  source: string;
  title: string;
  content: string;
  season: number | null;
  available_at: string | null;
  score: number;
};

export type EvaluationResult = {
  name: string;
  passed: boolean;
  detail: string;
};

export type AnalysisTrace = {
  session_id: string;
  driver_id: string;
  cutoff_lap: number;
  snapshot_hash: string;
  max_source_lap: number;
  tool_sequence: string[];
  evidence: string[];
  agent_status: "ready" | "requires_key";
};

export type WeatherObservation = {
  observed_at: string;
  temperature_c: number | null;
  precipitation_mm: number | null;
  wind_speed_kmh: number | null;
};

export type Capabilities = Record<string, "ready" | "requires_key">;

export type ActiveView = "replay" | "strategy" | "tyres" | "traffic" | "radio" | "weather" | "trace";
