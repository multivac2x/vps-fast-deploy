# Static & Dynamic Website Hosting Architecture

## Overview

This document describes how to configure and manage hosting for static and dynamic websites across multiple environments (dev, test, preproduction, production) using **Caddy** as the web server and **PM2** as the unified process manager for **all processes** — including Caddy itself.

---

## 1. Site Types Supported

| Type        | Technology     | Served by             | Managed by      |
|-------------|----------------|-----------------------|-----------------|
| Static      | HTML/CSS/JS    | Caddy                 | PM2 (via Caddy) |
| Dynamic     | Next.js        | Caddy (reverse proxy) | PM2             |
| Dynamic     | Flask (Python) | Caddy (reverse proxy) | PM2             |

> **Why PM2 manages Caddy too?** While Caddy is very stable, it can crash or be killed like any process. Running Caddy under PM2 ensures it is automatically restarted on failure, its logs are unified with all other processes, and a single tool (`pm2 monit`) gives visibility over the entire stack — including static sites.

---

## 2. Environment Model

Each website exists in up to four environments:

```
dev  →  test  →  preprod  →  production
```

Each environment runs on a **different port** (or subdomain) on the same server, or on separate servers. Promotion from one environment to the next is explicit and logged.

---

## 3. Site Registry — One File Per Site

Inspired by Apache's `sites-available/` pattern, each website has its **own YAML file** inside a `sites/` directory. There is no central registry file — `generate-config.py` simply globs all `*.yaml` files in that folder.

This makes it easy to add, remove, or edit a single site without touching anything else.

### `sites/` — Directory Layout

```
sites/
├── my-nextjs-app.yaml
├── my-flask-api.yaml
└── my-static-site.yaml
```

### `sites/my-nextjs-app.yaml` — Example

```yaml
id: my-nextjs-app
name: "My Next.js App"
type: nextjs
environments:
  dev:
    path: /var/apps/my-nextjs-app/dev
    port: 5001
    version: "2.1.0-dev"
    pm2_name: "nextjs-dev"
    auth: dev-team          # references auth/dev-team.yaml
  test:
    path: /var/apps/my-nextjs-app/test
    port: 5002
    version: "2.0.1"
    pm2_name: "nextjs-test"
    auth: dev-team          # same credentials file reused
  preprod:
    path: /var/apps/my-nextjs-app/preprod
    port: 5003
    version: "2.0.0"
    pm2_name: "nextjs-preprod"
    auth: stakeholders      # different credentials file for preprod
  production:
    path: /var/apps/my-nextjs-app/prod
    port: 5004
    version: "1.9.8"
    pm2_name: "nextjs-prod"
    # no auth: production is public (or behind a firewall/VPN)
```

The `auth` field is optional. When present, it references a credentials file by name from the `auth/` directory (see Section 3a). Omitting it means no login is required for that environment.

> **Convention:** the filename must match the `id` field (e.g. `my-nextjs-app.yaml` → `id: my-nextjs-app`). This is enforced by `generate-config.py` at load time.

---

## 3a. Shared Credentials — Auth Files

Credentials are stored in **separate files** inside an `auth/` directory. Each file defines a named set of users and their bcrypt-hashed passwords. Any number of site YAML files can reference the same auth file by name.

The generator reads these files and writes **Caddy `snippet` blocks** at the top of the `Caddyfile`. Each site environment then uses `import <snippet_name>` to apply auth — so the hashes are defined **only once**, no matter how many sites or environments reference the same credentials.

### `auth/` — Directory Layout

```
auth/
├── dev-team.yaml       # shared across all dev + test environments
└── stakeholders.yaml   # used for preprod access
```

### `auth/dev-team.yaml`

```yaml
# Credentials for dev and test environments
# Passwords are bcrypt hashes — generate with: caddy hash-password
users:
  - username: alice
    password: $2a$14$WPEJNSYMDcDvRKQmE9gZUeY1Bx6z3K2uF5TlO8RnHpVsA7cXdMqWi
  - username: bob
    password: $2a$14$3RkQpT7LmVcBnXoZ9WsUyOaFdPeH6Gj2NiKlA4MrYvDxEhCwJbSuT
```

### `auth/stakeholders.yaml`

