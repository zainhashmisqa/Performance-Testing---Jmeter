# Endpoint & response-shape map — VERIFY BEFORE THE FIRST REAL RUN

This is the single file that has to be reconciled with reality. Everything in
`tests/azm_sba_perf.jmx` reads these as **properties**, so correcting anything
here is a flag change or a one-line edit in `config/user.properties` — never a
change to the `.jmx`.

Target: **SBA Academy sandbox (Open edX)**. Paths below are the standard Open edX
API shapes and are a starting assumption, not confirmed fact.

---

## 1. Endpoints

| Property | Current value | Used by | Confirmed? |
|---|---|---|---|
| `base_url` | `sandbox-sba.example-fill-me-in.com` | everything | ☐ **BLOCKER** |
| `path_login` | `/api/user/v1/account/login_session/` | S00 Login | ☐ |
| `path_catalog` | `/api/courses/v1/courses/` | S01a/S01b/S03a/S03b/S05 | ☐ |
| `path_course` | `/api/courses/v1/courses/` | S02 Course detail | ☐ |
| `path_cart` | `/api/commerce/v1/baskets/` | S04/S06 Add to cart | ☐ |
| `path_checkout` | `/api/commerce/v1/checkout/` | S07 Checkout | ☐ |
| `path_order` | `/api/commerce/v1/orders/` | S08 Order status | ☐ |

**Open edX caveat:** the standard login endpoint is session/CSRF-based and may
return a cookie rather than a bearer token. If so, one of these applies:

- The sandbox exposes an OAuth2 token endpoint (`/oauth2/access_token/`) — point
  `path_login` at it, send `grant_type=password`, and the JSON Extractor picks up
  `$.access_token`. The self-heal alias list already covers `access_token`.
- It is cookie-only — then the Cookie Manager already in the plan carries the
  session, and the Bearer header becomes decorative. In that case **still keep**
  concept 10 meaningful by extracting and sending the CSRF token as
  `X-CSRFToken: ${authToken}` (change the header name in the Header Manager;
  the correlation, chaining and self-healing all still apply unchanged).

Record which one is true here once you know: **_______________________**

## 2. Response shapes to capture

Run each call once in Postman and paste the trimmed response.

### Login → which key holds the token?
```json
{ "PASTE LOGIN RESPONSE HERE": "..." }
```
→ set `token_json_path=` ______________

### Catalog → which key holds the course id?
Currently assumed `$.results[*].id` with match number `0` (random pick).
```json
{ "PASTE CATALOG RESPONSE HERE": "..." }
```

### Cart → which key holds the cart/basket id?
Currently assumed `$.id`.
```json
{ "PASTE CART RESPONSE HERE": "..." }
```

### Checkout → which key holds the order reference, and what does status say?
Currently assumed `$.order_number`, and the assertion accepts
`confirmed|complete|enrolled|success` (case-insensitive regex on `$.status`).
```json
{ "PASTE CHECKOUT RESPONSE HERE": "..." }
```

## 3. Database (Concept 11)

| Property | Current value | Confirmed? |
|---|---|---|
| `db_driver` | `com.mysql.cj.jdbc.Driver` | ☐ |
| `db_url` | `jdbc:mysql://HOST:3306/edxapp?useSSL=false` | ☐ |
| `db_table` | `student_courseenrollment` | ☐ |
| `db_ref_column` | `id` | ☐ |

**SQL Server alternative** (if the sandbox is not MySQL — swap by flag only):
```
-Jdb_driver=com.microsoft.sqlserver.jdbc.SQLServerDriver
-Jdb_url="jdbc:sqlserver://HOST:1433;databaseName=DB;encrypt=true;trustServerCertificate=true"
```

Driver `.jar` must sit in `<jmeter>/lib/` and JMeter must be restarted. Keep the
jar in this repo's `lib/` folder — the CI workflow copies it in automatically.

**Security gate — do not run a JDBC query until this is ticked:**
☐ Written confirmation from the lead that this DB contains **synthetic data only**.

## 4. Test accounts

`data/logins.csv` currently holds 120 **placeholder** rows
(`azm_test_001@staging.invalid` / `SandboxPass!001`). Replace with real sandbox
test accounts before the baseline run.

☐ ≥100 valid staging accounts obtained
☐ Confirmed none are production credentials or real customer identities

## 5. Authorization to load-test

☐ Lead / Kalim approved running **200 VUs** against this sandbox, and a window agreed.
A 200-VU peak against a shared sandbox affects everyone else using it.
