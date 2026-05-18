# Product Domain Launch Planning Matrix

Date: 2026-05-18
Audience: analyst, product planning, SEO planning, operations planning
Status: planning draft, no implementation changes

## Purpose

This document turns the current DevPilot Product Domain catalog into a launch planning matrix for analyst review.

It is a planning document only. It does not execute DNS, redirects, SSL, Nginx, Cloudflare, R2, registrar, deployment, hosting, or production setting changes.

## Source Inputs

- `services/product_domains.py`
- `docs/devpilot_architecture_progress_inventory_2026-05-18.md`
- Product Domain admin/read APIs:
  - `/admin/product-domain-launch-plan`
  - `/api/admin/product-domain-launch-plan`
  - `/product-domains`
  - `/api/product-domains`
  - `/api/product-domains/lookup?domain=...`
  - `/api/product-domains/redirect-plan`
  - `/api/product-domains/redirect-plan/export`

## Current Catalog Summary

```text
Brand: AI Office
Brand key: ai_office
Brand hub official domain: aioffice.com.tw
Brand hub redirect domain: aioffice.tw
Suites: 7
Products: 26
Domains: 60
Official domains: 27
Redirect domains: 32
Campaign domains: 1
Infra domains: 0
Reserved domains: 0
Catalog validation: ok
```

## Planning Rules

- Preserve the fixed hierarchy: `Brand -> Suite -> Product -> Module -> Domain`.
- Treat `aioffice.com.tw` as the Brand Hub official domain, not as an ordinary product site.
- Treat `aioffice.tw` as the Brand Hub redirect domain.
- Each Product keeps exactly one official domain.
- Redirect domains remain redirects unless an analyst explicitly reclassifies them.
- Campaign domains remain marketing/event domains and require separate campaign decisions.
- Launch waves are planning fields only. This draft does not decide the final launch order.
- All launch wave values are `pending_analysis` until product, SEO, and operations owners decide priorities.

## Launch Wave Field Definitions

| Field | Meaning |
| --- | --- |
| `launch_wave` | Analyst-owned sequencing field. Default: `pending_analysis`. |
| `launch_readiness` | Planning readiness only; not technical deployment state. |
| `canonical_action` | Draft canonical treatment for official, redirect, campaign, infra, or reserved domains. |
| `analyst_decision_needed` | Product/SEO/operations decision needed before execution planning. |
| `execution_allowed` | Always `false` in this document. |

## Dashboard/API Shape

The read-only dashboard/API should expose the launch planning matrix without executing infrastructure changes:

```text
GET /admin/product-domain-launch-plan
GET /api/admin/product-domain-launch-plan
```

Required safety fields:

- `read_only: true`
- `execution_allowed: false`
- `dns_write_enabled: false`
- `cloudflare_write_enabled: false`
- `nginx_write_enabled: false`
- `ssl_write_enabled: false`
- `deploy_enabled: false`

Every product row defaults to:

```text
launch_wave: pending_analysis
launch_readiness: catalog_ready
canonical_action: official_domain_canonical
execution_allowed: false
```

## Brand Hub Matrix

| Brand | Scope | Domain | Role | Target | Launch wave | Canonical action | Analyst decision needed | Execution allowed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AI Office | Brand Hub | aioffice.com.tw | official | - | pending_analysis | Canonical Brand Hub root | Confirm Brand Hub information architecture and primary CTA strategy | false |
| AI Office | Brand Hub | aioffice.tw | redirect | aioffice.com.tw | pending_analysis | Redirect to Brand Hub canonical | Confirm redirect type, path preservation, and tracking requirements | false |

## Product Launch Matrix

