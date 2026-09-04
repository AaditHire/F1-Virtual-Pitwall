"""No-key historical weather adapter for Open-Meteo."""

from datetime import UTC, date, datetime

import httpx
from pydantic import BaseModel, ConfigDict


class WeatherObservation(BaseModel):
    """Normalized hourly circuit weather."""

    model_config = ConfigDict(frozen=True)

    observed_at: datetime
    temperature_c: float | None
    precipitation_mm: float | None
    wind_speed_kmh: float | None


class OpenMeteoClient:
    """Fetch historical weather from Open-Meteo's keyless archive API."""

    endpoint = "https://archive-api.open-meteo.com/v1/archive"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def fetch_day(
        self,
        *,
        latitude: float,
        longitude: float,
        day: date,
    ) -> tuple[WeatherObservation, ...]:
        """Fetch an hourly historical series for one circuit day."""
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=15)
        try:
            response = await client.get(
                self.endpoint,
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "start_date": day.isoformat(),
                    "end_date": day.isoformat(),
                    "hourly": "temperature_2m,precipitation,wind_speed_10m",
                    "timezone": "UTC",
                },
            )
            response.raise_for_status()
            hourly = response.json()["hourly"]
            return tuple(
                WeatherObservation(
                    observed_at=datetime.fromisoformat(timestamp).replace(tzinfo=UTC),
                    temperature_c=hourly["temperature_2m"][index],
                    precipitation_mm=hourly["precipitation"][index],
                    wind_speed_kmh=hourly["wind_speed_10m"][index],
                )
                for index, timestamp in enumerate(hourly["time"])
            )
        finally:
            if owns_client:
                await client.aclose()
