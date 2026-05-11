# Product Domain Production Deploy Plan

Generated: 2026-05-11

This is a read-only controlled deploy preparation plan for the Product Domain UI/API work. It documents the intended production deploy scope and verification steps only. It does not perform deployment, infrastructure writes, backend restart, DNS changes, SSL changes, redirect rule writes, Nginx writes, token output, or database migration.

## 1. Scope

Deploy the latest DevPilot Product Domain read-only admin surface as one controlled production change set.

Included:

- AI Office product-domain catalog model using `Brand -> Suite -> Product -> Module -> Domain`.
- Product Domains admin UI.
- Product Domains read-only catalog API.
- Product Domains validation API.
- Domain lookup API.
- Redirect Plan read-only API.
- Redirect Plan export APIs for JSON, CSV, Nginx template, and Cloudflare Bulk JSON template.
- Navigation entry for Product Domains.
- Tests and documentation needed to verify and govern the release.

Safety scope:

- Catalog/UI/API work is read-only.
- Redirect exports are templates only.
- The change set must not apply redirects or infrastructure changes.
- The change set must not modify database schema.

## 2. Files to Deploy

Production runtime candidates:

- `app.py`
- `services/product_domains.py`
- `templates/base.html`
- `templates/product_domains.html`

Documentation and governance candidates:

- `AGENTS.md`
- `docs/ai_office_website_architecture_report.md`
- `docs/devpilot_admin_feature_status_report.md`
- `docs/product_domain_production_deploy_plan.md`

Verification-only files:

- `tests/test_product_domains.py`

The two status reports identify Product Domains, Redirect Plan, and Redirect Plan export APIs as the same pending controlled deploy batch. They should be reviewed and promoted together so production has matching UI, API, validation, and export behavior.

## 3. Routes Affected

Admin UI:

- `GET /product-domains`

Navigation:

- `templates/base.html` adds or preserves the Product Domains entry under the Safety/admin navigation area.

## 4. APIs Affected

Read-only catalog and validation APIs:

- `GET /api/product-domains`
- `GET /api/product-domains/lookup?domain=...`
- `GET /api/product-domains/validate`

Read-only redirect plan APIs:

- `GET /api/product-domains/redirect-plan`
- `GET /api/product-domains/redirect-plan/export?format=json`
- `GET /api/product-domains/redirect-plan/export?format=csv`
- `GET /api/product-domains/redirect-plan/export?format=nginx`
- `GET /api/product-domains/redirect-plan/export?format=cloudflare-bulk`

## 5. Pre-deploy Checks

Before any production deploy is approved, verify:

- `AGENTS.md` exists and preserves the AI Office product-domain rules.
- `app.py` contains the Product Domain UI/API routes.
- `services/product_domains.py` contains the canonical catalog, validation, lookup, redirect plan, and export logic.
- `templates/base.html` includes Product Domains navigation.
- `templates/product_domains.html` renders the read-only Product Domains admin UI.
- `tests/test_product_domains.py` covers catalog invariants, route/API smoke checks, redirect plan behavior, and export behavior.
- The two status reports exist and match the intended controlled deploy scope.
- Product Domains, Redirect Plan, and Export APIs are included in the same change set.
- No DB schema migration is included.
- No token, secret, or encrypted key output is included.
- `git status --short` is reviewed so unrelated working tree changes are not accidentally promoted.

Required local verification commands:

```powershell
python -m py_compile app.py services/product_domains.py
python -m unittest tests.test_product_domains
git diff --check
```

Expected result:

- Python compile succeeds.
- Product Domain test suite passes.
- Diff whitespace check passes.

## 6. Deploy Steps

These steps are documentation only and must not be executed by this preparation task.

1. Confirm approval for the controlled Product Domain UI/API deploy.
2. Confirm the exact production file list from this plan.
3. Confirm no unrelated working tree changes are included.
4. Create or review the release commit according to project practice.
5. Copy or deploy only the approved runtime files to the production target.
6. Include governance documentation if production documentation sync is part of the approved release process.
7. Restart or reload the backend only if separately approved for the production release window.
8. Run post-deploy read-only verification.
9. Record verification results in the release notes or operations log.

## 7. Post-deploy Verification

After the approved deploy, verify these routes return successful responses and do not expose secrets:

- `GET /product-domains`
- `GET /api/product-domains`
- `GET /api/product-domains/validate`
- `GET /api/product-domains/redirect-plan`
- `GET /api/product-domains/redirect-plan/export?format=json`
- `GET /api/product-domains/redirect-plan/export?format=csv`
- `GET /api/product-domains/redirect-plan/export?format=nginx`
- `GET /api/product-domains/redirect-plan/export?format=cloudflare-bulk`

Also verify:

- Product tree can be listed.
- Domain lookup maps domains to the owning Product or Brand Hub.
- Domain roles are limited to `official`, `redirect`, `campaign`, `infra`, and `reserved`.
- Redirect domains include `target_domain`.
- Official domains are unique.
- Each Product has exactly one official domain.
- Redirect exports are downloadable templates only.
- No Cloudflare write, DNS write, SSL write, redirect rule write, Nginx write, DB migration, token output, or git push occurred as part of verification.

## 8. Rollback Plan

Rollback is file-level and application-level only. It must not touch DNS, SSL, redirect rules, Nginx, Cloudflare, or database schema.

1. Identify the previously known-good production version of the approved runtime files.
2. Restore the previous versions of:
   - `app.py`
   - `services/product_domains.py`
   - `templates/base.html`
   - `templates/product_domains.html`
3. Restore documentation only if production documentation sync created user-visible confusion.
4. Restart or reload the backend only if separately approved.
5. Verify the admin app loads.
6. Verify the Product Domains route is either restored to the previous behavior or intentionally unavailable according to the rollback target.
7. Record the rollback reason, files restored, verification results, and any follow-up work.

Rollback checks:

```powershell
python -m py_compile app.py services/product_domains.py
python -m unittest tests.test_product_domains
git diff --check
```

If the rollback target predates Product Domain tests, run the nearest available admin smoke tests and document that the Product Domain test suite no longer applies to the restored version.

## 9. Explicit Non-actions

This preparation task and this deploy plan explicitly do not perform:

- no DNS write
- no SSL write
- no redirect rule write
- no Nginx write
- no DB migration
- no token output
- no git push
- no backend restart unless separately approved

Additional non-actions:

- no Cloudflare API mutation
- no registrar nameserver change
- no production deploy execution
- no website generation per domain
- no assumption that every owned domain is an independent website
