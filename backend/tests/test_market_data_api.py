from pathlib import Path

import pytest

from app.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def api(client, auth_headers):
    client.headers.update(auth_headers)
    return client


def upload(api, content: bytes, **form: str):
    files = {"file": ("prices.csv", content, "text/csv")}
    return api.post("/api/market-data/import", files=files, data={"symbol": "BTCUSDT"} | form)


def test_import_returns_the_summary(api):
    response = upload(api, (FIXTURES / "binance_1m.csv").read_bytes())

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "BTCUSDT"
    assert body["timeframe"] == "1m"
    assert body["format"] == "binance_klines"
    assert (body["inserted"], body["duplicates"], body["rejected"]) == (3, 0, 0)
    assert body["first_ts"] == "2026-01-05T00:00:00Z"


def test_import_reports_rejected_rows(api):
    content = b"timestamp,open,high,low,close\n2026-01-05,1,2,0.5,1.5\n2026-01-06,1,0.9,0.5,1.5\n"

    body = upload(api, content, timeframe="1d").json()

    assert body["rejected"] == 1
    assert body["rejections"][0]["line"] == 3


def test_import_requires_a_token(client):
    assert upload(client, b"").status_code == 401


def test_oversized_files_are_refused(api, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.market_data.get_settings", lambda: Settings(max_upload_mb=0)
    )

    response = upload(api, (FIXTURES / "binance_1m.csv").read_bytes())

    assert response.status_code == 413


@pytest.mark.parametrize(
    ("content", "form", "detail"),
    [
        (b"x,y\n1,2\n", {}, "Could not recognise the file format"),
        (b"a,b\n", {"format": "excel"}, "Unknown file format 'excel'"),
        (b"timestamp,open,high,low,close\n\xff\xfe\n", {"timeframe": "1d"}, "not UTF-8"),
    ],
)
def test_unusable_files_are_unprocessable(api, content, form, detail):
    response = upload(api, content, **form)

    assert response.status_code == 422
    assert detail in response.json()["detail"]


def test_symbol_and_file_are_required(api):
    response = api.post("/api/market-data/import", data={"symbol": "BTCUSDT"})

    assert response.status_code == 422
