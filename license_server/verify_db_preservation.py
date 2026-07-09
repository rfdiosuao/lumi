#!/usr/bin/env python3
"""Verify that a license-server deployment preserved customer data."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from typing import Iterable


PROTECTED_TABLES = (
    "codes",
    "activations",
    "accounts",
    "admin_sessions",
    "invite_codes",
    "audit_logs",
    "settings",
    "beta_claims",
    "prompt_templates",
    "account_gateway_settings",
    "publish_relay_packets",
)


@dataclass(frozen=True)
class TableComparison:
    table: str
    before_count: int
    after_count: int
    equal: bool
    expected_change: bool = False


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "select name from sqlite_master where type = 'table' and name not like 'sqlite_%'"
        )
    }


def _columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in connection.execute(f"pragma table_info({_quote_identifier(table)})")]


def _safe_value(value: object) -> tuple[str, str]:
    if value is None:
        return ("null", "")
    if isinstance(value, bytes):
        return ("bytes-sha256", hashlib.sha256(value).hexdigest())
    return (type(value).__name__, str(value))


def _row_digest(connection: sqlite3.Connection, table: str, columns: Iterable[str]) -> tuple[int, str]:
    column_list = list(columns)
    query = "select " + ",".join(_quote_identifier(column) for column in column_list)
    query += " from " + _quote_identifier(table)
    rows = sorted(tuple(_safe_value(value) for value in row) for row in connection.execute(query))
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"), sort_keys=False).encode("utf-8")
    return len(rows), hashlib.sha256(payload).hexdigest()


def compare_table(
    before: sqlite3.Connection,
    after: sqlite3.Connection,
    table: str,
    *,
    expected_change: bool = False,
) -> TableComparison:
    before_names = _table_names(before)
    after_names = _table_names(after)
    if table not in before_names or table not in after_names:
        return TableComparison(table, -1, -1, table not in before_names and table not in after_names, expected_change)

    before_columns = _columns(before, table)
    after_column_names = set(_columns(after, table))
    common_columns = [column for column in before_columns if column in after_column_names]
    if not common_columns:
        return TableComparison(table, -1, -1, False, expected_change)

    before_count, before_digest = _row_digest(before, table, common_columns)
    after_count, after_digest = _row_digest(after, table, common_columns)
    return TableComparison(table, before_count, after_count, before_digest == after_digest, expected_change)


def verify_databases(
    before_path: str,
    after_path: str,
    *,
    expected_changes: Iterable[str] = ("plans",),
) -> tuple[list[TableComparison], list[str]]:
    comparisons: list[TableComparison] = []
    failures: list[str] = []
    expected = tuple(dict.fromkeys(str(item).strip() for item in expected_changes if str(item).strip()))
    with closing(sqlite3.connect(before_path)) as before, closing(sqlite3.connect(after_path)) as after:
        for table in PROTECTED_TABLES:
            expected_change = table in expected
            result = compare_table(before, after, table, expected_change=expected_change)
            comparisons.append(result)
            if not result.equal and not expected_change:
                failures.append(table)
        for table in (item for item in expected if item not in PROTECTED_TABLES):
            comparisons.append(compare_table(before, after, table, expected_change=True))
    return comparisons, failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--expect-change", action="append", default=["plans"])
    args = parser.parse_args()

    comparisons, failures = verify_databases(
        args.before,
        args.after,
        expected_changes=args.expect_change,
    )
    for item in comparisons:
        print(
            f"{item.table}=before:{item.before_count},after:{item.after_count},"
            f"equal:{str(item.equal).lower()},expected_change:{str(item.expected_change).lower()}"
        )
    if failures:
        print("protected_tables_changed=" + ",".join(failures))
        return 1
    print("protected_tables=preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
