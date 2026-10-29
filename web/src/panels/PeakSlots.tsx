import { WEEKDAYS, fmtInt, hourLabel, peakSlots } from "../data/derive";
import { useExplorer } from "../state/store";

export function PeakSlots({ grid }: { grid: number[][] }) {
  const peaks = peakSlots(grid, 6);
  const focused = useExplorer((s) => s.focused);
  const setFocused = useExplorer((s) => s.setFocused);
  const setSelected = useExplorer((s) => s.setSelected);
  const byHour = Array.from({ length: 24 }, (_, h) => grid.reduce((s, row) => s + (row[h] ?? 0), 0));
  const byDay = grid.map((row) => row.reduce((a, b) => a + b, 0));
  const weekday = byDay.slice(0, 5).reduce((a, b) => a + b, 0) / 5;
  const weekend = ((byDay[5] ?? 0) + (byDay[6] ?? 0)) / 2;
  const busiest = byHour.indexOf(Math.max(...byHour));
  const quietest = byHour.indexOf(Math.min(...byHour));
  const top = peaks[0]?.trips ?? 1;
  return (
    <>
      <ol className="mt-2 px-2.5" onPointerLeave={() => setFocused(null)}>
        {peaks.map((s, i) => {
          const on = focused?.day === s.day && focused.hour === s.hour;
          return (
            <li key={`${s.day}-${s.hour}`}>
              <button
                type="button"
                onPointerEnter={() => setFocused(s)}
                onFocus={() => setFocused(s)}
                onBlur={() => setFocused(null)}
                onClick={() => setSelected(s)}
                className={`grid w-full grid-cols-[22px_1fr_auto] items-center gap-2 rounded-[9px] px-2 py-2 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-system ${on ? "bg-[#1a2233]" : "hover:bg-[#1a2233]"}`}
              >
                <span className="tabular-nums text-dim">{i + 1}</span>
                <span>
                  <span className="block text-[13px]">{WEEKDAYS[s.day]} {hourLabel(s.hour)}</span>
                  <span className="mt-1 block h-1.5 rounded bg-gradient-to-r from-demand to-heat" style={{ width: `${(s.trips / top) * 100}%` }} />
                </span>
                <span className="text-[12.5px] tabular-nums text-muted">{fmtInt.format(s.trips)}</span>
              </button>
            </li>
          );
        })}
      </ol>
      <dl className="flex flex-wrap gap-x-5 gap-y-1 px-4 pb-4 pt-1 text-xs text-muted">
        <div>Busiest hour <b className="font-semibold text-ink">{hourLabel(busiest)}</b></div>
        <div>Quietest <b className="font-semibold text-ink">{hourLabel(quietest)}</b></div>
        <div>Weekend vs weekday <b className="font-semibold text-ink">{weekday ? `${(((weekend / weekday) - 1) * 100).toFixed(0)}%` : "n/a"}</b></div>
      </dl>
    </>
  );
}
