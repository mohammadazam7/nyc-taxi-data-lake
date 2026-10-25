-- Pickups by ISO day of week (Monday = 1) and hour of day, in New York local time,
-- which is how TLC records pickup_at.
SELECT
    d.day_of_week,
    EXTRACT(HOUR FROM f.pickup_at) AS pickup_hour,
    COUNT(*) AS trips
FROM fact_trips AS f
JOIN dim_date AS d ON d.date_key = f.pickup_date_key
WHERE f.pickup_date_key BETWEEN :start_key AND :end_key
GROUP BY d.day_of_week, EXTRACT(HOUR FROM f.pickup_at)
ORDER BY d.day_of_week, pickup_hour
