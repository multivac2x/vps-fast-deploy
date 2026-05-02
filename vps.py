#!/usr/bin/env python3
"""
VPS Fast Deploy — CLI entry point.

Usage:
    python3 vps.py create-site [options]
    python3 vps.py generate
    python3 vps.py promote <site-id> <from-env> <to-env> <promoted-by>
"""

import argparse
import sys

from cli.commands import create_site, generate, promote


def main():
    parser = argparse.ArgumentParser(
        prog="vps",
        description="VPS Fast Deploy — manage sites, generate configs, promote versions.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", metavar="<subcommand>")
    subparsers.required = True

    create_site.register(subparsers)
    generate.register(subparsers)
    promote.register(subparsers)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
