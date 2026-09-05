import type { LapTime } from "@/lib/types";

const COLORS = ["#ff8736", "#28c5d9", "#edf0f2", "#e23b45", "#48c77e", "#9d83ff"];

export function LapChart({ laps, drivers, cutoff }: { laps: LapTime[]; drivers: string[]; cutoff: number }) {
  const valid = laps.filter((lap) => lap.is_clean && lap.lap_number <= cutoff)
    .sort((a, b) => a.lap_number - b.lap_number);
  if (!valid.length) return <div className="chart-empty">No clean lap data at this cutoff.</div>;
  const values = valid.map((lap) => lap.lap_time_ms);
  const min = Math.min(...values) - 500;
  const max = Math.max(...values) + 500;
  const x = (lap: number) => 42 + ((lap - 1) / Math.max(1, cutoff - 1)) * 718;
  const y = (time: number) => 164 - ((time - min) / Math.max(1, max - min)) * 130;

  return (
    <div className="chart-wrap">
      <div className="legend">
        {drivers.map((driver, index) => (
          <span key={driver}><i style={{ background: COLORS[index] }} />{driver}</span>
        ))}
      </div>
      <svg viewBox="0 0 800 190" role="img" aria-label="Lap time trend">
        {[0, 1, 2, 3].map((line) => {
          const lineY = 34 + line * 43;
          return <g key={line}><line x1="42" x2="760" y1={lineY} y2={lineY} className="grid-line" /><text x="0" y={lineY + 3} className="axis-text">{((max - (line / 3) * (max - min)) / 1000).toFixed(1)}s</text></g>;
        })}
        {drivers.map((driver, index) => {
          const points = valid
            .filter((lap) => lap.driver_id === driver)
            .map((lap) => `${x(lap.lap_number)},${y(lap.lap_time_ms)}`)
            .join(" ");
          return <g key={driver}><polyline points={points} fill="none" stroke={COLORS[index]} strokeWidth="2" />{valid.filter((lap) => lap.driver_id === driver).map((lap) => <circle key={lap.lap_number} cx={x(lap.lap_number)} cy={y(lap.lap_time_ms)} r="2.5" fill={COLORS[index]}><title>{driver} · Lap {lap.lap_number} · {(lap.lap_time_ms / 1000).toFixed(3)}s</title></circle>)}</g>;
        })}
        <line x1={x(cutoff)} x2={x(cutoff)} y1="22" y2="168" stroke="#ef3c43" />
        <text x="42" y="185" className="axis-text">LAP 1</text>
        <text x="730" y="185" className="axis-text">LAP {cutoff}</text>
      </svg>
    </div>
  );
}
