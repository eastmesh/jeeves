from __future__ import annotations

from pathlib import Path

import asyncio

from meshcore_pathbot.core.path_resolver import PathResolver
from meshcore_pathbot.config.schema import AppConfig
from meshcore_pathbot.core.repeater_db import RepeaterDB


def test_resolve_detailed_includes_prefix_options_for_ambiguous_hop(tmp_path: Path) -> None:
    db = RepeaterDB(tmp_path / "repeaters.json")
    asyncio.run(db.load())

    asyncio.run(db.update_from_contact(
        {
            "public_key": "aa1111",
            "adv_type": 2,
            "adv_name": "Alpha",
            "adv_lat": 40.0,
            "adv_lon": -74.0,
            "last_seen": 100,
        }
    ))
    asyncio.run(db.update_from_contact(
        {
            "public_key": "aa2222",
            "adv_type": 2,
            "adv_name": "Alpine",
            "adv_lat": 40.2,
            "adv_lon": -73.8,
            "last_seen": 200,
        }
    ))
    asyncio.run(db.update_from_contact(
        {
            "public_key": "bb3333",
            "adv_type": 2,
            "adv_name": "Bravo",
            "adv_lat": 41.0,
            "adv_lon": -73.0,
            "last_seen": 300,
        }
    ))

    resolver = PathResolver(db)
    hops = resolver.resolve_detailed("aabb")

    assert len(hops) == 2
    first = hops[0]
    assert first["prefix"] == "aa"
    assert first["ambiguous"] is True
    assert first["candidates"] == 2
    assert first["selected_by"] == "distance"
    assert [option["name"] for option in first["options"]] == ["Alpha", "Alpine"]


def test_resolve_detailed_uses_manual_selection_and_marks_selected_option(tmp_path: Path) -> None:
    db = RepeaterDB(tmp_path / "repeaters.json")
    asyncio.run(db.load())

    asyncio.run(db.update_from_contact(
        {
            "public_key": "aa1111",
            "adv_type": 2,
            "adv_name": "Alpha",
            "adv_lat": 10.0,
            "adv_lon": 10.0,
            "last_seen": 100,
        }
    ))
    asyncio.run(db.update_from_contact(
        {
            "public_key": "aa2222",
            "adv_type": 2,
            "adv_name": "Alpine",
            "adv_lat": 20.0,
            "adv_lon": 20.0,
            "last_seen": 200,
        }
    ))
    asyncio.run(db.update_from_contact(
        {
            "public_key": "bb3333",
            "adv_type": 2,
            "adv_name": "Bravo",
            "adv_lat": 21.0,
            "adv_lon": 21.0,
            "last_seen": 300,
        }
    ))

    resolver = PathResolver(db)
    hops = resolver.resolve_detailed("aabb", preferred_repeaters={"aa": "aa1111"})

    assert hops[0]["name"] == "Alpha"
    assert hops[0]["ambiguous"] is False
    assert hops[0]["selected_by"] == "manual"
    selected = [option for option in hops[0]["options"] if option["selected"]]
    assert len(selected) == 1
    assert selected[0]["public_key"] == "aa1111"
    assert hops[1]["distance_from_prev"] is not None


def test_resolve_detailed_home_repeater_last_hop_uses_bot_location(tmp_path: Path) -> None:
    db = RepeaterDB(tmp_path / "repeaters.json")
    asyncio.run(db.load())

    config = AppConfig()
    config.bot.home_repeater_name = "Home"
    config.bot.home_repeater_prefix = "bb"
    config.bot.lat = 12.34
    config.bot.lon = 56.78

    resolver = PathResolver(db, config=config)
    hops = resolver.resolve_detailed("aabb")

    assert hops[1]["name"] == "Home"
    assert hops[1]["lat"] == 12.34
    assert hops[1]["lon"] == 56.78


def test_normalize_path_accepts_plain_colon_and_comma_delimiters() -> None:
    assert PathResolver.normalize_path("c132fa9d7a") == "c132fa9d7a"
    assert PathResolver.normalize_path("c1:32:fa:9d:7a") == "c132fa9d7a"
    assert PathResolver.normalize_path("c1,32,fa,9d,7a") == "c132fa9d7a"


# ── get_by_prefix: variable-length prefix matching ────────────────────────────

