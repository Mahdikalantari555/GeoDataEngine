from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests
from data_engine.io.dynamic_weather_fetcher import DynamicWeatherFetcher


def test_dynamic_weather_fetcher_retry_on_429_then_succeed() -> None:
    fetcher = DynamicWeatherFetcher()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "hourly": {
            "time": ["2023-05-01T10:00"],
            "temperature_2m": [20.0],
            "relative_humidity_2m": [50.0],
            "surface_pressure": [1013.25],
            "shortwave_radiation": [600.0],
            "wind_speed_10m": [3.5],
        }
    }
    mock_resp.raise_for_status.return_value = None

    calls = 0

    def fake_get(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls < 3:
            err_resp = MagicMock()
            err_resp.status_code = 429
            raise requests.HTTPError(response=err_resp)
        return mock_resp

    with patch("requests.get", side_effect=fake_get):
        result = fetcher._fetch_weather_for_point(35.0, 51.0, "2023-05-01")
        assert result is not None
        assert calls == 3
