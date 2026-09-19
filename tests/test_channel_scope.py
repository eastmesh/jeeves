from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from meshcore import EventType

import meshcore_pathbot.core.bot as bot_mod
from meshcore_pathbot.config.schema import AppConfig, ChannelConfig
from meshcore_pathbot.core.bot import PathBot
from meshcore_pathbot.events.bus import EventBus

_real_sleep = asyncio.sleep  # the autouse fixture patches asyncio.sleep
OK = SimpleNamespace(type=EventType.OK, payload={})
ERR = SimpleNamespace(type=EventType.ERROR, payload={"reason": "boom"})


class FakeCommands:
    """Records the ordered command log; failures are injected by call index/name."""

    def __init__(self, scope_results=None, send_results=None) -> None:
        self.log: list[tuple] = []
        self.scope_results = list(scope_results or [])
        self.send_results = list(send_results or [])

    async def set_flood_scope(self, scope):
        self.log.append(("scope", scope))
        return self.scope_results.pop(0) if self.scope_results else OK

    async def send_chan_msg(self, channel_id, text):
        self.log.append(("send", channel_id, text))
        return self.send_results.pop(0) if self.send_results else OK


class DummyDB:
    def get_by_prefix(self, prefix):
        return []


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def fast(_):
        return None

    monkeypatch.setattr(bot_mod.asyncio, "sleep", fast)


def _bot(commands, flood_scope="", channels=None):
    config = AppConfig()
    config.bot.flood_scope = flood_scope
    config.bot.channels = channels or [ChannelConfig(id=1), ChannelConfig(id=2)]
    bot = PathBot(config=config, db=DummyDB(), bus=EventBus(), message_store=None)
    bot._mc = SimpleNamespace(commands=commands, is_connected=True)
    return bot


def test_precedence_channel_then_global_then_unscoped():
    cfg = AppConfig()
    cfg.bot.flood_scope = "global"
    cfg.bot.channels = [
        ChannelConfig(id=1, scope="chan"),
        ChannelConfig(id=2),
        ChannelConfig(id=3, scope="*"),
    ]
    assert cfg.bot.resolve_scope(1) == "chan"
    assert cfg.bot.resolve_scope(2) == "global"
    assert cfg.bot.resolve_scope(3) == ""
    cfg.bot.flood_scope = ""
    assert cfg.bot.resolve_scope(2) == ""
    assert cfg.bot.scope_management_enabled()  # channels 1/3 still configure scope


def test_scope_rejects_whitespace():
    with pytest.raises(ValueError):
        ChannelConfig(id=1, scope="au vic")


@pytest.mark.asyncio
async def test_set_send_chunks_restore_order_uses_channel_scope():
    cmds = FakeCommands()
    bot = _bot(cmds, flood_scope="global",
               channels=[ChannelConfig(id=1, scope="chan"), ChannelConfig(id=2)])
    bot._scope_known_unscoped = True
    long_text = ("word " * 60).strip()  # forces multiple chunks
    assert await bot.send_channel_message(1, long_text) is True
    kinds = [e[0] for e in cmds.log]
    assert cmds.log[0] == ("scope", "chan")
    assert kinds[1:-1] == ["send"] * (len(kinds) - 2) and len(kinds) > 3
    assert cmds.log[-1] == ("scope", None)
    assert bot._scope_known_unscoped is True

    cmds.log.clear()
    assert await bot.send_channel_message(2, "hi") is True  # falls back to global
    assert cmds.log == [("scope", "global"), ("send", 2, "hi"), ("scope", None)]


@pytest.mark.asyncio
async def test_restore_runs_when_send_fails_and_reports_failure():
    cmds = FakeCommands(send_results=[ERR])
    bot = _bot(cmds, channels=[ChannelConfig(id=1, scope="chan")])
    bot._scope_known_unscoped = True
    assert await bot.send_channel_message(1, "hi") is False
    assert cmds.log == [("scope", "chan"), ("send", 1, "hi"), ("scope", None)]
    assert bot.stats.errors == 1


