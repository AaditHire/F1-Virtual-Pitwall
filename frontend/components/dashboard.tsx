"use client";

import {
  Activity,
  Bot,
  ChevronLeft,
  ChevronRight,
  CircleGauge,
  CloudRain,
  Flag,
  Headphones,
  Menu,
  Pause,
  Play,
  Radio,
  Route,
  ShieldCheck,
  Timer,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { LapChart } from "@/components/lap-chart";
import type { DriverInfo, LapTime, Metadata, Snapshot, Strategy } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_PITWALL_API_URL ?? "http://127.0.0.1:8000";

type Session = { metadata: Metadata; drivers: DriverInfo[] };

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
  const [lap, setLap] = useState(13);
  const [driver, setDriver] = useState("NOR");
  const [playing, setPlaying] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API}/api/v1/session`)
      .then((response) => {
        if (!response.ok) throw new Error("Pit-wall API is unavailable");
        return response.json() as Promise<Session>;
      })
      .then((value) => {
        setSession(value);
        setDriver((current) =>
          value.drivers.some((item) => item.driver_id === current)
            ? current
            : (value.drivers[0]?.driver_id ?? ""),
        );
        setLap(Math.min(13, value.metadata.total_laps));
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to connect"));
  }, []);

  const loadLap = useCallback(async () => {
    if (!session || !driver) return;
    try {
      const selected = session.drivers.slice(0, 3).map((item) => item.driver_id).join(",");
      const [stateResponse, strategyResponse, timesResponse] = await Promise.all([
        fetch(`${API}/api/v1/snapshot/${lap}`),
        fetch(`${API}/api/v1/strategy/${driver}/${lap}`),
        fetch(`${API}/api/v1/lap-times/${lap}?drivers=${selected}`),
      ]);
      if (![stateResponse, strategyResponse, timesResponse].every((response) => response.ok)) {
        throw new Error("Analysis could not be loaded for this lap");
      }
      setSnapshot(await stateResponse.json() as Snapshot);
      setStrategy(await strategyResponse.json() as Strategy);
      setLapTimes(await timesResponse.json() as LapTime[]);
      setError(null);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Unable to load analysis");
    }
  }, [driver, lap, session]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadLap(), 0);
    return () => window.clearTimeout(timer);
  }, [loadLap]);

  useEffect(() => {
    if (!playing || !session) return;
    const timer = window.setInterval(() => {
      setLap((current) => current >= session.metadata.total_laps ? 1 : current + 1);
    }, 1_500);
    return () => window.clearInterval(timer);
  }, [playing, session]);

  const chartDrivers = useMemo(
    () => Array.from(new Set(lapTimes.map((item) => item.driver_id))),
    [lapTimes],
  );
  const target = snapshot?.drivers.find((item) => item.driver_id === driver);
  const preferred = strategy?.options.find((item) => item.action === strategy.preferred_action);
  const totalLaps = session?.metadata.total_laps ?? 30;

  return (
    <main className="shell">
      <header className="topbar">
        <button className="mobile-menu icon-button" onClick={() => setMenuOpen(true)} aria-label="Open navigation"><Menu /></button>
        <div className="brand"><Activity /><span>F1 Virtual Pit Wall</span><em>SIM</em></div>
        <div className="selectors">
          <div><Flag />{session?.metadata.event_name ?? "Loading session…"}</div>
          <label className="driver-select"><i style={{ background: `#${target?.team_color ?? "ff8736"}` }} /><select value={driver} onChange={(event) => setDriver(event.target.value)} aria-label="Driver">
            {session?.drivers.map((item) => <option key={item.driver_id} value={item.driver_id}>{item.full_name}</option>)}
          </select></label>
        </div>
        <div className="sync"><span /><div>DATA SYNCED<small>cutoff-safe replay</small></div></div>
      </header>

      <aside className={`sidebar ${menuOpen ? "open" : ""}`}>
        <button className="close-menu icon-button" onClick={() => setMenuOpen(false)} aria-label="Close navigation"><X /></button>
        <nav>
          <a className="active"><Play />Race Replay</a>
          <a><CircleGauge />Strategy</a><a><Timer />Tyres</a><a><Route />Traffic</a>
          <a><Headphones />Radio</a><a><CloudRain />Weather</a><a><Bot />Agent Trace</a>
        </nav>
        <div className="source-card"><span>DATA SOURCE</span><strong><i />{session?.metadata.source ?? "Connecting"}</strong><p><ShieldCheck /> No future laps exposed</p></div>
      </aside>

      <section className="workspace">
        {error && <div className="error-banner"><Radio />{error}. Start the backend with <code>pitwall serve</code>.</div>}
        <section className="replay-strip panel">
          <div className="lap-control"><strong>LAP {lap}</strong><span>/ {totalLaps}</span><button onClick={() => setLap(Math.max(1, lap - 1))} aria-label="Previous lap"><ChevronLeft /></button><button onClick={() => setLap(Math.min(totalLaps, lap + 1))} aria-label="Next lap"><ChevronRight /></button></div>
          <div className="timeline"><input type="range" min="1" max={totalLaps} value={lap} onChange={(event) => setLap(Number(event.target.value))} aria-label="Replay lap" /><div><span>1</span><strong>{lap}</strong><span>{totalLaps}</span></div></div>
          <button className="play-button" onClick={() => setPlaying(!playing)} aria-label={playing ? "Pause replay" : "Play replay"}>{playing ? <Pause /> : <Play />}</button>
        </section>

        <section className="race-grid">
          <section className="standings panel">
            <div className="section-heading"><div><span>LIVE CLASSIFICATION</span><h1>Race state</h1></div><small>END OF LAP {lap}</small></div>
            <div className="table-scroll"><table><thead><tr><th>POS</th><th>DRIVER</th><th>GAP</th><th>COMPOUND</th><th>TYRE AGE</th><th>LAST LAP</th></tr></thead><tbody>
              {snapshot?.drivers.map((item) => <tr key={item.driver_id} className={item.driver_id === driver ? "selected" : ""} onClick={() => setDriver(item.driver_id)}><td>{item.position ?? "—"}</td><td><i className="team-mark" style={{ background: `#${item.team_color}` }} /><strong>{item.driver_id}</strong><small>{item.full_name}</small></td><td>{formatGap(item.gap_to_leader_ms, item.position)}</td><td><b className={`compound ${item.compound.toLowerCase()}`}>{item.compound.at(0)}</b></td><td>{item.tyre_age_laps ?? "—"} LAPS</td><td className="mono">{formatTime(item.last_lap_time_ms)}</td></tr>)}
            </tbody></table></div>
          </section>

          <aside className="advisor panel">
            <div className="section-heading"><div><span>STRATEGY ADVISOR</span><h2>{target?.full_name ?? driver}</h2></div><small>LAP {lap}</small></div>
            <div className="recommendation"><span>RECOMMENDATION</span><strong>{strategy ? actionLabel(strategy.preferred_action) : "ANALYSING"}</strong><div className="confidence"><b>{Math.round((strategy?.confidence ?? 0) * 100)}%</b><i><em style={{ width: `${(strategy?.confidence ?? 0) * 100}%` }} /></i><small>MODEL CONFIDENCE</small></div></div>
            <div className="evidence"><h3>Evidence</h3>{strategy?.evidence.map((item) => <p key={item}><ShieldCheck />{item}</p>)}</div>
            <div className="metrics"><div><span>PREDICTED REJOIN</span><strong>P{preferred?.predicted_rejoin_position ?? "?"}</strong></div><div><span>TRAFFIC RISK</span><strong className="green">{preferred?.traffic_risk ?? "—"}</strong></div><div><span>CURRENT TYRE</span><strong>{target?.compound ?? "—"}</strong></div><div><span>TYRE AGE</span><strong>{target?.tyre_age_laps ?? "—"} LAPS</strong></div></div>
          </aside>
        </section>

        <section className="lower-grid">
          <section className="chart-panel panel"><div className="section-heading"><div><span>PACE MONITOR</span><h2>Lap time trend</h2></div><small>CLEAN LAPS</small></div><LapChart laps={lapTimes} drivers={chartDrivers} cutoff={lap} /></section>
          <section className="comparison panel"><div className="section-heading"><div><span>DECISION MATRIX</span><h2>Strategy comparison</h2></div></div><div className="option-head"><span>METRIC</span>{strategy?.options.map((option) => <strong key={option.action} className={option.action === strategy.preferred_action ? "best" : ""}>{actionLabel(option.action)}</strong>)}</div>
            {["Race time delta", "Rejoin position", "Traffic risk"].map((label, index) => <div className="option-row" key={label}><span>{label}</span>{strategy?.options.map((option) => <b key={option.action}>{index === 0 ? `+${((option.delta_to_best_ms ?? 0) / 1000).toFixed(1)}s` : index === 1 ? `P${option.predicted_rejoin_position ?? "?"}` : option.traffic_risk}</b>)}</div>)}
            <p className="disclaimer">Projections use only observations through lap {lap}. Safety cars and future weather are unknown.</p>
          </section>
        </section>
      </section>
    </main>
  );
}
