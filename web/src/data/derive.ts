import type { Daily, Report } from "./schema";

export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export type Range = readonly [number, number];

/** 7 x 24 pickups, Monday first, from the hourly_demand rows. */
export function demandGrid(report: Report): number[][] {
  const grid = WEEKDAYS.map(() => new Array<number>(24).fill(0));
  for (const r of report.hourly) grid[r.day_of_week - 1]![r.pickup_hour] = r.trips;
  return grid;
}

export interface Slot { day: number; hour: number; trips: number }

export function peakSlots(grid: number[][], n: number): Slot[] {
  return grid
    .flatMap((row, day) => row.map((trips, hour) => ({ day, hour, trips })))
    .sort((a, b) => b.trips - a.trips || a.day - b.day || a.hour - b.hour)
    .slice(0, n);
}

export interface Totals { trips: number; revenue: number; days: number }

export function totals(daily: readonly Daily[], [from, to]: Range): Totals {
  const t = { trips: 0, revenue: 0, days: 0 };
  for (let i = Math.max(0, from); i <= Math.min(daily.length - 1, to); i++) {
    t.trips += daily[i]!.trips;
    t.revenue += daily[i]!.revenue;
    t.days += 1;
  }
  return t;
}

export function tipShare(report: Report): number | null {
  const tips = report.monthly.reduce((s, r) => s + r.tips, 0);
  const fares = report.monthly.reduce((s, r) => s + r.fares, 0);
  return fares ? tips / fares : null;
}

export function monthLabel(key: string): string {
  const [y, m] = key.split("-");
  return `${MONTHS[Number(m) - 1] ?? m} ${y}`;
}

export const hourLabel = (h: number) => `${String(h).padStart(2, "0")}:00`;
export const fmtInt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
export const fmtMoney = (v: number) => `$${fmtInt.format(Math.round(v))}`;