@pytest.mark.asyncio
async def test_restore_runs_when_send_raises():
    cmds = FakeCommands()

    async def boom(*a):
        cmds.log.append(("send",))
        raise OSError("link down")

    cmds.send_chan_msg = boom
    bot = _bot(cmds, channels=[ChannelConfig(id=1, scope="chan")])
    assert await bot.send_channel_message(1, "hi") is False
    assert cmds.log[-1] == ("scope", None)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [ERR, None])
async def test_scope_setup_failure_prevents_send(bad):
    cmds = FakeCommands(scope_results=[bad])
    bot = _bot(cmds, channels=[ChannelConfig(id=1, scope="chan")])
    bot._scope_known_unscoped = True
    assert await bot.send_channel_message(1, "hi") is False
    assert not any(e[0] == "send" for e in cmds.log)
    assert cmds.log[-1] == ("scope", None)  # best-effort reset after partial failure


@pytest.mark.asyncio
async def test_restore_failure_reported_and_retried_before_next_send():
    cmds = FakeCommands(scope_results=[OK, ERR])
    bot = _bot(cmds, channels=[ChannelConfig(id=1, scope="chan"), ChannelConfig(id=2)])
    bot._scope_known_unscoped = True
    assert await bot.send_channel_message(1, "hi") is False  # delivered but radio state unknown
    assert bot._scope_known_unscoped is False

    cmds.log.clear()
    assert await bot.send_channel_message(2, "yo") is True  # unscoped channel resets first
    assert cmds.log == [("scope", None), ("send", 2, "yo")]
    assert bot._scope_known_unscoped is True


@pytest.mark.asyncio
async def test_unscoped_everywhere_never_touches_scope():
    cmds = FakeCommands()
    bot = _bot(cmds)
    assert await bot.send_channel_message(1, "hi") is True
    assert cmds.log == [("send", 1, "hi")]


@pytest.mark.asyncio
async def test_missing_sdk_support_fails_without_sending():
    class NoScope:
        def __init__(self):
            self.log = []

        async def send_chan_msg(self, channel_id, text):
            self.log.append(("send",))
            return OK

    cmds = NoScope()
    bot = _bot(cmds, flood_scope="au")
    assert await bot.send_channel_message(1, "hi") is False
    assert cmds.log == []


@pytest.mark.asyncio
async def test_reset_falls_back_to_zero_key_for_old_sdk():
    calls = []

    class OldCommands(FakeCommands):
        async def set_flood_scope(self, scope):
            calls.append(scope)
            if scope is None:
                raise TypeError("old sdk")
            return OK

    bot = _bot(OldCommands(), flood_scope="au")
    await bot._apply_scope(bot._mc, "")
    assert calls == [None, b"\0" * 16]


@pytest.mark.asyncio
async def test_send_uses_lock_and_current_mc_after_reconnect():
    """A send queued behind the lock must use the connection current when it runs."""
    old, new = FakeCommands(), FakeCommands()
    bot = _bot(old)
    await bot._send_lock.acquire()
    task = asyncio.create_task(bot.send_channel_message(1, "hi"))
    await asyncio.sleep(0)
    bot._mc = SimpleNamespace(commands=new, is_connected=True)
    bot._send_lock.release()
    assert await task is True
    assert old.log == [] and new.log == [("send", 1, "hi")]

    # Connection dropped while waiting -> failure, no exception.
    await bot._send_lock.acquire()
    task = asyncio.create_task(bot.send_channel_message(1, "hi"))
    await asyncio.sleep(0)
    bot._mc = None
    bot._send_lock.release()
    assert await task is False


@pytest.mark.asyncio
async def test_none_send_result_is_failure():
    cmds = FakeCommands(send_results=[None])
    bot = _bot(cmds)
    assert await bot.send_channel_message(1, "hi") is False


