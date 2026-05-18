# Product Domain Canonical Strategy Draft

Date: 2026-05-18
Audience: analyst, SEO planning, product planning, operations planning
Status: draft strategy, pending analyst decisions

## Purpose

This document proposes a canonical-domain strategy for the AI Office Product Domain catalog without executing redirects, DNS, SSL, Nginx, Cloudflare, R2, hosting, deployment, or production setting changes.

It is based on the fixed product-domain architecture:

```text
Brand -> Suite -> Product -> Module -> Domain
```

Related read-only planning surfaces:

```text
GET /admin/product-domain-launch-plan
GET /api/admin/product-domain-launch-plan
```

These surfaces display canonical strategy metadata for analyst review only. They do not execute DNS, redirect, SSL, Nginx, Cloudflare, R2, registrar, deploy, or production changes.

## Brand Canonical Rule

AI Office uses one Brand Hub canonical domain:

```text
aioffice.com.tw
```

Brand Hub redirect:

```text
aioffice.tw -> aioffice.com.tw
```

Strategy draft:

- Use `aioffice.com.tw` as the root brand canonical for the AI Office umbrella.
- Use `aioffice.tw` only as a redirect alias unless analysts approve a separate campaign use.
- Do not model `aioffice.com.tw` as an ordinary product website.
- Do not turn every owned domain into an independent website by default.

## Product Canonical Rule

Each Product has exactly one official domain in the catalog. That official domain is the draft canonical product domain.

Redirect, campaign, infra, and reserved domains should not be indexed as separate product websites by default.

Draft rule:

```text
Product official domain = canonical product domain
Product redirect domain = 301 redirect to product official domain
Campaign domain = campaign treatment pending analyst decision, usually redirects to official product domain
Infrastructure endpoint = public/private treatment pending analyst decision
Reserved domain = no public launch until explicitly approved
```

## Current Official Domain Canonicals

| Suite | Product | Draft canonical domain | Notes |
| --- | --- | --- | --- |
| Business AI | AICRM | aicrm.com.tw | Redirect variants exist for CRMAI naming. |
| Business AI | AIERP | aierp.com.tw | `.tw` alias redirects to canonical. |
| Business AI | AIHRM | aihrm.com.tw | `.tw` and `.net` aliases redirect to canonical. |
| Business AI | AISales | aisales.com.tw | No redirect alias currently in catalog. |
| Marketing AI | WebAI | webai.tw | `.net.tw` alias redirects to canonical. |
| Marketing AI | AIAD | aiad.com.tw | Includes `aiad.fun` as campaign domain. |
| Marketing AI | AIKOL | aikol.com.tw | Includes `kolai.tw` alternate naming alias. |
| Marketing AI | AIImage | aiimage.com.tw | Includes ImageAI brand-order aliases. |
| Commerce AI | AIShopping | aishopping.com.tw | Includes ShopAI aliases. |
| Commerce AI | AIPOS | aipos.tw | No redirect alias currently in catalog. |
| Service AI | AIBooking | aibooking.tw | BookingAI aliases redirect to canonical. |
| Service AI | LiveAI | liveai.com.tw | Includes AI Live naming alias. |
| Service AI | AIChat | aichat.tw | `.net.tw` alias redirects to canonical. |
| Industry AI | TruckAI | truckai.com.tw | `.tw` and `.net` aliases redirect to canonical. |
| Industry AI | CarAI | carai.tw | No redirect alias currently in catalog. |
| Industry AI | CleanAI | cleanai.com.tw | `.tw` alias redirects to canonical. |
| Industry AI | MoveAI | moveai.com.tw | `.tw` alias redirects to canonical. |
| Industry AI | FixAI | fixai.com.tw | `.tw` alias redirects to canonical. |
| Creative AI | PaintAI | paintai.com.tw | `.tw` and `.net` aliases redirect to canonical. |
| Creative AI | PrintAI | printai.com.tw | `.tw` alias redirects to canonical. |
| Infrastructure AI | AISystem | aisystem.com.tw | Public product versus platform story needs analyst decision. |
| Infrastructure AI | AICenter | aicenter.com.tw | Infrastructure endpoint treatment needs analyst decision. |
| Infrastructure AI | AIServer | aiserver.com.tw | Infrastructure endpoint treatment needs analyst decision. |
| Infrastructure AI | AITV | aitv.com.tw | Product/category boundary needs analyst decision. |
| Infrastructure AI | AIVideo | aivideo.com.tw | Overlap with AITV needs analyst decision. |
| Infrastructure AI | OEMAI | oemai.com.tw | `.tw` alias redirects to canonical. |

