"""
vps.py create-site

Scaffolds a new site YAML file inside sites/ from command-line arguments.
Auto-assigns ports by scanning existing site files and validates all inputs
before writing anything.
"""

import os
import sys
import yaml

from cli.utils.ports import find_next_base_port

ENVIRONMENTS = ["dev", "test", "preprod", "production"]
SITES_DIR = "sites"


# ---------------------------------------------------------------------------
# argparse registration
# ---------------------------------------------------------------------------

def register(subparsers):
    p = subparsers.add_parser(
        "create-site",
        help="Scaffold a new site YAML file in sites/",
    )
    p.add_argument("--id",           required=True,  help="Site ID and filename (e.g. my-app)")
    p.add_argument("--name",         required=True,  help="Human-readable display name")
    p.add_argument("--type",         required=True,  choices=["static", "nextjs", "flask"],
                   help="Site type")
    p.add_argument("--base-port",    type=int,       help="First port for dev. Auto-detected if omitted.")
    p.add_argument("--base-path",                    help="Root filesystem path. Auto-set if omitted.")
    p.add_argument("--auth-dev",                     help="Auth file name for dev environment")
    p.add_argument("--auth-test",                    help="Auth file name for test environment")
    p.add_argument("--auth-preprod",                 help="Auth file name for preprod environment")
    p.add_argument("--version",      default="0.1.0", help="Initial version (default: 0.1.0)")
    p.add_argument("--dry-run",      action="store_true", help="Print YAML without writing file")
    p.set_defaults(func=run)


# ---------------------------------------------------------------------------
# Command implementation
# ---------------------------------------------------------------------------

def run(args):
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
    site = _build_site(args, base_port)
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
    print()
    print("Next steps:")
    print(f"  1. Review {output_file} and adjust paths or versions if needed")
    print(f"  2. python3 vps.py generate")
    print(f"  3. pm2 reload caddy")
    print(f"  4. pm2 reload generated/ecosystem.config.js")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_auth(auth_name: str):
    """Warn if the referenced auth file does not exist yet."""
    if auth_name and not os.path.exists(f"auth/{auth_name}.yaml"):
        print(
            f"⚠️  Warning: auth/{auth_name}.yaml does not exist yet. "
            f"Create it before running 'python3 vps.py generate'."
        )


def _build_site(args, base_port: int) -> dict:
    site_id = args.id
    site_type = args.type

    if args.base_path:
        base_path = args.base_path
    elif site_type == "static":
        base_path = f"/var/www/{site_id}"
    else:
        base_path = f"/var/apps/{site_id}"

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

    envs = {}
    for env in ENVIRONMENTS:
        port = env_ports[env]
        env_path = base_path + ("/" + env if env != "production" else "/prod")

        entry = {
            "path": env_path,
            "port": port,
            "version": args.version,
        }

        if site_type in ("nextjs", "flask"):
            entry["pm2_name"] = f"{site_id}-{env}"

        auth = auth_map.get(env)
        if auth:
            entry["auth"] = auth
            _validate_auth(auth)

        envs[env] = entry

    return {
        "id": site_id,
        "name": args.name,
        "type": site_type,
        "environments": envs,
    }
