"""
Hosting Dashboard — Flask app
Reads sites/*.yaml and promotion.log from the parent hosting/ directory.
Supports promoting a site between environments via subprocess.
"""

import glob
import os
import re
import subprocess
from pathlib import Path

import yaml
from flask import Flask, jsonify, render_template, request

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent   # hosting/
SITES_DIR = BASE_DIR / "sites"
PROMOTE_SCRIPT = BASE_DIR / "promote.py"
GENERATE_SCRIPT = BASE_DIR / "generate-config.py"
PROMOTION_LOG = BASE_DIR / "promotion.log"

# ── Config ───────────────────────────────────────────────────────────────────
ENVIRONMENTS = ["dev", "test", "preprod", "production"]

app = Flask(__name__)


# ── Data loading ─────────────────────────────────────────────────────────────
def load_sites():
    sites = []
    for path in sorted(glob.glob(str(SITES_DIR / "*.yaml"))):
        with open(path) as f:
            site = yaml.safe_load(f)
        sites.append(site)
    return sites


def load_promotion_log():
    entries = []
    if not PROMOTION_LOG.exists():
        return entries
    pattern = re.compile(
        r"(?P<ts>\S+)\s*\|\s*site=(?P<site>\S+)\s*\|\s*(?P<from_env>\S+)\s*→\s*(?P<to_env>\S+)"
        r"\s*\|\s*version:\s*(?P<old_ver>\S+)\s*→\s*(?P<new_ver>\S+)\s*\|\s*by=(?P<by>\S+)"
    )
    with open(PROMOTION_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = pattern.match(line)
            if m:
                entries.append(m.groupdict())
    return list(reversed(entries))   # newest first


def build_matrix(sites):
    """Build a list of rows for the version matrix."""
    rows = []
    for site in sites:
        envs = site.get("environments", {})
        cells = []
        for env in ENVIRONMENTS:
            cfg = envs.get(env, {})
            cells.append({
                "env": env,
                "version": cfg.get("version", "—"),
                "present": env in envs,
            })
        # Compute arrows: show arrow between adjacent envs when versions differ
        for i in range(len(cells) - 1):
            a, b = cells[i], cells[i + 1]
            a["arrow"] = (
                a["present"] and b["present"] and a["version"] != b["version"]
            )
        cells[-1]["arrow"] = False

        rows.append({
            "id": site["id"],
            "name": site["name"],
            "type": site.get("type", "static"),
            "cells": cells,
        })
    return rows


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    sites = load_sites()
    matrix = build_matrix(sites)
    log = load_promotion_log()
    return render_template("index.html", matrix=matrix, log=log,
                           environments=ENVIRONMENTS)


@app.route("/api/promote", methods=["POST"])
def promote():
    data = request.get_json()
    site_id = data.get("site_id", "").strip()
    from_env = data.get("from_env", "").strip()
    to_env = data.get("to_env", "").strip()
    username = data.get("username", "").strip()

    # Validate
    if not all([site_id, from_env, to_env, username]):
        return jsonify({"error": "Missing fields (site_id, from_env, to_env, username)"}), 400
    if from_env not in ENVIRONMENTS or to_env not in ENVIRONMENTS:
        return jsonify({"error": "Invalid environment"}), 400
    if ENVIRONMENTS.index(from_env) + 1 != ENVIRONMENTS.index(to_env):
        return jsonify({"error": "Can only promote to the next environment"}), 400

    # Run promote.py
    promote_cmd = ["python3", str(PROMOTE_SCRIPT), site_id, from_env, to_env, username]
    result = subprocess.run(promote_cmd, capture_output=True, text=True, cwd=str(BASE_DIR))
    if result.returncode != 0:
        return jsonify({"error": result.stderr or "promote.py failed", "stdout": result.stdout}), 500

    # Regenerate Caddy + PM2 configs
    gen_result = subprocess.run(
        ["python3", str(GENERATE_SCRIPT)], capture_output=True, text=True, cwd=str(BASE_DIR)
    )

    # Reload PM2
    reload_caddy = subprocess.run(["pm2", "reload", "caddy"], capture_output=True, text=True)
    reload_pm2 = subprocess.run(
        ["pm2", "reload", "ecosystem.config.js"], capture_output=True, text=True, cwd=str(BASE_DIR)
    )

    return jsonify({
        "ok": True,
        "promote_out": result.stdout,
        "generate_ok": gen_result.returncode == 0,
        "pm2_caddy_ok": reload_caddy.returncode == 0,
        "pm2_eco_ok": reload_pm2.returncode == 0,
    })


@app.route("/api/data")
def data():
    """Return fresh matrix + log as JSON (for page refresh without full reload)."""
    sites = load_sites()
    return jsonify({
        "matrix": build_matrix(sites),
        "log": load_promotion_log(),
    })


if __name__ == "__main__":
    port = int(os.environ.get("DASHBOARD_PORT", 9000))
    app.run(host="0.0.0.0", port=port, debug=False)
