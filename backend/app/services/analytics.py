"""Analytics of the user's own closed trades. Open and cancelled trades have no P&L, so they
are left out. P&L is summed as recorded, without converting between quote currencies."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, String, cast, func, select
from sqlalchemy.orm import Session

from app.enums import BacktestStatus, TradeStatus
from app.errors import ConflictError
from app.models import BacktestTrade, JournalEntry, Strategy, Trade, User
from app.schemas.analytics import (
    BacktestComparison,
    ComparisonSide,
    EquityQuery,
    GroupBy,
    PerformanceGroup,
    PerformanceQuery,
    RealizedEquity,
    RealizedPoint,
)
from app.services import backtests


def performance(db: Session, user: User, query: PerformanceQuery) -> list[PerformanceGroup]:
    """P&L and win rate of closed trades per strategy, symbol, emotion or tag, best total P&L
    first. A trade counts once in each emotion or tag that its journal entries record."""
    match query.by:
        case GroupBy.SYMBOL:
            key = label = Trade.symbol
            source = Trade.__table__
        case GroupBy.STRATEGY:
            key, label = cast(Trade.strategy_id, String), Strategy.name
            source = Trade.__table__.outerjoin(Strategy, Strategy.id == Trade.strategy_id)
        case GroupBy.EMOTION | GroupBy.TAG:
            notes = _journal_keys(user, query).subquery()
            key = label = notes.c.key
            source = Trade.__table__.outerjoin(notes, notes.c.trade_id == Trade.id)

    total = func.sum(Trade.pnl)
    statement = (
        select(
            key.label("key"),
            label.label("label"),
            func.count().label("num_trades"),
            func.count().filter(Trade.pnl > 0).label("wins"),
            func.count().filter(Trade.pnl < 0).label("losses"),
            total.label("total_pnl"),
            func.round(func.avg(Trade.pnl), 12).label("average_pnl"),
        )
        .select_from(source)
        .where(*_closed_trades(user, query.closed_from, query.closed_to))
        .group_by(key, label)
        .order_by(total.desc(), key.asc().nulls_last())
    )
    return [
        PerformanceGroup(
            key=row.key,
            label=row.label,
            num_trades=row.num_trades,
            wins=row.wins,
            losses=row.losses,
            win_rate_pct=row.wins / row.num_trades * 100,
            total_pnl=row.total_pnl,
            average_pnl=row.average_pnl,
        )
        for row in db.execute(statement)
    ]


def compare_with_backtest(db: Session, user: User, backtest_id: uuid.UUID) -> BacktestComparison:
    """A completed backtest next to the live trades that followed the same strategy version on
    the same symbol, entered while its bars ran."""
    backtest = backtests.get_backtest(db, user, backtest_id)
    if backtest.status != BacktestStatus.COMPLETED:
        raise ConflictError(
            f"Only a completed backtest can be compared; this one is {backtest.status}"
        )
    period_end = backtest.last_bar_ts + backtest.timeframe.delta
    live = select(Trade.pnl, (Trade.pnl_pct / Trade.leverage).label("return_pct")).where(
        *_closed_trades(user, None, None),
        Trade.strategy_id == backtest.strategy_id,
        Trade.strategy_version == backtest.strategy_version,
        Trade.symbol == backtest.symbol,
        Trade.entry_time >= backtest.first_bar_ts,
        Trade.entry_time < period_end,
    )
    simulated = select(BacktestTrade.pnl, BacktestTrade.pnl_pct.label("return_pct")).where(
        BacktestTrade.backtest_id == backtest.id
    )
    return BacktestComparison(
        backtest_id=backtest.id,
        strategy_id=backtest.strategy_id,
        strategy_version=backtest.strategy_version,
        symbol=backtest.symbol,
        period_start=backtest.first_bar_ts,
        period_end=period_end,
        live=_comparison_side(db, live),
        backtest=_comparison_side(db, simulated),
    )


def _comparison_side(db: Session, trades: Select) -> ComparisonSide:
    """Statistics of a query's rows, each a trade's `pnl` and `return_pct`."""
    rows = trades.subquery()
    stats = db.execute(
        select(
            func.count().label("num_trades"),
            func.count().filter(rows.c.pnl > 0).label("wins"),
            func.round(func.avg(rows.c.return_pct), 4).label("average_return_pct"),
            func.coalesce(func.sum(rows.c.pnl), 0).label("total_pnl"),
        )
    ).one()
    return ComparisonSide(
        num_trades=stats.num_trades,
        win_rate_pct=stats.wins / stats.num_trades * 100 if stats.num_trades else None,
        average_return_pct=stats.average_return_pct,
        total_pnl=stats.total_pnl,
    )


def _journal_keys(user: User, query: PerformanceQuery):
    """Each trade's distinct emotions or tags, from the user's journal entries about it."""
    if query.by == GroupBy.EMOTION:
        keys = select(JournalEntry.trade_id, JournalEntry.emotion.label("key"))
        keys = keys.where(JournalEntry.emotion.is_not(None))
    else:
        keys = select(JournalEntry.trade_id, func.unnest(JournalEntry.tags).label("key"))
    keys = keys.where(JournalEntry.user_id == user.id, JournalEntry.trade_id.is_not(None))
    if query.entry_type is not None:
        keys = keys.where(JournalEntry.entry_type == query.entry_type)
    return keys.distinct()


def realized_equity(db: Session, user: User, query: EquityQuery) -> RealizedEquity:
    """Closed trades' P&L accumulated in closing order, with the deepest drawdown."""
    conditions = _closed_trades(user, query.closed_from, query.closed_to)
    if query.symbol is not None:
        conditions.append(Trade.symbol == query.symbol)
    if query.strategy_id is not None:
        conditions.append(Trade.strategy_id == query.strategy_id)
    rows = db.execute(
        select(Trade.id, Trade.exit_time, Trade.pnl)
        .where(*conditions)
        .order_by(Trade.exit_time, Trade.entry_time, Trade.id)
    )

    points: list[RealizedPoint] = []
    cumulative = high = max_drawdown = Decimal(0)
    for trade_id, exit_time, pnl in rows:
        cumulative += pnl
        high = max(high, cumulative)
        max_drawdown = max(max_drawdown, high - cumulative)
        points.append(
            RealizedPoint(ts=exit_time, trade_id=trade_id, pnl=pnl, cumulative_pnl=cumulative)
        )
    return RealizedEquity(points=points, total_pnl=cumulative, max_drawdown=max_drawdown)


def _closed_trades(user: User, closed_from: datetime | None, closed_to: datetime | None) -> list:
    conditions = [Trade.user_id == user.id, Trade.status == TradeStatus.CLOSED]
    if closed_from is not None:
        conditions.append(Trade.exit_time >= closed_from)
    if closed_to is not None:
        conditions.append(Trade.exit_time < closed_to)
    return conditions
