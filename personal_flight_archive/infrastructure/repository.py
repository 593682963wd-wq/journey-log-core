from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from personal_flight_archive.domain.models import PersonalFlight
from personal_flight_archive.domain.validation import DuplicateFlightError, ValidationError


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class PersonalArchiveRepository:
    """SQLite repository with explicit connection close on every operation."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path).expanduser()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS flights (
                    flight_id TEXT PRIMARY KEY,
                    flight_date TEXT NOT NULL,
                    flight_number TEXT,
                    origin_icao TEXT NOT NULL,
                    destination_icao TEXT NOT NULL,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_flights_date ON flights(flight_date);
                CREATE INDEX IF NOT EXISTS idx_flights_route ON flights(origin_icao, destination_icao);
                CREATE TABLE IF NOT EXISTS archive_batches (
                    batch_id TEXT PRIMARY KEY,
                    batch_type TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    license TEXT NOT NULL,
                    fetched_at TEXT,
                    observed_at TEXT,
                    expires_at TEXT,
                    freshness TEXT NOT NULL,
                    quality_status TEXT NOT NULL,
                    raw_payload_hash TEXT NOT NULL,
                    adapter_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'preview'
                );
                CREATE TABLE IF NOT EXISTS attachments (
                    attachment_id TEXT PRIMARY KEY,
                    flight_id TEXT NOT NULL REFERENCES flights(flight_id),
                    original_name TEXT NOT NULL,
                    storage_name TEXT NOT NULL UNIQUE,
                    mime_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    deleted_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_attachments_flight ON attachments(flight_id);
                CREATE TABLE IF NOT EXISTS audit_log (
                    audit_id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _flight_payload(flight: PersonalFlight | dict[str, Any]) -> dict[str, Any]:
        return asdict(flight) if isinstance(flight, PersonalFlight) else dict(flight)

    @staticmethod
    def _flight_from_row(row: sqlite3.Row) -> PersonalFlight:
        payload = json.loads(row["payload_json"])
        payload["created_at"] = row["created_at"]
        payload["updated_at"] = row["updated_at"]
        payload["deleted_at"] = row["deleted_at"]
        return PersonalFlight(**payload)

    def add_flight(self, flight: PersonalFlight) -> PersonalFlight:
        payload = self._flight_payload(flight)
        now = flight.updated_at or utc_now()
        created = flight.created_at or now
        payload["created_at"] = created
        payload["updated_at"] = now
        try:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO flights(flight_id, flight_date, flight_number, origin_icao, destination_icao, dedupe_key, payload_json, created_at, updated_at, deleted_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        flight.flight_id,
                        flight.flight_date,
                        flight.flight_number,
                        flight.origin_icao,
                        flight.destination_icao,
                        flight.dedupe_key,
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        created,
                        now,
                        flight.deleted_at,
                    ),
                )
                self._audit(connection, "create", "flight", flight.flight_id, {"source": flight.source})
        except sqlite3.IntegrityError as exc:
            if "dedupe_key" in str(exc) or "flights.dedupe_key" in str(exc):
                raise DuplicateFlightError("重复飞行记录：日期、航班、航段和起飞时间相同") from exc
            raise
        return self.get_flight(flight.flight_id) or flight

    def update_flight(self, flight: PersonalFlight) -> PersonalFlight:
        payload = self._flight_payload(flight)
        now = flight.updated_at or utc_now()
        payload["updated_at"] = now
        with self._connection() as connection:
            existing = connection.execute("SELECT flight_id FROM flights WHERE flight_id = ?", (flight.flight_id,)).fetchone()
            if existing is None:
                raise ValidationError("目标飞行记录不存在")
            try:
                connection.execute(
                    """
                    UPDATE flights SET flight_date=?, flight_number=?, origin_icao=?, destination_icao=?, dedupe_key=?, payload_json=?, updated_at=?, deleted_at=?
                    WHERE flight_id=?
                    """,
                    (
                        flight.flight_date,
                        flight.flight_number,
                        flight.origin_icao,
                        flight.destination_icao,
                        flight.dedupe_key,
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        now,
                        flight.deleted_at,
                        flight.flight_id,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                if "dedupe_key" in str(exc):
                    raise DuplicateFlightError("修改后与已有记录重复") from exc
                raise
            self._audit(connection, "update", "flight", flight.flight_id, {"source": flight.source})
        return self.get_flight(flight.flight_id) or flight

    def get_flight(self, flight_id: str, *, include_deleted: bool = False) -> PersonalFlight | None:
        with self._connection() as connection:
            query = "SELECT * FROM flights WHERE flight_id = ?"
            params: list[Any] = [flight_id]
            if not include_deleted:
                query += " AND deleted_at IS NULL"
            row = connection.execute(query, params).fetchone()
        return self._flight_from_row(row) if row else None

    def list_flights(self, *, include_deleted: bool = False) -> list[PersonalFlight]:
        with self._connection() as connection:
            query = "SELECT * FROM flights"
            if not include_deleted:
                query += " WHERE deleted_at IS NULL"
            query += " ORDER BY flight_date DESC, updated_at DESC, created_at DESC"
            rows = connection.execute(query).fetchall()
        return [self._flight_from_row(row) for row in rows]

    def soft_delete_flight(self, flight_id: str, *, confirm: bool = False) -> PersonalFlight:
        if not confirm:
            raise ValidationError("删除飞行记录必须明确 confirm=true")
        target = self.get_flight(flight_id)
        if target is None:
            raise ValidationError("目标飞行记录不存在或已删除")
        deleted = utc_now()
        updated = PersonalFlight(**{**target.to_dict(), "deleted_at": deleted, "updated_at": deleted})
        return self.update_flight(updated)

    def add_batch(
        self,
        *,
        batch_id: str,
        batch_type: str,
        original_name: str,
        payload: dict[str, Any],
        source: str,
        source_url: str,
        license_name: str,
        fetched_at: str | None,
        observed_at: str | None,
        expires_at: str | None,
        freshness: str,
        quality_status: str,
        raw_payload_hash: str,
        adapter_version: str,
        status: str = "preview",
    ) -> dict[str, Any]:
        created = utc_now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO archive_batches(batch_id, batch_type, original_name, payload_json, source, source_url, license, fetched_at, observed_at, expires_at, freshness, quality_status, raw_payload_hash, adapter_version, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    batch_type,
                    original_name[:240],
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    source,
                    source_url,
                    license_name,
                    fetched_at,
                    observed_at,
                    expires_at,
                    freshness,
                    quality_status,
                    raw_payload_hash,
                    adapter_version,
                    created,
                    status,
                ),
            )
            self._audit(connection, "create", "batch", batch_id, {"batch_type": batch_type, "status": status})
        return self.get_batch(batch_id) or {}

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM archive_batches WHERE batch_id = ?", (batch_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        return result

    def update_batch_status(self, batch_id: str, status: str) -> None:
        with self._connection() as connection:
            connection.execute("UPDATE archive_batches SET status=? WHERE batch_id=?", (status, batch_id))
            self._audit(connection, "status", "batch", batch_id, {"status": status})

    def list_batches(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM archive_batches ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 200)),)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            result.append(item)
        return result

    def add_attachment(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO attachments(attachment_id, flight_id, original_name, storage_name, mime_type, size_bytes, sha256, created_at, deleted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    payload["attachment_id"],
                    payload["flight_id"],
                    payload["original_name"],
                    payload["storage_name"],
                    payload["mime_type"],
                    payload["size_bytes"],
                    payload["sha256"],
                    payload.get("created_at") or utc_now(),
                ),
            )
            self._audit(connection, "create", "attachment", payload["attachment_id"], {"flight_id": payload["flight_id"]})
        return self.get_attachment(payload["attachment_id"]) or payload

    def get_attachment(self, attachment_id: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
        with self._connection() as connection:
            query = "SELECT * FROM attachments WHERE attachment_id=?"
            if not include_deleted:
                query += " AND deleted_at IS NULL"
            row = connection.execute(query, (attachment_id,)).fetchone()
        return dict(row) if row else None

    def list_attachments(self, flight_id: str, *, include_deleted: bool = False) -> list[dict[str, Any]]:
        with self._connection() as connection:
            query = "SELECT * FROM attachments WHERE flight_id=?"
            if not include_deleted:
                query += " AND deleted_at IS NULL"
            query += " ORDER BY created_at DESC"
            rows = connection.execute(query, (flight_id,)).fetchall()
        return [dict(row) for row in rows]

    def list_attachments_for_export(self) -> list[dict[str, Any]]:
        """Return attachment metadata without exposing storage paths."""
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT attachment_id, flight_id, original_name, mime_type, size_bytes, sha256, created_at, deleted_at FROM attachments ORDER BY created_at"
            ).fetchall()
        return [dict(row) for row in rows]

    def soft_delete_attachment(self, attachment_id: str, *, confirm: bool = False) -> dict[str, Any]:
        if not confirm:
            raise ValidationError("删除附件必须明确 confirm=true")
        if self.get_attachment(attachment_id) is None:
            raise ValidationError("目标附件不存在或已删除")
        deleted = utc_now()
        with self._connection() as connection:
            connection.execute("UPDATE attachments SET deleted_at=? WHERE attachment_id=?", (deleted, attachment_id))
            self._audit(connection, "delete", "attachment", attachment_id, {})
        return self.get_attachment(attachment_id, include_deleted=True) or {}

    def audit_events(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 500)),)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["summary"] = json.loads(item.pop("summary_json"))
            result.append(item)
        return result

    def health(self) -> dict[str, Any]:
        try:
            with self._connection() as connection:
                connection.execute("SELECT 1").fetchone()
                count = int(connection.execute("SELECT COUNT(*) FROM flights WHERE deleted_at IS NULL").fetchone()[0])
            return {"ok": True, "flight_count": count}
        except sqlite3.Error:
            return {"ok": False, "flight_count": None}

    @staticmethod
    def _audit(connection: sqlite3.Connection, action: str, entity_type: str, entity_id: str, summary: dict[str, Any]) -> None:
        connection.execute(
            "INSERT INTO audit_log(audit_id, action, entity_type, entity_id, summary_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, action, entity_type, entity_id, json.dumps(summary, ensure_ascii=False), utc_now()),
        )


__all__ = ["PersonalArchiveRepository", "utc_now"]
