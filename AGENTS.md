# DevPilot Product Domain Rules

This repository uses a fixed AI Office product-domain architecture. Future Codex work must preserve these rules unless the user explicitly requests a new architecture phase.

## Product Domain Architecture

Use this hierarchy:

```text
Brand -> Suite -> Product -> Module -> Domain
```

- `Brand` is the top-level company or umbrella brand.
- `Suite` groups related products by market or capability.
- `Product` is the sellable product identity.
- `Module` is a product surface or capability, such as `Public Web` or `Infrastructure Endpoint`.
- `Domain` is an internet domain assigned to the brand hub or to a product module.

The current implementation lives in:

```text
services/product_domains.py
```

The admin UI and read-only APIs are:

```text
/product-domains
/api/product-domains
/api/product-domains/lookup?domain=...
```

## AI Office Brand Hub

The AI Office brand is:

```text
Brand: AI Office
Brand key: ai_office
Brand hub: aioffice.com.tw
```

Rules:

- `aioffice.com.tw` is the Brand Hub official domain.
- `aioffice.tw` is the Brand Hub redirect domain.
- Do not model `aioffice.com.tw` as an ordinary product website.
- Do not turn every owned domain into an independent website.

## Domain Roles

Every domain must have exactly one role:

```text
official
redirect
campaign
infra
reserved
```

Definitions:

- `official`: The canonical domain for a product or the Brand Hub.
- `redirect`: A domain that forwards to a product official domain or the Brand Hub.
- `campaign`: A marketing or event domain. It may forward to the official product domain.
- `infra`: A domain used for infrastructure, platform, admin, service, or operational endpoints.
- `reserved`: A held or parked domain with no active product website yet.

## Product Official Domain Rules

Each Product must have exactly one `official` domain.

Forbidden:

- Multiple official domains for the same Product.
- Reusing the same official domain across products.
- Treating redirect, campaign, infra, or reserved domains as separate products by default.

## Redirect Rules

Every `redirect` domain must define `target_domain`.

For product redirects:

```text
target_domain = that Product's official domain
```

For Brand Hub redirects:

```text
target_domain = aioffice.com.tw
```

Do not leave redirect targets implicit.

## Catalog Change Checklist

When modifying the product-domain catalog, run:

```powershell
python -m py_compile app.py services/product_domains.py
python -m unittest tests.test_product_domains
git diff --check
```

Also verify:

- The complete product tree can be listed.
- Any domain can be looked up and mapped to its owning Product or Brand Hub.
- Domain role is one of `official`, `redirect`, `campaign`, `infra`, or `reserved`.
- Redirect domains include `target_domain`.
- Official domains are unique.
- Each Product has exactly one official domain.

## Safety Boundary

Product-domain catalog work is read-only model/UI work unless a later phase explicitly allows external changes.

Do not assume catalog edits should:

- Create Cloudflare DNS records.
- Change SSL mode.
- Create redirect rules.
- Change registrar nameservers.
- Deploy websites.
- Create one website per domain.

Those actions require separate, explicit phases.
