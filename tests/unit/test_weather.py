import asyncio
from datetime import UTC, date

import httpx

from f1_pitwall.weather import OpenMeteoClient


def test_open_meteo_observations_are_utc_aware() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["timezone"] == "UTC"
        return httpx.Response(
            200,
            json={
                "hourly": {
                    "time": ["2024-03-02T00:00"],
                    "temperature_2m": [20.0],
                    "precipitation": [0.0],
                    "wind_speed_10m": [15.0],
                }
            },
        )

    async def fetch() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            observations = await OpenMeteoClient(client).fetch_day(
                latitude=26.0325,
                longitude=50.5106,
                day=date(2024, 3, 2),
            )
        assert observations[0].observed_at.tzinfo is UTC
        assert observations[0].observed_at.hour == 0

    asyncio.run(fetch())
