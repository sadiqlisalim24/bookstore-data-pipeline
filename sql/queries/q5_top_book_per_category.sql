-- 5. Hər kateqoriyada gəlirə görə 1-ci yerdə olan kitab (window function).
-- RANK(): bərabər gəlir olarsa, hər iki kitab göstərilir.
WITH book_revenue AS (
    SELECT
        p.category,
        p.product_id,
        p.title,
        sum(f.amount) AS revenue_azn
    FROM fact_orders f
    JOIN dim_product p USING (product_id)
    WHERE f.is_revenue AND p.is_known
    GROUP BY p.category, p.product_id, p.title
),
ranked AS (
    SELECT *, RANK() OVER (PARTITION BY category ORDER BY revenue_azn DESC) AS rnk
    FROM book_revenue
)
SELECT category, product_id, title, revenue_azn
FROM ranked
WHERE rnk = 1
ORDER BY category;