| Suite | Product | Module | Official domain | Redirect/campaign domains | Launch wave | Launch readiness | Canonical action | Analyst decision needed | Execution allowed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Business AI | AICRM | Public Web | aicrm.com.tw | crmai.com.tw, crmai.tw | pending_analysis | catalog_ready | Official domain canonical; redirects point to official | Confirm CRM positioning, ICP, and whether CRMAI redirect names support search intent | false |
| Business AI | AIERP | Public Web | aierp.com.tw | aierp.tw | pending_analysis | catalog_ready | Official domain canonical; redirect points to official | Confirm ERP launch priority and content depth required | false |
| Business AI | AIHRM | Public Web | aihrm.com.tw | aihrm.tw, aihrm.net | pending_analysis | catalog_ready | Official domain canonical; redirects point to official | Confirm HRM product scope and `.net` redirect treatment | false |
| Business AI | AISales | Public Web | aisales.com.tw | - | pending_analysis | catalog_ready | Official domain canonical | Confirm whether a companion `.tw` or campaign domain is needed | false |
| Marketing AI | WebAI | Public Web | webai.tw | webai.net.tw | pending_analysis | catalog_ready | Official domain canonical; redirect points to official | Confirm whether `.tw` remains canonical versus `.com.tw` acquisition need | false |
| Marketing AI | AIAD | Public Web | aiad.com.tw | aiad.tw, aiad.net.tw, aiad.fun campaign | pending_analysis | catalog_ready | Official domain canonical; redirects/campaign point to official | Confirm campaign role for `aiad.fun` and ad-tech positioning | false |
| Marketing AI | AIKOL | Public Web | aikol.com.tw | aikol.tw, kolai.tw | pending_analysis | catalog_ready | Official domain canonical; redirects point to official | Confirm KOL/influencer keyword strategy and `kolai.tw` usage | false |
| Marketing AI | AIImage | Public Web | aiimage.com.tw | aiimage.tw, imageai.com.tw, imageai.tw | pending_analysis | catalog_ready | Official domain canonical; redirects point to official | Confirm image generation positioning and whether ImageAI brand variants stay redirects | false |
| Commerce AI | AIShopping | Public Web | aishopping.com.tw | aishopping.tw, shopai.com.tw, shopai.tw | pending_analysis | catalog_ready | Official domain canonical; redirects point to official | Confirm commerce/storefront product scope and ShopAI naming treatment | false |
| Commerce AI | AIPOS | Public Web | aipos.tw | - | pending_analysis | catalog_ready | Official domain canonical | Confirm whether POS product should use `.tw` canonical long term | false |
| Service AI | AIBooking | Public Web | aibooking.tw | bookingai.com.tw, bookingai.tw | pending_analysis | catalog_ready | Official domain canonical; redirects point to official | Confirm appointment/booking vertical scope and BookingAI keyword plan | false |
| Service AI | LiveAI | Public Web | liveai.com.tw | liveai.tw, ailive.tw | pending_analysis | catalog_ready | Official domain canonical; redirects point to official | Confirm live chat/live commerce/live stream interpretation | false |
| Service AI | AIChat | Public Web | aichat.tw | aichat.net.tw | pending_analysis | catalog_ready | Official domain canonical; redirect points to official | Confirm AI chat product boundaries versus Brand Hub assistant positioning | false |
| Industry AI | TruckAI | Public Web | truckai.com.tw | truckai.tw, truckai.net | pending_analysis | catalog_ready | Official domain canonical; redirects point to official | Confirm trucking/logistics vertical priority and `.net` treatment | false |
| Industry AI | CarAI | Public Web | carai.tw | - | pending_analysis | catalog_ready | Official domain canonical | Confirm automotive vertical scope and missing redirect needs | false |
| Industry AI | CleanAI | Public Web | cleanai.com.tw | cleanai.tw | pending_analysis | catalog_ready | Official domain canonical; redirect points to official | Confirm cleaning services SaaS scope and vertical launch priority | false |
| Industry AI | MoveAI | Public Web | moveai.com.tw | moveai.tw | pending_analysis | catalog_ready | Official domain canonical; redirect points to official | Confirm moving/logistics service scope | false |
| Industry AI | FixAI | Public Web | fixai.com.tw | fixai.tw | pending_analysis | catalog_ready | Official domain canonical; redirect points to official | Confirm repair/maintenance service scope | false |
| Creative AI | PaintAI | Public Web | paintai.com.tw | paintai.tw, paintai.net | pending_analysis | catalog_ready | Official domain canonical; redirects point to official | Confirm painting/design vertical and `.net` treatment | false |
| Creative AI | PrintAI | Public Web | printai.com.tw | printai.tw | pending_analysis | catalog_ready | Official domain canonical; redirect points to official | Confirm print-shop/productization priority | false |
| Infrastructure AI | AISystem | Public Web | aisystem.com.tw | aisystem.tw | pending_analysis | catalog_ready | Official domain canonical; redirect points to official | Confirm whether AISystem is product marketing or internal platform story | false |
| Infrastructure AI | AICenter | Infrastructure Endpoint | aicenter.com.tw | - | pending_analysis | catalog_ready | Official domain canonical for infrastructure endpoint | Confirm whether this should be public marketing, admin portal, or reserved infrastructure | false |
| Infrastructure AI | AIServer | Infrastructure Endpoint | aiserver.com.tw | - | pending_analysis | catalog_ready | Official domain canonical for infrastructure endpoint | Confirm whether this should expose public content or stay infrastructure-only | false |
| Infrastructure AI | AITV | Public Web | aitv.com.tw | - | pending_analysis | catalog_ready | Official domain canonical | Confirm product category and launch dependency on video stack | false |
| Infrastructure AI | AIVideo | Public Web | aivideo.com.tw | - | pending_analysis | catalog_ready | Official domain canonical | Confirm overlap with AITV and content/video product boundaries | false |
| Infrastructure AI | OEMAI | Public Web | oemai.com.tw | oemai.tw | pending_analysis | catalog_ready | Official domain canonical; redirect points to official | Confirm OEM/channel partner positioning | false |

