import uuid
from dataclasses import asdict
from datetime import timedelta

import pytest
from sqlalchemy import delete, select

from app.backtest import engine
from app.backtest.engine import BacktestConfig
from app.backtest.metrics import buy_and_hold, summarize
from app.enums import BacktestStatus
from app.errors import ConflictError, NotFoundError
from app.market_data.timeframes import Timeframe
from app.models import Backtest, BacktestTrade, MarketData
from app.schemas.backtest import BacktestCreate
from app.services import backtests
from app.services.market_data import load_bars
from app.strategies.definition import StrategyDefinition
from tests.helpers import ENTRY_TIME, RSI_SWINGS, make_strategy, random_bars, store_bars


@pytest.fixture
def strategy(db_session, user):
    store_bars(db_session, random_bars(300))
    return make_strategy(db_session, user, definition=RSI_SWINGS)


def create(db_session, user, strategy, **overrides) -> Backtest:
    fields = {"strategy_id": strategy.id, "symbol": "BTCUSD", "timeframe": "1m"}
    fields |= {"fee_pct": "0.1", "slippage_pct": "0.05"} | overrides
    return backtests.create_backtest(db_session, user, BacktestCreate.model_validate(fields))


def test_a_run_stores_its_results(db_session, user, strategy):
    backtest = backtests.run_backtest(db_session, create(db_session, user, strategy).id)

    bars = load_bars(db_session, "BTCUSD", Timeframe.M1)
    config = BacktestConfig(10_000, fee_pct=0.1, slippage_pct=0.05)
    expected = engine.run(bars, StrategyDefinition.model_validate(RSI_SWINGS), config)
    benchmark = buy_and_hold(bars, config)
    db_session.refresh(backtest)
    assert backtest.status == BacktestStatus.COMPLETED
    assert backtest.started_at <= backtest.completed_at
    assert (backtest.bars_count, backtest.first_bar_ts, backtest.last_bar_ts) == (
        300,
        bars.index[0],
        bars.index[-1],
    )
    assert len(backtest.data_hash) == 64
    assert backtest.metrics == asdict(summarize(expected, benchmark=benchmark))

    stored = db_session.scalars(
        select(BacktestTrade)
        .where(BacktestTrade.backtest_id == backtest.id)
        .order_by(BacktestTrade.number)
    ).all()
    assert len(expected.trades) > 5
    assert [trade.number for trade in stored] == list(range(1, len(expected.trades) + 1))
    for trade, simulated in zip(stored, expected.trades, strict=True):
        assert (trade.entry_time, trade.exit_time) == (simulated.entry_time, simulated.exit_time)
        assert (trade.direction, trade.exit_reason) == (simulated.direction, simulated.exit_reason)
        for field in ("entry_price", "exit_price", "size", "entry_fee", "exit_fee", "pnl"):
            assert float(getattr(trade, field)) == pytest.approx(getattr(simulated, field))
        assert float(trade.pnl_pct) == pytest.approx(simulated.pnl_pct, abs=5e-5)

    assert backtest.equity_curve[0] == {
        "ts": bars.index[0].isoformat(),
        "equity": 10_000,
        "benchmark": benchmark.equity.iloc[0],
    }
    assert backtest.equity_curve[-1]["equity"] == expected.equity.iloc[-1]
    assert backtest.equity_curve[-1]["benchmark"] == benchmark.equity.iloc[-1]


def test_a_run_settles_inside_bars_with_finer_ones(db_session, user, strategy):
    plain = backtests.run_backtest(
        db_session, create(db_session, user, strategy, timeframe="5m").id
    )
    detailed = backtests.run_backtest(
        db_session, create(db_session, user, strategy, timeframe="5m", detail_timeframe="1m").id
    )

    bars = load_bars(db_session, "BTCUSD", Timeframe.M5)
    finer = load_bars(db_session, "BTCUSD", Timeframe.M1)
    config = BacktestConfig(10_000, fee_pct=0.1, slippage_pct=0.05)
    detail = engine.Detail(finer, timedelta(minutes=5))
    expected = engine.run(bars, StrategyDefinition.model_validate(RSI_SWINGS), config, detail)
    db_session.refresh(detailed)
    assert detailed.status == BacktestStatus.COMPLETED
    assert detailed.metrics == asdict(summarize(expected, benchmark=buy_and_hold(bars, config)))
    # The fingerprint covers the finer bars too.
    assert detailed.data_hash == backtests.fingerprint(bars, finer) != plain.data_hash


def test_runs_over_the_same_bars_have_the_same_fingerprint(db_session, user, strategy):
    end = (ENTRY_TIME + timedelta(minutes=200)).isoformat()
    runs = [
        backtests.run_backtest(db_session, create(db_session, user, strategy, **overrides).id)
        for overrides in ({}, {"fee_pct": "0.2"}, {"end": end})
    ]

    full, same_bars, fewer_bars = (run.data_hash for run in runs)
    assert full == same_bars != fewer_bars


def test_the_fingerprint_does_not_depend_on_time_resolution():
    bars = random_bars(10)
    coarser = bars.set_axis(bars.index.as_unit("s"))

    assert backtests.fingerprint(bars) == backtests.fingerprint(coarser)


def test_a_backtest_runs_once(db_session, user, strategy):
    backtest = backtests.run_backtest(db_session, create(db_session, user, strategy).id)

    with pytest.raises(ConflictError, match="Cannot run a completed backtest"):
        backtests.run_backtest(db_session, backtest.id)


def test_an_unknown_backtest_cannot_run(db_session):
    with pytest.raises(NotFoundError):
        backtests.run_backtest(db_session, uuid.uuid4())


def assert_failed_without_results(db_session, backtest: Backtest, reason: str) -> None:
    db_session.refresh(backtest)
    assert backtest.status == BacktestStatus.FAILED
    assert backtest.error_message == reason
    assert backtest.started_at <= backtest.completed_at
    assert (backtest.metrics, backtest.equity_curve, backtest.data_hash) == (None, None, None)
    trades = select(BacktestTrade).where(BacktestTrade.backtest_id == backtest.id)
    assert db_session.scalars(trades).all() == []


def test_a_failed_run_keeps_no_partial_results(db_session, user, strategy, monkeypatch):
    # Fail after the trades are inserted, while storing the equity curve.
    def broken(equity):
        raise RuntimeError("chart data is broken")

    monkeypatch.setattr(backtests, "downsample_equity", broken)

    backtest = backtests.run_backtest(db_session, create(db_session, user, strategy).id)

    reason = "Unexpected error (RuntimeError): chart data is broken"
    assert_failed_without_results(db_session, backtest, reason)


def test_a_run_whose_bars_are_gone_fails_with_the_reason(db_session, user, strategy):
    backtest = create(db_session, user, strategy)
    db_session.execute(delete(MarketData))

    backtests.run_backtest(db_session, backtest.id)

    assert_failed_without_results(db_session, backtest, "There are no BTCUSD bars in this range")
