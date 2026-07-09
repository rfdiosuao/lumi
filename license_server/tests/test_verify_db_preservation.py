from __future__ import annotations

import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "verify_db_preservation.py"
SPEC = importlib.util.spec_from_file_location("verify_db_preservation", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def create_database(path: Path, *, code_value: str, plan_features: str) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("create table codes (code_hash text primary key, features_json text)")
        connection.execute("insert into codes values (?, ?)", (code_value, '[\"openclaw\"]'))
        connection.execute("create table plans (plan_key text primary key, features_json text)")
        connection.execute("insert into plans values ('monthly', ?)", (plan_features,))
        connection.execute("create table audit_logs (id integer primary key, action text)")
        connection.execute("insert into audit_logs values (1, 'before')")
        connection.commit()


class VerifyDatabasePreservationTests(unittest.TestCase):
    def test_allows_expected_plan_change_when_codes_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = root / "before.db"
            after = root / "after.db"
            create_database(before, code_value="hash-a", plan_features='[\"openclaw\"]')
            create_database(after, code_value="hash-a", plan_features='[\"openclaw\",\"matrix.devices\"]')

            comparisons, failures = MODULE.verify_databases(str(before), str(after))

            self.assertEqual([], failures)
            plan = next(item for item in comparisons if item.table == "plans")
            self.assertTrue(plan.expected_change)
            self.assertFalse(plan.equal)

    def test_rejects_changed_authorization_codes_without_printing_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = root / "before.db"
            after = root / "after.db"
            create_database(before, code_value="hash-a", plan_features='[\"openclaw\"]')
            create_database(after, code_value="hash-b", plan_features='[\"openclaw\"]')

            _comparisons, failures = MODULE.verify_databases(str(before), str(after))

            self.assertEqual(["codes"], failures)

    def test_allows_explicit_audit_log_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = root / "before.db"
            after = root / "after.db"
            create_database(before, code_value="hash-a", plan_features='[\"openclaw\"]')
            create_database(after, code_value="hash-a", plan_features='[\"openclaw\"]')
            with closing(sqlite3.connect(after)) as connection:
                connection.execute("insert into audit_logs values (2, 'test-cleanup')")
                connection.commit()

            comparisons, failures = MODULE.verify_databases(
                str(before),
                str(after),
                expected_changes=("audit_logs",),
            )

            self.assertEqual([], failures)
            audit = next(item for item in comparisons if item.table == "audit_logs")
            self.assertTrue(audit.expected_change)
            self.assertFalse(audit.equal)


if __name__ == "__main__":
    unittest.main()
