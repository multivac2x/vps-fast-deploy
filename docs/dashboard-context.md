# Dashboard Project — Context Summary

This document summarises the hosting system already designed and documented, to provide
full context for building the dashboard as a separate application.

---

## 1. What Has Been Built — Hosting System

A multi-environment hosting management system for static and dynamic websites.

**Web server:** Caddy (serves static files, reverse proxy, SSL, basic auth via snippets)
**Process manager:** PM2 (manages all processes including Caddy itself, auto-restarts on crash)
**Environments per site:** `dev → test → preprod → production`

---

## 2. Directory Structure

```
hosting/
├── sites/                    # One YAML file per website — source of truth
│   ├── pescatoreluca.yaml
│   └── my-flask-api.yaml
├── auth/                     # Shared bcrypt credential files for basic auth
│   ├── dev-team.yaml
│   └── stakeholders.yaml
├── create-site.py            # Scaffolds a new site YAML with auto port assignment
├── generate-config.py        # Reads sites/ + auth/ → writes Caddyfile + ecosystem.config.js
├── promote.py                # Promotes a site between environments + appends to promotion.log
├── Caddyfile                 # Auto-generated — do not edit manually
├── ecosystem.config.js       # Auto-generated — do not edit manually
├── promotion.log             # Append-only audit log of all promotions
└── README.md
```

---

## 3. Site YAML Format

Each website has its own file in `sites/`. The filename must match the `id` field.

```yaml
id: pescatoreluca
name: Pescatore Luca
type: nextjs              # static | nextjs | flask
environments:
  dev:
    path: /var/apps/pescatoreluca/dev
    port: 4000
    version: 0.1.0
    pm2_name: pescatoreluca-dev
    auth: dev-team        # references auth/dev-team.yaml — optional
  test:
    path: /var/apps/pescatoreluca/test
    port: 4001
    version: 0.1.0
    pm2_name: pescatoreluca-test
    auth: dev-team
  preprod:
    path: /var/apps/pescatoreluca/preprod
    port: 4002
    version: 0.1.0
    pm2_name: pescatoreluca-preprod
    auth: stakeholders    # different credentials for preprod
  production:
    path: /var/apps/pescatoreluca/prod
    port: 4003
    version: 0.1.0
    pm2_name: pescatoreluca-prod
                          # no auth = public
```

**Rules:**
- `type: static` has no `pm2_name` (served directly by Caddy)
- `type: nextjs` and `type: flask` have a `pm2_name` per environment
- `auth` is optional; omitting it means no login required for that environment
- Each environment gets its own port; ports are auto-assigned in blocks of 10 by `create-site.py`

---

## 4. Auth File Format

```yaml
# auth/dev-team.yaml
users:
  - username: alice
    password: $2a$14$WPEJNSYMDcDvRKQmE9gZUeY1Bx6z3K2uF5TlO8RnHpVsA7cXdMqWi
  - username: bob
    password: $2a$14$3RkQpT7LmVcBnXoZ9WsUyOaFdPeH6Gj2NiKlA4MrYvDxEhCwJbSuT
```

Auth files are compiled into **named Caddy snippets** at the top of the generated Caddyfile:

```caddyfile
(auth_dev-team) {
    basicauth {
        alice $2a$14$...
        bob   $2a$14$...
    }
}
```

Each site environment then uses `import auth_dev-team` — hashes are defined once regardless
of how many sites reference the same credentials file.

---

## 5. Scripts

### `create-site.py` — Scaffold a new site

```bash
python3 create-site.py \
  --id pescatoreluca \
  --name "Pescatore Luca" \
  --type nextjs \
  --auth-dev dev-team \
  --auth-test dev-team \
  --auth-preprod stakeholders \
  --version 1.0.0
```

Options:

