# Registrar Nameserver Automation Workflow

This workflow connects Cloudflare zone creation with registrar-side nameserver updates.

## Safety Mode

Default mode is dry-run. Dry-run may open the registrar dashboard, search domains, and locate the nameserver settings page, but it must not fill fields or save changes.

Never automate these actions:

- registrant/contact changes
- payment changes
- domain purchases
- domain deletion
- domain transfer
- auto-renewal changes
- paid add-on activation
- domains not listed in `nameserver-update-list.csv`

Real registrar nameserver updates require separate approval. For real execution, stop before every Save/Confirm action and wait for human confirmation.

## Step 1: Cloudflare Zone Setup

Dry-run first:

```bash
python cf_batch.py all
```

Real zone creation after review:

```bash
python cf_batch.py add-zone --apply --confirm-real-write
```

`add-zone` writes:

- `cloudflare-result.csv`
- `nameserver-update-list.csv`

`nameserver-update-list.csv` columns:

```csv
domain,cloudflare_nameserver_1,cloudflare_nameserver_2,status,note
```

Only use registrar automation after the Cloudflare nameserver columns contain real values like `name.ns.cloudflare.com`.

## Step 2: Registrar Browser Dry-run

Use a logged-in Chrome session and the registrar domain management page.

For each `pending_nameserver_update` row:

1. Search the domain.
2. Open the domain management page.
3. Find Nameserver / DNS server / Name server settings.
4. Record current nameservers.
5. Confirm whether custom nameserver mode is available.
6. Do not fill fields.
7. Do not save.

Dry-run report columns:

```csv
domain,found_domain,found_nameserver_page,current_ns,target_ns_1,target_ns_2,status,note
```

Suggested statuses:

- `ready_for_manual_update`
- `domain_not_found`
- `nameserver_page_not_found`
- `requires_2fa`
- `manual_check_required`
- `blocked_by_registrar_ui`

## Step 3: Registrar Real Update

For each domain:

1. Show the current nameservers and target Cloudflare nameservers.
2. Fill target nameserver 1 and nameserver 2.
3. Stop before Save/Confirm.
4. Continue only after explicit human confirmation.
5. Save and record the result.

## Step 4: Verification

After registrar updates:

```bash
python cf_batch.py verify --apply
```

`verify --apply` is read-only against Cloudflare, but it still uses a token and writes local report CSV files.

`verify` writes:

- `cloudflare-result.csv`
- `nameserver-update-list.csv`
- `nameserver-update-result.csv`

`nameserver-update-result.csv` columns:

```csv
domain,old_nameservers,new_nameservers,cloudflare_nameserver_1,cloudflare_nameserver_2,status,verified_at,error_message
```

Statuses:

- `nameserver_ok`
- `pending_dns_propagation`
- `failed`
- `manual_check_required`
