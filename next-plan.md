# Next Plan — Sprint 2

Status: drafted **2026-05-21**, after Sprint 1 close.
Owner: backend team. Estimated duration: 2 weeks.

---

## 0. Sprint 1 retrospective

**Shipped:**

- Django 5 skeleton (`config/settings/{base,dev,prod}`, Celery wiring, OpenAPI via drf-spectacular).
- Auth flow: phone → OTP → JWT, multi-store membership selection.
- `tenants` (Store, Org, CompanyInfo) + `accounts` (User, Membership, OTPCode) + `audit` (append-only with PG trigger).
- RBAC permission classes: `HasActiveStore`, `IsAdmin`, `CanApproveDocuments`, `CanEditCatalog`, etc.
- `/api/company/`, `/api/users/*`, `/api/audit-log/`, `/api/auth/*`.
- 3 e2e tests green (happy path, wrong OTP, RBAC).

**Not shipped (deferred from Sprint 1):**

- Postgres (we're on SQLite for the dev DB — pgvector + Postgres needed by Sprint 4).
- Eskiz.uz SMS — console stub only.
- STIR lookup against Soliq.uz — only a frontend mock today.
- Frontend ↔ backend wiring — `lib/store.ts` still mocks everything.

---

## 1. Kamchiliklar (gaps surfaced in Sprint 1)

Ranked by blast radius. Items marked **[S2]** fixed inside Sprint 2; **[S3+]** punted with rationale.

### 1.1 Security / correctness

1. **[S2] `verify_otp` silently creates users on `purpose=login`.**
   `apps/accounts/services.py:109` auto-`get_or_create`s a User row for any
   successful OTP — even for the login flow. That means anyone who knows a
   phone number and can intercept an SMS gets a brand-new account with
   zero memberships (low-value but still a footgun). Fix: split into
   `_get_user_for_login` (raises if missing) vs `_get_or_create_for_register`.

2. **[S2] STIR not validated.**
   `RegisterStoreSerializer` and `CompanyInfo.stir` accept any string of
   length 9–14. Add a digit-only + length 9 (MChJ) / 14 (YaT) validator
   matching `supplier-form-modal.tsx`.

3. **[S2] CompanyInfo.stir is globally unique.**
   Two stores cannot share STIR (correct), but the error today bubbles up
   as a 500. Catch `IntegrityError` in `RegisterStoreView` and return a
   structured 409.

4. **[S2] SECRET_KEY default too short.**
   Default dev key is 29 bytes → PyJWT warns about RFC 7518. Bump to ≥
   32 bytes in `.env.example` and add a `generate_secret_key` mgmt
   command for first-run.

5. **[S3] Refresh-token rotation enabled but no client-side rotation
   helper.** Frontend wiring lands in Sprint 2 — the helper will live
   in `web/lib/api.ts`. Backend itself is correct.

6. **[S2] `verify_otp` increments `attempts` even on wrong purpose match
   failure.** When no OTP row matches (`otp is None`), we silently
   return None. That hides whether the code was wrong vs no code was
   sent. Acceptable, but log it for incident response.

### 1.2 API surface

7. **[S2] No structured error envelope.**
   Some endpoints return `{"error": "msg"}`, some `{"detail": "msg"}`,
   DRF defaults to `{"field": ["..."]}` on serializer errors. Adopt a
   single envelope (`{"error": {"code": "...", "message": "...", "fields": {...}}}`)
   via a custom exception handler.

8. **[S2] Pagination shape mismatch.**
   `LimitOffsetPagination` returns `{count, next, previous, results}`.
   Frontend currently expects raw arrays from server actions. Standardize
   on `{count, results}` and update the new `lib/api.ts` helpers.

9. **[S2] No openapi-typescript pipeline.**
   `drf-spectacular` is installed but the frontend has no script to
   regenerate `lib/types.ts` from `/api/schema/`. Without this, types
   will drift the moment we start wiring.

10. **[S3] No write-side audit on read-side endpoints.**
    Listing audit log itself isn't audited. Acceptable for now; revisit
    when Auditor role becomes a separate persona (Sprint 6).

11. **[S2] `select-store` doesn't update `last_seen_at` of the *previous*
    store.** Only the new one gets touched. Minor; not user-visible.

### 1.3 Multi-tenancy

12. **[S2] No DB-level tenant guard.**
    All filtering is in app code (`TenantScopedViewSet`). One missing
    `get_queryset` override = cross-tenant read. Add Postgres RLS policy
    (`USING (store_id = current_setting('app.active_store')::uuid)`) once
    we move to Postgres in Sprint 2.

13. **[S2] `request.active_store_id` is set in permission, not auth.**
    Means tasks (Celery), management commands, signals see no tenant
    context. Move resolution into a custom JWTAuthentication subclass
    that stamps `request.active_store_id` during `authenticate()`.

### 1.4 Data integrity

14. **[S2] `Org.stir` is unique but unused.**
    We never set it — RegisterStoreView creates Store without Org. OK
    today (distributor portal deferred). Document as known-NULL.

15. **[S2] No soft-delete strategy.**
    `delete()` on Product / Supplier wipes them. Historical documents
    keep a FK — would break with `PROTECT` cascade once Sprint 3 lands.
    Decision: use `SET_NULL` on document → product FKs, keep hard-delete
    for the catalog. Re-evaluate in Sprint 6.

### 1.5 DevEx / Ops

16. **[S2] No Docker Compose.**
    Postgres + Redis + pgvector are needed for Sprint 2–4. Ship
    `compose.yml` + `make up` + first-run seed script.

17. **[S2] No CI.**
    Tests, ruff, migrations check should run on every PR. GitHub
    Actions YAML in this sprint.

18. **[S3] No structured logging.**
    `print` and `log.warning` only. Bring in `structlog` in Sprint 5
    when we wire Sentry breadcrumbs to Celery tasks.

19. **[S2] No `manage.py` shortcuts.**
    Ship `make migrate / make test / make seed / make schema` so
    contributors don't have to remember `.venv/bin/python manage.py …`.

### 1.6 Testing

20. **[S2] Coverage gaps in `apps/accounts/tests/test_auth_flow.py`:**
    - OTP expiry (set `freezegun` past `expires_at`).
    - Max-attempts lockout (5 wrong tries → 6th rejects even with correct code).
    - Rate limit (>10 OTPs / hour returns 429).
    - Invite flow + toggle-status + delete-from-store.
    - `select-store` 403 for non-member.
    - Audit immutability at the PG trigger level (not just ORM).

21. **[S2] No factory_boy fixtures.**
    Tests build models inline. Adds friction once Sprint 2 has 8+
    models. Add `apps/*/tests/factories.py`.

---

## 2. Sprint 2 scope

Goal: **Catalog + suppliers + stock movements wired end-to-end with the
frontend.** After Sprint 2 a user should be able to log in, see live
suppliers and products, edit them, and adjust stock — all going through
the Django API instead of `lib/store.ts`.

### 2.1 Backend deliverables

#### Suppliers (`apps/suppliers/`)

```
GET    /api/suppliers/                       — list
POST   /api/suppliers/                       — create (admin, omborchi)
GET    /api/suppliers/{id}/                  — detail
PATCH  /api/suppliers/{id}/                  — update
DELETE /api/suppliers/{id}/                  — delete
GET    /api/suppliers/lookup-stir/?stir=…    — Soliq.uz lookup (mock + real)
```

Models:
- `Supplier(TenantScoped)` — id, name, stir, verified, soliq_last_checked.
  `unique_together = (store, stir)`.

Services:
- `soliq_client.lookup_stir(stir) → {name, status, verified} | None`
  - Mock implementation reuses `MOCK_NAME_POOL_3X` from
    `supplier-form-modal.tsx` for parity.
  - Real implementation behind `SOLIQ_API_TOKEN`. If unset, fall back to mock.

Permissions: `CanEditCatalog` for write, `HasActiveStore` for read.

#### Products (`apps/products/`)

```
GET    /api/products/                       — list (filter: status, has_mxik)
POST   /api/products/
GET    /api/products/{id}/
PATCH  /api/products/{id}/
DELETE /api/products/{id}/
POST   /api/products/{id}/stock-adjust/     — kirim/chiqim/inventarizatsiya
GET    /api/products/stats/                 — KPI aggregates (matches getProductStats)
```

Models:
- `Product(TenantScoped)` — name, mxik (CharField for now, FK to
  MxikCode lands in Sprint 4), unit, current_stock, min_stock,
  avg_price, last_received_at.
- `StockMovement(TenantScoped)` — product FK, kind
  (kirim/chiqim/inventarizatsiya/doc_approve), delta, before, after,
  reason, actor, document FK (nullable).

Service:
- `adjust_stock(product, kind, qty, reason, actor) -> StockMovement`
  - Wraps the change in `transaction.atomic`.
  - Refuses negative `current_stock` on chiqim.
  - For inventarizatsiya, sets to exact value, computes delta.
  - On kirim, bumps `last_received_at`.

#### MXIK lookup (stub for Sprint 4)

```
GET /api/mxik/?q=…&limit=10
```
- Returns hard-coded fuzzy matches from a seed JSON of ~200 popular codes
  for the demo. pgvector + embeddings land in Sprint 4.
- Schema mirrors `MxikSuggestion` from `lib/types.ts` so frontend
  doesn't change when the real ML rolls in.

#### Infrastructure

- **Postgres + pgvector + Redis via Docker Compose.**
  `compose.yml`: `postgres:16` with `ankane/pgvector` image, `redis:7-alpine`.
  Volumes mounted to `./data/{pg,redis}`.
- **Postgres RLS** policy on every TenantScoped table:
  ```sql
  ALTER TABLE products_product ENABLE ROW LEVEL SECURITY;
  CREATE POLICY tenant_isolation ON products_product
      USING (store_id::text = current_setting('app.active_store', true));
  ```
  Set via custom DB router middleware:
  `SET LOCAL app.active_store = '<uuid>'` at request start.
- **Custom JWTAuthentication** that stamps `request.active_store_id`
  at auth time (fixes gap #13).
- **Custom exception handler** for the structured error envelope
  (fixes gap #7).

#### Tests

- factory_boy factories for all new models (`StoreFactory`,
  `UserFactory`, `MembershipFactory`, `SupplierFactory`,
  `ProductFactory`).
- Per-app tests:
  - `suppliers/`: CRUD, STIR uniqueness within store, lookup-stir mock vs
    real, RBAC denials (kassir → 403 on POST).
  - `products/`: CRUD, stock-adjust (each kind), refusal of over-draw on
    chiqim, audit row written, stats endpoint shape.
- Cross-tenant isolation test: User A from Store A cannot see Store B's
  products even with a forged store_id in URL.
- RLS test: raw SQL `SELECT * FROM products_product` returns nothing
  when `app.active_store` isn't set.

### 2.2 Frontend deliverables

#### `web/lib/api.ts` — replaces server actions' direct store calls

- `apiClient(path, init)` — adds `Authorization: Bearer …` from a
  cookie-stored access token; retries once on 401 by calling
  `/api/auth/refresh/`.
- Resource helpers:
  - `auth.sendOtp / verifyOtp / register / selectStore / me / logout`
  - `company.get / patch`
  - `suppliers.list / create / update / delete / lookupStir`
  - `products.list / create / update / delete / adjustStock / stats`
  - `users.list / invite / update / delete / toggleStatus`
  - `auditLog.list`
- All return typed responses sourced from generated `lib/api/types.ts`.

#### Auth integration

- **httpOnly cookie storage** for access + refresh tokens. Set via
  Server Action wrapper around `/api/auth/verify-otp/` so tokens never
  hit the browser JS.
- `/login` + `/register` + `/onboarding` pages wired to the real
  endpoints. `lib/store.ts` users path retired.
- New `middleware.ts` in Next.js — redirects unauthenticated requests
  to `/login` and missing-store users to `/select-store`.

#### Type generation

- New `web/scripts/sync-types.sh`:
  ```bash
  curl -fsS $BACKEND/api/schema/ > openapi.json
  npx openapi-typescript openapi.json -o lib/api/types.ts
  ```
- Pre-commit hook in backend to regenerate when serializers change.
- Update `lib/types.ts` to re-export from `lib/api/types.ts` so callers
  don't churn.

#### Page wiring (`web/app/(app)`)

| Page | Action |
|---|---|
| `/dashboard` | Replace `getDocumentStats` + `getProductStats` with `/api/products/stats/` + (Sprint 3) docs stats. |
| `/nomenklatura` | `getProducts → products.list`; ProductFormModal calls `products.create/update`; delete calls API. |
| `/ombor` | Same as nomenklatura + `adjustStock` → `products.adjustStock`. |
| `/yetkazib-beruvchilar` | `suppliers.*`; modal's "Soliq.uz dan tekshirish" calls `suppliers.lookupStir`. |
| `/sozlamalar` Foydalanuvchilar | `users.*`. |
| `/sozlamalar` Korxona | `company.get/patch`. |
| `/audit-log` | `auditLog.list` with filters. |
| `/hujjatlar`, `/insights`, `/review-queue` | Stay on `lib/store.ts` mock until Sprint 3–4. |

#### Cleanup

- Remove `lib/store.ts` write functions that Sprint 2 replaces
  (products / suppliers / users / company / audit reads). Keep
  documents/insights/integrations mock layer until later sprints.
- `lib/actions/*.ts` becomes thin wrappers calling `apiClient` (still
  used as Next.js Server Actions so `revalidatePath` works).

---

## 3. Acceptance criteria

A reviewer should be able to verify Sprint 2 by:

1. `make up` boots Postgres + Redis + Django + Next.js in <60s.
2. `make test` exits 0 with ≥85% line coverage on `apps/{accounts,tenants,audit,suppliers,products}`.
3. A new operator can:
   - Register a store via the frontend at `/register`.
   - Add 3 suppliers (one via STIR lookup).
   - Add 5 products (one with auto-suggested MXIK from /api/mxik/).
   - Adjust stock (kirim + inventarizatsiya).
   - See the audit log reflect each action.
   - Log out, log back in, and the data persists.
4. `npm run sync-types` regenerates `lib/api/types.ts` and the frontend
   still builds (`bunx tsc --noEmit` clean).
5. Cross-tenant test passes: a second store cannot read first store's
   products via API, both with forged JWT and direct SQL (RLS).
6. `/api/schema/` is the single source of truth for endpoints — Swagger
   UI shows every Sprint 2 endpoint without spectacular warnings.

---

## 4. Risks

- **pgvector image on macOS ARM**: `ankane/pgvector` is multi-arch but
  startup script sometimes fails on first volume mount. Mitigation:
  Docker Compose health check + retry, document in README.
- **RLS + Django ORM**: `SET LOCAL` needs an open transaction; DRF's
  `atomic_requests` not enabled by default. Plan: wrap every request in
  a transaction via a custom middleware that opens `with transaction.atomic()`.
  Performance impact minimal (single connection, txn ends on response).
- **Soliq.uz API availability**: unknown rate limits + ToS. We cache
  results 24h per STIR; fall back to mock when down. Verify with a
  partner before going to demo.
- **Type drift between OpenAPI and hand-rolled frontend types**:
  mitigated by `lib/types.ts` re-exporting from generated module + a
  CI check that fails if `sync-types.sh` produces a diff.
- **httpOnly cookie + Next.js Server Actions**: need to confirm that
  Next.js 16 allows reading the access token cookie inside Server
  Actions (the new Cookies API). If not, fall back to passing a
  short-lived token via a custom header from the Next.js edge
  middleware.

---

## 5. Out of scope (parked)

- pgvector embeddings + real MXIK fuzzy matching → **Sprint 4**.
- Document upload (Excel / PDF / photo) + GPT-4o parse → **Sprint 3**.
- Didox webhook → **Sprint 5**.
- Telegram notifications → **Sprint 5**.
- Real Eskiz.uz SMS — `console` provider stays default. Add `eskiz`
  provider with HMAC auth in **Sprint 5** when the demo flow needs it.
- Soft-delete + restore — **Sprint 6**, with a `deleted_at` audit story.
- Billing / Stripe / Atmos integration — **Sprint 6**.

---

## 6. Day-by-day breakdown (suggested)

| Day | Backend | Frontend |
|---|---|---|
| 1 | compose.yml, Postgres+pgvector boot, migrate, RLS skeleton. | scripts/sync-types.sh, generate first types file. |
| 2 | Custom JWTAuth + structured error envelope + exception handler. | lib/api.ts client + auth helpers. |
| 3 | Suppliers app: model + serializer + viewset + STIR validator. | /yetkazib-beruvchilar wired (list + create + delete). |
| 4 | Soliq.uz mock client + lookup endpoint + tests. | Supplier-form-modal STIR lookup wired. |
| 5 | Products app: model + serializer + viewset + tests. | /nomenklatura wired. |
| 6 | StockMovement model + adjust_stock service + endpoint + tests. | /ombor adjust + delete + edit wired. |
| 7 | /api/products/stats/ + /api/mxik/ stub + seed JSON. | Dashboard KPI cards wired (partial). |
| 8 | factory_boy fixtures, missing OTP/throttle tests. | /sozlamalar (Korxona + Foydalanuvchilar) wired. |
| 9 | CI (GitHub Actions): lint, test, migrate, schema diff check. | /audit-log wired with filters. |
| 10 | RLS hardening + cross-tenant integration test. | Next.js middleware.ts (auth gate + store guard). |
| 11 | Buffer / polish / docs. | E2E smoke: register → suppliers → products → stock. |
| 12 | Demo prep + Sprint 3 prep doc. | Same. |

---

## 7. Definition of done

- All endpoints listed in §2.1 respond per their OpenAPI contract.
- All pages listed in §2.2 source live data (no `lib/store.ts` for
  products/suppliers/users/company/audit).
- `make test` and `bunx tsc --noEmit` both green.
- README updated with `make up` boot instructions.
- next-plan.md (this file) replaced with Sprint 3 plan, summarising what
  shipped and what carried over.
