"use client";

import { Bot, CheckCircle2, CloudRain, Headphones, Search, ShieldCheck, XCircle } from "lucide-react";
import { FormEvent, useState } from "react";

import { pitwallRequest } from "@/lib/api";
import type {
  AnalysisTrace,
  Capabilities,
  EvaluationResult,
  KnowledgeHit,
  RadioSignal,
  TrafficAnalysis,
  TyreTrend,
  WeatherObservation,
} from "@/lib/types";

function valueOrDash(value: number | null, suffix = "") {
  return value === null ? "—" : `${value}${suffix}`;
}

export function TyrePanel({ trend }: { trend: TyreTrend | null }) {
  return (
    <section className="feature-grid">
      <article className="feature-card panel feature-wide">
        <div className="section-heading"><div><span>TYRE MODEL</span><h1>Current-stint degradation</h1></div><small>CUTOFF SAFE</small></div>
        <div className="feature-metrics">
          <div><span>COMPOUND</span><strong>{trend?.compound ?? "—"}</strong></div>
          <div><span>STINT</span><strong>{valueOrDash(trend?.stint ?? null)}</strong></div>
          <div><span>CLEAN SAMPLES</span><strong>{trend?.sample_count ?? 0}</strong></div>
          <div><span>ESTIMATED PACE</span><strong>{trend?.pace_ms ? `${(trend.pace_ms / 1000).toFixed(3)}s` : "—"}</strong></div>
          <div><span>DEGRADATION</span><strong>{trend?.degradation_ms_per_lap === null || trend?.degradation_ms_per_lap === undefined ? "—" : `${trend.degradation_ms_per_lap.toFixed(1)} ms/lap`}</strong></div>
          <div><span>MAX SOURCE LAP</span><strong>{trend?.max_source_lap ?? "—"}</strong></div>
        </div>
        <p className="feature-note">A transparent linear fit over accurate laps in the current stint. Pit-in, pit-out, and disrupted laps are excluded.</p>
      </article>
    </section>
  );
}

export function TrafficPanel({ traffic }: { traffic: TrafficAnalysis | null }) {
  return (
    <section className="feature-grid">
      <article className="feature-card panel feature-wide">
        <div className="section-heading"><div><span>PIT-WINDOW ANALYSIS</span><h1>Predicted green-flag rejoin</h1></div><small>FIXED LOSS MODEL</small></div>
        <div className="feature-metrics">
          <div><span>ASSUMED PIT LOSS</span><strong>{traffic ? `${(traffic.assumed_pit_loss_ms / 1000).toFixed(1)}s` : "—"}</strong></div>
          <div><span>REJOIN POSITION</span><strong>{traffic?.predicted_rejoin_position ? `P${traffic.predicted_rejoin_position}` : "—"}</strong></div>
          <div><span>TRAFFIC RISK</span><strong className={traffic?.risk === "LOW" ? "green" : "amber"}>{traffic?.risk ?? "—"}</strong></div>
          <div><span>NEARBY CARS</span><strong>{traffic?.nearby_driver_ids.join(", ") || "NONE"}</strong></div>
        </div>
        <p className="feature-note">This V1 estimate holds pit loss constant and compares the projected gap with the observed field at the selected lap.</p>
      </article>
    </section>
  );
}

export function RadioPanel() {
  const [text, setText] = useState("Box, box. Tyres are sliding in traffic.");
  const [signal, setSignal] = useState<RadioSignal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    try {
      setSignal(await pitwallRequest<RadioSignal>("/radio/classify", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text }),
      }));
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Radio analysis failed");
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="feature-grid">
      <article className="feature-card panel feature-wide">
        <div className="section-heading"><div><span>RADIO INTELLIGENCE</span><h1>Transcript classifier</h1></div><Headphones /></div>
        <form className="feature-form" onSubmit={submit}>
          <label htmlFor="radio-text">Team radio transcript</label>
          <textarea id="radio-text" value={text} onChange={(event) => setText(event.target.value)} minLength={1} maxLength={2_000} required />
          <button disabled={pending}>{pending ? "CLASSIFYING…" : "CLASSIFY RADIO"}</button>
        </form>
        {error && <p className="inline-error">{error}</p>}
        {signal && <div className="result-block"><span>CATEGORIES</span><div className="chips">{signal.categories.map((category) => <b key={category}>{category}</b>)}</div><span>MATCHED TERMS</span><p>{signal.matched_terms.join(", ") || "No strategy keywords detected."}</p></div>}
      </article>
    </section>
  );
}