## Suite-Level Planning View

| Suite | Product count | Primary planning question | Launch wave |
| --- | ---: | --- | --- |
| Business AI | 4 | Which operational SaaS product has the clearest buyer and shortest content path? | pending_analysis |
| Marketing AI | 4 | Which marketing product should demonstrate lead-gen value first? | pending_analysis |
| Commerce AI | 2 | Should commerce launch as storefront/e-commerce AI, POS AI, or a combined narrative? | pending_analysis |
| Service AI | 3 | Which service workflow has the strongest near-term customer story? | pending_analysis |
| Industry AI | 5 | Which vertical has evidence of demand, assets, or customer pipeline? | pending_analysis |
| Creative AI | 2 | Should creative products launch as vertical SaaS or template/gallery products? | pending_analysis |
| Infrastructure AI | 6 | Which infrastructure names are public products versus platform/admin endpoints? | pending_analysis |

## Analyst Decisions Needed

1. Confirm first-wave launch candidates.
2. Confirm whether every official product domain should get a standalone landing page.
3. Confirm whether the Brand Hub should route users by suite, use case, industry, or product grid.
4. Confirm canonical preference for `.com.tw` versus `.tw` when both exist.
5. Confirm whether `.net`, `.net.tw`, and alternate word-order domains remain redirects.
6. Confirm campaign handling for `aiad.fun`.
7. Confirm whether infrastructure products are public products, internal/admin surfaces, or reserved endpoints.
8. Confirm whether `www` should redirect for every canonical domain.
9. Confirm path preservation and tracking policy for redirects.
10. Confirm which products need content, demo, lead form, pricing, docs, or login surfaces before launch.
11. Confirm which launch waves require legal/trademark review.
12. Confirm minimum safe production launch set.

## Non-Execution Statement

This matrix is not an execution plan.

It does not:

- create DNS records
- change Cloudflare settings
- create Cloudflare redirect rules
- write Nginx config
- change SSL mode or certificates
- change registrar nameservers
- deploy websites
- upload files to R2
- create one website per domain
- modify production settings

Execution requires a later explicit phase with dry-runs, approval gates, rollback notes, and operator confirmation.
