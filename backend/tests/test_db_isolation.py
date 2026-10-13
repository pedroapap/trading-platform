"""Each test's writes, including committed ones, must be gone before the next test."""

import pytest
from sqlalchemy import text


@pytest.fixture(scope="module", autouse=True)
def probe_table(engine):
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE isolation_probe (id int PRIMARY KEY)"))
    yield
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE isolation_probe"))


@pytest.mark.parametrize("attempt", [1, 2])
def test_committed_rows_do_not_leak_between_tests(db_session, attempt):
    db_session.execute(text("INSERT INTO isolation_probe (id) VALUES (1)"))
    db_session.commit()

    count = db_session.execute(text("SELECT count(*) FROM isolation_probe")).scalar_one()
    assert count == 1
