"""Run db_checks/constraints_check.sql against the migrated test database.

The script raises on the first rule the database fails to enforce, and rolls
everything back, so a clean run means every check passed.
"""

from pathlib import Path

import psycopg
import pytest
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.integration

SCRIPT = Path(__file__).resolve().parents[1] / "db_checks" / "constraints_check.sql"


def test_database_enforces_every_listed_rule(database_url: str) -> None:
    url = make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)
    sql = SCRIPT.read_text(encoding="utf-8").replace(
        "ROLLBACK;", ""
    )  # keep the log readable before rollback
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)  # no parameters: sent verbatim; raises on any failed check
            cur.execute("SELECT count(*) FROM check_log WHERE outcome LIKE 'PASS%'")
            passed = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM check_log")
            total = cur.fetchone()[0]
        conn.rollback()
    assert (
        passed == total == 33
    )  # 7 provenance, 16 observation, 6 publication, 4 account/history checks
