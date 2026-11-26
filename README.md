# Kitab mağazası: CSV → PostgreSQL data pipeline

Onlayn kitab mağazasının CSV fayllarını oxuyan, təmizləyən, ulduz sxeminə (star schema) yükləyən
və analitik suallara cavab verən təkrar işə salına bilən (idempotent) pipeline.

**Texnologiyalar:** Python 3.12, pandas, PostgreSQL 16, psycopg2, Docker Compose, pytest.

## Necə işə salmaq

### Variant 1: Docker (tövsiyə olunur)

```bash
docker compose up --build
```

Bu əmr PostgreSQL-i qaldırır, sonra `pipeline` konteyneri ardıcıl olaraq bunları edir:
cədvəlləri sıfırdan yaradır → əsas yükləmə → keyfiyyət yoxlamaları → SQL nəticələri →
noyabr faylının inkremental yüklənməsi → yenidən yoxlamalar və nəticələr. Hamısı loga çıxır.

Ayrı-ayrı addımlar:

```bash
docker compose up -d db
docker compose run --rm pipeline python -m pipeline load          # əsas yükləmə
docker compose run --rm pipeline python -m pipeline load          # təkrar: heç nə ikiləşmir
docker compose run --rm pipeline python -m pipeline incremental   # noyabr faylı
docker compose run --rm pipeline python -m pipeline check         # keyfiyyət yoxlamaları
docker compose run --rm pipeline python -m pipeline report        # SQL nəticələri
docker compose exec db psql -U postgres bookstore                 # bazaya baxmaq
```

### Variant 2: Lokal Python

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
docker compose up -d db          # və ya öz PostgreSQL-iniz
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/bookstore
python -m pipeline all --reset
```

### Testlər

```bash
pytest -q
```

`tests/test_cleaning.py` təmizləmə qaydalarını bazasız yoxlayır. `tests/test_pipeline_db.py`
işləyən PostgreSQL ilə idempotentliyi və inkremental yükləməni yoxlayır (baza yoxdursa skip olunur).

## Layihənin strukturu

```
data/                     xam CSV faylları (dəyişdirilmir)
pipeline/
  cleaning.py             təmizləmə qaydaları (yalnız pandas, baza yoxdur)
  load.py                 bazaya yükləmə (upsert), inkremental məntiq
  quality.py              yükləmədən sonrakı keyfiyyət yoxlamaları
  report.py               sql/queries-i işə salıb Markdown cədvəli çap edir
  db.py, config.py        qoşulma və parametrlər (DATABASE_URL, DATA_DIR)
  __main__.py             komanda sətri: python -m pipeline <load|incremental|check|report|all>
sql/
  schema.sql              cədvəllər
  queries/q1..q5_*.sql    SQL sualları
