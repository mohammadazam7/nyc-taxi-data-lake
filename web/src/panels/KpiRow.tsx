import { useMemo } from "react";
import { useCountUp, useReducedMotion } from "../atlas/hooks";
import { fmtInt, fmtMoney, tipShare, totals } from "../data/derive";
import type { Report } from "../data/schema";
import { useExplorer } from "../state/store";

function Kpi({ label, value, format, note }: { label: string; value: number | null; format: (v: number) => string; note: string }) {
  const reduced = useReducedMotion();
  const shown = useCountUp(value ?? 0, 900, !reduced);
  return (
    <div className="rounded-panel border border-line bg-gradient-to-b from-raised to-panel px-4 pb-3 pt-3.5 shadow-panel">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-0.5 text-[26px] font-semibold tabular-nums text-ink">{value == null ? "n/a" : format(shown)}</div>
      <div className="mt-0.5 text-[11.5px] text-dim">{note}</div>
    </div>
  );
}

export function KpiRow({ report }: { report: Report }) {
  const range = useExplorer((s) => s.range);
  const all: [number, number] = [0, report.daily.length - 1];
  const t = useMemo(() => totals(report.daily, range ?? all), [report, range]); // eslint-disable-line react-hooks/exhaustive-deps
  const note = range ? `${t.days} selected days` : `all ${t.days} days`;
  const share = tipShare(report);
  return (
    <section aria-label="Summary figures" className="grid grid-cols-2 gap-3 md:grid-cols-5">
      <Kpi label="Trips" value={t.trips} format={(v) => fmtInt.format(v)} note={note} />
      <Kpi label="Revenue" value={t.revenue} format={fmtMoney} note={note} />
      <Kpi label="Revenue per trip" value={t.trips ? t.revenue / t.trips : null} format={(v) => `$${v.toFixed(2)}`} note={note} />
      <Kpi label="Trips per day" value={t.days ? t.trips / t.days : null} format={(v) => fmtInt.format(v)} note={note} />
      <Kpi label="Tips as share of fares" value={share == null ? null : share * 100} format={(v) => `${v.toFixed(1)}%`} note="whole report" />
    </section>
  );
}
