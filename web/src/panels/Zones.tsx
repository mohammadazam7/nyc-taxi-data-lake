import { useState } from "react";
import { Segmented } from "../atlas/Segmented";
import { fmtInt, fmtMoney } from "../data/derive";
import type { Zone } from "../data/schema";

type Key = "trips" | "revenue";

export function Zones({ zones }: { zones: readonly Zone[] }) {
  const [key, setKey] = useState<Key>("trips");
  const rows = [...zones].sort((a, b) => b[key] - a[key]);
  const top = rows[0]?.[key] || 1;
  return (
    <>
      <div className="absolute right-4 top-3">
        <Segmented label="Sort zones by" value={key} onChange={setKey} options={[{ value: "trips", label: "Trips" }, { value: "revenue", label: "Revenue" }]} />
      </div>
      <ol className="px-4 pb-4 pt-2.5">
        {rows.map((z, i) => (
          <li key={z.zone_id} className="grid h-6 grid-cols-[170px_1fr_76px] items-center gap-2.5 text-[12.5px]">
            <span className="truncate" title={`${z.zone_name} (${z.borough})`}>{z.zone_name} <small className="text-dim">{z.borough}</small></span>
            <span className="h-2.5 overflow-hidden rounded-full bg-white/[0.03]">
              <span
                className="block h-full rounded-full bg-gradient-to-r from-system to-violet transition-[width] duration-700 ease-out"
                style={{ width: `${(z[key] / top) * 100}%`, transitionDelay: `${i * 30}ms` }}
              />
            </span>
            <span className="text-right tabular-nums text-muted">{key === "trips" ? fmtInt.format(z.trips) : fmtMoney(z.revenue)}</span>
          </li>
        ))}
      </ol>
    </>
  );
}
