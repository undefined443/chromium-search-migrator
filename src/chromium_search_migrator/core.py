"""Core migration logic for Chromium search engines."""

import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

SqlValue: TypeAlias = bytes | float | int | None | str

KEYWORDS_COLUMNS = [
    "short_name",
    "keyword",
    "favicon_url",
    "url",
    "safe_for_autoreplace",
    "originating_url",
    "date_created",
    "usage_count",
    "input_encodings",
    "suggest_url",
    "prepopulate_id",
    "created_by_policy",
    "last_modified",
    "sync_guid",
    "alternate_urls",
    "image_url",
    "search_url_post_params",
    "suggest_url_post_params",
    "image_url_post_params",
    "new_tab_url",
    "last_visited",
    "created_from_play_api",
    "is_active",
    "starter_pack_id",
    "enforced_by_policy",
    "featured_by_policy",
    "url_hash",
]


@dataclass(frozen=True)
class SearchEngine:
    """Search engine summary used by the CLI and callers.

    Attributes:
        short_name: Display name from Chromium's keywords table.
        keyword: Search shortcut keyword.
        url: Search URL template.
    """

    short_name: str
    keyword: str
    url: str


@dataclass(frozen=True)
class MigrationResult:
    """Result of a search engine migration.

    Attributes:
        source: Source Web Data database path.
        target: Target Web Data database path.
        active_in_source: Number of active search engines in the source database.
        imported: Number of search engines inserted into the target database.
        skipped: Number of active source search engines skipped due to duplicates.
        candidates: Search engines selected for import.
        backup_path: Backup path when a write backup was created.
        integrity_check: SQLite integrity check result after writing.
    """

    source: Path
    target: Path
    active_in_source: int
    imported: int
    skipped: int
    candidates: tuple[SearchEngine, ...]
    backup_path: Path | None = None
    integrity_check: str | None = None


def migrate_search_engines(
    source_path: Path,
    target_path: Path,
    *,
    apply: bool = False,
    backup: bool = True,
    backup_dir: Path = Path("/tmp"),
) -> MigrationResult:
    """Migrates active Chromium search engines from source to target.

    Args:
        source_path: Source Web Data database path.
        target_path: Target Web Data database path.
        apply: Whether to write changes. If false, only computes a dry-run result.
        backup: Whether to back up the target database before writing.
        backup_dir: Directory for target backup files.

    Returns:
        Migration summary.

    Raises:
        FileNotFoundError: If source or target database does not exist.
        ValueError: If source and target schemas are incompatible.
        sqlite3.OperationalError: If SQLite cannot read or write the databases.
    """
    source_path = source_path.expanduser().resolve()
    target_path = target_path.expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"source does not exist: {source_path}")
    if not target_path.exists():
        raise FileNotFoundError(f"target does not exist: {target_path}")

    source = _connect(source_path)
    target = _connect(target_path)
    _check_schema(source, target)
    candidates, skipped = _candidate_rows(source, target)
    search_engines = tuple(_search_engine(row) for row in candidates)

    backup_path = None
    integrity_check = None
    if apply:
        if backup:
            backup_path = _backup(target_path, backup_dir.expanduser().resolve())
        _insert_rows(target, candidates)
        integrity_check = _integrity_check(target)

    return MigrationResult(
        source=source_path,
        target=target_path,
        active_in_source=len(candidates) + len(skipped),
        imported=len(candidates),
        skipped=len(skipped),
        candidates=search_engines,
        backup_path=backup_path,
        integrity_check=integrity_check,
    )


def _connect(path: Path) -> sqlite3.Connection:
    """Connects to a SQLite database.

    Args:
        path: SQLite database path.

    Returns:
        A SQLite connection with row factory enabled.
    """
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _keywords_schema(conn: sqlite3.Connection) -> list[str]:
    """Returns column names for the Chromium keywords table.

    Args:
        conn: SQLite connection.

    Returns:
        Column names in table order.
    """
    rows = conn.execute("PRAGMA table_info(keywords)").fetchall()
    return [row["name"] for row in rows]


