from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PersonalFlight:
    flight_id: str
    flight_date: str
    flight_number: str | None
    origin_icao: str
    destination_icao: str
    departure_local: str | None = None
    arrival_local: str | None = None
    origin_timezone: str | None = None
    destination_timezone: str | None = None
    airline: str | None = None
    aircraft_type: str | None = None
    registration: str | None = None
    seat: str | None = None
    cabin: str | None = None
    purpose_tags: list[str] = field(default_factory=list)
    companion_label: str | None = None
    notes: str | None = None
    source: str = "manual"
    confirmed_at: str | None = None
    privacy_level: str = "private"
    distance_nm: float | None = None
    distance_source: str | None = None
    duration_minutes: int | None = None
    dedupe_key: str = ""
    manual_fields: list[str] = field(default_factory=list)
    source_url: str = ""
    license: str = "user_confirmed"
    fetched_at: str | None = None
    observed_at: str | None = None
    expires_at: str | None = None
    freshness: str = "fresh"
    quality_status: str = "fresh"
    raw_payload_hash: str = ""
    adapter_version: str = "personal_flight_archive/0.1.0"
    created_at: str | None = None
    updated_at: str | None = None
    deleted_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