```yaml
# Credentials for preprod environment
users:
  - username: product-owner
    password: $2a$14$HqL8NmKzVbPsRcWoT5XyUeJdFgA2Ei7MnBvDxCjYlO9GrHwZuKpSa
  - username: qa-lead
    password: $2a$14$7YpRnFkMvCqBsXoW4TzUiOaEdPeL9Gj3NhKlA2MrDvExHhCwJcSuT
```

### Generating a bcrypt hash

Caddy ships with a built-in password hashing command:

```bash
caddy hash-password
# Enter password at the prompt → outputs the hash to paste into the yaml
```

---

## 4. Caddy Configuration

Caddy is configured via a `Caddyfile` that is **auto-generated** from the `sites/` and `auth/` directories by a script (see Section 6).

The generator writes all auth credential sets as **named Caddy snippets** at the top of the file. Each snippet is defined once and reused via `import` — so if ten sites share `dev-team` credentials, the hashes appear in the file exactly once.

### Generated `Caddyfile` — Example

```caddyfile
# -------------------------------------------------------
# Auth snippets — auto-generated, do not edit manually
# -------------------------------------------------------

(auth_dev-team) {
    basicauth {
        alice         $2a$14$WPEJNSYMDcDvRKQmE9gZUeY1Bx6z3K2uF5TlO8RnHpVsA7cXdMqWi
        bob           $2a$14$3RkQpT7LmVcBnXoZ9WsUyOaFdPeH6Gj2NiKlA4MrYvDxEhCwJbSuT
    }
}

(auth_stakeholders) {
    basicauth {
        product-owner $2a$14$HqL8NmKzVbPsRcWoT5XyUeJdFgA2Ei7MnBvDxCjYlO9GrHwZuKpSa
        qa-lead       $2a$14$7YpRnFkMvCqBsXoW4TzUiOaEdPeL9Gj3NhKlA2MrDvExHhCwJcSuT
    }
}

# -------------------------------------------------------
# Sites
# -------------------------------------------------------

# my-nextjs-app — dev
:5001 {
    reverse_proxy localhost:5001
    import auth_dev-team
}

# my-nextjs-app — test
:5002 {
    reverse_proxy localhost:5002
    import auth_dev-team
}

# my-nextjs-app — preprod
:5003 {
    reverse_proxy localhost:5003
    import auth_stakeholders
}

# my-nextjs-app — production (no auth)
:5004 {
    reverse_proxy localhost:5004
}
```

> **Note:** The `import` line is injected only when an `auth` key is present in the environment's YAML. Adding a new user to `auth/dev-team.yaml` and re-running the generator updates every site that references it in one shot.

### SSL with Caddy

For public-facing domains, replace the port binding with a domain name and Caddy handles SSL automatically:

```caddyfile
myapp.example.com {
    reverse_proxy localhost:5004
}
```

No extra configuration needed — Caddy provisions and renews Let's Encrypt certificates automatically.

---

## 5. PM2 Configuration — All Processes

PM2 manages **everything**: Caddy (which serves static sites) and all dynamic app processes. A single **ecosystem file** is auto-generated from the `sites/` directory.

### Generated `ecosystem.config.js` — Example

```js
module.exports = {
  apps: [
    // Caddy — serves all static sites and acts as reverse proxy
    {
      name: "caddy",
      script: "caddy",
      args: "run --config /path/to/hosting/Caddyfile",
      interpreter: "none",
      autorestart: true,
      watch: false,
      env: { HOME: "/root" }
    },

    // Next.js apps
    {
      name: "nextjs-dev",
      cwd: "/var/apps/my-nextjs-app/dev",
      script: "node_modules/.bin/next",
      args: "start -p 5001",
      env: { NODE_ENV: "development" }
    },
    {
      name: "nextjs-prod",
      cwd: "/var/apps/my-nextjs-app/prod",
      script: "node_modules/.bin/next",
      args: "start -p 5004",
      env: { NODE_ENV: "production" }
    },

    // Flask apps (via gunicorn)
    {
      name: "flask-dev",
      cwd: "/var/apps/my-flask-api/dev",
      script: "gunicorn",
      args: "app:app --bind 0.0.0.0:6001 --workers 2",
      interpreter: "none"
    },
    {
      name: "flask-prod",
      cwd: "/var/apps/my-flask-api/prod",
      script: "gunicorn",
      args: "app:app --bind 0.0.0.0:6004 --workers 4",
      interpreter: "none"
    }
  ]
};
```

