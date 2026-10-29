import { WEEKDAYS, fmtInt, hourLabel, type Slot } from "../data/derive";
import { useExplorer } from "../state/store";

/** Detail for the clicked bar: that day's 24-hour profile and that hour across the week. */
export function SlotDetail({ grid, slot }: { grid: number[][]; slot: Slot }) {
  const setSelected = useExplorer((s) => s.setSelected);
  const day = grid[slot.day] ?? [];
  const week = grid.map((row) => row[slot.hour] ?? 0);
  const flat = grid.flat();
  const avg = flat.reduce((a, b) => a + b, 0) / (flat.length || 1);
  const rank = [...flat].sort((a, b) => b - a).indexOf(slot.trips) + 1;
  const dayMax = Math.max(...day, 1);
  const dayMin = Math.min(...day);
  const yOf = (v: number) => H - ((v - dayMin) / (dayMax - dayMin || 1)) * (H - 10) - 5;
  const weekMax = Math.max(...week, 1);
  const W = 300;
  const H = 70;
  const pts = day.map((v, h) => `${(h / 23) * W},${yOf(v)}`).join(" ");

  return (
    <div className="px-4 pb-4 pt-2">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[22px] font-semibold tabular-nums">{fmtInt.format(slot.trips)}</div>
          <div className="text-xs text-muted">pickups on {WEEKDAYS[slot.day]} {hourLabel(slot.hour)}</div>
        </div>
        <button
          type="button"
          onClick={() => setSelected(null)}
          className="rounded-lg border border-line px-2.5 py-1 text-xs text-muted hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-system"
        >
          Back to peaks
        </button>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-lg bg-white/[0.03] px-3 py-2"><dt className="text-muted">vs average hour</dt><dd className="text-[15px] font-semibold tabular-nums">{avg ? `${(slot.trips / avg).toFixed(2)}x` : "n/a"}</dd></div>
        <div className="rounded-lg bg-white/[0.03] px-3 py-2"><dt className="text-muted">rank of 168 hours</dt><dd className="text-[15px] font-semibold tabular-nums">#{rank}</dd></div>
      </dl>

      <h3 className="mt-4 text-xs font-semibold text-muted">{WEEKDAYS[slot.day]}, hour by hour</h3>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-1 h-[70px] w-full" role="img" aria-label={`Pickups through ${WEEKDAYS[slot.day]}`}>
        <polyline points={pts} fill="none" stroke="#f7b733" strokeWidth="2" strokeLinejoin="round" />
        <text x="0" y={H} className="fill-dim text-[9px]">00:00</text>
        <text x={W} y={H} textAnchor="end" className="fill-dim text-[9px]">23:00</text>
        <circle cx={(slot.hour / 23) * W} cy={yOf(slot.trips)} r="4" fill="#fff" />
      </svg>

      <h3 className="mt-3 text-xs font-semibold text-muted">{hourLabel(slot.hour)} across the week</h3>
      <ul className="mt-1.5 space-y-1">
        {week.map((v, d) => (
          <li key={d} className="grid grid-cols-[32px_1fr_44px] items-center gap-2 text-[11.5px]">
            <span className={d === slot.day ? "font-semibold text-ink" : "text-muted"}>{WEEKDAYS[d]}</span>
            <span className="h-2 overflow-hidden rounded-full bg-white/[0.04]">
              <span className={`block h-full rounded-full ${d === slot.day ? "bg-gradient-to-r from-demand to-heat" : "bg-system/70"}`} style={{ width: `${(v / weekMax) * 100}%` }} />
            </span>
            <span className="text-right tabular-nums text-muted">{fmtInt.format(v)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
