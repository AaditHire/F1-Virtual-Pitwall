"use client";

import {
  Activity, Bot, ChevronLeft, ChevronRight, CircleGauge, CloudRain, Flag, Headphones,
  Menu, Pause, Play, Radio, RefreshCw, Route, ShieldCheck, Timer, X,
} from "lucide-react";
import { CSSProperties, useEffect, useMemo, useState } from "react";

import {
  RadioPanel, StrategyKnowledge, TracePanel, TrafficPanel, TyrePanel, WeatherPanel,
} from "@/components/feature-panels";
import { LapChart } from "@/components/lap-chart";
import { pitwallRequest } from "@/lib/api";
import type {
  ActiveView, AnalysisTrace, Capabilities, DriverInfo, EvaluationResult, LapTime,
  Metadata, Snapshot, Strategy, TrafficAnalysis, TyreTrend,
} from "@/lib/types";

type Session = { metadata: Metadata; drivers: DriverInfo[] };

const NAV_ITEMS = [
  { id: "replay", label: "Race Replay", icon: Play },
  { id: "strategy", label: "Strategy", icon: CircleGauge },
  { id: "tyres", label: "Tyres", icon: Timer },
  { id: "traffic", label: "Traffic", icon: Route },
  { id: "radio", label: "Radio", icon: Headphones },
  { id: "weather", label: "Weather", icon: CloudRain },
  { id: "trace", label: "Agent Trace", icon: Bot },
] satisfies { id: ActiveView; label: string; icon: typeof Play }[];

function formatTime(ms: number | null) {
  if (ms === null) return "—";
  const minutes = Math.floor(ms / 60_000);
  return `${minutes}:${((ms % 60_000) / 1_000).toFixed(3).padStart(6, "0")}`;
}

function formatGap(ms: number | null, position: number | null) {
  if (position === 1) return "LEADER";
  return ms === null ? "—" : `+${(ms / 1_000).toFixed(3)}`;
}

function actionLabel(action: string) {
  return action.replaceAll("_", " ");
}

