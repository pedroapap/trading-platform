import uuid

import pytest

from app.schemas.strategy import StrategyCreate
from app.services import strategies, users
from tests.helpers import MINIMAL_DEFINITION


@pytest.fixture
def api(client, auth_headers):
    client.headers.update(auth_headers)
    return client


def create(api, name="RSI dip", **fields) -> dict:
    response = api.post(
        "/api/strategies", json={"name": name, "definition": MINIMAL_DEFINITION} | fields
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_returns_the_strategy_with_its_full_definition(api):
    body = create(api, description="Buy fear")

    assert body["name"] == "RSI dip"
    assert body["current_version"] == 1
    assert body["definition"]["entry"]["left"] == {
        "indicator": "rsi",
        "period": 14,
        "source": "close",
    }


def test_invalid_rules_report_where_they_fail(api):
    bad = MINIMAL_DEFINITION | {
        "entry": {"all": [{"left": {"indicator": "vwap"}, "op": "<", "right": {"value": 1}}]}
    }

    response = api.post("/api/strategies", json={"name": "Bad", "definition": bad})

    assert response.status_code == 422
    (error,) = response.json()["detail"]
    assert error["loc"][:5] == ["body", "definition", "entry", "all", "all"]
    assert "vwap" in error["msg"]


def test_list_and_get(api):
    first = create(api, "Trend follow")
    create(api, "Breakout")

    assert [s["name"] for s in api.get("/api/strategies").json()] == ["Breakout", "Trend follow"]
    assert api.get(f"/api/strategies/{first['id']}").json() == first


def test_foreign_and_unknown_strategies_are_not_found(api, db_session):
    other = users.create_user(db_session, "other@example.com", "another-long-password")
    foreign = strategies.create_strategy(
        db_session, other, StrategyCreate(name="Theirs", definition=MINIMAL_DEFINITION)
    )

    for strategy_id in (foreign.id, uuid.uuid4()):
        assert api.get(f"/api/strategies/{strategy_id}").status_code == 404
        assert api.patch(f"/api/strategies/{strategy_id}", json={"name": "x"}).status_code == 404


def test_patch_versions_the_definition(api):
    strategy = create(api)

    response = api.patch(
        f"/api/strategies/{strategy['id']}",
        json={"definition": MINIMAL_DEFINITION | {"stop_loss_pct": 3}},
    )

    assert response.status_code == 200
    assert response.json()["current_version"] == 2
    assert response.json()["definition"]["stop_loss_pct"] == 3


def test_duplicate_names_conflict(api):
    create(api)

    response = api.post(
        "/api/strategies", json={"name": "RSI dip", "definition": MINIMAL_DEFINITION}
    )

    assert response.status_code == 409


def test_strategies_require_a_token(client):
    assert client.get("/api/strategies").status_code == 401


def test_versions_record_the_history(api):
    strategy = create(api)
    url = f"/api/strategies/{strategy['id']}"
    api.patch(url, json={"definition": MINIMAL_DEFINITION | {"stop_loss_pct": 3}})
    api.patch(url, json={"definition": MINIMAL_DEFINITION | {"direction": "short"}})

    history = api.get(f"{url}/versions").json()

    assert [(v["version"], v["changed_fields"]) for v in history] == [
        (1, None),
        (2, ["stop_loss_pct"]),
        (3, ["direction", "stop_loss_pct"]),
    ]
    assert api.get(f"{url}/versions/1").json() == history[0]
    assert api.get(f"{url}/versions/1").json()["definition"] == strategy["definition"]


def test_unknown_versions_are_not_found(api):
    strategy = create(api)
    url = f"/api/strategies/{strategy['id']}/versions"

    assert api.get(f"{url}/2").json() == {"detail": "The strategy has no version 2"}
    assert api.get(f"{url}/0").status_code == 422
    assert api.get(f"/api/strategies/{uuid.uuid4()}/versions").status_code == 404
