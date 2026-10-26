-- Trips per payment type, with tips as a share of fares. TLC only records tips paid by
-- card, so cash trips show a tip rate near zero by construction, not by behaviour.
SELECT
    p.payment_type_id,
    p.payment_type_name,
    COUNT(*) AS trips,
    SUM(f.total_amount) AS revenue,
    ROUND(SUM(f.tip_amount) / NULLIF(SUM(f.fare_amount), 0), 4) AS tip_rate
FROM fact_trips AS f
JOIN dim_payment_type AS p ON p.payment_type_key = f.payment_type_key
WHERE f.pickup_date_key BETWEEN :start_key AND :end_key
GROUP BY p.payment_type_id, p.payment_type_name
ORDER BY trips DESC, p.payment_type_id
