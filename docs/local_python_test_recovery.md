# Local Python Test Recovery

Generated: 2026-05-11

This document records the local Python/test environment recovery check. It is documentation only. No product code, templates, tests, database schema, deployment target, DNS, SSL, Cloudflare, Nginx, redirect rule, backend process, git remote, token, or secret was changed.

## 1. Problem Summary

The Product Domain UI/API controlled deploy preparation is complete, but local Python validation cannot currently run from this workstation.

Required validation commands:

```powershell
python -m py_compile app.py services/product_domains.py
python -m unittest tests.test_product_domains
```

Current result:

- `python` is not available on `PATH`.
- `python3` is not available on `PATH`.
- `py` launcher exists at `C:\Windows\py.exe`, but reports that no installed Python is available.
- The existing `.venv` is broken because it points to a missing Python installation.
- Docker project files exist, but the local `docker` command is not available on this workstation.

## 2. Current Failure Cause

The repo contains an existing virtual environment config:

```text
.venv\pyvenv.cfg
```

It points to:

```text
C:\Users\chaokun\AppData\Local\Programs\Python\Python314\python.exe
```

That interpreter path is not available, so:

```powershell
.\.venv\Scripts\python.exe -m py_compile app.py services/product_domains.py
```

fails before Python starts.

Environment command results from this check:

```text
py --version      -> No installed Python found
python --version  -> command not found
python3 --version -> command not found
where python      -> not found
where py          -> C:\Windows\py.exe
where python3     -> not found
docker --version  -> command not found
```

## 3. Dependency / Runtime Files Detected

Detected:

- `requirements.txt`
- `Dockerfile`
- `docker-compose.yml`
- `README.md`

README variants:

- `README.md`

Not detected in this repo root during the check:

- `pyproject.toml`
- `Pipfile`
- `poetry.lock`
- `uv.lock`
- `runtime.txt`

Dependency management appears to be `requirements.txt` based.

Runtime hints:

- `Dockerfile` uses `python:3.12-slim`.
- `requirements.txt` includes Flask, python-dotenv, cryptography, requests, pandas, and dnspython.
- README includes a local setup pattern using `python -m venv .venv`, `.venv\Scripts\activate`, and `pip install -r requirements.txt`.

## 4. Recommended Fix

Install a normal local Python interpreter, preferably Python 3.12 to match the Dockerfile runtime.

Recommended source:

- Official Python 3.12 Windows installer from python.org, with the Python launcher enabled.

After Python is installed, use the `py -3.12` launcher selector to recreate the repo virtual environment.

Do not repair the current `.venv` by editing `pyvenv.cfg` manually. Recreate it instead.

Do not install dependencies globally unless that is an intentional workstation policy. Prefer a repo-local virtual environment.

Before recreating `.venv`, remove the broken local virtual environment only after confirming the current directory is the repo root. This removes local environment files only; it must not touch product code, templates, tests, data, uploads, backups, `.env`, or database files.

## 5. Recommended `.venv` Rebuild Commands

Run these from the repo root in Windows PowerShell:

```powershell
cd E:\Ai-project\devpilot_project_manager_v1\devpilot_project_manager
Get-Location

if (Test-Path .\.venv) {
    Remove-Item -Recurse -Force .\.venv
}

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt

python -m py_compile app.py services/product_domains.py
python -m unittest tests.test_product_domains
git diff --check
```

If PowerShell blocks activation scripts, either allow scripts for the current process:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

or call the virtual environment interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m py_compile app.py services/product_domains.py
.\.venv\Scripts\python.exe -m unittest tests.test_product_domains
```

## 6. Safety Reminder

Do not commit `.venv`.

The README already notes that `.venv` should be excluded from repo/runtime import workflows. Keep virtual environment files local to the workstation.

Do not print, export, commit, or paste tokens or secrets while recovering the local Python environment. Do not inspect or output `.env` values unless a separate secret-handling task explicitly requires it.

Before committing environment recovery documentation, review:

```powershell
git status --short
git diff --check
```

## 7. Verification Commands After Recovery

After Python 3.12 and the virtual environment are restored, run:

```powershell
py -3.12 --version
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m py_compile app.py services/product_domains.py
.\.venv\Scripts\python.exe -m unittest tests.test_product_domains
git diff --check
```

For the Product Domain controlled deploy readiness specifically, also verify:

```powershell
.\.venv\Scripts\python.exe -m py_compile app.py services/product_domains.py
.\.venv\Scripts\python.exe -m unittest tests.test_product_domains
```

Expected result after recovery:

- Python version is available.
- `py_compile` succeeds.
- `tests.test_product_domains` passes.
- `git diff --check` passes, aside from any existing CRLF warnings.