tests/                    pytest testləri
```

## Tapılan məlumat problemləri və qərarlar

Bütün qaydalar `pipeline/cleaning.py` faylındadır. Xam fayllar dəyişdirilmir.

### customers.csv (326 sətir → 320 müştəri)

| Problem | Nə etdim | Niyə |
|---|---|---|
| 6 `customer_id` iki dəfə var (C0038, C0100, C0207, C0266, C0285, C0291). Fərq yalnız addadır: bir sətirdə BÖYÜK hərflə yazılıb | ID-yə görə tək sətir saxladım, adı BÖYÜK hərflə olmayan sətri seçdim | Digər sahələr eynidir, deməli eyni müştəridir. Normal yazılış daha düzgündür |
| Şəhər 15 fərqli formada: `Bakı`, ` Bakı`, `Baki`, `BAKU`, `baku `, `Gence`, `GANJA`, `SUMGAIT`, `Sheki`, `Lenkeran` və s. | Boşluqları sildim, kiçik hərfə saldım və xəritə (`CITY_MAP`) ilə 5 standart ada gətirdim: Bakı, Gəncə, Sumqayıt, Şəki, Lənkəran | Şəhər üzrə qruplaşdırma (sual 3) yalnız standart adla düzgün işləyir. Xəritədə olmayan yeni dəyər gəlsə, atılmır: loga xəbərdarlıq yazılır |
| `signup_date` 3 formatdadır: `2024-07-04`, `19.06.2025`, `14/03/2025` | Hər formatı ayrıca (`strptime`) oxudum, gün-ay-il qəbul etdim | `/` və `.` formatlarında birinci rəqəm 12-dən böyük ola bilir (39 və 53 halda), ikinci isə heç vaxt. Deməli format `dd/mm/yyyy`-dir, `mm/dd` deyil |
| 20 müştərinin e-poçtu boşdur | `NULL` saxladım | Müştəri və onun sifarişləri realdır. E-poçt analitika üçün vacib deyil |
| Python-da `"İ".lower()` iki simvol (`i` + nöqtə) qaytarır | Müqayisədən əvvəl `İ` → `i` əvəzləməsi (`normalize_key`) | Əks halda `BƏDİİ` xəritədə tapılmır |

### products.csv (60 kitab)

| Problem | Nə etdim | Niyə |
|---|---|---|
| Qiymət formatları qarışıqdır: `22 AZN`, `25,00`, `12.5 AZN`, `6.00` | `AZN`-i sildim, vergülü nöqtə ilə əvəz etdim, rəqəmə çevirdim | Bir rəqəm tipi lazımdır |
| P001 və P045-in qiyməti boşdur | Sifarişlərdə həmin kitabın ən çox rast gəlinən `unit_price`-ı ilə doldurdum (12.50 və 18.00) | Sifarişlərdə bu kitabların qiyməti həmişə eynidir. Digər kitablarda kataloq qiyməti sifariş qiyməti ilə 100% üst-üstə düşür, ona görə bu mənbə etibarlıdır |
| Kateqoriya 11 variantdadır: `Biznes`/`biznes `, `Tarix`/`TARIX`, `texnologiya`/`Texnologiya`/`IT`, `usaq kitablari`/`Uşaq kitabları`, `bədii ədəbiyyat`/`BƏDİİ` | `CATEGORY_MAP` ilə 5 kateqoriyaya gətirdim. `IT` → Texnologiya | Sual 5 kateqoriya üzrədir. `IT` ayrıca kateqoriya kimi cəmi 5 kitabdır və mənaca texnologiyadır. Bu bir fərziyyədir, biznesdən təsdiq istənməlidir |

### orders_2026_08_10.csv (2425 sətir → 2382 sifariş + 18 karantin)

| Problem | Nə etdim | Niyə |
|---|---|---|
| 25 sətir tam dublikatdır (bütün sütunlar eynidir) | Sildim, sonra `order_id` üzrə də unikallığı təmin etdim | Eyni sifariş iki dəfə sayılsa, gəlir şişir |
| `status`: `completed`, `Completed`, `COMPLETED` | Kiçik hərfə saldım. Yalnız `completed/cancelled/refunded` qəbul olunur | Qruplaşdırma üçün |
| `order_ts` 3 formatdadır: `2026-10-28T03:29:40`, `2026-11-01 00:06:55`, `05.10.2026 22:15` | Hər formatı ayrıca oxudum, gün-ay-il qəbul etdim | 480 halda birinci rəqəm 12-dən böyükdür. Bütün tarixlər avqust–oktyabr aralığına düşür, bu da qərarı təsdiqləyir |
| 18 sətirdə `quantity` mənfidir (-1…-4), status isə əksər hallarda `completed`-dir | Silmədim, `rejected_orders` cədvəlinə səbəbi ilə köçürdüm | Mənfi miqdar qaytarma ola bilərdi, amma qaytarmalar ayrıca `refunded` statusu ilə gəlir. Deməli bu, xəta ehtimalıdır. Gəlirə daxil etmirəm, amma itirmirəm də: biznes yoxlaya bilsin |
| 44 sifarişdə `customer_id` boşdur | Sifarişi saxladım, `customer_id = NULL` | Satış baş verib, gəlir realdır. Sadəcə müştəriyə/şəhərə bağlana bilmir (sual 3 və 4-də iştirak etmir, sual 1, 2, 5-də iştirak edir) |
| 25 sifariş `P999` məhsuluna aiddir, kataloqda belə məhsul yoxdur | `dim_product`-a `is_known = FALSE` olan "Naməlum məhsul (P999)" sətri əlavə etdim | Gəlir itməsin deyə (sual 1-də daxildir). Sual 2 və 5 "kitab" haqqındadır, orada naməlum məhsul çıxarılır |

### orders_2026_11_01.csv (inkremental, 68 sətir)

60 yeni sifariş və 8 köhnə sifariş var. Köhnələrin statusu `completed` → `refunded` dəyişib
(məs. O000610, O001279). Həll yolu aşağıda, "İnkremental yükləmə" bölməsindədir.

### Gəlir qərarı

**Gəlir = yalnız `status = 'completed'` sifarişlərin `quantity × unit_price` cəmi.**
`cancelled` (ləğv) sifarişlər üçün ödəniş alınmayıb. `refunded` sifarişlərin pulu geri qaytarılıb.
Hər ikisi gəlirə daxil deyil. Bu qayda bir dəfə, `fact_orders.is_revenue` generated sütununda yazılıb,
ona görə bütün sorğular eyni məntiqi istifadə edir. Gəlir `unit_price` ilə hesablanır,
`list_price` ilə yox: satış anındakı qiymət daha doğrudur.

## Model

```
                 dim_date (date_key PK)
                        |
