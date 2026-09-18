from __future__ import annotations

import asyncio
from types import SimpleNamespace

from meshcore_pathbot.config.schema import AppConfig, ChannelConfig
from meshcore_pathbot.core.bot import PathBot, _PAYLOAD_TYPE_CHANNEL_MSG
from meshcore_pathbot.events.bus import EventBus


class DummyDB:
    def get_by_prefix(self, prefix: str):
        return []


class DummyStore:
    async def add(self, *args, **kwargs):
        return None

    async def add_event(self, *args, **kwargs):
        return None

    def get_paths_for_peer(self, peer: str):
        return []


class DummyCommands:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_chan_msg(self, channel_id: int, text: str):
        self.sent.append((channel_id, text))
        return SimpleNamespace(type=None, payload={})


def _make_bot(channel_ids: list[int]) -> tuple[PathBot, DummyCommands]:
    config = AppConfig()
    config.bot.channels = [
        ChannelConfig(id=i, enabled_commands=["ping"], rate_limit_enabled=False)
        for i in channel_ids
    ]
    bot = PathBot(config=config, db=DummyDB(), bus=EventBus(), message_store=DummyStore())
    commands = DummyCommands()
    bot._mc = SimpleNamespace(commands=commands)
    return bot, commands


def test_configured_region_accepts_matching_transport_code() -> None:
    bot, commands = _make_bot([2])
    bot.config.bot.flood_scope = "au-vic"
    bot._chan_hash_by_idx = {2: "aa"}

    asyncio.run(bot._on_rx_log_data(SimpleNamespace(payload={
        "chan_hash": "aa",
        "payload_type": _PAYLOAD_TYPE_CHANNEL_MSG,
        "route_type": 0x00,
        "transport_code": "9683a543",
        "path_len": 1,
        "path_hash_size": 1,
        "path": "a1",
    })))
    asyncio.run(bot._on_channel_msg(SimpleNamespace(payload={
        "text": "Alice: ping", "channel_idx": 2,
    })))

    assert commands.sent == [(2, "@[Alice] rxed a1 (1 hops)")]


def test_configured_region_accepts_inbound_messages_without_filtering() -> None:
    """Inbound scope is not enforced; replies use the configured radio scope."""
    bot, commands = _make_bot([2])
    bot.config.bot.flood_scope = "au-vic"
    bot._chan_hash_by_idx = {2: "aa"}

    for transport_code in (None, "856eebe2"):
        payload = {
            "chan_hash": "aa",
            "payload_type": _PAYLOAD_TYPE_CHANNEL_MSG,
            "route_type": 0x00 if transport_code else 0x01,
            "path_len": 1,
            "path_hash_size": 1,
            "path": "a1",
        }
        if transport_code:
            payload["transport_code"] = transport_code
        asyncio.run(bot._on_rx_log_data(SimpleNamespace(payload=payload)))
        asyncio.run(bot._on_channel_msg(SimpleNamespace(payload={
            "text": "Alice: ping", "channel_idx": 2,
        })))

    assert len(commands.sent) == 2
    assert all(reply.startswith("@[Alice] rxed a1 (1 hops)") for _, reply in commands.sent)


def test_rx_log_routed_to_correct_channel_by_chan_hash() -> None:
    """A ping on channel 2 must NOT receive path data logged for channel 3."""
    bot, commands = _make_bot([2, 3])
    bot._chan_hash_by_idx = {2: "aa", 3: "bb"}

    asyncio.run(bot._on_rx_log_data(SimpleNamespace(payload={
        "chan_hash": "bb",  # logged for channel 3
        "payload_type": _PAYLOAD_TYPE_CHANNEL_MSG,
        "path_len": 3,
        "path_hash_size": 1,
        "path": "deadbe",
    })))

    # Ping arrives on channel 2 — must not pick up channel 3's path.
    event = SimpleNamespace(payload={"text": "Alice: ping", "channel_idx": 2})
    asyncio.run(bot._on_channel_msg(event))

    assert commands.sent == [(2, "@[Alice] rxed")]
    # And channel 3's queue still holds its entry until consumed by ch3.
    assert len(bot._rx_path_by_chan_hash["bb"]) == 1


def test_rx_log_paired_with_matching_channel_msg() -> None:
    """When channel hashes match, the RX log path is attached to the message."""
    bot, commands = _make_bot([2])
    bot._chan_hash_by_idx = {2: "aa"}

    asyncio.run(bot._on_rx_log_data(SimpleNamespace(payload={
        "chan_hash": "aa",
        "payload_type": _PAYLOAD_TYPE_CHANNEL_MSG,
        "path_len": 3,
        "path_hash_size": 1,
        "path": "a1b2c3",
    })))

    event = SimpleNamespace(payload={"text": "Alice: ping", "channel_idx": 2})
    asyncio.run(bot._on_channel_msg(event))

    assert commands.sent == [(2, "@[Alice] rxed a1:b2:c3 (3 hops)")]


