"""Backtests: a strategy version run over a symbol's bars."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import InvalidOperationError
from app.models import Backtest, Strategy, User
from app.schemas.backtest import BacktestCreate
from app.services import market_data


def create_backtest(db: Session, user: User, data: BacktestCreate) -> Backtest:
    """A pending backtest, after checking the strategy version and that there are bars."""
    owned = select(Strategy).where(Strategy.id == data.strategy_id, Strategy.user_id == user.id)
    strategy = db.scalar(owned)
    if strategy is None:
        raise InvalidOperationError("Unknown strategy")
    version = data.strategy_version or strategy.current_version
    if version > strategy.current_version:
        raise InvalidOperationError(f"The strategy has no version {version}")
    market_data.require_bars(db, data.symbol, data.timeframe, data.start, data.end)

    backtest = Backtest(
        user_id=user.id,
        strategy_id=strategy.id,
        strategy_version=version,
        symbol=data.symbol,
        timeframe=data.timeframe,
        start_ts=data.start,
        end_ts=data.end,
        initial_capital=data.initial_capital,
        position_size_pct=data.position_size_pct,
        fee_pct=data.fee_pct,
        slippage_pct=data.slippage_pct,
        periods_per_year=data.periods_per_year,
    )
    db.add(backtest)
    db.commit()
    db.refresh(backtest)
    return backtest
