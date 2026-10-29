import { Suspense, lazy, useEffect, useMemo, useState } from "react";
import { Card } from "./atlas/Card";
import { ErrorBoundary } from "./atlas/ErrorBoundary";
import { hasWebGL, useReducedMotion } from "./atlas/hooks";
import { Segmented } from "./atlas/Segmented";
import { TooltipLayer } from "./atlas/Tooltip";
import { demandGrid, monthLabel, peakSlots, WEEKDAYS, hourLabel } from "./data/derive";
import { ReportError, loadReport } from "./data/loadReport";
import type { Report } from "./data/schema";
import { DailyTrend } from "./panels/DailyTrend";
import { DayPlayer } from "./panels/DayPlayer";
import { SlotDetail } from "./panels/SlotDetail";
import { DemandTable } from "./panels/DemandTable";
import { KpiRow } from "./panels/KpiRow";
import { PaymentMix } from "./panels/PaymentMix";
import { PeakSlots } from "./panels/PeakSlots";
import { Zones } from "./panels/Zones";
import { useExplorer } from "./state/store";

const Scene = lazy(() => import("./scene/Scene"));
const REPORT_URL = `${import.meta.env.BASE_URL}data/report.json`;

type Load = { state: "loading" } | { state: "ready"; report: Report } | { state: "error"; error: ReportError | Error };

export function App() {
  const [load, setLoad] = useState<Load>({ state: "loading" });
  useEffect(() => {
    const ctrl = new AbortController();
    loadReport(REPORT_URL, ctrl.signal)
      .then((report) => setLoad({ state: "ready", report }))
      .catch((error: Error) => error.name !== "AbortError" && setLoad({ state: "error", error }));
    return () => ctrl.abort();
  }, []);

  if (load.state === "loading") return <Splash text="Loading the analytics report" />;
  if (load.state === "error") {
    return (
      <Splash text={load.error.message}>
        {load.error instanceof ReportError && load.error.detail && (
          <pre className="mt-3 max-w-2xl whitespace-pre-wrap text-left text-xs text-muted">{load.error.detail}</pre>
        )}
      </Splash>
    );
  }
  return <Explorer report={load.report} />;
}

function Splash({ text, children }: { text: string; children?: React.ReactNode }) {
  return (
    <main className="grid min-h-screen place-items-center p-6 text-center text-muted">
      <div>
        <p role="status">{text}</p>
        {children}
      </div>
    </main>
  );
}

