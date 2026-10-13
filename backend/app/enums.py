"""Domain enumerations shared by models, schemas and services."""

from enum import StrEnum


class Direction(StrEnum):
    LONG = "long"
    SHORT = "short"


class TradeStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class TradeEvent(StrEnum):
    ENTRY = "entry"
    UPDATE = "update"
    EXIT = "exit"
    CANCEL = "cancel"
    CORRECTION = "correction"


class ExitReason(StrEnum):
    """Why a backtest closed a position."""

    SIGNAL = "signal"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    END_OF_DATA = "end_of_data"
