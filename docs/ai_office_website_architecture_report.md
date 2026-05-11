# AI Office Website Architecture Status Report

Generated: 2026-05-11

This report summarizes the current DevPilot / AI Office website-domain architecture work for product, strategy, and analyst review. It distinguishes completed read-only architecture work from work that still requires a separate execution phase.

## 1. Executive Summary

AI Office now has a product-domain architecture model based on:

```text
Brand -> Suite -> Product -> Module -> Domain
```

The key strategic rule is:

```text
Do not turn every owned domain into an independent website.
```

Instead:

- `aioffice.com.tw` is the Brand Hub.
- Each Product has exactly one official domain.
- Extra domains are classified as `redirect`, `campaign`, `infra`, or `reserved`.
- Redirect and campaign domains point back to the correct official product domain or Brand Hub.

The current catalog contains:

- Brand: `AI Office`
- Brand key: `ai_office`
- Brand Hub: `aioffice.com.tw`
- Suites: 7
- Products: 26
- Domains: 60

Cloudflare zone and registrar nameserver onboarding for the current 60-domain priority set has been completed and verified as active. DNS records, SSL settings, and redirect rules have not yet been applied by automation.

## 2. Completed Work

### 2.1 Product Domain Rules Locked In

The repo now includes `AGENTS.md`, which defines long-term domain rules for future Codex work:

- Product hierarchy: Brand -> Suite -> Product -> Module -> Domain.
- Valid domain roles: `official`, `redirect`, `campaign`, `infra`, `reserved`.
- Each Product must have exactly one official domain.
- Redirect domains must define `target_domain`.
- `aioffice.com.tw` is the Brand Hub.
- `aioffice.tw` is the Brand Hub redirect.
- Catalog work is read-only unless a later phase explicitly allows external changes.

### 2.2 Product Domain Catalog

Implemented in:

```text
services/product_domains.py
```

The catalog currently models:

- Business AI
- Marketing AI
- Commerce AI
- Service AI
- Industry AI
- Creative AI
- Infrastructure AI

Each product has one official domain. Redirect and campaign domains are tied back to the official domain.

Examples:

```text
AICRM
official: aicrm.com.tw
redirects: crmai.com.tw, crmai.tw

AIAD
official: aiad.com.tw
redirects: aiad.tw, aiad.net.tw
campaign: aiad.fun

AI Office Brand Hub
official: aioffice.com.tw
redirect: aioffice.tw -> aioffice.com.tw
```

### 2.3 Product Domain Admin UI

Implemented read-only page:

```text
/product-domains
```

Current UI supports:

- Full product tree display.
- Search by domain / product / suite.
- Role filter:
  - all
  - official
  - redirect
  - campaign
  - infra
  - reserved
- Summary cards:
  - suite count
  - product count
  - domain count
  - official count
  - redirect count
  - campaign count
- Read-only validation status.
- Redirect Plan preview section.

### 2.4 Product Domain APIs

Implemented read-only APIs:

```text
GET /api/product-domains
GET /api/product-domains/lookup?domain=...
GET /api/product-domains/validate
GET /api/product-domains/redirect-plan
```

Supported filters:

```text
role
suite
product
q
```

### 2.5 Redirect Plan

Redirect Plan is generated only from the catalog. It does not connect to Cloudflare and does not modify DNS, SSL, redirect rules, or Nginx.

Rules:

- `official` domains do not generate redirect rules.
- `redirect` domains generate source -> target.
- `campaign` domains can generate source -> target, but are marked as campaign.
- Brand Hub redirect is included:
  - `aioffice.tw -> aioffice.com.tw`
- Default redirect type is `301`.

Each plan row includes:

```text
source_domain
target_domain
role
product
suite
brand
redirect_type
status
notes
```

### 2.6 Redirect Plan Export Templates

Implemented read-only export APIs:

```text
GET /api/product-domains/redirect-plan/export?format=json
GET /api/product-domains/redirect-plan/export?format=csv
GET /api/product-domains/redirect-plan/export?format=nginx
GET /api/product-domains/redirect-plan/export?format=cloudflare-bulk
```

Export formats:

- JSON: complete redirect plan, summary, validation.
- CSV: analyst-friendly tabular export.
- Nginx: server block template only.
- Cloudflare Bulk JSON: JSON array for future manual/API workflow.

Important: export templates are not applied automatically.

### 2.7 Validation and Tests

Implemented tests in:

```text
tests/test_product_domains.py
```

Current test coverage validates:

- Catalog validation succeeds.
- Each product has exactly one official domain.
- Official domains are unique.
- Redirect domains have target domains.
- Unknown lookup returns 404.
- Filters work for role / suite / q.
- Redirect plan excludes official domains.
- Redirect plan includes:
  - `crmai.tw -> aicrm.com.tw`
  - `aioffice.tw -> aioffice.com.tw`
  - `aiad.fun -> aiad.com.tw`
- Redirect plan exports work for JSON / CSV / Nginx / Cloudflare bulk.
- Unknown export format returns 400.
- Validation failure blocks export.

Latest verification:

```powershell
python -m py_compile app.py services/product_domains.py
python -m unittest tests.test_product_domains
git diff --check
```

Result:

```text
31 tests OK
```

### 2.8 Cloudflare Zone and Nameserver Onboarding

For the current 60-domain priority set:

- Cloudflare zones exist: 60
- Cloudflare status active: 60
- Nameserver status active: 60

Verified report path on NAS:

```text
/volume1/docker/devpilot/scripts/cloudflare_batch/cloudflare-active-verify-priority.csv
```

Actions not performed in this step:

- DNS record creation/update
- SSL mode update
- Redirect rule creation
- Nginx config deployment
- Website deployment

## 3. Current Website / Domain Strategy

