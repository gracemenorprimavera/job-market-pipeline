#!/usr/bin/env python3
"""
Run all PR quality checks locally in one go.

Usage:
    uv run python scripts/check.py           # run all checks
    uv run python scripts/check.py --fix     # auto-fix ruff issues first, then run all
    uv run python scripts/check.py --only lint type   # run specific checks by keyword

Each check streams its output live so you can see exactly what failed.
A summary table is printed at the end showing PASS / FAIL and elapsed time.
"""

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass

# ANSI colours — work in Git Bash, macOS Terminal, Linux, Windows Terminal
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


@dataclass
class Check:
    key: str  # short keyword for --only filtering
    name: str
    cmd: list[str]
    description: str


CHECKS: list[Check] = [
    Check(
        key="lint",
        name="Lint (ruff check)",
        cmd=["ruff", "check", "."],
        description="Style violations, bad patterns, unsorted imports",
    ),
    Check(
        key="format",
        name="Format (ruff format)",
        cmd=["ruff", "format", "--check", "."],
        description="Consistent code formatting",
    ),
    Check(
        key="type",
        name="Type Check (mypy)",
        cmd=["mypy", "config/", "tasks/", "flows/", "deployment/"],
        description="Static type correctness across all modules",
    ),
    Check(
        key="bandit",
        name="Security — Bandit",
        cmd=[
            "bandit",
            "-r",
            "config/",
            "tasks/",
            "flows/",
            "deployment/",
            "-c",
            "pyproject.toml",
        ],
        description="Unsafe code patterns, potential injection points",
    ),
    Check(
        key="audit",
        name="Security — pip-audit",
        cmd=["pip-audit"],
        description="Known CVEs in installed dependencies",
    ),
    Check(
        key="secrets",
        name="Secrets Scan (detect-secrets)",
        cmd=["detect-secrets", "scan", "--baseline", ".secrets.baseline"],
        description="Accidentally committed API keys or tokens",
    ),
    Check(
        key="dead",
        name="Dead Code (vulture)",
        cmd=[
            "vulture",
            "config/",
            "tasks/",
            "flows/",
            "deployment/",
            "--min-confidence",
            "80",
        ],
        description="Unused functions, variables, and imports",
    ),
    Check(
        key="test",
        name="Tests & Coverage (pytest)",
        cmd=["pytest", "--cov", "--cov-report=term-missing"],
        description="All tests pass; coverage meets the configured threshold",
    ),
]


def separator(char: str = "-", width: int = 62) -> str:
    return char * width


def run_check(check: Check) -> tuple[bool, float]:
    """Stream a single check to the terminal. Returns (passed, elapsed_seconds)."""
    print(f"\n{CYAN}{BOLD}[ {check.name} ]{RESET}  {DIM}{check.description}{RESET}")
    print(f"  {YELLOW}$ uv run {' '.join(check.cmd)}{RESET}")
    print(separator())

    start = time.monotonic()
    result = subprocess.run(["uv", "run"] + check.cmd)
    elapsed = time.monotonic() - start

    return result.returncode == 0, elapsed


def auto_fix() -> None:
    print(f"\n{YELLOW}{BOLD}-- Auto-fixing with ruff (lint + format) --{RESET}")
    subprocess.run(["uv", "run", "ruff", "check", "--fix", "."])
    subprocess.run(["uv", "run", "ruff", "format", "."])
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run all PR quality checks locally",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Check keywords for --only:\n"
            "  lint     ruff lint\n"
            "  format   ruff format\n"
            "  type     mypy\n"
            "  bandit   bandit security scan\n"
            "  audit    pip-audit CVE check\n"
            "  secrets  detect-secrets scan\n"
            "  dead     vulture dead code\n"
            "  test     pytest + coverage\n"
        ),
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix ruff lint/format issues before running checks",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="KEY",
        help="Run only specific checks by keyword (e.g. --only lint type test)",
    )
    args = parser.parse_args()

    if args.fix:
        auto_fix()

    checks_to_run = CHECKS
    if args.only:
        keys = {k.lower() for k in args.only}
        checks_to_run = [c for c in CHECKS if c.key in keys]
        if not checks_to_run:
            print(f"{RED}No checks matched keywords: {args.only}{RESET}")
            sys.exit(1)

    print(f"\n{BOLD}{separator('=')}{RESET}")
    print(f"{BOLD}  PR Quality Checks  ({len(checks_to_run)} of {len(CHECKS)} selected){RESET}")
    print(f"{BOLD}{separator('=')}{RESET}")

    results: list[tuple[str, bool, float]] = []
    for check in checks_to_run:
        passed, elapsed = run_check(check)
        results.append((check.name, passed, elapsed))

    # Summary table
    print(f"\n{BOLD}{separator('=')}{RESET}")
    print(f"{BOLD}  Summary{RESET}")
    print(f"{BOLD}{separator('=')}{RESET}")

    all_passed = True
    for name, passed, elapsed in results:
        status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
        if not passed:
            all_passed = False
        print(f"  {status}  {name:<42} {elapsed:>5.1f}s")

    print(f"{BOLD}{separator('=')}{RESET}")

    if all_passed:
        print(f"\n{GREEN}{BOLD}All checks passed.{RESET} Safe to push!\n")
        sys.exit(0)
    else:
        failed = sum(1 for _, p, _ in results if not p)
        print(f"\n{RED}{BOLD}{failed} check(s) failed.{RESET} Fix the issues above before pushing.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
