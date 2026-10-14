from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.enums import BacktestStatus, Direction, ExitReason
from app.models import Backtest, BacktestTrade
from tests.helpers import ENTRY_TIME, make_backtest, make_strategy


def test_a_backtest_starts_pending(db_session, user):
    backtest = make_backtest(db_session, user, make_strategy(db_session, user))

    assert backtest.status == BacktestStatus.PENDING
    assert backtest.created_at is not None


def test_a_backtest_needs_an_existing_strategy_version(db_session, user):
    strategy = make_strategy(db_session, user)

    with pytest.raises(IntegrityError, match="fk_backtests_strategy_id_strategy_versions"):
        make_backtest(db_session, user, strategy, strategy_version=2)


def test_a_backtest_needs_a_registered_symbol(db_session, user):
    backtest = make_backtest(db_session, user, make_strategy(db_session, user))

    with pytest.raises(IntegrityError, match="fk_backtests_symbol_instruments"):
        db_session.execute(
            text("UPDATE backtests SET symbol = 'UNREGISTERED' WHERE id = :id"),
            {"id": backtest.id},
        )


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"initial_capital": Decimal(0)}, "initial_capital_positive"),
        ({"position_size_pct": Decimal(0)}, "position_size_in_range"),
        ({"position_size_pct": Decimal("100.5")}, "position_size_in_range"),
        ({"fee_pct": Decimal(-1)}, "fee_in_range"),
        ({"slippage_pct": Decimal(11)}, "slippage_in_range"),
        ({"periods_per_year": 0}, "periods_per_year_in_range"),
        ({"start_ts": ENTRY_TIME, "end_ts": ENTRY_TIME}, "range_not_empty"),
    ],
)
def test_invalid_parameters_are_rejected(db_session, user, overrides, constraint):
    strategy = make_strategy(db_session, user)

    with pytest.raises(IntegrityError, match=f"ck_backtests_{constraint}"):
        make_backtest(db_session, user, strategy, **overrides)


def test_a_failed_backtest_says_why(db_session, user):
    strategy = make_strategy(db_session, user)

    with pytest.raises(IntegrityError, match="ck_backtests_failed_has_reason"):
        make_backtest(db_session, user, strategy, status=BacktestStatus.FAILED)


def test_a_completed_backtest_has_results(db_session, user):
    strategy = make_strategy(db_session, user)

    with pytest.raises(IntegrityError, match="ck_backtests_completed_has_results"):
        make_backtest(db_session, user, strategy, status=BacktestStatus.COMPLETED)


def make_backtest_trade(backtest: Backtest, number: int = 1, **overrides: object) -> BacktestTrade:
    values: dict[str, object] = {
        "direction": Direction.LONG,
        "entry_time": ENTRY_TIME,
        "entry_price": Decimal("100"),
        "exit_time": ENTRY_TIME + timedelta(days=1),
        "exit_price": Decimal("110"),
        "size": Decimal("1"),
        "entry_fee": Decimal("0"),
        "exit_fee": Decimal("0"),
        "slippage": Decimal("0"),
        "pnl": Decimal("10"),
        "pnl_pct": Decimal("10"),
        "exit_reason": ExitReason.SIGNAL,
    }
    return BacktestTrade(backtest_id=backtest.id, number=number, **(values | overrides))


def test_trade_numbers_are_unique_per_backtest(db_session, user):
    backtest = make_backtest(db_session, user, make_strategy(db_session, user))
    db_session.add(make_backtest_trade(backtest, 1))
    db_session.flush()

    db_session.add(make_backtest_trade(backtest, 1))
    with pytest.raises(IntegrityError, match="pk_backtest_trades"):
        db_session.flush()


def test_a_trade_cannot_exit_before_it_enters(db_session, user):
    backtest = make_backtest(db_session, user, make_strategy(db_session, user))

    db_session.add(make_backtest_trade(backtest, exit_time=ENTRY_TIME - timedelta(minutes=1)))
    with pytest.raises(IntegrityError, match="ck_backtest_trades_exit_not_before_entry"):
        db_session.flush()


def test_trades_are_deleted_with_their_backtest(db_session, user):
    backtest = make_backtest(db_session, user, make_strategy(db_session, user))
    db_session.add_all([make_backtest_trade(backtest, 1), make_backtest_trade(backtest, 2)])
    db_session.flush()

    db_session.delete(backtest)
    db_session.flush()

    assert db_session.scalars(select(BacktestTrade)).all() == []
