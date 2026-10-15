"""Execute a reviewed SQL migration file verbatim.

``Connection.exec_driver_sql`` passes an (empty) parameter set, which makes psycopg
treat every ``%`` in the file - including PL/pgSQL ``RAISE '... %'`` format
markers - as a bind placeholder. Executing through the DBAPI cursor with no
parameters sends the file exactly as reviewed, inside Alembic's transaction.
"""

from pathlib import Path

from sqlalchemy.engine import Connection

SQL_DIR = Path(__file__).resolve().parents[2] / "alembic" / "sql"


def execute_sql_file(bind: Connection, filename: str) -> None:
    sql = (SQL_DIR / filename).read_text(encoding="utf-8")
    cursor = bind.connection.dbapi_connection.cursor()  # type: ignore[union-attr]
    try:
        cursor.execute(sql)
    finally:
        cursor.close()