@pytest.mark.asyncio
async def test_initialization_resets_scope_and_marks_known():
    cmds = FakeCommands()
    bot = _bot(cmds, flood_scope="au")
    bot._scope_known_unscoped = False
    await bot._initialize_scope_state(bot._mc)
    assert cmds.log == [("scope", None)] and bot._scope_known_unscoped is True


@pytest.mark.asyncio
async def test_initialization_failure_raises_and_unconfigured_is_noop():
    bot = _bot(FakeCommands(scope_results=[ERR]), flood_scope="au")
    with pytest.raises(ConnectionError):
        await bot._initialize_scope_state(bot._mc)
    assert bot._scope_known_unscoped is False

    quiet = FakeCommands()
    await _bot(quiet)._initialize_scope_state(quiet)
    assert quiet.log == []


@pytest.mark.asyncio
async def test_failed_reconnect_init_disconnects_new_connection(monkeypatch):
    disconnected = []

    class FakeMC:
        async def disconnect(self):
            disconnected.append(True)

    bot = _bot(FakeCommands())
    bot.config.connection.max_reconnect_attempts = 1

    async def connect():
        return FakeMC()

    async def init():
        raise ConnectionError("scope init failed")

    bot._connect = connect
    bot._initialize_connected_meshcore = init
    await bot._reconnect_tcp_companion()
    assert bot._mc is None and disconnected == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [SimpleNamespace(payload={}), object()])
async def test_malformed_send_result_is_failure_and_restores(bad):
    cmds = FakeCommands(send_results=[bad])
    bot = _bot(cmds, flood_scope="au")
    bot._scope_known_unscoped = True
    assert await bot.send_channel_message(1, "hi") is False
    assert cmds.log == [("scope", "au"), ("send", 1, "hi"), ("scope", None)]
    assert bot._scope_known_unscoped is True


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["error", "raise", "malformed"])
async def test_unscoped_send_failure_forces_reset_next_send(mode):
    cmds = FakeCommands()
    bot = _bot(cmds, channels=[ChannelConfig(id=1), ChannelConfig(id=2, scope="au")])
    bot._scope_known_unscoped = True
    if mode == "error":
        cmds.send_results = [ERR]
    elif mode == "malformed":
        cmds.send_results = [SimpleNamespace()]
    else:
        async def boom(*a):
            raise OSError("link down")

        cmds.send_chan_msg = boom
    assert await bot.send_channel_message(1, "hi") is False
    assert bot._scope_known_unscoped is False
    assert ("scope", None) not in cmds.log  # unscoped send skipped setup
    cmds.log.clear()
    cmds.send_chan_msg = FakeCommands.send_chan_msg.__get__(cmds)
    assert await bot.send_channel_message(1, "again") is True
    assert cmds.log == [("scope", None), ("send", 1, "again")]


@pytest.mark.asyncio
async def test_sdk_connection_events_invalidate_scope_state():
    subs = []
    cmds = FakeCommands()
    bot = _bot(cmds, channels=[ChannelConfig(id=1), ChannelConfig(id=2, scope="au")])
    bot._mc.subscribe = lambda et, cb, **kw: subs.append((et, cb))
    bot._mc.start_auto_message_fetching = lambda: asyncio.sleep(0)
    bot._sync_contacts = lambda: asyncio.sleep(0)
    bot._sync_channel_hashes = lambda ch: asyncio.sleep(0)
    await bot._initialize_connected_meshcore()
    handlers = {et: cb for et, cb in subs}
    assert [et for et, _ in subs].count(EventType.CONNECTED) == 1
    assert [et for et, _ in subs].count(EventType.DISCONNECTED) == 1
    assert bot._scope_known_unscoped is True
    await handlers[EventType.DISCONNECTED](SimpleNamespace())
    assert bot._scope_known_unscoped is False
    # Unscoped channel must re-verify/reset after the SDK reconnect.
    cmds.log.clear()
    assert await bot.send_channel_message(1, "hi") is True
    assert cmds.log == [("scope", None), ("send", 1, "hi")]


