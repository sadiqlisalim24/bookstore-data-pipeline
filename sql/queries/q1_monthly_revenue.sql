-- 1. Hər ay üzrə ümumi gəlir və sifariş sayı.
-- Gəlir = yalnız 'completed' sifarişlər (cancelled/refunded pul gətirməyib).
-- total_orders bütün statusları, completed_orders yalnız gəlirə düşənləri sayır.
SELECT
    d.year_month                                         AS month,
    count(*)                                             AS total_orders,
    count(*) FILTER (WHERE f.is_revenue)                 AS completed_orders,
    coalesce(sum(f.amount) FILTER (WHERE f.is_revenue), 0) AS revenue_azn
FROM fact_orders f
JOIN dim_date d USING (date_key)
GROUP BY d.year_month
ORDER BY d.year_month;
