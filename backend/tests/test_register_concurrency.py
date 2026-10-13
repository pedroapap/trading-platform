"""Concurrent first registrations must still create exactly one account.

This test needs real commits on separate connections, so it bypasses the rolled-back
`db_session` fixture and deletes what it created.
"""

import threading

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_db, get_session_factory
from app.main import app
from app.models import User


def test_concurrent_registrations_create_one_account(engine):
    def committed_session():
        with Session(engine, expire_on_commit=False) as session:
            yield session

    statuses: list[int] = []
    barrier = threading.Barrier(5)

    def register(client: TestClient, i: int) -> None:
        barrier.wait()
        body = {"email": f"user{i}@example.com", "password": "x" * 12}
        statuses.append(client.post("/api/auth/register", json=body).status_code)

    app.dependency_overrides[get_db] = committed_session
    # Startup's own work must also use the test database.
    app.dependency_overrides[get_session_factory] = lambda: sessionmaker(engine)
    try:
        with TestClient(app) as client:
            threads = [threading.Thread(target=register, args=(client, i)) for i in range(5)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        with Session(engine) as session:
            accounts = session.scalar(select(func.count()).select_from(User))
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_session_factory, None)
        with engine.begin() as conn:
            conn.execute(delete(User))

    assert sorted(statuses) == [201, 403, 403, 403, 403]
    assert accounts == 1
