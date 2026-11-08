from __future__ import annotations

from collections import Counter, defaultdict
import json
from typing import Any

from personal_flight_archive.domain.models import PersonalFlight
AirportCatalog=object
from personal_flight_archive.infrastructure.repository import PersonalArchiveRepository


class StatisticsService:
    def __init__(self, repository: PersonalArchiveRepository, catalog: AirportCatalog):
        self.repository = repository
        self.catalog = catalog

    def summary(self) -> dict[str, Any]:
        flights = self.repository.list_flights()
        years = Counter(item.flight_date[:4] for item in flights)
        airlines = Counter(item.airline or "未填写" for item in flights)
        aircraft = Counter(item.aircraft_type or "未填写" for item in flights)
        routes = Counter(json.dumps([item.origin_icao, item.destination_icao], ensure_ascii=False) for item in flights)
        months = Counter(item.flight_date[:7] for item in flights)
        total_distance = round(sum(item.distance_nm or 0 for item in flights), 1)
        total_duration = sum(item.duration_minutes or 0 for item in flights)
        airports = sorted({code for item in flights for code in (item.origin_icao, item.destination_icao)})
        return {
            "total_flights": len(flights),
            "total_distance_nm": total_distance,
            "total_duration_minutes": total_duration,
            "airport_count": len(airports),
            "missing_time_count": sum(not item.departure_local or not item.arrival_local for item in flights),
            "by_year": dict(sorted(years.items(), reverse=True)),
            "by_month": dict(sorted(months.items(), reverse=True)),
            "by_airline": dict(airlines.most_common(20)),
            "by_aircraft_type": dict(aircraft.most_common(20)),
            "by_route": dict(routes.most_common(20)),
        }

    def calendar(self) -> list[dict[str, Any]]:
        return [
            {
                "date": item.flight_date,
                "flight_id": item.flight_id,
                "route": f"{item.origin_icao} → {item.destination_icao}",
                "flight_number": item.flight_number,
                "quality_status": item.quality_status,
            }
            for item in self.repository.list_flights()
        ]

    def map_data(self) -> dict[str, Any]:
        airports: dict[str, dict[str, Any]] = {}
        routes = []
        for item in self.repository.list_flights():
            origin = self.catalog.get(item.origin_icao)
            destination = self.catalog.get(item.destination_icao)
            if origin:
                airports[origin.icao] = {**origin.to_dict(), "flight_count": airports.get(origin.icao, {}).get("flight_count", 0) + 1}
            if destination:
                airports[destination.icao] = {**destination.to_dict(), "flight_count": airports.get(destination.icao, {}).get("flight_count", 0) + 1}
            if origin and destination:
                routes.append(
                    {
                        "origin_icao": origin.icao,
                        "destination_icao": destination.icao,
                        "origin": [origin.longitude, origin.latitude],
                        "destination": [destination.longitude, destination.latitude],
                        "distance_nm": item.distance_nm,
                    }
                )
        return {"airports": list(airports.values()), "routes": routes}


__all__ = ["StatisticsService"]