> **Note:** Caddy is listed first so PM2 starts it before the dynamic apps. The `autorestart: true` flag ensures Caddy is automatically restarted if it crashes for any reason.

Start all processes with:

```bash
pm2 start ecosystem.config.js
pm2 save
pm2 startup   # registers PM2 itself to start on server reboot
```

To reload Caddy after a config change without downtime:

```bash
pm2 reload caddy
# or, to trigger a graceful Caddy config reload internally:
pm2 exec caddy -- caddy reload --config /path/to/Caddyfile
```

---

## 6. Config Generator Script

A single script globs all `*.yaml` files from the `sites/` and `auth/` directories, writes auth snippets once at the top of the `Caddyfile`, and uses `import` in each site block.

### Script: `generate-config.py`

```python
import glob
import os
import yaml
import json

ENVIRONMENTS = ["dev", "test", "preprod", "production"]
CADDYFILE_PATH = "/path/to/hosting/Caddyfile"

# --- Load auth credential files ---
auth_store = {}
for filepath in glob.glob("auth/*.yaml"):
    name = os.path.splitext(os.path.basename(filepath))[0]
    with open(filepath) as f:
        auth_store[name] = yaml.safe_load(f)

# --- Load all site definitions ---
sites = []
for filepath in sorted(glob.glob("sites/*.yaml")):
    with open(filepath) as f:
        site = yaml.safe_load(f)
    expected_id = os.path.splitext(os.path.basename(filepath))[0]
    if site["id"] != expected_id:
        raise ValueError(f"File {filepath} has id '{site['id']}', expected '{expected_id}'")
    sites.append(site)

# --- Build Caddyfile ---
lines = []

# Write auth snippets at the top — each defined only once
lines.append("# -------------------------------------------------------")
lines.append("# Auth snippets — auto-generated, do not edit manually")
lines.append("# -------------------------------------------------------\n")
for auth_name, auth_data in sorted(auth_store.items()):
    user_lines = "\n".join(
        f"        {u['username']} {u['password']}"
        for u in auth_data["users"]
    )
    lines.append(f"(auth_{auth_name}) {{")
    lines.append(f"    basicauth {{")
    lines.append(user_lines)
    lines.append(f"    }}")
    lines.append(f"}}\n")

lines.append("# -------------------------------------------------------")
lines.append("# Sites")
lines.append("# -------------------------------------------------------\n")

pm2_apps = [
    {
        "name": "caddy",
        "script": "caddy",
        "args": f"run --config {CADDYFILE_PATH}",
        "interpreter": "none",
        "autorestart": True,
        "watch": False,
        "env": {"HOME": "/root"}
    }
]

for site in sites:
    for env in ENVIRONMENTS:
        env_cfg = site["environments"].get(env)
        if not env_cfg:
            continue

        port = env_cfg["port"]
        site_type = site["type"]
        auth_name = env_cfg.get("auth")

        if auth_name and auth_name not in auth_store:
            raise ValueError(f"Auth file 'auth/{auth_name}.yaml' not found")

        # Build the import line if auth is set
        auth_line = f"\n    import auth_{auth_name}" if auth_name else ""

        lines.append(f"# {site['name']} — {env}")
        if site_type == "static":
            lines.append(f":{port} {{")
            lines.append(f"    root * {env_cfg['path']}")
            lines.append(f"    file_server{auth_line}")
            lines.append(f"}}\n")
        else:
            lines.append(f":{port} {{")
            lines.append(f"    reverse_proxy localhost:{port}{auth_line}")
            lines.append(f"}}\n")

        # --- PM2 entry (dynamic apps only) ---
        if site_type == "nextjs":
            pm2_apps.append({
                "name": env_cfg["pm2_name"],
                "cwd": env_cfg["path"],
                "script": "node_modules/.bin/next",
                "args": f"start -p {port}",
                "env": {"NODE_ENV": "production" if env == "production" else "development"}
            })
        elif site_type == "flask":
            workers = 4 if env == "production" else 2
            pm2_apps.append({
                "name": env_cfg["pm2_name"],
                "cwd": env_cfg["path"],
                "script": "gunicorn",
                "args": f"app:app --bind 0.0.0.0:{port} --workers {workers}",
                "interpreter": "none"
            })

# Write Caddyfile
with open("Caddyfile", "w") as f:
    f.write("\n".join(lines))

# Write ecosystem.config.js
with open("ecosystem.config.js", "w") as f:
    f.write("module.exports = {\n  apps: ")
    f.write(json.dumps(pm2_apps, indent=2))
    f.write("\n};\n")

print(f"✅ Loaded {len(sites)} site(s), {len(auth_store)} auth snippet(s). Configs generated.")
```

