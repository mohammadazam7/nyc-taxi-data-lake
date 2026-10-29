import { z } from "zod";

/**
 * The analytics report as `nyc-lake explore --json` writes it. Every query result is a
 * named table; the page validates the ones it draws and passes the rest through.
 */
const num = z.number().finite();
const nullableNum = num.nullable();

export const MonthlyRow = z.object({
  year: num, month: num, trips: num, revenue: num, fares: num, tips: num,
  other_charges: num, avg_revenue_per_trip: nullableNum,
});
export const DailyRow = z.object({
  calendar_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/), trips: num, revenue: num,
  avg_distance_mi: nullableNum,
});
export const HourlyRow = z.object({
  day_of_week: num.int().min(1).max(7), pickup_hour: num.int().min(0).max(23), trips: num,
});
export const ZoneRow = z.object({
  zone_id: num, zone_name: z.string(), borough: z.string(), trips: num, revenue: num,
});
export const PaymentRow = z.object({
  payment_type_id: num, payment_type_name: z.string(), trips: num, revenue: num,
  tip_rate: nullableNum,
});

const result = <T extends z.ZodTypeAny>(name: string, row: T) =>
  z.object({ name: z.literal(name), columns: z.array(z.string()), rows: z.array(row) });

const Results = z.array(z.object({ name: z.string(), columns: z.array(z.string()), rows: z.array(z.unknown()) }));

export const Report = z
  .object({
    taxi_type: z.string(),
    start: z.string().regex(/^\d{4}-\d{2}$/),
    end: z.string().regex(/^\d{4}-\d{2}$/),
    source_note: z.string().default(""),
    results: Results,
  })
  .transform((r, ctx) => {
    const pick = <T extends z.ZodTypeAny>(name: string, row: T): z.infer<T>[] => {
      const raw = r.results.find((x) => x.name === name);
      const parsed = result(name, row).safeParse(raw);
      if (!parsed.success) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["results", name],
          message: raw ? parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ") : "missing",
        });
        return [];
      }
      return parsed.data.rows;
    };
    return {
      taxiType: r.taxi_type,
      start: r.start,
      end: r.end,
      sourceNote: r.source_note,
      monthly: pick("monthly_revenue", MonthlyRow),
      daily: pick("daily_trips", DailyRow),
      hourly: pick("hourly_demand", HourlyRow),
      zones: pick("busiest_pickup_zones", ZoneRow),
      payments: pick("payment_mix", PaymentRow),
    };
  });

export type Report = z.output<typeof Report>;
export type Daily = z.infer<typeof DailyRow>;
export type Zone = z.infer<typeof ZoneRow>;
export type Payment = z.infer<typeof PaymentRow>;
