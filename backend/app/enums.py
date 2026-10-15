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


class BacktestStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ExitReason(StrEnum):
    """Why a backtest closed a position."""

    SIGNAL = "signal"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    END_OF_DATA = "end_of_data"
    TRAILING_STOP = "trailing_stop"
    TIME_EXIT = "time_exit"


class EntryType(StrEnum):
    PRE_TRADE = "pre_trade"
    POST_TRADE = "post_trade"
    NOTE = "note"


class Emotion(StrEnum):
    """How the trader felt, for spotting which states cost money."""

    CALM = "calm"
    CONFIDENT = "confident"
    EXCITED = "excited"
    GREEDY = "greedy"
    FOMO = "fomo"
    FEARFUL = "fearful"
    FRUSTRATED = "frustrated"
    IMPATIENT = "impatient"
    UNCERTAIN = "uncertain"


class JournalStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
