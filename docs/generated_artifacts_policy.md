# Generated Artifacts Policy

Generated: 2026-05-11

This policy covers local/generated artifacts discovered after the Product Domain deploy package was committed. It does not authorize deployment, Cloudflare writes, DNS writes, SSL changes, redirect rule writes, Nginx changes, backend restart, DB migration, or git push.

## Scope

Reviewed files and directories:

- `cloudflare-result.csv`
- `domains.csv`
- `nameserver-registrar-dry-run.csv`
- `nameserver-update-list.csv`
- `nameserver-update-result.csv`
- `backups/*`
- `.gitignore`
- `docs/`

## Classification

Generated report artifacts:

- `cloudflare-result.csv`
- `nameserver-registrar-dry-run.csv`
- `nameserver-update-list.csv`
- `nameserver-update-result.csv`

Local runtime backup artifacts:

- `backups/*`

Manual review item:

- `domains.csv`

## Policy

Runtime-generated backups must not be committed. Keep them local only, or delete them locally after confirming they are no longer needed.

Cloudflare result CSV files are ignored by default. They may be committed only after manual review, redaction if needed, and relocation to a documentation/report path such as:

```text
docs/reports/
```

Registrar and nameserver dry-run reports may be preserved as governance evidence only if they are reviewed for secrets and moved to `docs/reports/` with a clear date, source, and purpose. They should not be committed from the repository root.

`domains.csv` is not automatically treated as generated output. If it is the human-maintained source of truth for batch tooling, handle it in a separate Cloudflare tooling commit after encoding and data review. If it is only a batch input/output scratch file, keep it local or move a reviewed copy into `docs/reports/`.

All CSV files that contain execution results, external account status, Cloudflare zone/status data, nameserver status, or registrar workflow results are report artifacts. Do not commit them with tooling code unless they have been intentionally reviewed and relocated.

## Secret Review

Do not print or commit token, secret, API key, password, authorization header, cookie, session, or private key values.

The reviewed root CSV reports did not produce sensitive keyword matches during this policy preparation. The local `backups/*` files did produce keyword matches for token/authorization/API key/secret-like terms and must not be committed without manual review. The matches were treated as sensitive metadata; raw matched lines were not printed.

## Git Ignore Policy

Ignored by default:

```text
backups/
cloudflare-result.csv
nameserver-registrar-dry-run.csv
nameserver-update-list.csv
nameserver-update-result.csv
```

Not ignored by this policy:

```text
domains.csv
```

`domains.csv` remains visible so a future Cloudflare tooling review can decide whether it is a source-of-truth input file, a local scratch file, or a report artifact.

## Future Commit Guidance

Suggested separate commit packages:

1. Generated artifacts policy:
   - `.gitignore`
   - `docs/generated_artifacts_policy.md`

2. Cloudflare batch tooling after safety review:
   - Cloudflare CLI/tooling files
   - reviewed README changes
   - reviewed dependency changes
   - reviewed `domains.csv` only if it is source-of-truth input

3. Optional report archive after manual review:
   - reviewed and redacted CSV reports under `docs/reports/`

Do not mix generated artifacts with production deploy packages.
