import { scaleLinear } from "d3-scale";
import { area, curveMonotoneX, line } from "d3-shape";
import { useMemo, useRef, useState, type PointerEvent } from "react";
import { hideTip, showTip } from "../atlas/Tooltip";
import { fmtInt, fmtMoney } from "../data/derive";
import type { Daily } from "../data/schema";
import { useExplorer, type Metric } from "../state/store";

const W = 1160;
const H = 210;
const PAD = { l: 58, r: 18, t: 16, b: 28 };

const tick = (m: Metric, v: number) =>
  m === "revenue" ? (v >= 1000 ? `$${Math.round(v / 1000)}k` : `$${Math.round(v)}`) : m === "trips" ? fmtInt.format(v) : `${v.toFixed(1)} mi`;

/** Daily line with a brush: drag selects days, the KPIs follow, double-click resets. */
export function DailyTrend({ daily }: { daily: readonly Daily[] }) {
  const metric = useExplorer((s) => s.metric);
  const range = useExplorer((s) => s.range);
  const setRange = useExplorer((s) => s.setRange);
  const svg = useRef<SVGSVGElement>(null);
  const [anchor, setAnchor] = useState<number | null>(null);
  const [hover, setHover] = useState<number | null>(null);

  const values = daily.map((d) => d[metric] ?? 0);
  const x = useMemo(() => scaleLinear().domain([0, Math.max(1, daily.length - 1)]).range([PAD.l, W - PAD.r]), [daily.length]);
  const y = useMemo(() => scaleLinear().domain([0, Math.max(...values, 1) * 1.1]).nice().range([H - PAD.b, PAD.t]), [values]);
  const linePath = line<number>().x((_, i) => x(i)).y((v) => y(v)).curve(curveMonotoneX)(values) ?? "";
  const areaPath = area<number>().x((_, i) => x(i)).y0(H - PAD.b).y1((v) => y(v)).curve(curveMonotoneX)(values) ?? "";

  const indexAt = (e: PointerEvent) => {
    const box = svg.current!.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * W;
    return Math.max(0, Math.min(daily.length - 1, Math.round(x.invert(px))));
  };
  const move = (e: PointerEvent<SVGSVGElement>) => {
    const i = indexAt(e);
    setHover(i);
    if (anchor != null) setRange([Math.min(anchor, i), Math.max(anchor, i)]);
    const d = daily[i]!;
    showTip(e.clientX, e.clientY, (
      <>
        <b className="block text-[13px]">{d.calendar_date}</b>
        {fmtInt.format(d.trips)} trips · {fmtMoney(d.revenue)}
        {d.avg_distance_mi != null && ` · ${d.avg_distance_mi.toFixed(2)} mi avg`}
      </>
    ));
  };

  const ticks = y.ticks(4);
  const step = Math.ceil(daily.length / 10);
  return (
    <svg
      ref={svg}
      viewBox={`0 0 ${W} ${H}`}
      className="block h-[210px] w-full cursor-crosshair touch-none select-none"
      role="img"
      aria-label={`Daily ${metric.replace(/_/g, " ")}; drag to select a date range`}
      onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); setAnchor(indexAt(e)); }}
      onPointerMove={move}
      onPointerUp={() => setAnchor(null)}
      onPointerLeave={() => { setHover(null); hideTip(); }}
      onDoubleClick={() => setRange(null)}
    >
      <defs>
        <linearGradient id="trend-fill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#f7b733" stopOpacity="0.35" />
          <stop offset="1" stopColor="#f7b733" stopOpacity="0" />
        </linearGradient>
      </defs>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} stroke="rgba(255,255,255,.05)" />
          <text x={PAD.l - 8} y={y(t) + 4} textAnchor="end" className="fill-dim text-[11px]">{tick(metric, t)}</text>
        </g>
      ))}
      {daily.map((d, i) => i % step === 0 && (
        <text key={d.calendar_date} x={x(i)} y={H - 8} textAnchor="middle" className="fill-dim text-[11px]">{d.calendar_date.slice(5)}</text>
      ))}
      {range && (
        <rect x={x(range[0]) - 3} y={PAD.t} width={x(range[1]) - x(range[0]) + 6} height={H - PAD.t - PAD.b} fill="rgba(79,163,255,.12)" rx="4" />
      )}
      <path d={areaPath} fill="url(#trend-fill)" />
      <path d={linePath} fill="none" stroke="#f7b733" strokeWidth="2" />
      {hover != null && (
        <g>
          <line x1={x(hover)} x2={x(hover)} y1={PAD.t} y2={H - PAD.b} stroke="rgba(255,255,255,.25)" />
          <circle cx={x(hover)} cy={y(values[hover] ?? 0)} r="4" fill="#fff" />
        </g>
      )}
    </svg>
  );
}
