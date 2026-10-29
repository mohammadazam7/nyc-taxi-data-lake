import { WEEKDAYS, fmtInt, hourLabel } from "../data/derive";

/** The same data as the 3D scene, as a heatmap table: the no-WebGL and screen-reader view. */
export function DemandTable({ grid }: { grid: number[][] }) {
  const flat = grid.flat();
  const hi = Math.max(...flat, 1);
  return (
    <div className="overflow-x-auto px-4 pb-4 pt-3">
      <table className="w-full border-separate border-spacing-[2px] text-[10.5px]">
        <caption className="sr-only">Pickups by weekday and hour</caption>
        <thead>
          <tr>
            <th scope="col" />
            {grid[0]?.map((_, h) => <th key={h} scope="col" className="font-normal text-dim">{h % 3 === 0 ? hourLabel(h).slice(0, 2) : ""}</th>)}
          </tr>
        </thead>
        <tbody>
          {grid.map((row, d) => (
            <tr key={d}>
              <th scope="row" className="pr-2 text-left font-normal text-muted">{WEEKDAYS[d]}</th>
              {row.map((v, h) => (
                <td key={h} title={`${WEEKDAYS[d]} ${hourLabel(h)}: ${fmtInt.format(v)}`} className="h-6 rounded-[3px]" style={{ background: `rgba(247,183,51,${0.08 + (v / hi) * 0.85})` }}>
                  <span className="sr-only">{fmtInt.format(v)}</span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