def test_get_by_prefix_one_byte_uses_stored_prefix_field(tmp_path: Path) -> None:
    """1-byte prefix still matches via the fast stored prefix field."""
    db = RepeaterDB(tmp_path / "repeaters.db")
    asyncio.run(db.load())
    asyncio.run(db.update_from_contact(
        {"public_key": "fb1f11", "adv_type": 2, "adv_name": "Hilltop", "adv_lat": 0, "adv_lon": 0}
    ))
    asyncio.run(db.update_from_contact(
        {"public_key": "fb2f22", "adv_type": 2, "adv_name": "Flatland", "adv_lat": 0, "adv_lon": 0}
    ))
    # Both share the "fb" 1-byte prefix
    results = db.get_by_prefix("fb")
    assert {r["name"] for r in results} == {"Hilltop", "Flatland"}


def test_get_by_prefix_multibyte_filters_by_public_key(tmp_path: Path) -> None:
    """A 4-char prefix matches only the repeater whose public_key starts with it."""
    db = RepeaterDB(tmp_path / "repeaters.db")
    asyncio.run(db.load())
    asyncio.run(db.update_from_contact(
        {"public_key": "fb1f11", "adv_type": 2, "adv_name": "Hilltop", "adv_lat": 0, "adv_lon": 0}
    ))
    asyncio.run(db.update_from_contact(
        {"public_key": "fb2f22", "adv_type": 2, "adv_name": "Flatland", "adv_lat": 0, "adv_lon": 0}
    ))
    # 2-byte prefix "fb1f" should only match Hilltop
    results = db.get_by_prefix("fb1f")
    assert len(results) == 1
    assert results[0]["name"] == "Hilltop"


# ── lookup_prefixes: multibyte path handling ──────────────────────────────────

def test_lookup_prefixes_1byte_path_unchanged(tmp_path: Path) -> None:
    """Standard 1-byte colon-separated path still works as before."""
    db = RepeaterDB(tmp_path / "repeaters.db")
    asyncio.run(db.load())
    asyncio.run(db.update_from_contact(
        {"public_key": "fb1111", "adv_type": 2, "adv_name": "Hilltop", "adv_lat": 0, "adv_lon": 0}
    ))
    asyncio.run(db.update_from_contact(
        {"public_key": "7a2222", "adv_type": 2, "adv_name": "Valley", "adv_lat": 0, "adv_lon": 0}
    ))
    resolver = PathResolver(db)
    result = resolver.lookup_prefixes("fb:7a")
    assert "Hilltop" in result
    assert "Valley" in result


def test_lookup_prefixes_2byte_path_uses_full_segment(tmp_path: Path) -> None:
    """2-byte-per-hop path eliminates the collision — only the correct repeater is shown."""
    db = RepeaterDB(tmp_path / "repeaters.db")
    asyncio.run(db.load())
    # Two repeaters sharing 1-byte prefix "fb" but distinct 2-byte prefixes
    asyncio.run(db.update_from_contact(
        {"public_key": "fb1f11", "adv_type": 2, "adv_name": "Hilltop", "adv_lat": 0, "adv_lon": 0}
    ))
    asyncio.run(db.update_from_contact(
        {"public_key": "fb2f22", "adv_type": 2, "adv_name": "Flatland", "adv_lat": 0, "adv_lon": 0}
    ))
    asyncio.run(db.update_from_contact(
        {"public_key": "7ab233", "adv_type": 2, "adv_name": "Valley", "adv_lat": 0, "adv_lon": 0}
    ))
    resolver = PathResolver(db)
    # Full 2-byte segments: "fb1f" and "7ab2"
    result = resolver.lookup_prefixes("fb1f:7ab2")
    assert "Hilltop" in result
    assert "Valley" in result
    assert "Flatland" not in result  # eliminated by 2-byte match


def test_lookup_prefixes_2byte_unknown_shows_question_mark(tmp_path: Path) -> None:
    """Unknown 2-byte prefix shows '?' instead of crashing."""
    db = RepeaterDB(tmp_path / "repeaters.db")
    asyncio.run(db.load())
    resolver = PathResolver(db)
    result = resolver.lookup_prefixes("fb1f:7ab2")
    assert "?" in result


def test_lookup_prefixes_4char_no_separator_assumes_2byte_prefix(tmp_path: Path) -> None:
    """A 4-char hex string without separator is treated as a single 2-byte prefix."""
    db = RepeaterDB(tmp_path / "repeaters.db")
    asyncio.run(db.load())
    asyncio.run(db.update_from_contact(
        {"public_key": "fb1111", "adv_type": 2, "adv_name": "Hilltop", "adv_lat": 0, "adv_lon": 0}
    ))
    asyncio.run(db.update_from_contact(
        {"public_key": "fb1f22", "adv_type": 2, "adv_name": "Valley", "adv_lat": 0, "adv_lon": 0}
    ))
    resolver = PathResolver(db)
    # "fb1f" without separator → one 2-byte prefix hop ["fb1f"]
    result = resolver.lookup_prefixes("fb1f")
    assert "Valley" in result
    assert "Hilltop" not in result