def test_non_channel_rx_log_does_not_displace_pending_path() -> None:
    """Acks / adverts / contact msgs must not overwrite a pending channel path."""
    bot, commands = _make_bot([2])
    bot._chan_hash_by_idx = {2: "aa"}

    asyncio.run(bot._on_rx_log_data(SimpleNamespace(payload={
        "chan_hash": "aa",
        "payload_type": _PAYLOAD_TYPE_CHANNEL_MSG,
        "path_len": 3,
        "path_hash_size": 1,
        "path": "a1b2c3",
    })))

    # An advert / ack arrives between RX_LOG_DATA and CHANNEL_MSG_RECV.
    asyncio.run(bot._on_rx_log_data(SimpleNamespace(payload={
        "payload_type": 0x04,  # advert, not a channel msg
        "path_len": 1,
        "path_hash_size": 1,
        "path": "ff",
    })))

    event = SimpleNamespace(payload={"text": "Alice: ping", "channel_idx": 2})
    asyncio.run(bot._on_channel_msg(event))

    assert commands.sent == [(2, "@[Alice] rxed a1:b2:c3 (3 hops)")]


def test_channel_msg_path_hash_mode_overrides_cached_size() -> None:
    """A cached path_hash_size from a different region must not corrupt parsing
    of the current channel message: the channel msg carries its own path_hash_mode."""
    bot, commands = _make_bot([2])
    # No chan_hash mapping configured: legacy single-slot fallback is in use,
    # which is exactly the scenario where contamination used to occur.
    bot._latest_rx_path = {
        "path": "a1c3e5",
        "full_path": "a1b2c3d4e5f6",
        "path_hash_size": 2,  # stale value from a prior 2-byte-hash region
        "path_len": 3,
    }
    # The channel msg itself reports path_hash_mode=1 (=> path_hash_size=2),
    # so this should still render correctly as a 2-byte hash path.
    event = SimpleNamespace(payload={
        "text": "Alice: ping",
        "channel_idx": 2,
        "path_hash_mode": 1,
        "path_len": 3,
    })

    asyncio.run(bot._on_channel_msg(event))

    assert commands.sent == [(2, "@[Alice] rxed a1b2:c3d4:e5f6 (3 hops)")]


def test_prefix_command_uses_channel_msg_hash_mode_not_stale_cache() -> None:
    """Regression: a `prefix ab1f7a` on a 1-byte-hash channel must split into
    three prefixes, not be parsed as one big 3-byte prefix because some other
    channel's RX_LOG_DATA happened to land in the cache with path_hash_size=3."""
    config = AppConfig()
    config.bot.channels = [
        ChannelConfig(id=2, enabled_commands=["prefix"], rate_limit_enabled=False)
    ]
    bot = PathBot(config=config, db=DummyDB(), bus=EventBus(), message_store=DummyStore())
    commands = DummyCommands()
    bot._mc = SimpleNamespace(commands=commands)

    # Stale large-hash entry from a different region/channel.
    bot._latest_rx_path = {"path_hash_size": 3, "path_len": 1, "path": "ab"}

    # The channel msg itself is a normal 1-byte-hash flood: path_hash_mode=0.
    event = SimpleNamespace(payload={
        "text": "Alice: prefix ab1f7a",
        "channel_idx": 2,
        "path_hash_mode": 0,
        "path_len": 0,
    })
    asyncio.run(bot._on_channel_msg(event))

    # With path_hash_size=1, "ab1f7a" splits into three 1-byte prefixes.
    # With the previous bug (stale path_hash_size=3), it would have been
    # parsed as a single "ab1f7a" prefix.
    assert commands.sent == [(2, "@[Alice] ab=?, 1f=?, 7a=?")]


def test_legacy_single_slot_still_works_without_chan_hash_mapping() -> None:
    """Single-channel deployments without get_channel access still work."""
    bot, commands = _make_bot([2])
    # _chan_hash_by_idx left empty.
    bot._latest_rx_path = {"path": "a1b2c3", "path_len": 3}
    event = SimpleNamespace(payload={"text": "Alice: ping", "channel_idx": 2})

    asyncio.run(bot._on_channel_msg(event))

    assert commands.sent == [(2, "@[Alice] rxed a1:b2:c3 (3 hops)")]


def test_direct_channel_msg_ping_does_not_report_255_hops() -> None:
    """Regression: a direct-routed channel msg (plen=0xFF / path_hash_mode=-1)
    must not be reported as a 255-hop flood. With the v1.15.0 default-scope
    feature, scoped traffic often arrives via direct routing once paths are
    known, exposing this sentinel value."""
    bot, commands = _make_bot([2])
    bot._chan_hash_by_idx = {2: "aa"}
    # No RX_LOG_DATA correlation — direct messages aren't logged the same way
    # as flood channel messages, so the bot has nothing in the rx queue.

    event = SimpleNamespace(payload={
        "text": "Alice: ping",
        "channel_idx": 2,
        "path_hash_mode": -1,
        "path_len": 0xFF,
    })
    asyncio.run(bot._on_channel_msg(event))

    assert commands.sent == [(2, "@[Alice] rxed direct")]


