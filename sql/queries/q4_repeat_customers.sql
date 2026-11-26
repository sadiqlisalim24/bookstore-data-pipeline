-- 4. Müştərilərin neçə faizi 1-dən çox sifariş verib?
-- Məxrəc: qeydiyyatlı bütün müştərilər.
-- any_status: statusundan asılı olmayaraq verilmiş sifarişlər (sifariş vermək davranışı);
-- completed_only: yalnız tamamlanmış sifarişlər (müqayisə üçün).
WITH per_customer AS (
    SELECT
        c.customer_id,
        count(f.order_id)                            AS orders_any,
        count(f.order_id) FILTER (WHERE f.is_revenue) AS orders_completed
    FROM dim_customer c
    LEFT JOIN fact_orders f USING (customer_id)
    WHERE c.is_known
    GROUP BY c.customer_id
)
SELECT
    count(*)                                         AS total_customers,
    count(*) FILTER (WHERE orders_any > 1)           AS repeat_any_status,
    round(100.0 * count(*) FILTER (WHERE orders_any > 1) / count(*), 2)       AS pct_any_status,
    count(*) FILTER (WHERE orders_completed > 1)     AS repeat_completed_only,
    round(100.0 * count(*) FILTER (WHERE orders_completed > 1) / count(*), 2) AS pct_completed_only
FROM per_customer;