| Option | Required | Description |
|---|---|---|
| `--id` | ✅ | Site ID and filename |
| `--name` | ✅ | Human-readable display name |
| `--type` | ✅ | `static`, `nextjs`, or `flask` |
| `--base-port` | | First port for dev. Auto-detected if omitted |
| `--base-path` | | Root filesystem path. Auto-set if omitted |
| `--auth-dev` | | Auth file name for dev |
| `--auth-test` | | Auth file name for test |
| `--auth-preprod` | | Auth file name for preprod |
| `--version` | | Initial version. Defaults to `0.1.0` |
| `--dry-run` | | Print YAML without writing |

### `generate-config.py` — Rebuild Caddy + PM2 configs

```bash
python3 generate-config.py
pm2 reload caddy
pm2 reload ecosystem.config.js
```

Reads all `sites/*.yaml` and `auth/*.yaml`, writes `Caddyfile` and `ecosystem.config.js`.

### `promote.py` — Promote a site between environments

```bash
python3 promote.py <site-id> <from-env> <to-env> <promoted-by>

# Example:
python3 promote.py pescatoreluca preprod production alice
python3 generate-config.py
pm2 reload caddy
pm2 reload ecosystem.config.js
```

Edits only the specific site's YAML file (updates the target environment version),
then appends one line to `promotion.log`.

---

## 6. Promotion Log Format

`promotion.log` is an **append-only plain text file**. One line per promotion event.

```
2025-04-10T14:32:01Z | site=pescatoreluca    | preprod → production | version: 0.9.0 → 1.0.0   | by=alice
2025-04-15T09:12:44Z | site=my-flask-api     | test → preprod       | version: 0.2.7 → 0.2.8   | by=bob
2025-04-20T17:55:10Z | site=my-static-site   | dev → test           | version: 0.9.0 → 1.0.0   | by=alice
```

Fields: `timestamp | site=<id> | <from> → <to> | version: <old> → <new> | by=<user>`

---

## 7. Dashboard — Requirements

The dashboard is a **separate read-only web application**. It reads `sites/*.yaml` and
`promotion.log` and never writes to them.

### 7.1 Main View — Version Matrix

A table where:

- **Rows** = one per website (sourced from `sites/*.yaml`)
- **Columns** = `dev`, `test`, `preprod`, `production`
- Each **cell** shows: site name, type badge (`static` / `nextjs` / `flask`), and the version
  string currently deployed in that environment
- An **arrow →** is displayed between two adjacent columns when their versions differ,
  indicating a promotion is pending or available
- **No arrow** when two adjacent environments share the same version

Example layout:

```
Site                  | dev          →  test         →  preprod        production
----------------------|-----------------------------------------------------------
Pescatore Luca        | 0.2.0-dev    →  0.1.5        →  0.1.4       =  0.1.4
My Flask API  [flask] | 0.3.0-dev    →  0.2.9           0.2.9       =  0.2.9
My Static Site        | 1.0.0-dev       1.0.0-dev    →  0.9.5       =  0.9.5
```

### 7.2 Promotion History View

A chronological log view driven by `promotion.log`, showing:

- Timestamp
- Site name
- From environment → to environment
- Old version → new version
- Promoted by (username)

Filterable by site and by environment.

### 7.3 Constraints

- The dashboard is **read-only** — it does not trigger promotions or write any files
- It must be **served separately** from the hosted sites (different port or subdomain)
- It should be **lightweight** — no heavy framework required unless justified
- It should **reload data on page load or refresh** (no need for real-time websocket updates
  unless desired)
- Tech stack is open — options include a simple Flask app, a Next.js app, or a pure
  HTML + JS single file served by Caddy

---

## 8. Key Design Decisions Already Made

| Decision | Choice | Reason |
|---|---|---|
| One config file per site | `sites/<id>.yaml` | Mirrors Apache `sites-available/` pattern |
| Auth credentials separate from site config | `auth/<name>.yaml` | Reusable across sites and environments |
| Auth in Caddyfile | Named snippets + `import` | Hashes defined once, not repeated per site |
| Process supervision | PM2 manages Caddy too | Single tool for all processes, unified logs |
| Promotion audit trail | Append-only `promotion.log` | Simple, durable, no database needed |
| Dashboard separation | Separate app, read-only | Avoids coupling config management to UI |
