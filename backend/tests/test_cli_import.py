from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app import cli
from app.models import MarketData

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def test_session(db_session, monkeypatch):
    @contextmanager
    def scope():
        yield db_session

    monkeypatch.setattr(cli, "session_scope", scope)


def test_cli_imports_a_file(db_session, capsys):
    exit_code = cli.main(["import-csv", str(FIXTURES / "binance_1m.csv"), "--symbol", "btcusdt"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Imported 3 1m bars for BTCUSDT (binance_klines): 0 already stored" in output
    assert db_session.scalar(select(func.count()).select_from(MarketData)) == 3


def test_cli_reports_rejected_rows(tmp_path, capsys):
    path = tmp_path / "prices.csv"
    path.write_text("date,open,high,low,close\n2026-01-05,1,2,0.5,1.5\n2026-01-06,1,0.9,0.5,1.5\n")

    exit_code = cli.main(["import-csv", str(path), "--symbol", "BTC", "--timeframe", "1d"])

    assert exit_code == 0
    assert "line 3: low/high do not bracket open and close" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("path", "message"),
    [("missing.csv", "Cannot read missing.csv"), (__file__, "Import failed")],
)
def test_cli_fails_cleanly(path, message, capsys):
    assert cli.main(["import-csv", path, "--symbol", "BTCUSD"]) == 1
    assert message in capsys.readouterr().err
