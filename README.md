# vps-dashboard

A self-hosted VPS management system for deploying and managing static and dynamic websites across multiple environments, powered by **Caddy** as the web server and **PM2** as the unified process manager — plus a lightweight **read-only dashboard** for monitoring site versions and promotion history.

---

## Overview

This project has two components:

1. **Hosting system** — configuration-driven site management via YAML files, generator scripts, Caddy, and PM2
2. **Dashboard** — a read-only web app that visualises deployed versions and promotion history

**Stack:**
- [Caddy](https://caddyserver.com/) — web server, reverse proxy, automatic SSL, basic auth
- [PM2](https://pm2.keymetrics.io/) — process manager for all processes (Caddy + Next.js + Flask)
- Python 3 — generator, promotion, and scaffolding scripts
- Dashboard — lightweight Flask app (served on a separate port)

---

## Site Types Supported

| Type    | Technology     | Served by             | Managed by      |
|---------|----------------|-----------------------|-----------------|
| Static  | HTML/CSS/JS    | Caddy                 | PM2 (via Caddy) |
| Dynamic | Next.js        | Caddy (reverse proxy) | PM2             |
| Dynamic | Flask (Python) | Caddy (reverse proxy) | PM2             |

---

## Environment Model

Each site runs in up to four environments on separate ports (or subdomains):

```
dev  →  test  →  preprod  →  production
```

---

## Project Structure

```
hosting/
├── sites/                   # One YAML file per website — source of truth
│   ├── my-nextjs-app.yaml
│   ├── my-flask-api.yaml
│   └── my-static-site.yaml
├── auth/                    # Shared bcrypt credential files
│   ├── dev-team.yaml
│   └── stakeholders.yaml
├── create-site.py           # Scaffold a new site YAML with auto port assignment
├── generate-config.py       # Globs sites/ + auth/ → Caddyfile + ecosystem.config.js
├── promote.py               # Promote a site version between environments + log
├── Caddyfile                # Auto-generated — do not edit manually
├── ecosystem.config.js      # Auto-generated — do not edit manually
├── promotion.log            # Append-only promotion audit trail
├── dashboard/               # Read-only status dashboard
│   ├── app.py
│   ├── requirements.txt
│   └── templates/
│       └── index.html
└── docs/
    ├── hosting-architecture.md   # Full hosting system documentation
    └── dashboard-context.md      # Dashboard requirements and context
```

---

## Quick Start

### 1. Create a new site

```bash
# Static site, auto port assignment
python3 create-site.py --id my-site --name "My Site" --type static

# Next.js app with auth on dev/test/preprod
python3 create-site.py \
  --id my-app \
  --name "My App" \
  --type nextjs \
  --auth-dev dev-team \
  --auth-test dev-team \
  --auth-preprod stakeholders \
  --version 1.0.0

# Flask API, dry run first
python3 create-site.py \
  --id my-api \
  --name "My API" \
  --type flask \
  --auth-dev dev-team \
  --dry-run
```

`create-site.py` options:

| Option | Required | Description |
|---|---|---|
| `--id` | ✅ | Site ID and filename (e.g. `my-app`) |
| `--name` | ✅ | Human-readable display name |
| `--type` | ✅ | `static`, `nextjs`, or `flask` |
| `--base-port` | | First port for dev. Auto-detected if omitted |
| `--base-path` | | Root filesystem path. Auto-set if omitted |
| `--auth-dev` | | Auth file name for dev environment |
| `--auth-test` | | Auth file name for test environment |
| `--auth-preprod` | | Auth file name for preprod environment |
| `--version` | | Initial version. Defaults to `0.1.0` |
| `--dry-run` | | Print YAML without writing |

### 2. Generate configs

```bash
python3 generate-config.py
```

Reads all `sites/*.yaml` and `auth/*.yaml`, writes `Caddyfile` and `ecosystem.config.js`.

### 3. Start all processes

```bash
pm2 start ecosystem.config.js
pm2 save
pm2 startup   # auto-start on server reboot
```

### 4. Reload after config changes

```bash
pm2 reload caddy
pm2 reload ecosystem.config.js
```

---

## Site YAML Format

Each site has its own file in `sites/`. The filename must match the `id` field.

```yaml
id: my-nextjs-app
name: My Next.js App
type: nextjs              # static | nextjs | flask
environments:
  dev:
    path: /var/apps/my-nextjs-app/dev
    port: 4000
    version: 0.2.0-dev
    pm2_name: my-nextjs-app-dev
    auth: dev-team        # references auth/dev-team.yaml — optional
  test:
    path: /var/apps/my-nextjs-app/test
    port: 4001
    version: 0.1.5
    pm2_name: my-nextjs-app-test
    auth: dev-team
  preprod:
    path: /var/apps/my-nextjs-app/preprod
    port: 4002
    version: 0.1.4
    pm2_name: my-nextjs-app-preprod
    auth: stakeholders
  production:
    path: /var/apps/my-nextjs-app/prod
    port: 4003
    version: 0.1.4
    pm2_name: my-nextjs-app-prod
    # no auth = public
```

**Rules:**
- `type: static` has no `pm2_name` (served directly by Caddy)
- `type: nextjs` and `type: flask` have a `pm2_name` per environment
- `auth` is optional; omitting it means no login required for that environment
- Ports are auto-assigned in blocks of 10 by `create-site.py`

---

## Adding Auth Credentials

Create or edit a file in `auth/` with bcrypt-hashed passwords:

```yaml
# auth/dev-team.yaml
users:
  - username: alice
    password: $2a$14$...
  - username: bob
    password: $2a$14$...
```

Generate a hash with:

```bash
caddy hash-password
```

Auth files are compiled into **named Caddy snippets** — hashes are defined once regardless of how many sites reference the same credentials file.

---

## Promoting Between Environments

```bash
python3 promote.py <site-id> <from-env> <to-env> <promoted-by>

# Example
python3 promote.py my-nextjs-app preprod production alice
python3 generate-config.py
pm2 reload caddy
pm2 reload ecosystem.config.js
```

All promotions are appended to `promotion.log` in this format:

```
2025-04-10T14:32:01Z | site=my-nextjs-app  | preprod → production | version: 0.1.4 → 0.1.5 | by=alice
2025-04-15T09:12:44Z | site=my-flask-api   | test → preprod       | version: 0.2.7 → 0.2.8 | by=bob
```

---

## Dashboard

The dashboard is a **read-only web application** that reads `sites/*.yaml` and `promotion.log` — it never writes to them.

### Version Matrix

A table showing the currently deployed version of every site in every environment. An arrow `→` between two adjacent columns indicates a promotion is available (the versions differ):

```
Site                   | dev          →  test         →  preprod        production
-----------------------|------------------------------------------------------------
My Next.js App         | 0.2.0-dev    →  0.1.5        →  0.1.4       =  0.1.4
My Flask API  [flask]  | 0.3.0-dev    →  0.2.9           0.2.9       =  0.2.9
My Static Site         | 1.0.0-dev       1.0.0-dev    →  0.9.5       =  0.9.5
```

### Promotion History

A chronological log of all promotions, filterable by site and environment, showing timestamp, site, from/to environment, old/new version, and who promoted it.

### Running the dashboard

```bash
cd dashboard
pip install -r requirements.txt
python3 app.py
```

The dashboard is served on a separate port and must be added as its own entry in `sites/` and `ecosystem.config.js` if you want PM2 to manage it.

---

## Key Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| One config file per site | `sites/<id>.yaml` | Mirrors Apache `sites-available/` pattern |
| Auth credentials separate from site config | `auth/<name>.yaml` | Reusable across sites and environments |
| Auth in Caddyfile | Named snippets + `import` | Hashes defined once, not repeated per site |
| Process supervision | PM2 manages Caddy too | Single tool for all processes, unified logs |
| Promotion audit trail | Append-only `promotion.log` | Simple, durable, no database needed |
| Dashboard separation | Separate app, read-only | Avoids coupling config management to UI |

---

## Documentation

- [`docs/hosting-architecture.md`](docs/hosting-architecture.md) — full hosting system reference (scripts, Caddyfile generation, PM2 config)
- [`docs/dashboard-context.md`](docs/dashboard-context.md) — dashboard requirements, view specs, and design decisions