@pytest.mark.asyncio
async def test_reconnect_waits_for_inflight_send_and_blocks_queued_until_init():
    events = []
    gate = asyncio.Event()

    class SlowCommands(FakeCommands):
        async def send_chan_msg(self, channel_id, text):
            events.append("send-start")
            await gate.wait()
            events.append("send-end")
            return OK

    class NewMC:
        commands = FakeCommands()

        async def disconnect(self):
            pass

    class OldMC(SimpleNamespace):
        async def stop_auto_message_fetching(self):
            events.append("old-stop")

        async def disconnect(self):
            events.append("old-disconnect")

    bot = _bot(SlowCommands())
    bot._mc = OldMC(commands=bot._mc.commands, is_connected=True)
    bot.config.connection.max_reconnect_attempts = 1
    new = NewMC()

    async def connect():
        events.append("connect")
        return new

    async def init():
        events.append("init-start")
        await _real_sleep(0)
        events.append("init-end")

    bot._connect = connect
    bot._initialize_connected_meshcore = init

    s1 = asyncio.create_task(bot.send_channel_message(1, "a"))
    await _real_sleep(0)
    rec = asyncio.create_task(bot._reconnect_tcp_companion())
    await _real_sleep(0)
    s2 = asyncio.create_task(bot.send_channel_message(1, "b"))
    await _real_sleep(0)
    assert events == ["send-start"]  # reconnect blocked behind in-flight send
    gate.set()
    await asyncio.gather(s1, rec, s2)
    assert events.index("send-end") < events.index("old-disconnect")
    assert events.index("init-end") < len(events)
    assert new.commands.log == [("send", 1, "b")]  # queued send used new mc after init


@pytest.mark.asyncio
async def test_stop_waits_for_inflight_send():
    events = []
    gate = asyncio.Event()

    class SlowCommands(FakeCommands):
        async def send_chan_msg(self, channel_id, text):
            await gate.wait()
            events.append("send-end")
            return OK

    class MC(SimpleNamespace):
        async def stop_auto_message_fetching(self):
            events.append("stop-fetch")

        async def disconnect(self):
            events.append("disconnect")

    bot = _bot(SlowCommands())
    bot._mc = MC(commands=bot._mc.commands, is_connected=True)
    send = asyncio.create_task(bot.send_channel_message(1, "a"))
    await _real_sleep(0)
    stop = asyncio.create_task(bot.stop())
    await _real_sleep(0)
    assert events == []
    gate.set()
    await asyncio.gather(send, stop)
    assert events == ["send-end", "stop-fetch", "disconnect"]
    assert bot._mc is None


@pytest.mark.asyncio
@pytest.mark.parametrize("when", ["before_second_chunk", "during_send"])
async def test_connection_event_during_scoped_send_aborts_without_restore(when, monkeypatch):
    cmds = FakeCommands()
    bot = _bot(cmds, channels=[ChannelConfig(id=1, scope="chan")])
    bot._scope_known_unscoped = True
    fired = []

    async def fire():
        fired.append(1)
        await bot._on_connection_state(SimpleNamespace())

    orig_send = cmds.send_chan_msg

    async def send(channel_id, text):
        result = await orig_send(channel_id, text)
        if when == "during_send" and not fired:
            await fire()  # event lands while first chunk is in flight
        return result

    cmds.send_chan_msg = send
    if when == "before_second_chunk":
        async def sleeper(_):
            if not fired:
                await fire()

        monkeypatch.setattr(bot_mod.asyncio, "sleep", sleeper)
    assert await bot.send_channel_message(1, ("word " * 60).strip()) is False
    sends = [e for e in cmds.log if e[0] == "send"]
    assert len(sends) == 1  # no further chunks after the epoch change
    assert cmds.log[-1][0] == "send"  # no restore through the stale connection
    assert bot._scope_known_unscoped is False
    assert bot.stats.errors >= 1

    # A later send re-establishes scope from scratch.
    cmds.send_chan_msg = orig_send
    cmds.log.clear()
    assert await bot.send_channel_message(1, "hi") is True
    assert cmds.log == [("scope", "chan"), ("send", 1, "hi"), ("scope", None)]