### 3.1 Brand Hub

```text
aioffice.com.tw
```

Purpose:

- Main AI Office umbrella entry.
- Brand explanation.
- Suite navigation.
- Product discovery.
- Conversion hub.

Should not be treated as a normal single product site.

### 3.2 Product Official Domains

Each product gets one official website domain. This is where product-specific landing pages, pricing, lead capture, and SEO should focus.

Examples:

```text
AICRM -> aicrm.com.tw
AIAD -> aiad.com.tw
AIImage -> aiimage.com.tw
AIShopping -> aishopping.com.tw
TruckAI -> truckai.com.tw
```

### 3.3 Redirect Domains

Redirect domains are defensive, alternate, typo/brand-order, or `.tw` / `.com.tw` pairings. They should generally redirect to the official product domain.

Examples:

```text
crmai.tw -> aicrm.com.tw
aiad.tw -> aiad.com.tw
shopai.tw -> aishopping.com.tw
truckai.net -> truckai.com.tw
```

### 3.4 Campaign Domains

Campaign domains are marketing assets and may redirect to official product domains unless a campaign microsite is explicitly approved.

Current example:

```text
aiad.fun -> aiad.com.tw
```

### 3.5 Infra / Reserved Domains

The system supports `infra` and `reserved`, but the current catalog is primarily official / redirect / campaign. Future infrastructure domains should be explicitly tagged instead of being mixed into product websites.

## 4. Not Yet Completed

### 4.1 Production Deployment of Latest Product Domain UI

The current product-domain features are implemented in the repo working tree. A controlled deployment phase is still needed before assuming production users can access the latest UI and APIs.

Pending:

- Commit, if desired.
- Controlled deploy of:
  - `app.py`
  - `services/product_domains.py`
  - `templates/product_domains.html`
  - `templates/base.html`
  - `AGENTS.md` if documentation should be deployed/copied
  - tests are not deployed to production runtime unless project practice requires it.

### 4.2 DNS Records

Cloudflare zones and nameservers are active, but product DNS records are not yet configured by automation.

Pending decisions:

- Main target for official product domains.
- Whether `@` should CNAME/A/AAAA to a hosting platform, reverse proxy, or static hosting.
- Whether each product needs:
  - `www`
  - `app`
  - `api`
  - admin/internal subdomains

### 4.3 SSL Mode

SSL mode has not been updated by the batch tool in this architecture phase.

Pending decisions:

- Cloudflare SSL mode: Full vs Full strict.
- Origin certificate strategy.
- NAS / reverse proxy certificate ownership.

### 4.4 Redirect Rules

Redirect Plan and exports exist, but rules are not applied.

Pending decisions:

- Use Cloudflare Redirect Rules, Bulk Redirects, Page Rules, or Nginx.
- Whether campaign domains use immediate redirect or a temporary landing page.
- Whether `www.source-domain` should also redirect for every source domain.

### 4.5 Website Content Architecture

The product-domain model is ready, but website content architecture still needs analyst/product decisions.

Pending:

- Brand Hub sitemap.
- Suite pages.
- Product landing page templates.
- Cross-linking strategy between Brand Hub and product official domains.
- Canonical URL policy.
- SEO title/meta conventions.
- Analytics and conversion tracking.

### 4.6 Product Module Expansion

Most products currently use the default module:

```text
Public Web
```

Future expansion may add modules such as:

- App Console
- API Endpoint
- Documentation
- Admin Portal
- Demo / Sandbox

These should be modeled explicitly instead of adding random domains ad hoc.

### 4.7 Role Coverage

Current catalog uses:

- official
- redirect
- campaign

Roles supported but not heavily populated yet:

- infra
- reserved

Analyst review should decide which domains should be reclassified as `infra` or `reserved`.

## 5. Analyst Review Questions

Recommended questions for the analyst:

1. Does each Product official domain match the intended brand and market positioning?
2. Are there products that should be grouped differently under another Suite?
3. Should `shopai.com.tw` remain a redirect to `aishopping.com.tw`, or should the official product name become ShopAI?
4. Should `aiad.fun` redirect immediately, or remain available for campaign landing pages?
5. Which domains should be `reserved` instead of redirect?
6. Which domains are infrastructure endpoints rather than public marketing sites?
7. What should `aioffice.com.tw` contain as the Brand Hub sitemap?
8. Should every official product domain get its own landing page now, or should rollout be staged by Suite?
9. What is the canonical SEO policy between `.tw`, `.com.tw`, and `.net.tw` variants?
10. Should redirects preserve path using `$request_uri` / Cloudflare preserve path?

## 6. Recommended Next Phases

### Phase A: Analyst Review Freeze

Review and approve:

- Suite grouping.
- Product names.
- Official domains.
- Redirect/campaign classifications.
- Brand Hub sitemap.

No code or DNS changes required.

### Phase B: DNS Plan Dry-run

Generate DNS plan only:

- `@`
- `www`
- optional `app`
- optional `api`

No Cloudflare write until manually approved.

### Phase C: Redirect Rule Dry-run

Use the current Redirect Plan exports to compare options:

- Cloudflare Bulk JSON
- Nginx template
- CSV review

No redirect rule write until approved.

### Phase D: Brand Hub Information Architecture

Design:

- Home page sections.
- Suite navigation.
- Product cards.
- Lead capture.
- Cross-linking and canonical URLs.

### Phase E: Product Landing Template

Create a reusable official product landing page template before building each product page individually.

## 7. Safety Notes

Current product-domain architecture work is read-only.

It must not be assumed to perform:

- Cloudflare DNS writes.
- SSL changes.
- Redirect rule writes.
- Registrar nameserver changes.
- Nginx config writes.
- Production deployment.
- Website file generation.

Those require separate, explicit phases and approvals.