export function StrategyKnowledge() {
  const [query, setQuery] = useState("undercut tyre degradation");
  const [hits, setHits] = useState<KnowledgeHit[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      setHits(await pitwallRequest<KnowledgeHit[]>(`/knowledge/search?query=${encodeURIComponent(query)}`));
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Knowledge search failed");
    }
  }

  return (
    <article className="feature-card panel">
      <div className="section-heading"><div><span>HISTORICAL RAG</span><h2>Strategy knowledge</h2></div><Search /></div>
      <form className="search-form" onSubmit={submit}><label className="sr-only" htmlFor="knowledge-query">Knowledge query</label><input id="knowledge-query" value={query} onChange={(event) => setQuery(event.target.value)} required /><button>SEARCH</button></form>
      {error && <p className="inline-error">{error}</p>}
      <div className="knowledge-results">{hits.length ? hits.map((hit) => <article key={hit.source}><strong>{hit.title}</strong><p>{hit.content.slice(0, 240)}{hit.content.length > 240 ? "…" : ""}</p><small>{hit.source}</small></article>) : <p>Search the local, source-attributed strategy index.</p>}</div>
    </article>
  );
}

export function WeatherPanel() {
  const [observations, setObservations] = useState<WeatherObservation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function loadWeather() {
    setPending(true);
    try {
      setObservations(await pitwallRequest<WeatherObservation[]>("/weather?latitude=26.0325&longitude=50.5106&day=2024-03-02"));
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Weather lookup failed");
    } finally {
      setPending(false);
    }
  }

  const wetHours = observations.filter((item) => (item.precipitation_mm ?? 0) > 0).length;
  const temperatures = observations.flatMap((item) => item.temperature_c === null ? [] : [item.temperature_c]);
  const minimumTemperature = temperatures.length ? `${Math.min(...temperatures).toFixed(1)}°C` : "—";
  const maximumTemperature = temperatures.length ? `${Math.max(...temperatures).toFixed(1)}°C` : "—";
  return (
    <section className="feature-grid">
      <article className="feature-card panel feature-wide">
        <div className="section-heading"><div><span>FREE HISTORICAL FEED</span><h1>Bahrain race-day weather</h1></div><CloudRain /></div>
        <div className="feature-action"><p>Load hourly observations for Bahrain International Circuit on 2 March 2024 from Open-Meteo.</p><button onClick={() => void loadWeather()} disabled={pending}>{pending ? "LOADING…" : "LOAD WEATHER"}</button></div>
        {error && <p className="inline-error">{error}</p>}
        {observations.length > 0 && <><div className="feature-metrics"><div><span>OBSERVATIONS</span><strong>{observations.length}</strong></div><div><span>MIN TEMP</span><strong>{minimumTemperature}</strong></div><div><span>MAX TEMP</span><strong>{maximumTemperature}</strong></div><div><span>WET HOURS</span><strong>{wetHours}</strong></div></div><div className="weather-list">{observations.slice(0, 8).map((item) => <div key={item.observed_at}><span>{new Date(item.observed_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", timeZone: "UTC" })} UTC</span><strong>{valueOrDash(item.temperature_c, "°C")}</strong><small>{valueOrDash(item.precipitation_mm, " mm")}</small></div>)}</div></>}
      </article>
    </section>
  );
}

export function TracePanel({ trace, evaluations, capabilities }: { trace: AnalysisTrace | null; evaluations: EvaluationResult[]; capabilities: Capabilities | null }) {
  return (
    <section className="feature-grid trace-grid">
      <article className="feature-card panel">
        <div className="section-heading"><div><span>DETERMINISTIC TRACE</span><h1>Analysis provenance</h1></div><Bot /></div>
        <dl className="trace-list"><div><dt>Driver / cutoff</dt><dd>{trace ? `${trace.driver_id} / L${trace.cutoff_lap}` : "—"}</dd></div><div><dt>Maximum source lap</dt><dd>{trace?.max_source_lap ?? "—"}</dd></div><div><dt>Snapshot hash</dt><dd className="hash">{trace?.snapshot_hash ?? "—"}</dd></div><div><dt>Tool sequence</dt><dd>{trace?.tool_sequence.join(" → ") ?? "—"}</dd></div><div><dt>LLM agent</dt><dd>{capabilities?.agent === "requires_key" ? "Optional key required" : "Ready"}</dd></div></dl>
      </article>
      <article className="feature-card panel">
        <div className="section-heading"><div><span>AUTOMATED CHECKS</span><h2>Historical replay evaluations</h2></div><ShieldCheck /></div>
        <div className="evaluation-list">{evaluations.map((evaluation) => <div key={evaluation.name}>{evaluation.passed ? <CheckCircle2 /> : <XCircle />}<span><strong>{evaluation.name.replaceAll("_", " ")}</strong><small>{evaluation.detail}</small></span></div>)}</div>
      </article>
    </section>
  );
}