Run with:

```bash
python3 generate-config.py
pm2 reload caddy        # reloads Caddy with new Caddyfile
pm2 reload ecosystem.config.js   # reloads dynamic app processes
```

---

## 7. Promotion Between Environments

Promotion (e.g. preprod → production) is handled by a dedicated script that:

1. Opens only the **specific site's YAML file** from `sites/`
2. Updates the version for the target environment
3. Regenerates and reloads Caddy + PM2 configs
4. **Appends a log entry** to `promotion.log`

### Script: `promote.py`

```python
import yaml
import sys
from datetime import datetime

LOG_FILE = "promotion.log"

site_id = sys.argv[1]          # e.g. my-nextjs-app
from_env = sys.argv[2]         # e.g. preprod
to_env = sys.argv[3]           # e.g. production
promoted_by = sys.argv[4]      # e.g. alice

site_file = f"sites/{site_id}.yaml"

with open(site_file) as f:
    site = yaml.safe_load(f)

from_cfg = site["environments"][from_env]
to_cfg = site["environments"][to_env]

old_version = to_cfg["version"]
new_version = from_cfg["version"]

# Update version in the site's own file only
to_cfg["version"] = new_version

with open(site_file, "w") as f:
    yaml.dump(site, f, default_flow_style=False)

# Log the promotion
log_entry = (
    f"{datetime.utcnow().isoformat()}Z | "
    f"site={site_id} | "
    f"{from_env} → {to_env} | "
    f"version: {old_version} → {new_version} | "
    f"by={promoted_by}\n"
)
with open(LOG_FILE, "a") as f:
    f.write(log_entry)

print(f"✅ Promoted {site_id} from {from_env} to {to_env} ({new_version})")
print("🔁 Re-run generate-config.py and reload Caddy/PM2 to apply.")
```

Usage:

```bash
python3 promote.py my-nextjs-app preprod production alice
python3 generate-config.py
pm2 reload caddy
pm2 reload ecosystem.config.js
```

### `promotion.log` — Example Output

```
2025-04-10T14:32:01Z | site=my-nextjs-app | preprod → production | version: 1.9.8 → 2.0.0 | by=alice
2025-04-15T09:12:44Z | site=my-flask-api  | test → preprod       | version: 0.2.7 → 0.2.8 | by=bob
2025-04-20T17:55:10Z | site=my-static-site | dev → test          | version: 0.9.0 → 1.0.0-dev | by=alice
```

---

## 8. Site Creation Script

`create-site.py` scaffolds a new site YAML file inside `sites/` from command-line arguments. It auto-assigns ports by scanning existing site files to find the next available port block, and validates all inputs before writing anything.

### Usage

```bash
python3 create-site.py [OPTIONS]
```

### Options

| Option | Required | Description |
|---|---|---|
| `--id` | ✅ | Site identifier, used as filename (e.g. `pescatoreluca`) |
| `--name` | ✅ | Human-readable display name (e.g. `"Pescatore Luca"`) |
| `--type` | ✅ | Site type: `static`, `nextjs`, or `flask` |
| `--base-port` | | First port to assign to dev. If omitted, auto-detected from existing sites |
| `--base-path` | | Root path for site files. Defaults to `/var/www/{id}` (static) or `/var/apps/{id}` (dynamic) |
| `--auth-dev` | | Auth file name for dev environment (e.g. `dev-team`) |
| `--auth-test` | | Auth file name for test environment |
| `--auth-preprod` | | Auth file name for preprod environment |
| `--version` | | Initial version string. Defaults to `0.1.0` |
| `--dry-run` | | Print the YAML to stdout without writing the file |

