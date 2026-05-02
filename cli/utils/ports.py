"""
Shared port-scanning utility.
Scans all existing site YAML files and returns the next free port block start.
"""

import glob
import yaml

SITES_DIR = "sites"
PORT_BLOCK_SIZE = 10   # each site reserves 10 ports: dev, test, preprod, prod + spares
PORT_START = 4000      # lowest port to assign when no sites exist yet


def find_next_base_port() -> int:
    """Scan existing site files and return the next free port block start."""
    used_ports: set[int] = set()
    for filepath in glob.glob(f"{SITES_DIR}/*.yaml"):
        with open(filepath) as f:
            site = yaml.safe_load(f)
        for env_cfg in site.get("environments", {}).values():
            if "port" in env_cfg:
                used_ports.add(env_cfg["port"])
    if not used_ports:
        return PORT_START
    max_port = max(used_ports)
    next_block = ((max_port // PORT_BLOCK_SIZE) + 1) * PORT_BLOCK_SIZE
    return next_block
