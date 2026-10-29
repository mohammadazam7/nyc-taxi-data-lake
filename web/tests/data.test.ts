import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { demandGrid, peakSlots, tipShare, totals } from "../src/data/derive";
import { Report } from "../src/data/schema";

const raw = JSON.parse(readFileSync(resolve(__dirname, "../public/data/report.json"), "utf8"));

describe("report schema", () => {
  it("accepts the report the pipeline exported", () => {
    const report = Report.parse(raw);
    expect(report.daily.length).toBeGreaterThan(27);
    expect(report.hourly).toHaveLength(168);
  });

  it("names the result and field when a row is wrong", () => {
    const broken = structuredClone(raw);
    broken.results.find((r: { name: string }) => r.name === "daily_trips").rows[0].trips = "many";
    const parsed = Report.safeParse(broken);
    expect(parsed.success).toBe(false);
    expect(parsed.error?.issues[0]?.path).toEqual(["results", "daily_trips"]);
    expect(parsed.error?.issues[0]?.message).toMatch(/rows\.0\.trips/);
  });

  it("reports a missing result instead of drawing an empty chart", () => {
    const partial = { ...raw, results: raw.results.filter((r: { name: string }) => r.name !== "payment_mix") };
    const parsed = Report.safeParse(partial);
    expect(parsed.success).toBe(false);
    expect(parsed.error?.issues[0]?.message).toBe("missing");
  });
});

describe("derived figures", () => {
  const report = Report.parse(raw);

  it("puts every hourly row in its weekday and hour cell", () => {
    const grid = demandGrid(report);
    const sum = grid.flat().reduce((a, b) => a + b, 0);
    expect(sum).toBe(report.hourly.reduce((a, r) => a + r.trips, 0));
    const first = report.hourly.find((r) => r.day_of_week === 1 && r.pickup_hour === 0)!;
    expect(grid[0]![0]).toBe(first.trips);
  });

  it("agrees with the monthly totals over the whole range", () => {
    const t = totals(report.daily, [0, report.daily.length - 1]);
    expect(t.trips).toBe(report.monthly.reduce((a, r) => a + r.trips, 0));
    expect(t.revenue).toBeCloseTo(report.monthly.reduce((a, r) => a + r.revenue, 0), 0);
  });

  it("sums only the selected days", () => {
    const t = totals(report.daily, [2, 4]);
    expect(t.days).toBe(3);
    expect(t.trips).toBe(report.daily[2]!.trips + report.daily[3]!.trips + report.daily[4]!.trips);
  });

  it("ranks peak slots busiest first with a stable order", () => {
    const peaks = peakSlots(demandGrid(report), 5);
    expect(peaks).toHaveLength(5);
    for (let i = 1; i < peaks.length; i++) expect(peaks[i - 1]!.trips).toBeGreaterThanOrEqual(peaks[i]!.trips);
  });

  it("computes the tip share from fares, not revenue", () => {
    const m = report.monthly[0]!;
    expect(tipShare(report)).toBeCloseTo(m.tips / m.fares, 6);
  });
});
