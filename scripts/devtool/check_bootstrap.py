#!/usr/bin/env python3
"""Explicitly a planning/identity check, not build or release qualification."""
import sys
from bootstrap_contract import check_component

if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError("usage: check_bootstrap.py {webui|runtime|android|release}")
        print(check_component(sys.argv[1]))
    except (AssertionError, ValueError, OSError, KeyError) as exc:
        print(f"SKYBIND BOOTSTRAP FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