def _check_schema(source: sqlite3.Connection, target: sqlite3.Connection) -> None:
    """Checks whether source and target keywords schemas are compatible.

    Args:
        source: Source database connection.
        target: Target database connection.

    Raises:
        ValueError: If schemas differ or required columns are missing.
    """
    source_schema = _keywords_schema(source)
    target_schema = _keywords_schema(target)
    if source_schema != target_schema:
        raise ValueError("source and target keywords schema do not match")

    missing = [column for column in KEYWORDS_COLUMNS if column not in target_schema]
    if missing:
        raise ValueError(f"target keywords table is missing columns: {missing}")


def _candidate_rows(
    source: sqlite3.Connection,
    target: sqlite3.Connection,
) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
    """Finds importable active search engines.

    Args:
        source: Source database connection.
        target: Target database connection.

    Returns:
        A tuple of importable rows and skipped rows.
    """
    target_keywords = {
        row["keyword"] for row in target.execute("SELECT keyword FROM keywords")
    }
    target_urls = {row["url"] for row in target.execute("SELECT url FROM keywords")}

    rows = source.execute(
        """
        SELECT *
        FROM keywords
        WHERE is_active = 1
        ORDER BY short_name COLLATE NOCASE, keyword COLLATE NOCASE
        """
    ).fetchall()

    candidates: list[sqlite3.Row] = []
    skipped: list[sqlite3.Row] = []
    for row in rows:
        if row["keyword"] in target_keywords or row["url"] in target_urls:
            skipped.append(row)
        else:
            candidates.append(row)

    return candidates, skipped


def _backup(path: Path, backup_dir: Path) -> Path:
    """Creates a target database backup.

    Args:
        path: Target database path.
        backup_dir: Backup directory.

    Returns:
        Backup file path.
    """
    backup_dir.mkdir(parents=True, exist_ok=True)
    name_parts = [path.parts[-3], path.parts[-2], path.name]
    backup_name = "-".join(name_parts).lower().replace(" ", "-") + ".bak"
    backup_path = backup_dir / backup_name
    index = 1
    while backup_path.exists():
        backup_path = backup_dir / f"{backup_name}.{index}"
        index += 1
    shutil.copy2(path, backup_path)
    return backup_path


def _insert_rows(target: sqlite3.Connection, rows: list[sqlite3.Row]) -> None:
    """Inserts search engine rows into the target database.

    Args:
        target: Target database connection.
        rows: Source rows to insert.
    """
    placeholders = ", ".join("?" for _ in KEYWORDS_COLUMNS)
    columns = ", ".join(KEYWORDS_COLUMNS)
    sql = f"INSERT INTO keywords ({columns}) VALUES ({placeholders})"

    values: list[list[SqlValue]] = []
    for row in rows:
        item: list[SqlValue] = []
        for column in KEYWORDS_COLUMNS:
            if column == "sync_guid":
                item.append(
                    target.execute("SELECT lower(hex(randomblob(16)))").fetchone()[0]
                )
            elif column == "is_active":
                item.append(1)
            else:
                item.append(row[column])
        values.append(item)

    with target:
        target.executemany(sql, values)


def _integrity_check(conn: sqlite3.Connection) -> str:
    """Runs SQLite integrity check.

    Args:
        conn: SQLite connection.

    Returns:
        Integrity check result.
    """
    return conn.execute("PRAGMA integrity_check").fetchone()[0]


def _search_engine(row: sqlite3.Row) -> SearchEngine:
    """Converts a SQLite row to a search engine summary.

    Args:
        row: Chromium keywords table row.

    Returns:
        Search engine summary.
    """
    return SearchEngine(
        short_name=row["short_name"],
        keyword=row["keyword"],
        url=row["url"],
    )