def test_direct_channel_msg_trace_reports_direct_not_255() -> None:
    bot, commands = _make_bot([2])
    bot._chan_hash_by_idx = {2: "aa"}
    bot.config.bot.channels[0].enabled_commands = ["trace"]

    event = SimpleNamespace(payload={
        "text": "Alice: trace",
        "channel_idx": 2,
        "path_hash_mode": -1,
        "path_len": 0xFF,
    })
    asyncio.run(bot._on_channel_msg(event))

    assert commands.sent == [(2, "@[Alice] rxed direct r=0")]


def test_direct_msg_prefix_command_ignores_stale_multibyte_hash_size() -> None:
    """Regression: a direct-delivery CHANNEL_MSG_RECV (path_hash_mode=-1)
    must not inherit `path_hash_size` from a prior region-scoped RX_LOG_DATA
    that's still sitting in the legacy single-slot cache. Otherwise a
    `prefix ab1f7a` would be mis-parsed as one 3-byte token instead of three
    1-byte tokens."""
    config = AppConfig()
    config.bot.channels = [
        ChannelConfig(id=2, enabled_commands=["prefix"], rate_limit_enabled=False)
    ]
    bot = PathBot(config=config, db=DummyDB(), bus=EventBus(), message_store=DummyStore())
    commands = DummyCommands()
    bot._mc = SimpleNamespace(commands=commands)

    # Stale large-hash entry from a prior region-scoped packet.
    bot._latest_rx_path = {"path_hash_size": 3, "path_len": 1, "path": "ab"}

    event = SimpleNamespace(payload={
        "text": "Alice: prefix ab1f7a",
        "channel_idx": 2,
        "path_hash_mode": -1,
        "path_len": 0xFF,
    })
    asyncio.run(bot._on_channel_msg(event))

    assert commands.sent == [(2, "@[Alice] ab=?, 1f=?, 7a=?")]


def test_ping_reply_omits_region_scope_suffix() -> None:
    """A TRANSPORT_FLOOD (route_type=0x00) packet carries a transport_code,
    i.e. it's scoped to a MeshCore region. Ping omits the r= suffix."""
    bot, commands = _make_bot([2])
    bot._chan_hash_by_idx = {2: "aa"}
    asyncio.run(bot._on_rx_log_data(SimpleNamespace(payload={
        "chan_hash": "aa",
        "payload_type": _PAYLOAD_TYPE_CHANNEL_MSG,
        "route_type": 0x00,
        "transport_code": "deadbeef",
        "path_len": 1,
        "path_hash_size": 1,
        "path": "a1",
    })))

    event = SimpleNamespace(payload={"text": "Alice: ping", "channel_idx": 2})
    asyncio.run(bot._on_channel_msg(event))

    assert commands.sent == [(2, "@[Alice] rxed a1 (1 hops)")]


def test_trace_reply_marks_region_scoped_packet_with_r1() -> None:
    bot, commands = _make_bot([2])
    bot._chan_hash_by_idx = {2: "aa"}
    bot.config.bot.channels[0].enabled_commands = ["trace"]
    asyncio.run(bot._on_rx_log_data(SimpleNamespace(payload={
        "chan_hash": "aa",
        "payload_type": _PAYLOAD_TYPE_CHANNEL_MSG,
        "route_type": 0x03,  # TRANSPORT_DIRECT — also scoped
        "transport_code": "deadbeef",
        "path_len": 1,
        "path_hash_size": 1,
        "path": "a1",
    })))

    event = SimpleNamespace(payload={"text": "Alice: trace", "channel_idx": 2})
    asyncio.run(bot._on_channel_msg(event))

    # No repeater in DummyDB matches "a1", so resolver returns "A1 (1 hops)".
    assert commands.sent == [(2, "@[Alice] A1 (1 hops) r=1")]


def test_direct_channel_msg_with_correlated_rx_log_uses_logged_path() -> None:
    """If somehow an RX log entry IS correlated for a direct delivery, trust
    the logged hop count rather than the channel-msg sentinel."""
    bot, commands = _make_bot([2])
    bot._chan_hash_by_idx = {2: "aa"}
    asyncio.run(bot._on_rx_log_data(SimpleNamespace(payload={
        "chan_hash": "aa",
        "payload_type": _PAYLOAD_TYPE_CHANNEL_MSG,
        "path_len": 2,
        "path_hash_size": 1,
        "path": "a1b2",
    })))

    event = SimpleNamespace(payload={
        "text": "Alice: ping",
        "channel_idx": 2,
        "path_hash_mode": -1,
        "path_len": 0xFF,
    })
    asyncio.run(bot._on_channel_msg(event))

    assert commands.sent == [(2, "@[Alice] rxed a1:b2 (2 hops)")]