## Redirect Strategy Draft

Default redirect behavior for product redirects:

```text
source redirect domain -> product official domain
```

Default redirect behavior for Brand Hub redirects:

```text
source redirect domain -> aioffice.com.tw
```

Open redirect details for later execution planning:

- HTTP status: likely 301, but final choice is pending.
- Path preservation: pending.
- Query string preservation: pending.
- UTM and analytics policy: pending.
- `www` handling: pending.
- Cloudflare Redirect Rules versus Bulk Redirects versus Nginx: pending.

## Campaign Domain Strategy Draft

Current campaign domain:

```text
aiad.fun -> aiad.com.tw
```

Draft options for analyst review:

| Option | Description | Tradeoff |
| --- | --- | --- |
| Campaign redirect | Keep `aiad.fun` as a campaign alias that redirects to `aiad.com.tw`. | Simple, low maintenance, less campaign-specific SEO surface. |
| Campaign landing page | Use `aiad.fun` for a time-boxed event or paid campaign landing page. | More flexible marketing path, but needs content ownership, analytics, and expiry policy. |
| Reserved alias | Hold `aiad.fun` without public launch until campaign plan exists. | Avoids premature launch, but leaves owned domain unused. |

No option should be executed without a later explicit campaign phase.

## Infrastructure Endpoint Strategy Draft

Infrastructure AI includes products/modules that may be public products, operational endpoints, or reserved platform names:

- AISystem: `aisystem.com.tw`
- AICenter: `aicenter.com.tw`
- AIServer: `aiserver.com.tw`
- AITV: `aitv.com.tw`
- AIVideo: `aivideo.com.tw`
- OEMAI: `oemai.com.tw`

Analyst decisions needed:

- Which names are public marketing products?
- Which names are internal/admin/infrastructure endpoints?
- Which names should remain reserved until platform architecture is settled?
- Should public infrastructure product pages live under product domains or under the Brand Hub?
- Do any of these require access control before public launch?

## Canonical Metadata Draft

When product pages eventually exist, recommended metadata policy:

- Canonical URL should point to the official product domain.
- Redirect aliases should not emit their own canonical pages unless converted into campaign pages.
- Brand Hub should link to products by official domain or canonical product path.
- Product pages should link back to the Brand Hub.
- If a product is not ready, the official domain should not be silently launched as a thin duplicate page.

## Analyst Decisions Needed

1. Confirm the canonical domain for products whose official domain is `.tw` rather than `.com.tw`.
2. Confirm whether alternate-name domains should always redirect or sometimes become campaign pages.
3. Confirm the universal `www` policy.
4. Confirm whether product canonical URLs should preserve language paths such as `/zh-TW/`.
5. Confirm whether the Brand Hub should host suite-level pages before product-level domains launch.
6. Confirm noindex/robots strategy for prelaunch or placeholder pages.
7. Confirm analytics source attribution for redirect domains.
8. Confirm whether campaign domains have expiry dates and owners.
9. Confirm infrastructure endpoint access-control policy.
10. Confirm execution technology only after strategy approval: Cloudflare, Nginx, app-level redirect, or registrar forwarding.

## Non-Execution Statement

This canonical strategy is a planning artifact only.

It does not:

- create or edit DNS records
- create or edit redirect rules
- change Cloudflare settings
- change Nginx config
- change SSL settings or certificates
- change registrar nameservers
- deploy applications
- upload R2 assets
- modify production settings
- perform domain ownership verification

Any execution must be handled in a later explicit phase with dry-run output, approval gates, rollback planning, and operator confirmation.