### Examples

```bash
# Static site, auto port, no auth
python3 create-site.py --id pescatoreluca --name "Pescatore Luca" --type static

# Next.js app with auth on dev/test/preprod
python3 create-site.py \
  --id pescatoreluca \
  --name "Pescatore Luca" \
  --type nextjs \
  --auth-dev dev-team \
  --auth-test dev-team \
  --auth-preprod stakeholders \
  --version 1.0.0

# Flask API, custom base port and path, dry run first
python3 create-site.py \
  --id pescatoreluca-api \
  --name "Pescatore Luca API" \
  --type flask \
  --base-port 7000 \
  --base-path /var/apps/pescatoreluca-api \
  --auth-dev dev-team \
  --dry-run
```

### Script: `create-site.py`

```python
import argparse
import glob
import os
import sys
import yaml

ENVIRONMENTS = ["dev", "test", "preprod", "production"]
SITES_DIR = "sites"
PORT_BLOCK_SIZE = 10   # each site reserves 10 ports: dev, test, preprod, prod + spare
PORT_START = 4000      # lowest port to assign if no sites exist yet

def find_next_base_port():
    """Scan existing site files and return the next free port block start."""
    used_ports = set()
    for filepath in glob.glob(f"{SITES_DIR}/*.yaml"):
        with open(filepath) as f:
            site = yaml.safe_load(f)
        for env_cfg in site.get("environments", {}).values():
            if "port" in env_cfg:
                used_ports.add(env_cfg["port"])
    if not used_ports:
        return PORT_START
    # Round up to next clean block boundary
    max_port = max(used_ports)
    next_block = ((max_port // PORT_BLOCK_SIZE) + 1) * PORT_BLOCK_SIZE
    return next_block

def validate_auth(auth_name):
    """Warn if the referenced auth file does not exist."""
    if auth_name and not os.path.exists(f"auth/{auth_name}.yaml"):
        print(f"⚠️  Warning: auth/'{auth_name}.yaml' does not exist yet. "
              f"Create it before running generate-config.py.")

def build_site(args, base_port):
    """Build the site dict from parsed arguments."""
    site_id = args.id
    site_type = args.type

    if args.base_path:
        base_path = args.base_path
    elif site_type == "static":
        base_path = f"/var/www/{site_id}"
    else:
        base_path = f"/var/apps/{site_id}"

    envs = {}
    env_ports = {
        "dev":        base_port,
        "test":       base_port + 1,
        "preprod":    base_port + 2,
        "production": base_port + 3,
    }
    auth_map = {
        "dev":     args.auth_dev,
        "test":    args.auth_test,
        "preprod": args.auth_preprod,
    }

    for env in ENVIRONMENTS:
        port = env_ports[env]
        env_path = base_path + ("/" + env if env != "production" else "/prod")

        entry = {
            "path": env_path,
            "port": port,
            "version": args.version,
        }

        # pm2_name only for dynamic sites
        if site_type in ("nextjs", "flask"):
            entry["pm2_name"] = f"{site_id}-{env}"

        # auth only for dev/test/preprod if specified
        auth = auth_map.get(env)
        if auth:
            entry["auth"] = auth
            validate_auth(auth)

        envs[env] = entry

    return {
        "id": site_id,
        "name": args.name,
        "type": site_type,
        "environments": envs,
    }

def main():
    parser = argparse.ArgumentParser(
        description="Scaffold a new site YAML file in the sites/ directory."
    )
    parser.add_argument("--id",           required=True,  help="Site ID and filename (e.g. pescatoreluca)")
    parser.add_argument("--name",         required=True,  help="Human-readable site name")
    parser.add_argument("--type",         required=True,  choices=["static", "nextjs", "flask"])
    parser.add_argument("--base-port",    type=int,       help="First port (dev). Auto-detected if omitted.")
    parser.add_argument("--base-path",                    help="Root filesystem path. Auto-set if omitted.")
    parser.add_argument("--auth-dev",                     help="Auth file name for dev environment")
    parser.add_argument("--auth-test",                    help="Auth file name for test environment")
    parser.add_argument("--auth-preprod",                 help="Auth file name for preprod environment")
    parser.add_argument("--version",      default="0.1.0", help="Initial version (default: 0.1.0)")
    parser.add_argument("--dry-run",      action="store_true", help="Print YAML without writing file")
    args = parser.parse_args()

    # Validate site ID
    if not args.id.replace("-", "").replace("_", "").isalnum():
        print(f"❌ --id '{args.id}' must be alphanumeric (hyphens and underscores allowed).")
        sys.exit(1)

    output_file = os.path.join(SITES_DIR, f"{args.id}.yaml")
    if not args.dry_run and os.path.exists(output_file):
        print(f"❌ Site '{args.id}' already exists at {output_file}. Aborting.")
        sys.exit(1)

    os.makedirs(SITES_DIR, exist_ok=True)

    base_port = args.base_port or find_next_base_port()
    site = build_site(args, base_port)

    output = yaml.dump(site, default_flow_style=False, sort_keys=False)

    if args.dry_run:
        print("--- DRY RUN — nothing written ---")
        print(output)
        print("--- Ports assigned ---")
        for env, cfg in site["environments"].items():
            print(f"  {env:12} → port {cfg['port']}")
        return

    with open(output_file, "w") as f:
        f.write(output)

    print(f"✅ Created {output_file}")
    print(f"   Type    : {args.type}")
    print(f"   Ports   : dev={base_port}  test={base_port+1}  preprod={base_port+2}  production={base_port+3}")
    print(f"")
    print(f"Next steps:")
    print(f"  1. Review {output_file} and adjust paths or versions if needed")
    print(f"  2. python3 generate-config.py")
    print(f"  3. pm2 reload caddy")
    print(f"  4. pm2 reload ecosystem.config.js")

if __name__ == "__main__":
    main()
```