dim_customer ---- fact_orders ---- dim_product
(customer_id PK)  (order_id PK)    (product_id PK)

rejected_orders   (karantin: təmizləmədən keçməyən sətirlər)
```

| Cədvəl | Məzmun |
|---|---|
| `fact_orders` | Bir sətir = bir sifariş (fayllarda hər sifarişdə bir məhsul var). `quantity`, `unit_price`, `amount` (generated = quantity × unit_price), `status`, `is_revenue` (generated), `source_file`, `loaded_at`, `updated_at` |
| `dim_customer` | Müştəri: ad, standart şəhər, qeydiyyat tarixi, e-poçt, `is_known` |
| `dim_product` | Kitab: ad, standart kateqoriya, kataloq qiyməti, `is_known` |
| `dim_date` | Təqvim: `date_key` (YYYYMMDD), il, rüb, ay, `year_month`, həftə günü, həftə sonu |
| `rejected_orders` | Karantinə düşən xam sətirlər və səbəb (`reason`) |

**Niyə belə:**
- Ulduz sxemi analitika üçün standartdır. Rəqəmlər (miqdar, məbləğ) faktda, təsvir (şəhər, kateqoriya, ay) ölçülərdədir. Bütün suallar 1-2 JOIN ilə yazılır.
- Faktın səviyyəsi (grain) "bir sifariş"dir, çünki fayllarda `order_id` bir məhsula bağlıdır. Ayrıca `order_items` cədvəli lazım deyil.
- `dim_date` ay/rüb/həftə sonu kimi suallarda tarix funksiyalarını təkrar yazmamağa imkan verir.
- Natural açarlar (`C0001`, `P001`) saxlanılıb, surrogate açar (SERIAL) yox: məlumat kiçikdir, açarlar sabitdir və bu, upsert-i sadələşdirir.
- `CHECK` və `FOREIGN KEY` məhdudiyyətləri səhv məlumatın bazaya düşməsinə ikinci maneədir.
- "Naməlum" ölçü sətirləri (`is_known = FALSE`) Kimball yanaşmasıdır: fakt atılmır, amma problemli olduğu görünür.

## İdempotentlik və inkremental yükləmə

- Bütün yükləmələr `INSERT ... ON CONFLICT (açar) DO UPDATE` (upsert) ilə edilir. Skript neçə dəfə işə salınsa da, sətir sayı dəyişmir. Bunu `tests/test_pipeline_db.py` yoxlayır.
- Sətir yalnız nəsə həqiqətən dəyişəndə yenilənir (`IS DISTINCT FROM`). Bu zaman `updated_at` dəyişir. Log hər fayl üçün "yeni / yeniləndi / rədd edildi" saylarını göstərir:
  ```
  orders_2026_08_10.csv: oxundu 2425, yeni 2382, yeniləndi 0, rədd edildi 18
  orders_2026_11_01.csv: oxundu 68, yeni 60, yeniləndi 8, rədd edildi 0
  ```
- Köhnə fayl yenidən yüklənəndə yeni statusu geri qaytarmasın deyə şərt var: `EXCLUDED.source_file >= fact_orders.source_file`. Fayllar tarixlə adlandığı üçün əlifba sırası xronoloji sıraya bərabərdir. Yəni noyabr faylından sonra `load` yenidən işə salınsa, `refunded` statusu `completed`-ə qayıtmır (bu da testdə yoxlanılır).

## Keyfiyyət yoxlamaları

`python -m pipeline check` hər yükləmədən sonra işləyir (`pipeline/quality.py`). Hər yoxlama problemli sətirləri sayan bir SQL-dir.

| Səviyyə | Yoxlama | Nəticə |
|---|---|---|
| error | Mənfi/sıfır miqdar, mənfi/sıfır qiymət, naməlum status, gələcək tarixli sifariş | 0 |
| error | Kataloqda qiyməti olmayan kitab, yanlış formatlı/təkrarlanan e-poçt | 0 |
| error | Qeydiyyat tarixindən əvvəl verilmiş sifariş | 0 |
| warning | Naməlum məhsula (P999) aid sifariş | 25 |
| warning | Müştərisi boş sifariş | 44 (noyabrdan sonra 45) |
| warning | E-poçtu boş müştəri | 20 |
| warning | Karantindəki sətirlər | 18 |
| warning | Sifariş qiyməti kataloq qiymətindən fərqlidir | 0 |

`error` tapılarsa proses `exit code 1` ilə bitir (CI/cron bunu görə bilər). `warning` bilinən və qəbul edilmiş vəziyyətdir.

## SQL nəticələri

Sorğular `sql/queries/` qovluğundadır. Nəticələr `python -m pipeline report` ilə yaradılıb.

### Əsas tapşırıq (avqust–oktyabr, ilk üç fayl)

#### q1_monthly_revenue.sql

| month | total_orders | completed_orders | revenue_azn |
|---|---|---|---|
| 2026-08 | 808 | 654 | 15466.60 |
| 2026-09 | 755 | 613 | 14768.80 |
| 2026-10 | 819 | 676 | 15263.60 |

#### q2_top5_books.sql

| product_id | title | category | units_sold | revenue_azn |
|---|---|---|---|---|
| P038 | Kitab 38 | Tarix | 60 | 2100.00 |
| P022 | Kitab 22 | Texnologiya | 48 | 1680.00 |
| P007 | Kitab 7 | Biznes | 43 | 1505.00 |
| P053 | Kitab 53 | Tarix | 48 | 1435.20 |
| P006 | Kitab 6 | Biznes | 46 | 1375.40 |

#### q3_city_revenue.sql

| city | registered_customers | paying_customers | revenue_azn |
|---|---|---|---|
| Bakı | 182 | 181 | 25288.40 |
| Gəncə | 55 | 55 | 7434.40 |
| Sumqayıt | 51 | 51 | 6885.00 |
| Şəki | 21 | 21 | 3388.20 |
| Lənkəran | 11 | 11 | 1636.80 |

#### q4_repeat_customers.sql

| total_customers | repeat_any_status | pct_any_status | repeat_completed_only | pct_completed_only |
|---|---|---|---|---|
| 320 | 318 | 99.38 | 315 | 98.44 |

#### q5_top_book_per_category.sql

| category | product_id | title | revenue_azn |
|---|---|---|---|
| Bədii ədəbiyyat | P029 | Kitab 29 | 1232.00 |
| Biznes | P007 | Kitab 7 | 1505.00 |
| Tarix | P038 | Kitab 38 | 2100.00 |
| Texnologiya | P022 | Kitab 22 | 1680.00 |
| Uşaq kitabları | P003 | Kitab 3 | 1144.00 |

### Noyabr faylından sonra (bonus)

Gözlənildiyi kimi, 8 sifariş `refunded` olduğu üçün avqust–oktyabr gəliri azalıb, 2026-11 ayı isə yeni əlavə olunub.

#### q1_monthly_revenue.sql

| month | total_orders | completed_orders | revenue_azn |
|---|---|---|---|
| 2026-08 | 808 | 652 | 15429.60 |
| 2026-09 | 755 | 610 | 14720.30 |
| 2026-10 | 819 | 673 | 15212.60 |
| 2026-11 | 60 | 50 | 941.10 |

#### q2_top5_books.sql

| product_id | title | category | units_sold | revenue_azn |
|---|---|---|---|---|
| P038 | Kitab 38 | Tarix | 61 | 2135.00 |
| P022 | Kitab 22 | Texnologiya | 48 | 1680.00 |
| P007 | Kitab 7 | Biznes | 44 | 1540.00 |
| P006 | Kitab 6 | Biznes | 49 | 1465.10 |
| P053 | Kitab 53 | Tarix | 48 | 1435.20 |

#### q3_city_revenue.sql

| city | registered_customers | paying_customers | revenue_azn |
|---|---|---|---|
| Bakı | 182 | 181 | 25725.70 |
| Gəncə | 55 | 55 | 7500.90 |
| Sumqayıt | 51 | 51 | 7072.50 |
| Şəki | 21 | 21 | 3417.20 |
| Lənkəran | 11 | 11 | 1715.10 |

#### q4_repeat_customers.sql

| total_customers | repeat_any_status | pct_any_status | repeat_completed_only | pct_completed_only |
|---|---|---|---|---|
| 320 | 318 | 99.38 | 315 | 98.44 |

#### q5_top_book_per_category.sql

| category | product_id | title | revenue_azn |
|---|---|---|---|
| Bədii ədəbiyyat | P029 | Kitab 29 | 1210.00 |
| Biznes | P007 | Kitab 7 | 1540.00 |
| Tarix | P038 | Kitab 38 | 2135.00 |
| Texnologiya | P022 | Kitab 22 | 1680.00 |
| Uşaq kitabları | P003 | Kitab 3 | 1188.00 |

**Şərhlər:**
- Sual 4-də məxrəc qeydiyyatlı bütün 320 müştəridir. "Sifariş verib" ifadəsini statusdan asılı olmayaraq hesabladım (`pct_any_status`). Müqayisə üçün yalnız tamamlanmış sifarişlərə görə faiz də verilib.
- Sual 3-də müştəri sayı iki cür göstərilib: qeydiyyatlı və ən azı bir tamamlanmış sifarişi olan.
- Sual 5-də `RANK()` istifadə olunub, ona görə bərabər gəlir olsa hər iki kitab göstərilər (indiki məlumatda bərabərlik yoxdur).

## Daha çox vaxtım olsaydı

- **Orkestrasiya:** Airflow və ya Dagster ilə gündəlik iş, yeni faylları avtomatik tapmaq və işlənmiş faylları `etl_file_log` cədvəlində qeyd etmək (eyni faylı təkrar emal etməmək üçün).
- **Fayl sırası:** status üçün `source_file` adı əvəzinə faylın içində `updated_at`/çıxarış tarixi olsa, daha etibarlı olardı.
- **SCD Type 2:** müştərinin şəhəri dəyişəndə tarixçəni saxlamaq. İndi son vəziyyət saxlanılır.
- **Staging qatı:** xam məlumatı əvvəlcə `staging` sxeminə olduğu kimi yükləmək, təmizləməni SQL/dbt ilə etmək. dbt testləri `quality.py`-ni əvəz edərdi.
- **Status tarixçəsi:** sifarişin statusunun nə vaxt dəyişdiyini ayrıca cədvəldə saxlamaq (`order_status_history`), indi yalnız son status və `updated_at` var.
- **Biznesdən təsdiq:** `IT` → Texnologiya, mənfi miqdar və P999 haqqında qərarları biznes tərəfi ilə dəqiqləşdirmək.
- **CI:** GitHub Actions ilə hər push-da pytest və Docker build.

---

Tapşırığa sərf olunan vaxt: təxminən **TODO** saat.
AI alətlərindən istifadə: **TODO**
