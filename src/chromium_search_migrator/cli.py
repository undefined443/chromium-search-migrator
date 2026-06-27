"""Command line interface for migrating Chromium search engines."""

import argparse
import sqlite3
from pathlib import Path

from chromium_search_migrator.core import migrate_search_engines


def parse_args() -> argparse.Namespace:
    """Parses command line arguments.

    Returns:
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Migrate active Chromium search engines from source Web Data "
            "to target Web Data."
        )
    )
    parser.add_argument("source", type=Path, help="Source Web Data database path")
    parser.add_argument("target", type=Path, help="Target Web Data database path")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes. Without this flag, only print a dry-run summary.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create target backup before writing.",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=Path("/tmp"),
        help="Directory for target backup before writing. Default: /tmp.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List search engines that would be imported.",
    )
    return parser.parse_args()


def main() -> None:
    """Runs the search engine migration CLI."""
    args = parse_args()

    try:
        result = migrate_search_engines(
            args.source,
            args.target,
            apply=args.apply,
            backup=not args.no_backup,
            backup_dir=args.backup_dir,
        )
    except FileNotFoundError as error:
        raise SystemExit(str(error)) from error
    except ValueError as error:
        raise SystemExit(str(error)) from error
    except sqlite3.OperationalError as error:
        if "database is locked" in str(error):
            raise SystemExit(
                "database is locked; close the source/target browser and retry"
            ) from error
        raise

    print(f"source: {result.source}")
    print(f"target: {result.target}")
    print(f"active in source: {result.active_in_source}")
    print(f"to import: {result.imported}")
    print(f"skipped: {result.skipped}")

    if args.list:
        for search_engine in result.candidates:
            print(
                "import: "
                f"{search_engine.short_name} -> "
                f"{search_engine.keyword} -> "
                f"{search_engine.url}"
            )

    if not args.apply:
        print("dry-run only; pass --apply to write changes")
        return

    if result.backup_path is not None:
        print(f"backup: {result.backup_path}")
    print(f"integrity_check: {result.integrity_check}")
    print("done")


if __name__ == "__main__":
    main()
