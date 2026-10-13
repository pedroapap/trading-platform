"""The whole workflow through the API: import prices, define a strategy, backtest it.

The prices follow a sine wave, so a strategy that buys as RSI turns up from oversold and
sells as it turns down from overbought wins every trade. The original backtester could never
close a long at a profit; this guards against anything like it.
"""

from decimal import Decimal
from itertools import pairwise

import numpy as np
import pandas as pd
import pytest

from tests.helpers import wait_for_backtest

HOURS = 60 * 24
CYCLE_HOURS = 96

RSI_REVERSAL = {
    "direction": "long",
    "entry": {"left": {"indicator": "rsi"}, "op": "crosses_above", "right": {"value": 30}},
    "exit": {"left": {"indicator": "rsi"}, "op": "crosses_below", "right": {"value": 70}},
}


def sine_wave_csv() -> str:
    """Hourly bars whose closes swing between 90 and 110 every CYCLE_HOURS."""
    prices = 100 + 10 * np.sin(2 * np.pi * np.arange(HOURS + 1) / CYCLE_HOURS)
    start = pd.Timestamp("2026-01-01", tz="UTC")
    lines = ["timestamp,open,high,low,close,volume"]
    for hour, (open_, close) in enumerate(pairwise(prices)):
        ts = (start + pd.Timedelta(hours=hour)).isoformat()
        high, low = max(open_, close) + 0.25, min(open_, close) - 0.25
        lines.append(f"{ts},{open_:.6f},{high:.6f},{low:.6f},{close:.6f},1")
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize(
    ("timeframe", "bars"), [("1h", HOURS), ("4h", HOURS // 4)], ids=["stored", "aggregated"]
)
def test_a_backtest_of_imported_prices_makes_winning_trades(client, auth_headers, timeframe, bars):
    imported = client.post(
        "/api/market-data/import",
        headers=auth_headers,
        data={"symbol": "SINEUSD"},
        files={"file": ("sine.csv", sine_wave_csv(), "text/csv")},
    )
    assert (imported.status_code, imported.json()["inserted"]) == (200, HOURS)

    strategy = client.post(
        "/api/strategies",
        headers=auth_headers,
        json={"name": "RSI reversal", "definition": RSI_REVERSAL},
    )
    assert strategy.status_code == 201

    queued = client.post(
        "/api/backtests",
        headers=auth_headers,
        json={
            "strategy_id": strategy.json()["id"],
            "symbol": "SINEUSD",
            "timeframe": timeframe,
            "fee_pct": "0.1",
            "slippage_pct": "0.05",
        },
    )
    assert queued.status_code == 202

    backtest = wait_for_backtest(client, auth_headers, queued.json()["id"])
    assert backtest["status"] == "completed", backtest["error_message"]
    assert backtest["bars_count"] == bars
    metrics = backtest["metrics"]
    assert metrics["num_trades"] >= 10
    assert metrics["win_rate_pct"] == 100
    assert metrics["total_return_pct"] > 0

    trades = client.get(f"/api/backtests/{backtest['id']}/trades", headers=auth_headers).json()[
        "items"
    ]
    assert len(trades) == metrics["num_trades"]
    for trade in trades:
        assert Decimal(trade["exit_price"]) > Decimal(trade["entry_price"])
        assert Decimal(trade["pnl"]) > 0