@pytest.mark.asyncio
async def test_connection_event_callback_does_not_wait_for_send_lock():
    bot = _bot(FakeCommands())
    async with bot._send_lock:
        await asyncio.wait_for(bot._on_connection_state(SimpleNamespace()), 1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "wrong", [EventType.SELF_INFO, EventType.CONTACTS, EventType.DISCONNECTED]
)
async def test_wrong_non_error_result_types_fail_closed(wrong):
    bad = SimpleNamespace(type=wrong, payload={})
    # set_flood_scope result of the wrong type: nothing is sent.
    cmds = FakeCommands(scope_results=[bad])
    bot = _bot(cmds, channels=[ChannelConfig(id=1, scope="chan")])
    assert await bot.send_channel_message(1, "hi") is False
    assert not any(e[0] == "send" for e in cmds.log)
    # send_chan_msg result of the wrong type: failure, scope restored.
    cmds = FakeCommands(send_results=[bad])
    bot = _bot(cmds, channels=[ChannelConfig(id=1, scope="chan")])
    assert await bot.send_channel_message(1, "hi") is False
    assert cmds.log[-1] == ("scope", None)


@pytest.mark.asyncio
async def test_sdk_success_types_and_none_type_fake_convention_accepted():
    for ok in (
        SimpleNamespace(type=EventType.MSG_SENT, payload={}),
        SimpleNamespace(type=None, payload={}),
    ):
        cmds = FakeCommands(send_results=[ok])
        bot = _bot(cmds, channels=[ChannelConfig(id=1, scope="chan")])
        assert await bot.send_channel_message(1, "hi") is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    [
        None,
        object(),
        SimpleNamespace(type=EventType.OK),
        SimpleNamespace(type=EventType.MSG_SENT),
        SimpleNamespace(type=EventType.ERROR),
    ],
)
async def test_tcp_health_check_rejects_malformed_or_wrong_results(bad):
    bot = _bot(FakeCommands())

    async def appstart():
        return bad

    bot._mc.commands.send_appstart = appstart
    assert await bot._tcp_health_check() is False
    for good in (SimpleNamespace(type=EventType.SELF_INFO), SimpleNamespace(type=None)):
        async def appstart_ok(good=good):
            return good

        bot._mc.commands.send_appstart = appstart_ok
        assert await bot._tcp_health_check() is True


def test_duplicate_channel_ids_deduped_first_wins():
    cfg = AppConfig.model_validate(
        {"bot": {"channels": [
            {"id": 1, "scope": "first"}, {"id": 2}, {"id": 1, "scope": "second"},
        ]}}
    )
    assert [c.id for c in cfg.bot.channels] == [1, 2]
    assert cfg.bot.resolve_scope(1) == "first"


@pytest.mark.asyncio
async def test_initialization_subscribes_each_channel_once():
    subs = []
    cmds = FakeCommands()
    bot = _bot(cmds)
    # Bypass validation to simulate a config mutated in-place with duplicates.
    bot.config.bot.channels = [ChannelConfig(id=1), ChannelConfig(id=1), ChannelConfig(id=2)]
    bot._mc.subscribe = lambda et, cb, **kw: subs.append((et, kw))
    bot._mc.start_auto_message_fetching = lambda: asyncio.sleep(0)
    bot._sync_contacts = lambda: asyncio.sleep(0)
    bot._sync_channel_hashes = lambda ch: asyncio.sleep(0)
    await bot._initialize_connected_meshcore()
    idx = [kw["attribute_filters"]["channel_idx"] for et, kw in subs if et == EventType.CHANNEL_MSG_RECV]
    assert idx == [1, 2]