def test_lookup_prefixes_4char_no_separator_ignores_hash_size_hint(tmp_path: Path) -> None:
    """A bare 4-char token should still be interpreted as one 2-byte prefix."""
    db = RepeaterDB(tmp_path / "repeaters.db")
    asyncio.run(db.load())
    asyncio.run(db.update_from_contact(
        {"public_key": "fb1111", "adv_type": 2, "adv_name": "Hilltop", "adv_lat": 0, "adv_lon": 0}
    ))
    asyncio.run(db.update_from_contact(
        {"public_key": "fb1f22", "adv_type": 2, "adv_name": "Valley", "adv_lat": 0, "adv_lon": 0}
    ))
    resolver = PathResolver(db)
    result = resolver.lookup_prefixes("fb1f", path_hash_size=3)
    assert "Valley" in result
    assert "Hilltop" not in result


def test_lookup_prefixes_6char_no_separator_splits_into_1byte_hops(tmp_path: Path) -> None:
    """A 6-char hex string without separator is split into three 1-byte hops."""
    db = RepeaterDB(tmp_path / "repeaters.db")
    asyncio.run(db.load())
    asyncio.run(db.update_from_contact(
        {"public_key": "fb1111", "adv_type": 2, "adv_name": "Hilltop", "adv_lat": 0, "adv_lon": 0}
    ))
    asyncio.run(db.update_from_contact(
        {"public_key": "1f2222", "adv_type": 2, "adv_name": "Valley", "adv_lat": 0, "adv_lon": 0}
    ))
    asyncio.run(db.update_from_contact(
        {"public_key": "113333", "adv_type": 2, "adv_name": "Tower", "adv_lat": 0, "adv_lon": 0}
    ))
    resolver = PathResolver(db)
    # "fb1f11" without separator → three 1-byte hops ["fb", "1f", "11"]
    result = resolver.lookup_prefixes("fb1f11")
    assert "Hilltop" in result
    assert "Valley" in result
    assert "Tower" in result


# ── resolve / resolve_detailed: multibyte path support ───────────────────────

def test_resolve_multibyte_path_colon_separated(tmp_path: Path) -> None:
    """resolve() handles multibyte separator-delimited hops (e.g. 'fb1f:7ab2')."""
    db = RepeaterDB(tmp_path / "repeaters.db")
    asyncio.run(db.load())
    asyncio.run(db.update_from_contact(
        {"public_key": "fb1f11", "adv_type": 2, "adv_name": "Hilltop", "adv_lat": 0, "adv_lon": 0}
    ))
    asyncio.run(db.update_from_contact(
        {"public_key": "fb2f22", "adv_type": 2, "adv_name": "Flatland", "adv_lat": 0, "adv_lon": 0}
    ))
    asyncio.run(db.update_from_contact(
        {"public_key": "7ab233", "adv_type": 2, "adv_name": "Valley", "adv_lat": 0, "adv_lon": 0}
    ))
    resolver = PathResolver(db)
    result = resolver.resolve("fb1f:7ab2")
    assert "Hilltop" in result
    assert "Valley" in result
    assert "Flatland" not in result  # eliminated by 2-byte match
    assert "(2 hops)" in result


def test_resolve_detailed_multibyte_path(tmp_path: Path) -> None:
    """resolve_detailed() returns correct hop count and prefix for multibyte paths."""
    db = RepeaterDB(tmp_path / "repeaters.db")
    asyncio.run(db.load())
    asyncio.run(db.update_from_contact(
        {"public_key": "fb1f11", "adv_type": 2, "adv_name": "Hilltop", "adv_lat": 0, "adv_lon": 0}
    ))
    asyncio.run(db.update_from_contact(
        {"public_key": "7ab233", "adv_type": 2, "adv_name": "Valley", "adv_lat": 0, "adv_lon": 0}
    ))
    resolver = PathResolver(db)
    hops = resolver.resolve_detailed("fb1f:7ab2")
    assert len(hops) == 2
    assert hops[0]["prefix"] == "fb1f"
    assert hops[0]["name"] == "Hilltop"
    assert hops[1]["prefix"] == "7ab2"
    assert hops[1]["name"] == "Valley"


def test_raw_multibyte_path(tmp_path: Path) -> None:
    """raw() preserves multibyte segments in its output."""
    result = PathResolver.raw("fb1f:7ab2")
    assert result == "fb1f:7ab2 (2 hops)"
