"""FastAPI dependency injection."""

from __future__ import annotations

from fastapi import Request

from ..config.schema import AppConfig
from ..core.bot import PathBot
from ..core.message_store import MessageStore
from ..core.repeater_db import RepeaterDB
from ..events.bus import EventBus


def get_config(request: Request) -> AppConfig:
    return request.app.state.config


def get_bot(request: Request) -> PathBot:
    return request.app.state.bot


def get_db(request: Request) -> RepeaterDB:
    return request.app.state.db


def get_bus(request: Request) -> EventBus:
    return request.app.state.bus


def get_message_store(request: Request) -> MessageStore:
    return request.app.state.message_store
