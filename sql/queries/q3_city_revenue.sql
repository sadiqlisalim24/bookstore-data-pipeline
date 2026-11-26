-- 3. Hər şəhər üzrə gəlir və müştəri sayı.
-- registered_customers: həmin şəhərdən qeydiyyatlı müştərilər;
-- paying_customers: ən azı bir 'completed' sifarişi olanlar.
-- Müştərisi boş olan sifarişlər şəhərə bağlana bilmədiyi üçün buraya düşmür.
SELECT
    c.city,
    count(DISTINCT c.customer_id)                                  AS registered_customers,
    count(DISTINCT f.customer_id) FILTER (WHERE f.is_revenue)      AS paying_customers,
    coalesce(sum(f.amount) FILTER (WHERE f.is_revenue), 0)         AS revenue_azn
FROM dim_customer c
LEFT JOIN fact_orders f USING (customer_id)
WHERE c.is_known
GROUP BY c.city
ORDER BY revenue_azn DESC;
