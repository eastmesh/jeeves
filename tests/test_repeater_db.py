from __future__ import annotations

import time
from pathlib import Path

import pytest

from meshcore_pathbot.core.repeater_db import RepeaterDB


@pytest.mark.asyncio
async def test_repeater_db_updates_and_last_seen_is_monotonic(tmp_path: Path) -> None:
    db = RepeaterDB(tmp_path / "repeaters.json")
    await db.load()

    contact = {
        "public_key": "abcdef123456",
        "adv_type": 2,
        "adv_name": "R1",
        "adv_lat": 1.23,
        "adv_lon": 4.56,
        "last_seen": 1_700_000_000,
    }
    first = await db.update_from_contact(contact)

    # Older timestamp should not overwrite newer value.
    older = {**contact, "last_seen": 1_600_000_000}
    second = await db.update_from_contact(older)

    assert first is not None
    assert second is not None
    assert second["last_seen"] == 1_700_000_000
    assert db.filepath.suffix == ".db"


@pytest.mark.asyncio
async def test_repeater_db_cleanup_stale_entries(tmp_path: Path) -> None:
    db = RepeaterDB(tmp_path / "repeaters.json")
    await db.load()

    now = int(time.time())
    stale = {
        "public_key": "aa1111",
        "adv_type": 2,
        "adv_name": "Old",
        "last_seen": now - (8 * 24 * 60 * 60),
    }
    fresh = {
        "public_key": "bb2222",
        "adv_type": 2,
        "adv_name": "New",
        "last_seen": now,
    }

    await db.update_from_contact(stale)
    await db.update_from_contact(fresh)

    deleted = await db.cleanup_stale(max_age_days=7)

    assert deleted == 1
    assert db.count == 1
    assert db.get_all()[0]["public_key"] == "bb2222"


@pytest.mark.asyncio
async def test_repeater_db_uses_alternate_last_seen_fields_and_preserves_existing(tmp_path: Path) -> None:
    db = RepeaterDB(tmp_path / "repeaters.json")
    await db.load()

    contact = {
        "public_key": "cc3333",
        "adv_type": 2,
        "adv_name": "R2",
        "last_heard": 1_700_000_123_000,
    }
    first = await db.update_from_contact(contact)

    # A subsequent payload without any timestamp should not reset the stored value.
    no_ts = {
        "public_key": "cc3333",
        "adv_type": 2,
        "adv_name": "R2",
    }
    second = await db.update_from_contact(no_ts)

    assert first is not None
    assert second is not None
    assert first["last_seen"] == 1_700_000_123
    assert second["last_seen"] == 1_700_000_123


@pytest.mark.asyncio
async def test_guest_visit_stats_are_recorded_and_aggregated(tmp_path: Path) -> None:
    db = RepeaterDB(tmp_path / "repeaters.json")
    await db.load()

    await db.record_guest_visit("1.1.1.1", "/")
    await db.record_guest_visit("1.1.1.1", "/paths")
    await db.record_guest_visit("2.2.2.2", "/")

    guest_stats = db.guest_visit_stats(top_limit=5, recent_limit=5)

    assert guest_stats["total_hits"] == 3
    assert guest_stats["unique_ips"] == 2
    assert guest_stats["unique_pages"] == 2
    assert guest_stats["top_pages"][0] == {"path": "/", "hits": 2}
    assert guest_stats["top_ips"][0] == {"ip": "1.1.1.1", "hits": 2}
    assert len(guest_stats["recent_visits"]) == 3

    combined_stats = db.stats()
    assert combined_stats["guest_visitors"]["total_hits"] == 3
