"""Your example, end to end through the API: "the moving average falls below a threshold, and
price makes a new low at the same horizontal line twice within Y bars; then buy at Z with a
stop-loss at W". Every number below is worked out by hand from the planted bars."""

import io
from decimal import Decimal

import pandas as pd
import pytest

from tests.helpers import ENTRY_TIME, wait_for_backtest

# The 50-bar SMA crossed below 100 within the last 48 bars, and price made two swing lows (3
# bars on each side) within 0.5% of each other within 48 bars: buy with a limit 0.3% above the
# latest low, for 6 bars, with the stop 1% under that low and the target at twice the risk.
DOUBLE_BOTTOM = {
    "direction": "long",
    "entry": {
        "all": [
            {
                "happened": {
                    "left": {"indicator": "sma", "period": 50},
                    "op": "crosses_below",
                    "right": {"value": 100},
                },
                "within": 48,
            },
            {
                "pattern": "equal_lows",
                "strength": 3,
                "times": 2,
                "within": 48,
                "tolerance_pct": 0.5,
            },
        ]
    },
    "entry_order": {
        "type": "limit",
        "price": {"multiply": [{"indicator": "swing_low", "strength": 3}, {"value": 1.003}]},
        "expires_after": 6,
    },
    "stop_loss_at": {"multiply": [{"indicator": "swing_low", "strength": 3}, {"value": 0.99}]},
    "take_profit_r": 2,
}

# fmt: off
PLANTED = [
    # open,  high,  low, close
    (90.0, 90.3, 89.0, 89.2),  # 80  the slide
    (89.2, 89.4, 88.6, 88.8),  # 81
    (88.8, 89.0, 88.4, 88.5),  # 82
    (88.5, 88.7, 88.2, 88.3),  # 83
    (88.3, 88.5, 88.1, 88.2),  # 84
    (88.2, 88.6, 88.0, 88.5),  # 85  first low: 88.0, a swing low once bar 88 closes
    (88.5, 89.5, 88.4, 89.3),  # 86
    (89.3, 90.5, 89.2, 90.3),  # 87
    (90.3, 91.0, 90.0, 90.8),  # 88  the bounce
    (90.8, 90.9, 90.0, 90.1),  # 89
    (90.1, 90.2, 89.4, 89.5),  # 90
    (89.5, 89.6, 88.9, 89.0),  # 91
    (89.0, 89.1, 88.6, 88.7),  # 92
    (88.7, 88.8, 88.4, 88.5),  # 93
    (88.5, 88.6, 88.3, 88.4),  # 94
    (88.4, 88.7, 88.2, 88.6),  # 95  second low: 88.2, 0.2 above the first (0.5% is 0.441)
    (88.6, 89.4, 88.5, 89.2),  # 96
    (89.2, 89.9, 89.1, 89.7),  # 97
    (89.7, 90.0, 89.4, 89.5),  # 98  the low of 88.2 is confirmed: buy at 88.4646 or better
    (89.5, 89.6, 88.4, 89.0),  # 99  the low of 88.4 reaches it; the stop at 87.318 isn't
    (89.0, 89.5, 88.8, 89.3),  # 100
    (89.3, 90.0, 89.2, 89.9),  # 101
    (89.9, 90.9, 89.8, 90.5),  # 102 the target at 90.7578 is reached
    (90.5, 90.8, 90.3, 90.6),  # 103
    (90.6, 90.9, 90.4, 90.7),  # 104
]
# fmt: on


def double_bottom_bars() -> pd.DataFrame:
    """Hourly bars: 50 at 110, then 30 at 90, so the SMA(50) is exactly 100 on bar 74 and 99.6
    on bar 75, where it crosses below 100; then the planted double bottom."""
    rows = (
        [(110.0, 110.3, 109.7, 110.0)] * 50
        + [(110.0, 110.3, 89.7, 90.0)]  # 50: the drop
        + [(90.0, 90.3, 89.7, 90.0)] * 29  # 51-79: flat, so no swing lows
        + PLANTED
    )
    bars = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    bars["volume"] = 1.0
    bars.index = pd.date_range(ENTRY_TIME.replace(hour=0, minute=0), periods=len(rows), freq="h")
    return bars


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
