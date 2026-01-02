#!/usr/bin/env python3
"""
Test runner script for RAG Engine.

Usage:
    python scripts/run_tests.py                    # Run all unit tests
    python scripts/run_tests.py --integration      # Include integration tests
    python scripts/run_tests.py --coverage         # Run with coverage report
    python scripts/run_tests.py -k "test_config"   # Run specific tests
"""

import subprocess
import sys
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
TESTS_DIR = PROJECT_ROOT / "packages" / "rag_engine" / "tests"
PACKAGE_DIR = PROJECT_ROOT / "packages" / "rag_engine"


def run_tests(args: list = None):
    """Run pytest with the given arguments."""
    if args is None:
        args = []

    # Build pytest command
    cmd = [
        sys.executable, "-m", "pytest",
        str(TESTS_DIR),
        "-v",
        "--tb=short",
    ]

    # Add any additional arguments
    cmd.extend(args)

    # Set PYTHONPATH to include packages directory
    env = {
        "PYTHONPATH": str(PROJECT_ROOT / "packages"),
    }

    # Merge with current environment
    import os
    full_env = os.environ.copy()
    full_env.update(env)

    print(f"Running: {' '.join(cmd)}")
    print(f"PYTHONPATH: {env['PYTHONPATH']}")
    print("-" * 60)

    # Run tests
    result = subprocess.run(cmd, env=full_env)
    return result.returncode


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run RAG Engine tests")
    parser.add_argument(
        "--integration", "-i",
        action="store_true",
        help="Include integration tests (requires live system)"
    )
    parser.add_argument(
        "--coverage", "-c",
        action="store_true",
        help="Run with coverage report"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "-k",
        type=str,
        help="Only run tests matching the given expression"
    )
    parser.add_argument(
        "--unit-only",
        action="store_true",
        help="Only run unit tests (exclude integration)"
    )
    parser.add_argument(
        "extra_args",
        nargs="*",
        help="Additional pytest arguments"
    )

    args = parser.parse_args()

    pytest_args = []

    # Handle markers
    if args.unit_only:
        pytest_args.extend(["-m", "not integration and not requires_api"])
    elif not args.integration:
        pytest_args.extend(["-m", "not integration and not requires_api"])

    # Handle coverage
    if args.coverage:
        pytest_args.extend([
            "--cov=" + str(PACKAGE_DIR),
            "--cov-report=term-missing",
            "--cov-report=html:coverage_html",
        ])

    # Handle verbose
    if args.verbose:
        pytest_args.append("-vv")

    # Handle expression filter
    if args.k:
        pytest_args.extend(["-k", args.k])

    # Add any extra arguments
    pytest_args.extend(args.extra_args)

    # Run tests
    exit_code = run_tests(pytest_args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
