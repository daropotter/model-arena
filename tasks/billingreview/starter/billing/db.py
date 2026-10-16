"""SQLite connection, transactions and the migration runner.

Migrations are billing/migrations/NNNN_name.py modules with an
up(conn) function. Each runs in its own transaction together with its
schema_migrations row, so a failing migration leaves no trace. A module
that sets FOREIGN_KEYS_OFF = True runs with foreign keys disabled (needed
to rebuild a referenced table) and is checked with foreign_key_check.
"""

import importlib.util
import itertools
import sqlite3
from contextlib import contextmanager
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_savepoints = itertools.count()


def connect(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    return conn


@contextmanager
def transaction(conn):
    """BEGIN IMMEDIATE ... COMMIT, or a savepoint when already inside one."""
    if conn.in_transaction:
        name = f"sp{next(_savepoints)}"
        conn.execute(f"SAVEPOINT {name}")
        try:
            yield conn
        except BaseException:
            conn.execute(f"ROLLBACK TO {name}")
            conn.execute(f"RELEASE {name}")
            raise
        conn.execute(f"RELEASE {name}")
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def migration_files():
    return sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.py"))


def load_migration(path):
    spec = importlib.util.spec_from_file_location(f"billing_migration_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def migrate(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations ("
                 "name TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    done = {row[0] for row in conn.execute("SELECT name FROM schema_migrations")}
    for path in migration_files():
        if path.stem in done:
            continue
        module = load_migration(path)
        fk_off = getattr(module, "FOREIGN_KEYS_OFF", False)
        if fk_off:
            # table rebuilds: the pragma is a no-op inside a transaction,
            # so switch it before BEGIN and verify integrity before COMMIT
            conn.execute("PRAGMA foreign_keys = OFF")
        try:
            with transaction(conn):
                module.up(conn)
                if fk_off and conn.execute("PRAGMA foreign_key_check").fetchone():
                    raise sqlite3.IntegrityError(f"{path.stem}: foreign key violations")
                conn.execute("INSERT INTO schema_migrations (name) VALUES (?)", (path.stem,))
        finally:
            if fk_off:
                conn.execute("PRAGMA foreign_keys = ON")
