"""Postgres service: wait until ready, take row snapshots, reset between scenarios.

All SQL runs through `docker exec ... psql`, so no database port is opened to the host.
"""

import json
import logging
import time
from collections import Counter
from collections.abc import Callable
from typing import Any

from migrator.baseline.models import TableChange

log = logging.getLogger(__name__)

POSTGRES_IMAGE = "postgres:16-alpine"
DB_USER = DB_PASSWORD = DB_NAME = "app"
DB_PORT = 5432
DB_HOST = "db"  # network alias inside the sandbox network

# Bookkeeping tables of migration tools. Resetting them would break the app.
IGNORED_TABLES = {
    "alembic_version",
    "migrations",
    "typeorm_metadata",
    "knex_migrations",
    "knex_migrations_lock",
    "schema_migrations",
    "flyway_schema_history",
    "django_migrations",
}
# Constraint names are left out on purpose: they are generated and differ between ORMs.
SCHEMA_COLUMNS_SQL = """
SELECT coalesce(json_agg(c ORDER BY c.table_name, c.position), '[]') FROM (
    SELECT table_name, column_name, ordinal_position AS position, data_type,
           is_nullable, column_default
    FROM information_schema.columns WHERE table_schema = 'public'
) c
"""
SCHEMA_CONSTRAINTS_SQL = """
SELECT coalesce(json_agg(k ORDER BY k.table_name, k.type, k.columns), '[]') FROM (
    SELECT tc.table_name, tc.constraint_type AS type,
           string_agg(kcu.column_name, ',' ORDER BY kcu.ordinal_position) AS columns
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
    WHERE tc.table_schema = 'public'
    GROUP BY tc.table_name, tc.constraint_name, tc.constraint_type
) k
"""
TABLES_PER_QUERY = 40  # json_build_object takes at most 100 arguments

Snapshot = dict[str, list[dict[str, Any]]]
DockerOutput = Callable[..., str | None]


class Postgres:
    def __init__(self, container: str, docker_output: DockerOutput) -> None:
        self.container = container
        self.docker_output = docker_output

    def wait_ready(self, timeout_s: int = 60) -> None:
        # Use TCP (-h 127.0.0.1). During first-time init Postgres listens only on the unix
        # socket, so a socket check would say "ready" too early.
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            check = self.docker_output(
                "exec", self.container, "pg_isready", "-h", "127.0.0.1", "-U", DB_USER
            )
            if check is not None:
                log.info("Postgres is ready")
                return
            time.sleep(0.5)
        raise RuntimeError(f"Postgres did not become ready in {timeout_s}s")

    def tables(self) -> list[str]:
        sql = (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY 1"
        )
        names = self._query(sql).splitlines()
        return [name for name in names if name and name not in IGNORED_TABLES]

    def snapshot(self) -> Snapshot:
        tables = self.tables()
        snapshot: Snapshot = {}
        for start in range(0, len(tables), TABLES_PER_QUERY):
            chunk = tables[start : start + TABLES_PER_QUERY]
            parts = [
                f"{_literal(t)}, (SELECT coalesce(json_agg(t), '[]') FROM {_identifier(t)} t)"
                for t in chunk
            ]
            snapshot.update(
                json.loads(self._query(f"SELECT json_build_object({', '.join(parts)})"))
            )
        return snapshot

    def schema(self) -> dict[str, list[dict[str, Any]]]:
        """Columns and constraints of app tables, so schema changes are noticed too."""
        columns = json.loads(self._query(SCHEMA_COLUMNS_SQL))
        constraints = json.loads(self._query(SCHEMA_CONSTRAINTS_SQL))
        return {
            "columns": [c for c in columns if c["table_name"] not in IGNORED_TABLES],
            "constraints": [c for c in constraints if c["table_name"] not in IGNORED_TABLES],
        }

    def reset(self) -> None:
        """Empty every table and restart id sequences, so ids are the same on every run."""
        tables = self.tables()
        if tables:
            names = ", ".join(_identifier(t) for t in tables)
            self._query(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE")
        log.debug("Database reset (%d tables)", len(tables))

    def _query(self, sql: str) -> str:
        psql = ["psql", "-U", DB_USER, "-d", DB_NAME, "-v", "ON_ERROR_STOP=1", "-At", "-c", sql]
        output = self.docker_output("exec", self.container, *psql)
        if output is None:
            raise RuntimeError(f"Database query failed: {sql[:100]}")
        return output


def diff_snapshots(before: Snapshot, after: Snapshot) -> dict[str, TableChange]:
    """Rows added and removed per table. A changed row shows as one removed + one added."""
    changes: dict[str, TableChange] = {}
    for table in sorted(set(before) | set(after)):
        old = Counter(_canonical(row) for row in before.get(table, []))
        new = Counter(_canonical(row) for row in after.get(table, []))
        added = [json.loads(row) for row in (new - old).elements()]
        removed = [json.loads(row) for row in (old - new).elements()]
        if added or removed:
            changes[table] = TableChange(
                added=sorted(added, key=_row_key), removed=sorted(removed, key=_row_key)
            )
    return changes


def _canonical(row: dict[str, Any]) -> str:
    return json.dumps(row, sort_keys=True, default=str)


def _row_key(row: dict[str, Any]) -> tuple:
    """Sort by numeric id when there is one, else by the full row."""
    row_id = row.get("id")
    if isinstance(row_id, int):
        return (0, row_id, "")
    return (1, 0, _canonical(row))


def _identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _literal(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"
