-- 2. Gəlirə görə ən çox satan 5 kitab (naməlum məhsul P999 kitab olmadığı üçün çıxarılır).
SELECT
    p.product_id,
    p.title,
    p.category,
    sum(f.quantity) AS units_sold,
    sum(f.amount)   AS revenue_azn
FROM fact_orders f
JOIN dim_product p USING (product_id)
WHERE f.is_revenue AND p.is_known
GROUP BY p.product_id, p.title, p.category
ORDER BY revenue_azn DESC, p.product_id
LIMIT 5;
