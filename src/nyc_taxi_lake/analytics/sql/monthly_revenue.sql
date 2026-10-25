-- Revenue per pickup month, split into fares, tips and everything else (surcharges,
-- taxes, tolls), with the mean amount charged per trip.
SELECT
    d.year,
    d.month,
    COUNT(*) AS trips,
    SUM(f.total_amount) AS revenue,
    SUM(f.fare_amount) AS fares,
    SUM(f.tip_amount) AS tips,
    SUM(f.total_amount) - SUM(f.fare_amount) - SUM(f.tip_amount) AS other_charges,
    ROUND(AVG(f.total_amount), 2) AS avg_revenue_per_trip
FROM fact_trips AS f
JOIN dim_date AS d ON d.date_key = f.pickup_date_key
WHERE f.pickup_date_key BETWEEN :start_key AND :end_key
GROUP BY d.year, d.month
ORDER BY d.year, d.month
