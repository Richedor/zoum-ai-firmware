"""
Database — Queue SQLite offline-first multi-endpoint.

Tables :
  outbox : id, ts, endpoint, payload_json, retry_count, next_retry_at
  badge_cache : uid_hash, driver_id, driver_name, cached_at

Stratégie :
  - Chaque événement est inséré en queue
  - Le sync thread lit par batch et envoie
  - ACK → suppression
  - FAIL → retry_count++ + backoff exponentiel
"""
from __future__ import annotations
import sqlite3
import json
import time
from typing import Iterable


def init_db(db_path: str) -> None:
    with sqlite3.connect(db_path) as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            endpoint TEXT NOT NULL,
            payload TEXT NOT NULL,
            retry_count INTEGER DEFAULT 0,
            next_retry_at REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS badge_cache (
            uid_hash TEXT PRIMARY KEY,
            driver_id TEXT,
            driver_name TEXT,
            cached_at REAL
        );

        CREATE TABLE IF NOT EXISTS telemetry_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payload TEXT NOT NULL
        );
        """)

        # Migrer les anciennes données si présentes
        cur = con.execute("SELECT COUNT(*) FROM telemetry_queue")
        old_count = cur.fetchone()[0]
        if old_count > 0:
            con.execute("""
                INSERT INTO outbox (ts, endpoint, payload, retry_count, next_retry_at)
                SELECT 0, 'telemetry', payload, 0, 0 FROM telemetry_queue
            """)
            con.execute("DELETE FROM telemetry_queue")
            print(f"[DB] {old_count} anciens messages migrés vers outbox")

        con.commit()


def enqueue(db_path: str, endpoint: str, payload: dict) -> None:
    with sqlite3.connect(db_path) as con:
        con.execute(
            "INSERT INTO outbox(ts, endpoint, payload) VALUES (?, ?, ?)",
            (time.time(), endpoint, json.dumps(payload)),
        )
        con.commit()


def dequeue_batch(db_path: str, limit: int = 50) -> list[tuple[int, str, dict]]:
    """Retourne les messages prêts : [(id, endpoint, payload), ...]"""
    now = time.time()
    with sqlite3.connect(db_path) as con:
        cur = con.execute(
            "SELECT id, endpoint, payload FROM outbox "
            "WHERE next_retry_at <= ? ORDER BY id ASC LIMIT ?",
            (now, limit),
        )
        rows = cur.fetchall()
    return [(rid, ep, json.loads(p)) for rid, ep, p in rows]


def mark_sent(db_path: str, ids: Iterable[int]) -> None:
    ids = list(ids)
    if not ids:
        return
    q = "DELETE FROM outbox WHERE id IN (%s)" % ",".join(["?"] * len(ids))
    with sqlite3.connect(db_path) as con:
        con.execute(q, ids)
        con.commit()


def mark_failed(db_path: str, row_id: int) -> None:
    """Incrémente retry_count + backoff exponentiel (max 600 s)."""
    with sqlite3.connect(db_path) as con:
        cur = con.execute("SELECT retry_count FROM outbox WHERE id=?", (row_id,))
        row = cur.fetchone()
        if row is None:
            return
        retries = row[0] + 1
        delay = min(5 * (2 ** retries), 600)
        next_retry = time.time() + delay
        con.execute(
            "UPDATE outbox SET retry_count=?, next_retry_at=? WHERE id=?",
            (retries, next_retry, row_id),
        )
        con.commit()


def queue_size(db_path: str) -> int:
    with sqlite3.connect(db_path) as con:
        cur = con.execute("SELECT COUNT(*) FROM outbox")
        return cur.fetchone()[0]


def purge_old(db_path: str, max_items: int = 50000) -> int:
    """Supprime les télémétriques les plus anciennes si > max_items."""
    with sqlite3.connect(db_path) as con:
        cur = con.execute("SELECT COUNT(*) FROM outbox")
        total = cur.fetchone()[0]
        if total <= max_items:
            return 0
        excess = total - max_items
        con.execute(
            "DELETE FROM outbox WHERE id IN "
            "(SELECT id FROM outbox WHERE endpoint='telemetry' "
            "ORDER BY id ASC LIMIT ?)",
            (excess,),
        )
        con.commit()
        print(f"[DB] Purge : {excess} messages supprimés")
        return excess


# ── Cache badges ─────────────────────────────────────────────────────

def cache_badge(db_path: str, uid_hash: str, driver_id: str, driver_name: str):
    with sqlite3.connect(db_path) as con:
        con.execute(
            "INSERT OR REPLACE INTO badge_cache "
            "(uid_hash, driver_id, driver_name, cached_at) VALUES (?, ?, ?, ?)",
            (uid_hash, driver_id, driver_name, time.time()),
        )
        con.commit()


def lookup_badge(db_path: str, uid_hash: str) -> dict | None:
    with sqlite3.connect(db_path) as con:
        cur = con.execute(
            "SELECT driver_id, driver_name FROM badge_cache WHERE uid_hash=?",
            (uid_hash,),
        )
        row = cur.fetchone()
    if row:
        return {"driver_id": row[0], "driver_name": row[1]}
    return None


# ── Compat anciennes fonctions ───────────────────────────────────────

def delete_ids(db_path, ids):
    mark_sent(db_path, ids)
