"""Analytics of the user's own closed trades. Open and cancelled trades have no P&L, so they
are left out. P&L is summed as recorded, without converting between quote currencies."""

from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from app.enums import TradeStatus
from app.models import Strategy, Trade, User
from app.schemas.analytics import GroupBy, PerformanceGroup, PerformanceQuery


def performance(db: Session, user: User, query: PerformanceQuery) -> list[PerformanceGroup]:
    """P&L and win rate of closed trades per strategy or symbol, best total P&L first."""
    match query.by:
        case GroupBy.SYMBOL:
            key = label = Trade.symbol
            source = Trade.__table__
        case GroupBy.STRATEGY:
            key, label = cast(Trade.strategy_id, String), Strategy.name
            source = Trade.__table__.outerjoin(Strategy, Strategy.id == Trade.strategy_id)

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
        .where(*_closed_trades(user, query))
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


def _closed_trades(user: User, query: PerformanceQuery) -> list:
    conditions = [Trade.user_id == user.id, Trade.status == TradeStatus.CLOSED]
    if query.closed_from is not None:
        conditions.append(Trade.exit_time >= query.closed_from)
    if query.closed_to is not None:
        conditions.append(Trade.exit_time < query.closed_to)
    return conditions
