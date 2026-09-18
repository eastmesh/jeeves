"""SQLite-backed node database (all discovered MeshCore nodes)."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from pathlib import Path

log = logging.getLogger("pathbot.repeater_db")

# MeshCore ADV_TYPE values
ADV_TYPE_REPEATER = 2
ADV_TYPE_NAMES: dict[int, str] = {
    0: "unknown",
    1: "client",
    2: "repeater",
    3: "room",
    4: "bridge",
}
STALE_REPEATER_AGE_DAYS = 7


class RepeaterDB:
    """Thread/async-safe persistent store of known repeater nodes.

    Each entry is keyed by the full public_key hex string and contains:
        public_key, prefix, name, lat, lon, type, last_seen
    """

    def __init__(self, filepath: Path):
        self.legacy_filepath = filepath
        self.filepath = filepath.with_suffix(".db") if filepath.suffix == ".json" else filepath
        self.nodes: dict[str, dict] = {}
        self._lock = asyncio.Lock()
        self._conn: sqlite3.Connection | None = None

    async def load(self) -> None:
        """Load repeater data from SQLite, migrating legacy JSON if needed."""
        async with self._lock:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            self._init_db_sync()
            self._migrate_legacy_json_sync()
            self._load_sync()

    def _init_db_sync(self) -> None:
        """Open database connection and ensure schema exists."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.filepath)
            self._conn.row_factory = sqlite3.Row

        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS repeaters (
                public_key TEXT PRIMARY KEY,
                prefix TEXT NOT NULL,
                name TEXT NOT NULL,
                lat REAL NOT NULL DEFAULT 0,
                lon REAL NOT NULL DEFAULT 0,
                type INTEGER NOT NULL,
                last_seen INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_repeaters_prefix ON repeaters(prefix);
            CREATE INDEX IF NOT EXISTS idx_repeaters_last_seen ON repeaters(last_seen);

            CREATE TABLE IF NOT EXISTS guest_page_visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT NOT NULL,
                path TEXT NOT NULL,
                visited_at INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_guest_page_visits_visited_at
                ON guest_page_visits(visited_at DESC);
            CREATE INDEX IF NOT EXISTS idx_guest_page_visits_ip
                ON guest_page_visits(ip_address);
            CREATE INDEX IF NOT EXISTS idx_guest_page_visits_path
                ON guest_page_visits(path);
            """
        )
        self._conn.commit()

    def _migrate_legacy_json_sync(self) -> None:
        """Migrate data from legacy JSON file when present."""
        if self.legacy_filepath.suffix != ".json" or not self.legacy_filepath.exists():
            return

        cur = self._conn.execute("SELECT COUNT(1) FROM repeaters")
        row_count = cur.fetchone()[0]
        if row_count > 0:
            return

        try:
            with open(self.legacy_filepath, "r") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            log.warning(f"Could not migrate legacy repeater JSON: {e}")
            return

        migrated = 0
        for public_key, node in dict(data).items():
            normalized = self._normalize_entry({**node, "public_key": public_key})
            self._upsert_sync(normalized)
            migrated += 1

        if migrated:
            log.info(
                f"Migrated {migrated} repeaters from legacy JSON "
                f"{self.legacy_filepath} -> {self.filepath}"
            )

    def _load_sync(self) -> None:
        """Load all repeaters from SQLite into in-memory cache."""
        rows = self._conn.execute(
            "SELECT public_key, prefix, name, lat, lon, type, last_seen FROM repeaters"
        ).fetchall()
        self.nodes = {row["public_key"]: dict(row) for row in rows}
        log.info(f"Loaded {len(self.nodes)} nodes from {self.filepath}")

    async def save(self) -> None:
        """No-op for API compatibility; updates are persisted immediately."""
        return

    @staticmethod
    def _normalize_timestamp(raw: int | float | None) -> int:
        if raw is None:
            return int(time.time())
        ts = int(raw)
        if ts > 10_000_000_000:
            ts //= 1000
        if ts <= 0:
            return int(time.time())
        return ts

    def _normalize_entry(self, contact: dict) -> dict:
        """Normalize contact payload into repeater DB entry."""
        pub_key = contact.get("public_key", "")
        adv_type = int(contact.get("type", contact.get("adv_type", 0)))
        name = str(contact.get("adv_name", contact.get("name", "unknown")))
        lat = float(contact.get("adv_lat", contact.get("lat", 0.0)))
        lon = float(contact.get("adv_lon", contact.get("lon", 0.0)))
        raw_last_seen = (
            contact.get("last_seen")
            or contact.get("last_seen_ts")
            or contact.get("last_seen_at")
            or contact.get("last_heard")
            or contact.get("last_heard_ts")
            or contact.get("last_heard_at")
        )
        last_seen = (
            self._normalize_timestamp(raw_last_seen)
            if raw_last_seen is not None
            else None
        )

        return {
            "public_key": pub_key,
            "prefix": pub_key[:2].lower(),
            "name": name,
            "lat": lat,
            "lon": lon,
            "type": adv_type,
            "last_seen": last_seen,
        }

    def _upsert_sync(self, entry: dict) -> None:
        """Upsert a repeater entry into SQLite and cache."""
        existing = self.nodes.get(entry["public_key"])
        if entry["last_seen"] is None:
            entry["last_seen"] = existing.get("last_seen", int(time.time())) if existing else int(time.time())
        elif existing:
            entry["last_seen"] = max(existing.get("last_seen", 0), entry["last_seen"])

        self._conn.execute(
            """
            INSERT INTO repeaters (public_key, prefix, name, lat, lon, type, last_seen)
            VALUES (:public_key, :prefix, :name, :lat, :lon, :type, :last_seen)
            ON CONFLICT(public_key) DO UPDATE SET
                prefix=excluded.prefix,
                name=excluded.name,
                lat=excluded.lat,
                lon=excluded.lon,
                type=excluded.type,
                last_seen=CASE
                    WHEN excluded.last_seen > repeaters.last_seen
                    THEN excluded.last_seen
                    ELSE repeaters.last_seen
                END
            """,
            entry,
        )
        self._conn.commit()

        row = self._conn.execute(
            "SELECT public_key, prefix, name, lat, lon, type, last_seen "
            "FROM repeaters WHERE public_key = ?",
            (entry["public_key"],),
        ).fetchone()
        self.nodes[entry["public_key"]] = dict(row)

    @staticmethod
    def type_name(adv_type: int) -> str:
        """Return a human-readable name for a MeshCore ADV_TYPE integer."""
        return ADV_TYPE_NAMES.get(adv_type, f"type{adv_type}")

    async def update_from_contact(self, contact: dict) -> dict | None:
        """Update DB from a contact dict. Returns stored entry, or None if invalid."""
        pub_key = contact.get("public_key", "")

        if not pub_key or len(pub_key) < 2:
            return None

        entry = self._normalize_entry(contact)

        async with self._lock:
            is_new = pub_key not in self.nodes
            self._upsert_sync(entry)
            entry = self.nodes[pub_key]

        type_label = self.type_name(entry["type"])
        if is_new:
            log.info(
                f"New node [{type_label}]: {entry['name']} "
                f"(prefix={entry['prefix']}, lat={entry['lat']}, lon={entry['lon']})"
            )
        else:
            log.debug(f"Updated node [{type_label}]: {entry['name']} (prefix={entry['prefix']})")

        return entry

    async def cleanup_stale(self, max_age_days: int = STALE_REPEATER_AGE_DAYS) -> int:
        """Delete repeaters not seen in `max_age_days` days."""
        cutoff = int(time.time()) - (max_age_days * 24 * 60 * 60)
        async with self._lock:
            cursor = self._conn.execute("DELETE FROM repeaters WHERE last_seen < ?", (cutoff,))
            deleted = cursor.rowcount
            if deleted:
                self._conn.commit()
                self._load_sync()
            return deleted

    def get_by_prefix(self, prefix: str) -> list[dict]:
        """Get all repeaters matching a hex prefix.

        For a 1-byte prefix (2 hex chars) matches the stored prefix field.
        For longer prefixes (e.g. 4 hex chars from a 2-byte path hash) matches
        against the full public_key, eliminating more collisions.
        """
        prefix = prefix.lower()
        if len(prefix) == 2:
            return [n for n in self.nodes.values() if n["prefix"] == prefix]
        return [n for n in self.nodes.values() if n["public_key"].lower().startswith(prefix)]

    def get_all(self) -> list[dict]:
        """Return all repeater entries sorted by name."""
        return sorted(self.nodes.values(), key=lambda n: n.get("name", ""))

    async def delete(self, public_key: str) -> bool:
        """Remove a repeater by public key. Returns True if it existed."""
        async with self._lock:
            cursor = self._conn.execute("DELETE FROM repeaters WHERE public_key = ?", (public_key,))
            existed = cursor.rowcount > 0
            if existed:
                self._conn.commit()
                self.nodes.pop(public_key, None)
            return existed

    def get_collisions(self) -> list[dict]:
        """Return groups of repeaters that share the same prefix.

        Each group is a dict: {"prefix": "fb", "repeaters": [entry, entry, ...]}
        Only includes prefixes with 2+ repeaters. Sorted by prefix.
        """
        from collections import defaultdict

        by_prefix: dict[str, list[dict]] = defaultdict(list)
        for node in self.nodes.values():
            by_prefix[node["prefix"]].append(node)

        groups = []
        for prefix in sorted(by_prefix):
            entries = by_prefix[prefix]
            if len(entries) >= 2:
                groups.append({
                    "prefix": prefix,
                    "repeaters": sorted(entries, key=lambda n: n.get("name", "")),
                })
        return groups

    @property
    def count(self) -> int:
        return len(self.nodes)

    def stats(self) -> dict:
        """Return statistics about the repeater DB."""
        prefixes = set(n["prefix"] for n in self.nodes.values())
        collisions = sum(1 for p in prefixes if len(self.get_by_prefix(p)) > 1)
        with_location = sum(
            1 for n in self.nodes.values() if n.get("lat", 0) != 0 or n.get("lon", 0) != 0
        )
        return {
            "total": self.count,
            "unique_prefixes": len(prefixes),
            "collisions": collisions,
            "with_location": with_location,
            "guest_visitors": self.guest_visit_stats(),
        }

    async def record_guest_visit(self, ip_address: str, path: str) -> None:
        """Persist a guest page view for admin visibility."""
        clean_ip = (ip_address or "unknown").strip() or "unknown"
        clean_path = (path or "/").strip() or "/"
        visited_at = int(time.time())

        async with self._lock:
            self._conn.execute(
                "INSERT INTO guest_page_visits (ip_address, path, visited_at) VALUES (?, ?, ?)",
                (clean_ip, clean_path, visited_at),
            )
            self._conn.commit()

    def guest_visit_stats(self, top_limit: int = 10, recent_limit: int = 25) -> dict:
        """Return guest visitor aggregation for admin stats pages."""
        totals = self._conn.execute(
            """
            SELECT
                COUNT(1) AS total_hits,
                COUNT(DISTINCT ip_address) AS unique_ips,
                COUNT(DISTINCT path) AS unique_pages
            FROM guest_page_visits
            """
        ).fetchone()

        top_pages = [
            {"path": row["path"], "hits": row["hits"]}
            for row in self._conn.execute(
                """
                SELECT path, COUNT(1) AS hits
                FROM guest_page_visits
                GROUP BY path
                ORDER BY hits DESC, path ASC
                LIMIT ?
                """,
                (top_limit,),
            ).fetchall()
        ]

        top_ips = [
            {"ip": row["ip_address"], "hits": row["hits"]}
            for row in self._conn.execute(
                """
                SELECT ip_address, COUNT(1) AS hits
                FROM guest_page_visits
                GROUP BY ip_address
                ORDER BY hits DESC, ip_address ASC
                LIMIT ?
                """,
                (top_limit,),
            ).fetchall()
        ]

        recent_visits = [
            {"ip": row["ip_address"], "path": row["path"], "visited_at": row["visited_at"]}
            for row in self._conn.execute(
                """
                SELECT ip_address, path, visited_at
                FROM guest_page_visits
                ORDER BY visited_at DESC, id DESC
                LIMIT ?
                """,
                (recent_limit,),
            ).fetchall()
        ]

        return {
            "total_hits": totals["total_hits"],
            "unique_ips": totals["unique_ips"],
            "unique_pages": totals["unique_pages"],
            "top_pages": top_pages,
            "top_ips": top_ips,
            "recent_visits": recent_visits,
        }

    def stats_str(self) -> str:
        """Return a formatted stats string."""
        s = self.stats()
        return (
            f"{s['total']} nodes, "
            f"{s['unique_prefixes']} unique prefixes, "
            f"{s['collisions']} collisions"
        )
