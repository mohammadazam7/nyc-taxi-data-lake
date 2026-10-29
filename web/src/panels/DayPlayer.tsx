import { useEffect } from "react";
import { WEEKDAYS, fmtInt, hourLabel } from "../data/derive";
import { useExplorer } from "../state/store";

const STEP_MS = 700;

/** Plays the week hour by hour: the 3D light plane follows, and the readout shows that hour. */
export function DayPlayer({ grid }: { grid: number[][] }) {
  const hour = useExplorer((s) => s.hour);
  const playing = useExplorer((s) => s.playing);
  const setHour = useExplorer((s) => s.setHour);
  const setPlaying = useExplorer((s) => s.setPlaying);

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      const h = useExplorer.getState().hour ?? -1;
      if (h >= 23) setPlaying(false);
      else setHour(h + 1);
    }, STEP_MS);
    return () => window.clearInterval(id);
  }, [playing, setHour, setPlaying]);

  const column = hour == null ? null : grid.map((row) => row[hour] ?? 0);
  const total = column?.reduce((a, b) => a + b, 0) ?? 0;
  const avgHour = grid.flat().reduce((a, b) => a + b, 0) / 24;
  const busiestDay = column ? column.indexOf(Math.max(...column)) : -1;

  return (
    <div className="flex flex-wrap items-center gap-3 border-t border-line px-4 py-3">
      <button
        type="button"
        onClick={() => setPlaying(!playing)}
        aria-label={playing ? "Pause the day" : "Play the day hour by hour"}
        className="grid h-9 w-9 place-items-center rounded-full bg-gradient-to-br from-demand to-heat text-[#111] shadow-panel transition-transform hover:scale-105 focus-visible:outline focus-visible:outline-2 focus-visible:outline-system"
      >
        {playing ? (
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden><path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" /></svg>
        ) : (
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden><path d="M8 5v14l11-7z" /></svg>
        )}
      </button>
      <label className="flex min-w-[220px] flex-1 items-center gap-3 text-xs text-muted">
        <span className="w-12 tabular-nums text-ink">{hour == null ? "All day" : hourLabel(hour)}</span>
        <input
          type="range"
          min={-1}
          max={23}
          value={hour ?? -1}
          aria-label="Hour of day"
          onChange={(e) => {
            const v = Number(e.target.value);
            setPlaying(false);
            setHour(v < 0 ? null : v);
          }}
          className="h-1.5 flex-1 cursor-pointer accent-[#f7b733]"
        />
      </label>
      <div className="text-xs text-muted" aria-live="polite">
        {hour == null ? (
          <>Press play to sweep through the day</>
        ) : (
          <>
            <b className="font-semibold text-ink">{fmtInt.format(total)}</b> pickups across the week ·{" "}
            <b className="font-semibold text-ink">{avgHour ? `${(total / avgHour).toFixed(2)}x` : "n/a"}</b> the average hour · busiest on{" "}
            <b className="font-semibold text-ink">{WEEKDAYS[busiestDay]}</b>
          </>
        )}
      </div>
    </div>
  );
}
