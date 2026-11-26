"""Yükləmədən sonra işləyən məlumat keyfiyyəti yoxlamaları.

Hər yoxlama "problemli sətirlərin sayını" qaytaran bir SQL-dir.
error: say > 0 olarsa pipeline uğursuz sayılır (exit code 1).
warning: sadəcə xəbərdarlıq, bilinən və qəbul edilmiş vəziyyət.
"""
import logging

log = logging.getLogger(__name__)

CHECKS = [
    ("error", "Mənfi və ya sıfır miqdar",
     "SELECT count(*) FROM fact_orders WHERE quantity <= 0"),
    ("error", "Mənfi və ya sıfır qiymət",
     "SELECT count(*) FROM fact_orders WHERE unit_price <= 0"),
    ("error", "Naməlum status",
     "SELECT count(*) FROM fact_orders WHERE status NOT IN ('completed', 'cancelled', 'refunded')"),
    ("error", "Gələcək tarixli sifariş",
     "SELECT count(*) FROM fact_orders WHERE order_ts > now()"),
    ("error", "Kataloqda qiyməti olmayan məhsul",
     "SELECT count(*) FROM dim_product WHERE is_known AND list_price IS NULL"),
    ("error", "Yanlış formatlı e-poçt",
     "SELECT count(*) FROM dim_customer WHERE email !~ '^[^@\\s]+@[^@\\s]+\\.[a-z]+$'"),
    ("error", "Təkrarlanan e-poçt",
     "SELECT count(*) FROM (SELECT email FROM dim_customer WHERE email IS NOT NULL "
     "GROUP BY email HAVING count(*) > 1) d"),
    ("error", "Müştərinin qeydiyyatdan əvvəl verdiyi sifariş",
     "SELECT count(*) FROM fact_orders f JOIN dim_customer c USING (customer_id) "
     "WHERE f.order_ts::date < c.signup_date"),
    ("warning", "Naməlum məhsula aid sifariş (məs. P999)",
     "SELECT count(*) FROM fact_orders f JOIN dim_product p USING (product_id) WHERE NOT p.is_known"),
    ("warning", "Müştərisi boş olan sifariş",
     "SELECT count(*) FROM fact_orders WHERE customer_id IS NULL"),
    ("warning", "Sifariş qiyməti kataloq qiymətindən fərqlidir",
     "SELECT count(*) FROM fact_orders f JOIN dim_product p USING (product_id) "
     "WHERE p.is_known AND f.unit_price <> p.list_price"),
    ("warning", "E-poçtu boş olan müştəri",
     "SELECT count(*) FROM dim_customer WHERE is_known AND email IS NULL"),
    ("warning", "Rədd edilmiş (karantin) sətirlər",
     "SELECT count(*) FROM rejected_orders"),
]


def run_checks(conn) -> bool:
    failed = False
    with conn.cursor() as cur:
        for severity, name, sql in CHECKS:
            cur.execute(sql)
            count = cur.fetchone()[0]
            if count == 0:
                status = "OK"
            elif severity == "error":
                status, failed = "FAIL", True
            else:
                status = "WARN"
            log.info("[%-4s] %s: %s", status, name, count)
    return not failed
