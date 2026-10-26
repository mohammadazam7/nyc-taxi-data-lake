-- Trips, revenue and mean distance per pickup day.
SELECT
    d.calendar_date,
    COUNT(*) AS trips,
    SUM(f.total_amount) AS revenue,
    ROUND(AVG(f.trip_distance_mi), 2) AS avg_distance_mi
FROM fact_trips AS f
JOIN dim_date AS d ON d.date_key = f.pickup_date_key
WHERE f.pickup_date_key BETWEEN :start_key AND :end_key
GROUP BY d.calendar_date
ORDER BY d.calendar_date
