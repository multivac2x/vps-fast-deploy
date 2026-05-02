"""
vps.py promote

Promotes a single site's version from one environment to another,
updates its sites/<id>.yaml, and appends an entry to logs/promotion.log.
"""

import os
import sys
import yaml
from datetime import datetime, timezone

LOGS_DIR = "logs"
LOG_FILE = os.path.join(LOGS_DIR, "promotion.log")


# ---------------------------------------------------------------------------
# argparse registration
# ---------------------------------------------------------------------------

def register(subparsers):
    p = subparsers.add_parser(
        "promote",
        help="Promote a site's version between environments and log it",
    )
    p.add_argument("site_id",      help="Site identifier (e.g. my-nextjs-app)")
    p.add_argument("from_env",     help="Source environment (e.g. preprod)")
    p.add_argument("to_env",       help="Target environment (e.g. production)")
    p.add_argument("promoted_by",  help="Username performing the promotion (e.g. alice)")
    p.set_defaults(func=run)


# ---------------------------------------------------------------------------
# Command implementation
# ---------------------------------------------------------------------------

def run(args):
    site_file = os.path.join("sites", f"{args.site_id}.yaml")

    if not os.path.exists(site_file):
        print(f"❌ Site file not found: {site_file}")
        sys.exit(1)

    with open(site_file) as f:
        site = yaml.safe_load(f)

    environments = site.get("environments", {})

    if args.from_env not in environments:
        print(f"❌ Environment '{args.from_env}' not found in {site_file}")
        sys.exit(1)

    if args.to_env not in environments:
        print(f"❌ Environment '{args.to_env}' not found in {site_file}")
        sys.exit(1)

    from_cfg = environments[args.from_env]
    to_cfg = environments[args.to_env]

    old_version = to_cfg["version"]
    new_version = from_cfg["version"]

    # Update version in the target environment
    to_cfg["version"] = new_version

    with open(site_file, "w") as f:
        yaml.dump(site, f, default_flow_style=False)

    # Append to promotion log
    os.makedirs(LOGS_DIR, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log_entry = (
        f"{timestamp} | "
        f"site={args.site_id} | "
        f"{args.from_env} → {args.to_env} | "
        f"version: {old_version} → {new_version} | "
        f"by={args.promoted_by}\n"
    )
    with open(LOG_FILE, "a") as f:
        f.write(log_entry)

    print(f"✅ Promoted {args.site_id}: {args.from_env} → {args.to_env} ({new_version})")
    print("🔁 Run 'python3 vps.py generate' and reload Caddy/PM2 to apply.")
