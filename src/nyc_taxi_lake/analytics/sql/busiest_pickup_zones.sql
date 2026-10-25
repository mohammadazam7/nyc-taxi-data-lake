-- The 15 zones with the most pickups. Ties break on zone id so the ranking is stable.
SELECT
    z.zone_id,
    z.zone_name,
    z.borough,
    COUNT(*) AS trips,
    SUM(f.total_amount) AS revenue
FROM fact_trips AS f
JOIN dim_zone AS z ON z.zone_key = f.pickup_zone_key
WHERE f.pickup_date_key BETWEEN :start_key AND :end_key
GROUP BY z.zone_id, z.zone_name, z.borough
ORDER BY trips DESC, z.zone_id
LIMIT 15