export function Dashboard() {
  const [session, setSession] = useState<Session | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [lapTimes, setLapTimes] = useState<LapTime[]>([]);
  const [tyres, setTyres] = useState<TyreTrend | null>(null);
  const [traffic, setTraffic] = useState<TrafficAnalysis | null>(null);
  const [trace, setTrace] = useState<AnalysisTrace | null>(null);
  const [evaluations, setEvaluations] = useState<EvaluationResult[]>([]);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [lap, setLap] = useState(13);
  const [driver, setDriver] = useState("NOR");
  const [playing, setPlaying] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [view, setView] = useState<ActiveView>("replay");
  const [error, setError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [playbackMs, setPlaybackMs] = useState(1500);

  useEffect(() => {
    if (!menuOpen) return;
    function dismiss(event: KeyboardEvent) {
      if (event.key === "Escape") setMenuOpen(false);
    }
    window.addEventListener("keydown", dismiss);
    return () => window.removeEventListener("keydown", dismiss);
  }, [menuOpen]);

  useEffect(() => {
    const controller = new AbortController();
    pitwallRequest<Session>("/session", undefined, controller.signal)
      .then((value) => {
        setSession(value);
        setDriver((current) => value.drivers.some((item) => item.driver_id === current) ? current : (value.drivers[0]?.driver_id ?? ""));
        setLap((current) => Math.min(current, value.metadata.total_laps));
        setError(null);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Unable to connect");
      });
    return () => controller.abort();
  }, [retryKey]);

  const selectedDrivers = useMemo(() => {
    if (!session) return "";
    return Array.from(new Set([driver, ...session.drivers.map((item) => item.driver_id)]))
      .slice(0, 3).join(",");
  }, [driver, session]);

  useEffect(() => {
    if (!session) return;
    const controller = new AbortController();
    pitwallRequest<EvaluationResult[]>("/evaluations", undefined, controller.signal)
      .then(setEvaluations).catch(() => {});
    pitwallRequest<Capabilities>("/capabilities", undefined, controller.signal)
      .then(setCapabilities).catch(() => {});
    return () => controller.abort();
  }, [session, retryKey]);

  useEffect(() => {
    if (!session || !driver || !selectedDrivers) return;
    const controller = new AbortController();
    Promise.all([
      pitwallRequest<Snapshot>(`/snapshot/${lap}`, undefined, controller.signal),
      pitwallRequest<Strategy>(`/strategy/${driver}/${lap}`, undefined, controller.signal),
      pitwallRequest<LapTime[]>(`/lap-times/${lap}?drivers=${selectedDrivers}`, undefined, controller.signal),
      pitwallRequest<TyreTrend>(`/tyres/${driver}/${lap}`, undefined, controller.signal),
      pitwallRequest<TrafficAnalysis>(`/traffic/${driver}/${lap}`, undefined, controller.signal),
      pitwallRequest<AnalysisTrace>(`/trace/${driver}/${lap}`, undefined, controller.signal),
    ]).then(([nextSnapshot, nextStrategy, nextLaps, nextTyres, nextTraffic, nextTrace]) => {
      if (controller.signal.aborted) return;
      setSnapshot(nextSnapshot);
      setStrategy(nextStrategy);
      setLapTimes(nextLaps);
      setTyres(nextTyres);
      setTraffic(nextTraffic);
      setTrace(nextTrace);
      setError(null);
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Unable to load analysis");
    });
    return () => controller.abort();
  }, [driver, lap, retryKey, selectedDrivers, session]);

  const totalLaps = session?.metadata.total_laps ?? 30;
  const refreshing = !session || snapshot?.cutoff_lap !== lap ||
    strategy?.driver_id !== driver || strategy?.cutoff_lap !== lap;
  useEffect(() => {
    if (!playing || refreshing || error) return;
    const timer = window.setTimeout(() => {
      if (lap >= totalLaps) setPlaying(false);
      else setLap((current) => Math.min(current + 1, totalLaps));
    }, lap >= totalLaps ? 0 : playbackMs);
    return () => window.clearTimeout(timer);
  }, [lap, playing, totalLaps, playbackMs, refreshing, error]);

  const chartDrivers = useMemo(
    () => Array.from(new Set(lapTimes.map((item) => item.driver_id))),
    [lapTimes],
  );
  const target = snapshot?.drivers.find((item) => item.driver_id === driver);
  const preferred = strategy?.options.find((item) => item.action === strategy.preferred_action);
  const progress = totalLaps > 1 ? ((lap - 1) / (totalLaps - 1)) * 100 : 100;

  function chooseView(nextView: ActiveView) {
    setView(nextView);
    setMenuOpen(false);
  }

  const standings = (
    <section className="standings panel">
      <div className="section-heading"><div><span>OBSERVED CLASSIFICATION</span><h1>Race state</h1></div><small>END OF LAP {lap}</small></div>
      <div className="table-scroll"><table><thead><tr><th>POS</th><th>DRIVER</th><th>GAP</th><th>COMPOUND</th><th>TYRE AGE</th><th>LAST LAP</th></tr></thead><tbody>
        {snapshot?.drivers.map((item) => <tr key={item.driver_id} className={item.driver_id === driver ? "selected" : ""}><td>{item.position ?? "—"}</td><td><button className="driver-row" onClick={() => setDriver(item.driver_id)} aria-label={`Select ${item.full_name}`}><i className="team-mark" style={{ background: `#${item.team_color}` }} /><span><strong>{item.driver_id}</strong><small>{item.full_name}</small></span></button></td><td>{formatGap(item.gap_to_leader_ms, item.position)}</td><td><b className={`compound ${item.compound.toLowerCase()}`}>{item.compound.at(0)}</b></td><td>{item.tyre_age_laps ?? "—"} LAPS</td><td className="mono">{formatTime(item.last_lap_time_ms)}</td></tr>)}
      </tbody></table></div>
    </section>
  );

  const advisor = (
    <aside className="advisor panel">
      <div className="section-heading"><div><span>STRATEGY ADVISOR</span><h2>{target?.full_name ?? driver}</h2></div><small>LAP {lap}</small></div>
      <div className="recommendation"><span>SHORT-HORIZON COMPARISON</span><strong>{strategy ? actionLabel(strategy.preferred_action) : "ANALYSING"}</strong><div className="confidence"><b>{Math.round((strategy?.confidence ?? 0) * 100)}%</b><i><em style={{ width: `${(strategy?.confidence ?? 0) * 100}%` }} /></i><small>EVIDENCE SCORE</small></div></div>
      <div className="evidence"><h3>Evidence</h3>{strategy?.evidence.map((item) => <p key={item}><ShieldCheck />{item}</p>)}</div>
      <div className="metrics"><div><span>PREDICTED REJOIN</span><strong>{preferred?.predicted_rejoin_position ? `P${preferred.predicted_rejoin_position}` : "—"}</strong></div><div><span>TRAFFIC RISK</span><strong className={preferred?.traffic_risk === "LOW" ? "green" : "amber"}>{preferred?.traffic_risk ?? "—"}</strong></div><div><span>CURRENT TYRE</span><strong>{target?.compound ?? "—"}</strong></div><div><span>TYRE AGE</span><strong>{target?.tyre_age_laps ?? "—"} LAPS</strong></div></div>
      {strategy?.warnings.map((warning) => <p className="feature-note" key={`${warning.code}-${warning.driver_id}`}>{warning.message}</p>)}
    </aside>
  );

  const comparison = (
    <section className="comparison panel"><div className="section-heading"><div><span>DECISION MATRIX</span><h2>Strategy comparison</h2></div></div><div className="option-head"><span>METRIC</span>{strategy?.options.map((option) => <strong key={option.action} className={option.action === strategy.preferred_action ? "best" : ""}>{actionLabel(option.action)}</strong>)}</div>
      {["Race time delta", "Rejoin position", "Traffic risk"].map((label, index) => <div className="option-row" key={label}><span>{label}</span>{strategy?.options.map((option) => <b key={option.action}>{index === 0 ? `+${((option.delta_to_best_ms ?? 0) / 1000).toFixed(1)}s` : index === 1 ? `P${option.predicted_rejoin_position ?? "?"}` : option.traffic_risk}</b>)}</div>)}
      {!strategy?.options.length && <p className="feature-note">No valid pit-delay comparison at this cutoff.</p>}
      <details className="model-assumptions"><summary>Model assumptions</summary>{strategy?.options[0]?.assumptions.map((assumption) => <p key={assumption}>{assumption}</p>)}<p>The evidence score measures sample availability; it is not a calibrated probability of success.</p></details>
      <p className="disclaimer">Projections use only observations through lap {lap}. Safety cars and future weather are unknown.</p>
    </section>
  );

  return (
    <main className="shell">
      <header className="topbar">
        <button className="mobile-menu icon-button" onClick={() => setMenuOpen((open) => !open)} aria-label="Open navigation" aria-expanded={menuOpen} aria-controls="analysis-navigation"><Menu /></button>
        <div className="brand"><Activity /><span>F1 Virtual Pit Wall</span><em>SIM</em></div>
        <div className="selectors"><div><Flag />{session?.metadata.event_name ?? "Loading session…"}</div><label className="driver-select"><i style={{ background: `#${target?.team_color ?? "ff8736"}` }} /><select value={driver} onChange={(event) => setDriver(event.target.value)} aria-label="Driver">{session?.drivers.map((item) => <option key={item.driver_id} value={item.driver_id}>{item.full_name}</option>)}</select></label></div>
        <div className={`sync ${refreshing ? "refreshing" : ""} ${error ? "disconnected" : ""}`} role="status">{refreshing && !error ? <RefreshCw /> : <span />}<div>{error ? "CONNECTION ERROR" : refreshing ? "UPDATING" : "DATA SYNCED"}<small>cutoff-safe replay</small></div></div>
      </header>

      {menuOpen && <button className="menu-backdrop" onClick={() => setMenuOpen(false)} aria-label="Dismiss navigation" />}
      <aside id="analysis-navigation" className={`sidebar ${menuOpen ? "open" : ""}`}>
        <button className="close-menu icon-button" onClick={() => setMenuOpen(false)} aria-label="Close navigation"><X /></button>
        <nav aria-label="Analysis views">{NAV_ITEMS.map(({ id, label, icon: Icon }) => <button key={id} className={id === view ? "active" : ""} onClick={() => chooseView(id)} aria-current={id === view ? "page" : undefined}><Icon />{label}</button>)}</nav>
        <div className="source-card"><span>DATA SOURCE</span><strong><i />{session?.metadata.source ?? "Connecting"}</strong><p><ShieldCheck /> No future laps exposed</p></div>
      </aside>

      <section className="workspace">
        <div className="workspace-heading"><div><span>RACE ENGINEERING / {NAV_ITEMS.find((item) => item.id === view)?.label.toUpperCase()}</span><h1>{session?.metadata.event_name ?? "Connecting to your pit wall"}</h1><p>{session?.metadata.circuit ?? "Loading race context"} · {totalLaps} laps · {session?.drivers.length ?? 0} drivers</p></div><span className="session-badge">{session?.metadata.source.toLowerCase().includes("synthetic") ? "SYNTHETIC DEMO" : "HISTORICAL REPLAY"}</span></div>
        {error && <div className="error-banner" role="alert"><Radio /><span>{error}</span><button onClick={() => setRetryKey((value) => value + 1)}>RETRY</button></div>}
        <section className="replay-strip panel">
          <label className="playback-speed">SPEED<select aria-label="Playback speed" value={playbackMs} onChange={(event) => setPlaybackMs(Number(event.target.value))}><option value={3000}>0.5×</option><option value={1500}>1×</option><option value={750}>2×</option></select></label>
          <div className="lap-control"><strong>LAP {lap}</strong><span>/ {totalLaps}</span><button disabled={lap <= 1} onClick={() => setLap(Math.max(1, lap - 1))} aria-label="Previous lap"><ChevronLeft /></button><button disabled={lap >= totalLaps} onClick={() => setLap(Math.min(totalLaps, lap + 1))} aria-label="Next lap"><ChevronRight /></button></div>
          <div className="timeline"><input style={{ "--progress": `${progress}%` } as CSSProperties} type="range" min="1" max={totalLaps} value={lap} onChange={(event) => setLap(Number(event.target.value))} aria-label="Replay lap" /><div><span>1</span><strong>{lap}</strong><span>{totalLaps}</span></div></div>
          <button className="play-button" disabled={lap >= totalLaps && !playing} onClick={() => setPlaying((value) => !value)} aria-label={playing ? "Pause replay" : "Play replay"}>{playing ? <Pause /> : <Play />}</button>
        </section>

        {refreshing && !["radio", "weather"].includes(view) && <div className="loading-panel panel" role="status"><RefreshCw /><h2>{error ? "Analysis unavailable" : `Loading ${driver} at lap ${lap}`}</h2><p>{error ? "Retry the connection to continue replay." : "Synchronizing race state, tyre model, and strategy evidence."}</p></div>}
        <div hidden={refreshing && !["radio", "weather"].includes(view)}>
        {view === "replay" && <><section className="race-grid">{standings}{advisor}</section><section className="lower-grid"><section className="chart-panel panel"><div className="section-heading"><div><span>PACE MONITOR</span><h2>Lap time trend</h2></div><small>CLEAN LAPS</small></div><LapChart laps={lapTimes} drivers={chartDrivers} cutoff={lap} /></section>{comparison}</section></>}
        {view === "strategy" && <><section className="race-grid">{advisor}<StrategyKnowledge /></section><section className="lower-grid">{comparison}<section className="chart-panel panel"><div className="section-heading"><div><span>PACE CONTEXT</span><h2>Visible lap times</h2></div></div><LapChart laps={lapTimes} drivers={chartDrivers} cutoff={lap} /></section></section></>}
        {view === "tyres" && <><TyrePanel trend={tyres} /><section className="lower-grid"><section className="chart-panel panel"><div className="section-heading"><div><span>PACE MONITOR</span><h2>Lap time trend</h2></div></div><LapChart laps={lapTimes} drivers={chartDrivers} cutoff={lap} /></section>{standings}</section></>}
        {view === "traffic" && <><TrafficPanel traffic={traffic} /><section className="race-grid">{standings}{advisor}</section></>}
        {view === "radio" && <RadioPanel />}
        {view === "weather" && <WeatherPanel />}
        {view === "trace" && <TracePanel trace={trace} evaluations={evaluations} capabilities={capabilities} />}
        </div>
      </section>
    </main>
  );
}
