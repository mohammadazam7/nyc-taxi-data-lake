import { arc, pie } from "d3-shape";
import { useState } from "react";
import { fmtInt } from "../data/derive";
import type { Payment } from "../data/schema";

const COLORS = ["#4fa3ff", "#f7b733", "#36d39a", "#e86fa8", "#8b5cf6", "#8b95a8"];

export function PaymentMix({ payments }: { payments: readonly Payment[] }) {
  const [active, setActive] = useState<number | null>(null);
  const total = payments.reduce((s, p) => s + p.trips, 0) || 1;
  const slices = pie<Payment>().value((p) => p.trips).sort(null)([...payments]);
  const shape = arc<{ startAngle: number; endAngle: number }>().innerRadius(58).outerRadius(92).cornerRadius(3).padAngle(0.012);
  const p = active != null ? payments[active] : undefined;
  return (
    <div className="grid grid-cols-1 items-center gap-2 px-4 pb-4 pt-2 sm:grid-cols-[200px_1fr]" onPointerLeave={() => setActive(null)}>
      <svg viewBox="-100 -100 200 200" className="mx-auto h-[200px] w-[200px]" role="img" aria-label="Share of trips by payment type">
        {slices.map((s, i) => {
          const mid = (s.startAngle + s.endAngle) / 2;
          const out = i === active ? 6 : 0;
          return (
            <path
              key={s.data.payment_type_id}
              d={shape(s) ?? ""}
              transform={`translate(${Math.sin(mid) * out} ${-Math.cos(mid) * out})`}
              fill={COLORS[i % COLORS.length]}
              opacity={active == null || active === i ? 1 : 0.35}
              onPointerEnter={() => setActive(i)}
              className="transition-[opacity,transform] duration-200"
            />
          );
        })}
        <text textAnchor="middle" y="4" className="fill-ink text-[20px] font-semibold">{p ? `${((p.trips / total) * 100).toFixed(1)}%` : fmtInt.format(total)}</text>
        <text textAnchor="middle" y="22" className="fill-muted text-[11px]">{p ? p.payment_type_name : "trips"}</text>
        {p?.tip_rate != null && <text textAnchor="middle" y="37" className="fill-muted text-[10.5px]">tips {(p.tip_rate * 100).toFixed(1)}% of fares</text>}
      </svg>
      <ul className="text-[12.5px]">
        {payments.map((q, i) => (
          <li
            key={q.payment_type_id}
            onPointerEnter={() => setActive(i)}
            className={`grid grid-cols-[12px_1fr_auto] items-center gap-2 rounded-lg px-2 py-1.5 ${active === i ? "bg-[#1a2233]" : ""}`}
          >
            <i className="h-2.5 w-2.5 rounded-[3px]" style={{ background: COLORS[i % COLORS.length] }} />
            <span>{q.payment_type_name}</span>
            <span className="tabular-nums text-muted">{((q.trips / total) * 100).toFixed(1)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
