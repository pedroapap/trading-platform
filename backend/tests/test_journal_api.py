import pytest

from app.security import create_access_token
from app.services import users
from tests.helpers import make_trade


@pytest.fixture
def api(client, auth_headers):
    """POST/GET/PATCH helpers for /api/journal with the user's token."""

    class Api:
        def post(self, path="", **kwargs):
            return client.post(f"/api/journal{path}", headers=auth_headers, **kwargs)

        def get(self, path="", **kwargs):
            return client.get(f"/api/journal{path}", headers=auth_headers, **kwargs)

        def patch(self, path, **kwargs):
            return client.patch(f"/api/journal{path}", headers=auth_headers, **kwargs)

    return Api()


def new_entry(api, **fields) -> dict:
    body = {"entry_type": "post_trade", "title": "Breakout review"} | fields
    response = api.post(json=body)
    assert response.status_code == 201, response.json()
    return response.json()


def test_an_entry_is_drafted_and_read_back(api, db_session, user):
    trade = make_trade(db_session, user)

    entry = new_entry(api, trade_id=str(trade.id), emotion="frustrated", tags=["Late-Entry"])

    assert (entry["status"], entry["current_version"], entry["published_at"]) == (
        "draft",
        0,
        None,
    )
    assert (entry["trade_id"], entry["emotion"], entry["tags"]) == (
        str(trade.id),
        "frustrated",
        ["late-entry"],
    )
    assert api.get(f"/{entry['id']}").json() == entry


def test_publishing_then_editing_with_a_reason(api):
    entry = new_entry(api, lessons="Chased the move")

    published = api.post(f"/{entry['id']}/publish")
    assert (published.status_code, published.json()["status"]) == (200, "published")
    assert published.json()["current_version"] == 1

    refused = api.patch(f"/{entry['id']}", json={"lessons": "Waited for the retest"})
    assert (refused.status_code, refused.json()["detail"]) == (
        422,
        "Editing a published entry needs an edit_reason",
    )

    edited = api.patch(
        f"/{entry['id']}",
        json={"lessons": "Waited for the retest", "edit_reason": "Rewrote after review"},
    )
    assert edited.status_code == 200
    assert (edited.json()["lessons"], edited.json()["current_version"]) == (
        "Waited for the retest",
        2,
    )


def test_a_draft_is_edited_in_place(api):
    entry = new_entry(api, thesis="First idea")

    edited = api.patch(f"/{entry['id']}", json={"thesis": None, "title": "Renamed"}).json()

    assert (edited["thesis"], edited["title"], edited["current_version"]) == (None, "Renamed", 0)


def test_an_entry_is_published_once(api):
    entry = new_entry(api)
    api.post(f"/{entry['id']}/publish")

    response = api.post(f"/{entry['id']}/publish")

    assert (response.status_code, response.json()["detail"]) == (
        409,
        "The entry is already published",
    )


def test_invalid_entries_are_rejected_with_their_field(api):
    response = api.post(json={"entry_type": "note", "title": "Note", "emotion": "sleepy"})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "emotion"]


def test_an_entry_cannot_be_about_someone_elses_trade(api, db_session):
    other = users.create_user(db_session, "other@example.com", "another-long-password")
    trade = make_trade(db_session, other)

    response = api.post(json={"entry_type": "note", "title": "Note", "trade_id": str(trade.id)})

    assert (response.status_code, response.json()["detail"]) == (422, "Unknown trade")


def test_entries_are_private(api, client, db_session):
    entry = new_entry(api)
    other = users.create_user(db_session, "other@example.com", "another-long-password")
    headers = {"Authorization": f"Bearer {create_access_token(str(other.id))}"}

    assert client.get(f"/api/journal/{entry['id']}", headers=headers).status_code == 404
    assert client.post(f"/api/journal/{entry['id']}/publish", headers=headers).status_code == 404


def test_the_journal_requires_a_token(client):
    assert client.post("/api/journal", json={}).status_code == 401


@pytest.fixture
def three_entries(api, db_session, user) -> dict[str, dict]:
    """A note, then a published pre-trade entry and a post-trade draft about one trade."""
    trade_id = str(make_trade(db_session, user).id)
    note = new_entry(api, entry_type="note", title="Macro", tags=["macro"])
    plan = new_entry(
        api,
        entry_type="pre_trade",
        title="BTC plan",
        trade_id=trade_id,
        emotion="fomo",
        tags=["breakout", "fomo"],
    )
    plan = api.post(f"/{plan['id']}/publish").json()
    review = new_entry(
        api, entry_type="post_trade", title="BTC review", trade_id=trade_id, tags=["breakout"]
    )
    return {"note": note, "plan": plan, "review": review, "trade_id": trade_id}


def listed(api, **params) -> tuple[list[str], int]:
    page = api.get(params=params).json()
    return [entry["title"] for entry in page["items"]], page["total"]


def test_entries_are_listed_newest_first(api, three_entries):
    titles = [three_entries[key]["title"] for key in ("review", "plan", "note")]

    assert listed(api) == (titles, 3)
    assert listed(api, limit=1, offset=1) == ([three_entries["plan"]["title"]], 3)


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"entry_type": "pre_trade"}, ["plan"]),
        ({"status": "published"}, ["plan"]),
        ({"emotion": "fomo"}, ["plan"]),
        ({"tag": " Breakout "}, ["review", "plan"]),
        ({"tag": "macro"}, ["note"]),
    ],
)
def test_entries_can_be_filtered(api, three_entries, params, expected):
    titles = [three_entries[key]["title"] for key in expected]

    assert listed(api, **params) == (titles, len(titles))


def test_entries_can_be_filtered_by_trade_and_creation_time(api, three_entries):
    plan_created = three_entries["plan"]["created_at"]
    review, plan, note = (three_entries[key]["title"] for key in ("review", "plan", "note"))

    assert listed(api, trade_id=three_entries["trade_id"]) == ([review, plan], 2)
    assert listed(api, created_from=plan_created) == ([review, plan], 2)
    assert listed(api, created_to=plan_created) == ([note], 1)


def test_other_users_entries_are_not_listed(api, client, db_session, three_entries):
    other = users.create_user(db_session, "other@example.com", "another-long-password")
    headers = {"Authorization": f"Bearer {create_access_token(str(other.id))}"}

    assert client.get("/api/journal", headers=headers).json()["total"] == 0


def test_list_filters_are_validated(api):
    assert api.get(params={"tag": "two words"}).status_code == 422
