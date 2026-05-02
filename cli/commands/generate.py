"""
vps.py generate

Reads all sites/*.yaml and auth/*.yaml files, then writes:
  - generated/Caddyfile
  - generated/ecosystem.config.js
"""

import glob
import json
import os
import yaml

ENVIRONMENTS = ["dev", "test", "preprod", "production"]
GENERATED_DIR = "generated"
CADDYFILE_PATH = os.path.join(GENERATED_DIR, "Caddyfile")
ECOSYSTEM_PATH = os.path.join(GENERATED_DIR, "ecosystem.config.js")


# ---------------------------------------------------------------------------
# argparse registration
# ---------------------------------------------------------------------------

def register(subparsers):
    p = subparsers.add_parser(
        "generate",
        help="Generate Caddyfile and ecosystem.config.js from sites/ and auth/",
    )
    p.set_defaults(func=run)


# ---------------------------------------------------------------------------
# Command implementation
# ---------------------------------------------------------------------------

def run(_args):
    os.makedirs(GENERATED_DIR, exist_ok=True)

    auth_store = _load_auth()
    sites = _load_sites()

    caddyfile_lines = _build_caddyfile(sites, auth_store)
    pm2_apps = _build_pm2_apps(sites, auth_store)

    with open(CADDYFILE_PATH, "w") as f:
        f.write("\n".join(caddyfile_lines))

    with open(ECOSYSTEM_PATH, "w") as f:
        f.write("module.exports = {\n  apps: ")
        f.write(json.dumps(pm2_apps, indent=2))
        f.write("\n};\n")

    print(
        f"✅ Loaded {len(sites)} site(s), {len(auth_store)} auth snippet(s). "
        f"Configs written to {GENERATED_DIR}/."
    )


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _load_auth() -> dict:
    auth_store = {}
    for filepath in glob.glob("auth/*.yaml"):
        name = os.path.splitext(os.path.basename(filepath))[0]
        with open(filepath) as f:
            auth_store[name] = yaml.safe_load(f)
    return auth_store


def _load_sites() -> list:
    sites = []
    for filepath in sorted(glob.glob("sites/*.yaml")):
        with open(filepath) as f:
            site = yaml.safe_load(f)
        expected_id = os.path.splitext(os.path.basename(filepath))[0]
        if site["id"] != expected_id:
            raise ValueError(
                f"File {filepath} has id '{site['id']}', expected '{expected_id}'"
            )
        sites.append(site)
    return sites


# ---------------------------------------------------------------------------
# Caddyfile builder
# ---------------------------------------------------------------------------

def _build_caddyfile(sites: list, auth_store: dict) -> list[str]:
    lines = [
        "# -------------------------------------------------------",
        "# Auth snippets — auto-generated, do not edit manually",
        "# -------------------------------------------------------\n",
    ]

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

    lines += [
        "# -------------------------------------------------------",
        "# Sites",
        "# -------------------------------------------------------\n",
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

    return lines


# ---------------------------------------------------------------------------
# PM2 ecosystem builder
# ---------------------------------------------------------------------------

def _build_pm2_apps(sites: list, auth_store: dict) -> list[dict]:
    apps = [
        {
            "name": "caddy",
            "script": "caddy",
            "args": f"run --config {CADDYFILE_PATH}",
            "interpreter": "none",
            "autorestart": True,
            "watch": False,
            "env": {"HOME": "/root"},
        }
    ]

    for site in sites:
        site_type = site["type"]
        for env in ENVIRONMENTS:
            env_cfg = site["environments"].get(env)
            if not env_cfg:
                continue

            port = env_cfg["port"]

            if site_type == "nextjs":
                apps.append({
                    "name": env_cfg["pm2_name"],
                    "cwd": env_cfg["path"],
                    "script": "node_modules/.bin/next",
                    "args": f"start -p {port}",
                    "env": {
                        "NODE_ENV": "production" if env == "production" else "development"
                    },
                })
            elif site_type == "flask":
                workers = 4 if env == "production" else 2
                apps.append({
                    "name": env_cfg["pm2_name"],
                    "cwd": env_cfg["path"],
                    "script": "gunicorn",
                    "args": f"app:app --bind 0.0.0.0:{port} --workers {workers}",
                    "interpreter": "none",
                })

    return apps