### Example Output

Running the following command:

```bash
python3 create-site.py \
  --id pescatoreluca \
  --name "Pescatore Luca" \
  --type nextjs \
  --auth-dev dev-team \
  --auth-test dev-team \
  --auth-preprod stakeholders
```

Produces `sites/pescatoreluca.yaml`:

```yaml
id: pescatoreluca
name: Pescatore Luca
type: nextjs
environments:
  dev:
    path: /var/apps/pescatoreluca/dev
    port: 4000
    version: 0.1.0
    pm2_name: pescatoreluca-dev
    auth: dev-team
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
    auth: stakeholders
  production:
    path: /var/apps/pescatoreluca/prod
    port: 4003
    version: 0.1.0
    pm2_name: pescatoreluca-prod
```

---

## 9. Directory Structure

```
hosting/
├── sites/                         # One YAML file per website — edit here
│   ├── my-nextjs-app.yaml
│   ├── my-flask-api.yaml
│   └── my-static-site.yaml
├── auth/                          # Shared credential files — referenced by sites
│   ├── dev-team.yaml
│   └── stakeholders.yaml
├── create-site.py                 # Scaffolds a new site YAML with auto port assignment
├── generate-config.py             # Globs sites/ + auth/ → Caddyfile + ecosystem.config.js
├── promote.py                     # Promotes a single site's version + logs it
├── Caddyfile                      # Auto-generated — do not edit manually
├── ecosystem.config.js            # Auto-generated — do not edit manually
├── promotion.log                  # Append-only promotion history
└── README.md                      # This file
```

---

## 10. Summary of Responsibilities

| Tool       | Responsibility                                      |
|------------|-----------------------------------------------------|
| `sites/*.yaml` | One file per site — source of truth for versions, paths, and auth references |
| `auth/*.yaml` | Shared credential files (bcrypt hashes) — compiled into Caddy snippets, reusable across any site/env |
| Caddy      | Serve static files, reverse proxy, SSL, basic auth  |
| PM2        | Keep **all** processes alive (Caddy + Next.js + Flask), auto-restart on crash |
| `create-site.py` | Scaffold a new site YAML with validated inputs and auto port assignment |
| `generate-config.py` | Globs `sites/` + `auth/` → Caddy + PM2 configs |
| `promote.py` | Promotes a single site's version, updates its YAML, logs it |
| `promotion.log` | Immutable audit trail of all promotions        |

---

*Next document: Dashboard architecture (separate)*
