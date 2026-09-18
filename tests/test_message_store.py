from __future__ import annotations

import json
from pathlib import Path

import pytest

from meshcore_pathbot.core.message_store import MessageStore


@pytest.mark.asyncio
async def test_message_store_add_get_recent_and_paths_for_peer(tmp_path: Path) -> None:
    store = MessageStore(tmp_path / "messages.db")
    await store.load()

    await store.add("in", "Alice", "hello", timestamp=100.0, path="aa11", rxlog="rx:A")
    await store.add("in", "alice", "again", timestamp=200.0, path="")
    await store.add("out", "alice", "reply", timestamp=300.0, path="bb22")

    recent = store.get_recent(2)
    assert len(recent) == 2
    assert recent[0]["text"] == "reply"
    assert recent[1]["text"] == "again"
    assert recent[1]["rxlog"] == ""
    assert store.get_recent(3)[2]["rxlog"] == "rx:A"

    # only incoming messages for this peer, case-insensitive peer matching
    assert store.get_paths_for_peer("ALICE") == ["", "aa11"]


@pytest.mark.asyncio
async def test_message_store_migrates_legacy_json(tmp_path: Path) -> None:
    legacy_path = tmp_path / "messages.json"
    legacy_path.write_text(
        json.dumps(
            [
                {
                    "id": "1",
                    "direction": "in",
                    "peer": "Bob",
                    "text": "old",
                    "timestamp": 123.0,
                    "channel": 1,
                    "path": "ff00",
                    "rxlog": "legacy-rx",
                }
            ]
        )
    )

    store = MessageStore(legacy_path)
    await store.load()

    assert store.filepath.suffix == ".db"
    assert store.count == 1
    assert store.get_recent(1)[0]["text"] == "old"
    assert store.get_recent(1)[0]["rxlog"] == "legacy-rx"
    assert store.get_paths_for_peer("bob") == ["ff00"]


@pytest.mark.asyncio
async def test_message_store_upgrades_existing_db_with_rxlog_column(tmp_path: Path) -> None:
    db_path = tmp_path / "messages.db"
    # Simulate an older DB schema without rxlog
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE messages (
            id TEXT PRIMARY KEY,
            direction TEXT NOT NULL,
            peer TEXT NOT NULL,
            text TEXT NOT NULL,
            timestamp REAL NOT NULL,
            channel INTEGER,
            path TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        INSERT INTO messages (id, direction, peer, text, timestamp, channel, path)
        VALUES ('old-1', 'in', 'Carol', 'hi', 10.0, 7, 'abcd')
        """
    )
    conn.commit()
    conn.close()

    store = MessageStore(db_path)
    await store.load()

    rows = store.get_recent(1)
    assert rows[0]["id"] == "old-1"
    assert rows[0]["rxlog"] == ""


@pytest.mark.asyncio
async def test_get_recent_ping_responses_with_channel_filter(tmp_path: Path) -> None:
    store = MessageStore(tmp_path / "messages.db")
    await store.load()

    await store.add("in", "Alice", "Alice: ping", timestamp=100.0, channel=1)
    await store.add("out", "Alice", "@[Alice] rxed", timestamp=101.0, channel=1)
    await store.add("in", "Bob", "Bob: trace", timestamp=110.0, channel=1)
    await store.add("out", "Bob", "@[Bob] trace result", timestamp=111.0, channel=1)
    await store.add("in", "Alice", "Alice: ping", timestamp=120.0, channel=2)
    await store.add("out", "Alice", "@[Alice] rxed (2 hops)", timestamp=121.0, channel=2)

    all_channels = store.get_recent_ping_responses(channels=[1, 2], count=10)
    assert [row["channel"] for row in all_channels] == [2, 1]
    assert all("Alice" in row["peer"] for row in all_channels)

    ch1_only = store.get_recent_ping_responses(channels=[1], count=10)
    assert len(ch1_only) == 1
    assert ch1_only[0]["channel"] == 1