function Explorer({ report }: { report: Report }) {
  const grid = useMemo(() => demandGrid(report), [report]);
  const reduced = useReducedMotion();
  const webgl = useMemo(hasWebGL, []);
  const camera = useExplorer((s) => s.camera);
  const setCamera = useExplorer((s) => s.setCamera);
  const metric = useExplorer((s) => s.metric);
  const setMetric = useExplorer((s) => s.setMetric);
  const range = useExplorer((s) => s.range);
  const selected = useExplorer((s) => s.selected);
  const [view, setView] = useState<"3d" | "table">(webgl ? "3d" : "table");

  const span = report.start === report.end ? monthLabel(report.start) : `${monthLabel(report.start)} to ${monthLabel(report.end)}`;
  const taxi = report.taxiType.charAt(0).toUpperCase() + report.taxiType.slice(1);
  const synthetic = report.sourceNote && !report.sourceNote.startsWith("Source:");
  const peak = peakSlots(grid, 1)[0];
  const sceneLabel = peak
    ? `3D bars of pickups by weekday and hour; the busiest slot is ${WEEKDAYS[peak.day]} ${hourLabel(peak.hour)} with ${peak.trips.toLocaleString("en-US")} pickups`
    : "3D bars of pickups by weekday and hour";

  return (
    <div className="mx-auto max-w-[1240px] px-5 pb-12 pt-5">
      <header className="flex flex-wrap items-center gap-3.5">
        <div aria-hidden className="grid h-10 w-10 place-items-center rounded-[11px] bg-gradient-to-br from-demand to-heat font-extrabold text-[#111]">NY</div>
        <div>
          <h1 className="text-xl font-semibold tracking-tight">City Pulse · NYC {taxi} taxi trips</h1>
          <p className="text-[13px] text-muted">{span} · from the warehouse zone of the nyc-taxi-data-lake pipeline</p>
        </div>
        {report.sourceNote && (
          <span title={report.sourceNote} className={`ml-auto rounded-full border px-2.5 py-1 text-xs ${synthetic ? "border-demand/40 bg-demand/10 text-demand" : "border-health/40 bg-health/10 text-health"}`}>
            {synthetic ? "Synthetic sample data" : "TLC trip records"}
          </span>
        )}
      </header>

      <div className="mt-5"><KpiRow report={report} /></div>

      <div className="mt-3.5 grid gap-3.5 lg:grid-cols-[1.75fr_1fr]">
        <Card
          title="Demand landscape"
          note="pickups by weekday and hour"
          actions={
            <div className="flex gap-2">
              {view === "3d" && (
                <Segmented label="Camera" value={camera} onChange={setCamera} options={[{ value: "orbit", label: "Orbit" }, { value: "top", label: "Top" }, { value: "street", label: "Street" }]} />
              )}
              <Segmented label="View" value={view} onChange={setView} options={webgl ? [{ value: "3d", label: "3D" }, { value: "table", label: "Table" }] : [{ value: "table", label: "Table" }]} />
            </div>
          }
        >
          {view === "3d" ? (
            <div className="relative h-[420px]">
              <ErrorBoundary label="The 3D view" fallback={<DemandTable grid={grid} />}>
                <Suspense fallback={<div className="grid h-full place-items-center text-sm text-muted">Loading the 3D view</div>}>
                  <Scene grid={grid} reducedMotion={reduced} label={sceneLabel} />
                </Suspense>
              </ErrorBoundary>
              <p className="pointer-events-none absolute bottom-3 right-4 text-[11.5px] text-dim">Drag to orbit · scroll to zoom · click a bar for detail</p>
            </div>
          ) : (
            <DemandTable grid={grid} />
          )}
          {!webgl && <p className="px-4 pb-3 text-xs text-dim">This browser has no WebGL, so the table view is shown.</p>}
          {view === "3d" && <DayPlayer grid={grid} />}
        </Card>
        {selected ? (
          <Card title="Slot detail" note="the bar you clicked">
            <SlotDetail grid={grid} slot={selected} />
          </Card>
        ) : (
          <Card title="Peak slots" note="hover to find it, click to fly to it">
            <PeakSlots grid={grid} />
          </Card>
        )}
      </div>

      <Card
        className="mt-3.5"
        title="Daily trend"
        note={range ? `${report.daily[range[0]]?.calendar_date} to ${report.daily[range[1]]?.calendar_date}` : "drag across the chart to select days"}
        actions={<Segmented label="Metric" value={metric} onChange={setMetric} options={[{ value: "trips", label: "Trips" }, { value: "revenue", label: "Revenue" }, { value: "avg_distance_mi", label: "Avg distance" }]} />}
      >
        <div className="px-2 pb-2 pt-1"><DailyTrend daily={report.daily} /></div>
      </Card>

      <div className="mt-3.5 grid gap-3.5 lg:grid-cols-[1.35fr_1fr]">
        <Card title="Busiest pickup zones" note={`${report.zones.length} zones by pickups`}>
          <Zones zones={report.zones} />
        </Card>
        <Card title="Payment mix" note="share of trips">
          <PaymentMix payments={report.payments} />
        </Card>
      </div>

      <footer className="mt-6 text-xs text-dim">
        {report.sourceNote} Every figure comes from the SQL in src/nyc_taxi_lake/analytics/sql, run by nyc-lake analytics and exported with nyc-lake explore --json.
      </footer>
      <TooltipLayer />
    </div>
  );
}
