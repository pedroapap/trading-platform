"""Your example, end to end through the API: "the moving average falls below a threshold, and
price makes a new low at the same horizontal line twice within Y bars; then buy at Z with a
stop-loss at W". Every number below is worked out by hand from the planted bars."""

import io
from decimal import Decimal

import pandas as pd
import pytest

from tests.helpers import DOUBLE_BOTTOM, double_bottom_bars, wait_for_backtest


def as_csv(bars: pd.DataFrame) -> bytes:
    return bars.rename_axis("timestamp").to_csv().encode()


def test_your_double_bottom_strategy_end_to_end(client, auth_headers):
    bars = double_bottom_bars()
    imported = client.post(
        "/api/market-data/import",
        headers=auth_headers,
        data={"symbol": "DEMOUSDT"},
        files={"file": ("double-bottom.csv", io.BytesIO(as_csv(bars)), "text/csv")},
    )
    assert (imported.status_code, imported.json()["inserted"]) == (200, len(bars))
    strategy = client.post(
        "/api/strategies",
        headers=auth_headers,
        json={"name": "Double bottom after the dip", "definition": DOUBLE_BOTTOM},
    )
    assert strategy.status_code == 201

    queued = client.post(
        "/api/backtests",
        headers=auth_headers,
        json={
            "strategy_id": strategy.json()["id"],
            "symbol": "DEMOUSDT",
            "timeframe": "1h",
            "fee_pct": "0.1",
            "slippage_pct": "0.05",
        },
    )
    backtest = wait_for_backtest(client, auth_headers, queued.json()["id"])
    assert backtest["status"] == "completed"
    trades = client.get(f"/api/backtests/{backtest['id']}/trades", headers=auth_headers).json()

    [trade] = trades["items"]
    # A limit at 88.2 * 1.003, filled inside bar 99 without slippage.
    assert trade["entry_time"] == bars.index[99].isoformat().replace("+00:00", "Z")
    assert Decimal(trade["entry_price"]) == pytest.approx(Decimal("88.4646"))
    # The stop at 88.2 * 0.99 = 87.318 makes the risk 1.1466; twice that above the entry is
    # 90.7578, reached on bar 102, and a take-profit fills without slippage.
    assert trade["exit_time"] == bars.index[102].isoformat().replace("+00:00", "Z")
    assert Decimal(trade["exit_price"]) == pytest.approx(Decimal("90.7578"))
    assert trade["exit_reason"] == "take_profit"
    assert Decimal(trade["slippage"]) == 0
