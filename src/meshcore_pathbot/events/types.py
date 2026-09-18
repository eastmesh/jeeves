"""Internal application event types."""

from enum import Enum, auto


class AppEvent(Enum):
    """Events for cross-component communication within pathbot."""

    MSG_IN = auto()
    MSG_OUT = auto()
    REPEATER_UPDATE = auto()
    REPEATER_DELETE = auto()
    STATS_UPDATE = auto()
    CONFIG_UPDATE = auto()
    BOT_CONNECTED = auto()
    BOT_DISCONNECTED = auto()
    ERROR = auto()
