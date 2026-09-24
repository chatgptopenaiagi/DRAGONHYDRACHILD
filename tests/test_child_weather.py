"""Offline forecast semantics, exact endpoint, bounds and policy gates."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import gzip
from email.utils import format_datetime

from dragonhydra.child import weather
from dragonhydra.web.contracts import PipelineError


class ChildWeatherTests(unittest.TestCase):
    def fixture(self):
        now = datetime.now(timezone.utc)
        hours = [(now + timedelta(hours=i)).replace(minute=0, second=0, microsecond=0) for i in range(3)]
        data = {"utc_offset_seconds": 0, "latitude": 51.5, "longitude": -0.12, "hourly_units": {"time": "iso8601", "temperature_2m": "°C", "precipitation": "mm"}, "hourly": {"time": [hour.replace(tzinfo=None).isoformat(timespec="minutes") for hour in hours], "temperature_2m": [14.1, 14.4, 14.3], "precipitation": [0.0, 0.2, 0.3]}}
        return data, now.isoformat()

    def test_exact_endpoint_rejects_changed_query_host_credentials_fragment(self):
        with patch.object(weather.socket, "getaddrinfo") as dns:
            for url in (weather.FORECAST_URL + "&apikey=secret", weather.FORECAST_URL.replace("51.5", "51.6"), weather.FORECAST_URL.replace("api.open-meteo.com", "127.0.0.1"), weather.FORECAST_URL + "#fragment", weather.FORECAST_URL.replace("https://", "http://")):
                with self.subTest(url=url), self.assertRaises(PipelineError):
                    weather.request_fixed(url)
            dns.assert_not_called()

    def test_mixed_public_private_dns_rejected_before_socket(self):
        with patch.object(weather.LIMITER, "wait"), patch.object(weather.socket, "getaddrinfo", return_value=[(2, 1, 6, "", ("8.8.8.8", 443)), (2, 1, 6, "", ("127.0.0.1", 443))]), patch.object(weather.socket, "create_connection") as connect:
            with self.assertRaisesRegex(PipelineError, "NON_PUBLIC_DNS"):
                weather.request_fixed(weather.FORECAST_URL)
            connect.assert_not_called()

    def test_redirect_auth_compression_and_oversize_are_blocked(self):
        for status, headers, expected in ((302, {}, "REDIRECT_BLOCKED"), (403, {}, "AUTH_REQUIRED"), (429, {}, "RATE_LIMITED"), (200, {"Content-Type": "application/json", "Content-Encoding": "gzip"}, "CONTENT_ENCODING_UNSUPPORTED"), (200, {"Content-Type": "application/json", "Content-Length": "9999999999"}, "MAX_BYTES_EXCEEDED")):
            with self.subTest(expected=expected):
                response = MagicMock(status=status)
                response.getheader.side_effect = lambda key, default=None: headers.get(key, default)
                conn = MagicMock()
                conn.getresponse.return_value = response
                with patch.object(weather.LIMITER, "wait"), patch.object(weather.socket, "getaddrinfo", return_value=[(2, 1, 6, "", ("8.8.8.8", 443))]), patch.object(weather.socket, "create_connection", return_value=MagicMock()), patch.object(weather.ssl, "create_default_context", return_value=MagicMock()), patch.object(weather.http.client, "HTTPSConnection", return_value=conn), self.assertRaisesRegex(PipelineError, expected):
                    weather.request_fixed(weather.FORECAST_URL)

    def test_forecast_is_hypothesis_never_observed_weather(self):
        data, captured = self.fixture()
        rows = weather.parse_forecast(json.dumps(data).encode(), captured)
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["epistemic_state"], "HYPOTHESIS")
            self.assertEqual(row["temporal_mode"], "STRICT_PIT")
            self.assertEqual(row["available_at"], captured)
            self.assertGreater(datetime.fromisoformat(row["target_at"]), datetime.fromisoformat(captured))

    def test_units_locations_missingness_nonfinite_and_duplicate_times_rejected(self):
        for mutation in (lambda d: d.update(utc_offset_seconds=3600), lambda d: d.update(latitude=40.1), lambda d: d["hourly_units"].update(temperature_2m="F"), lambda d: d["hourly"]["precipitation"].__setitem__(0, None), lambda d: d["hourly"]["temperature_2m"].__setitem__(0, float("nan")), lambda d: d["hourly"]["time"].__setitem__(1, d["hourly"]["time"][0])):
            data, captured = self.fixture()
            mutation(data)
            with self.assertRaisesRegex(PipelineError, "SCHEMA_CHANGED"):
                weather.parse_forecast(json.dumps(data).encode(), captured)

    def test_robots_denial_and_excessive_delay_fail_closed(self):
        for body in (b"User-agent: *\nDisallow: /", b"User-agent: *\nCrawl-delay: 5\nAllow: /"):
            with self.assertRaises(PipelineError):
                weather.robots_gate(body, 200, weather.FORECAST_URL)
        self.assertEqual(weather.robots_gate(b"", 404, weather.FORECAST_URL)["robots_status"], "ABSENT")

    def test_terms_hash_change_blocks_before_forecast_and_persists_failure(self):
        calls = []
        def request(url):
            calls.append(url)
            return (b"User-agent: *\nAllow: /", "text/plain", 200) if url == weather.SITE_ROBOTS else (b"changed-policy", "text/html", 200)
        with tempfile.TemporaryDirectory() as directory, patch.object(weather, "request_fixed", request):
            entry = weather.collect_weather_once(Path(directory))
            self.assertEqual(entry["reason"], "TERMS_CHANGED_REVIEW_REQUIRED")
            self.assertNotIn(weather.FORECAST_URL, calls)
            self.assertEqual(len(list((Path(directory) / "runtime/prospective/open-meteo-london").glob("*.json"))), 1)

    def test_capture_is_immutable_rate_bounded_and_attributed(self):
        data, _ = self.fixture()
        terms, licence = b"reviewed terms", b"reviewed licence"
        def request(url):
            if url in (weather.SITE_ROBOTS, weather.API_ROBOTS):
                return b"User-agent: *\nAllow: /", "text/plain", 200
            if url == weather.TERMS_URL:
                return terms, "text/html", 200
            if url == weather.LICENSE_URL:
                return licence, "text/html", 200
            return json.dumps(data).encode(), "application/json", 200
        with tempfile.TemporaryDirectory() as directory, patch.object(weather, "request_fixed", side_effect=request) as requester, patch.object(weather, "APPROVED_TERMS_SHA256", hashlib.sha256(terms).hexdigest()), patch.object(weather, "APPROVED_LICENSE_SHA256", hashlib.sha256(licence).hexdigest()):
            entry = weather.collect_weather_once(Path(directory))
            self.assertEqual(entry["status"], "CAPTURED")
            self.assertEqual(entry["requests_attempted"], 5)
            snapshot = entry["snapshot"]
            self.assertEqual(snapshot["attribution"]["license"], "CC-BY-4.0")
            self.assertFalse(snapshot["location"]["is_stadium_location"])
            path = Path(directory) / "runtime/prospective/open-meteo-london" / (entry["attempt_id"] + ".json")
            before = path.read_bytes()
            second = weather.collect_weather_once(Path(directory))
            self.assertEqual(second["status"], "NOT_DUE")
            self.assertEqual(requester.call_count, 5)
            self.assertEqual(path.read_bytes(), before)


class ChildMetWeatherTests(unittest.TestCase):
    def fixture(self):
        now = datetime.now(timezone.utc)
        hours = [now + timedelta(hours=i) for i in range(3)]
        rows = [{"time": stamp.isoformat(), "data": {"instant": {"details": {"air_temperature": 14.0}}, "next_1_hours": {"details": {"precipitation_amount": 0.1}}}} for stamp in hours]
        return {"geometry": {"type": "Point", "coordinates": [-.12, 51.5, 25]}, "properties": {"meta": {"updated_at": (now - timedelta(hours=1)).isoformat(), "units": {"air_temperature": "celsius", "precipitation_amount": "mm"}}, "timeseries": rows}}, now.isoformat()

    def test_met_fixed_endpoint_cannot_accept_altered_coordinates_or_new_host(self):
        for url in (weather.MET_FORECAST_URL + "&altitude=12", weather.FORECAST_URL, weather.MET_FORECAST_URL.replace("51.5", "60.1")):
            with self.assertRaises(PipelineError):
                weather.request_met_fixed(url)

    def test_met_forecasts_preserve_missingness_and_hypothesis_semantics(self):
        data, captured = self.fixture()
        del data["properties"]["timeseries"][1]["data"]["next_1_hours"]
        rows = weather.parse_met_forecast(json.dumps(data).encode(), captured)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["epistemic_state"], "HYPOTHESIS")
        self.assertEqual(rows[0]["temporal_mode"], "STRICT_PIT")
        self.assertTrue(rows[0]["precipitation_missing"])
        self.assertIsNone(rows[0]["precipitation_next_hour_mm"])

    def test_met_model_update_from_future_rejected(self):
        data, captured = self.fixture()
        data["properties"]["meta"]["updated_at"] = (datetime.fromisoformat(captured) + timedelta(hours=1)).isoformat()
        with self.assertRaisesRegex(PipelineError, "SCHEMA_CHANGED"):
            weather.parse_met_forecast(json.dumps(data).encode(), captured)

    def test_met_decompression_bomb_is_bounded(self):
        compressed = gzip.compress(b"x" * (weather.MAX_BYTES + 1))
        response = MagicMock(status=200)
        headers = {"Content-Type": "application/json", "Content-Encoding": "gzip"}
        response.getheader.side_effect = lambda key, default=None: headers.get(key, default)
        response.read1.side_effect = [compressed, b""]
        conn = MagicMock()
        conn.getresponse.return_value = response
        with patch.object(weather.LIMITER, "wait"), patch.object(weather.socket, "getaddrinfo", return_value=[(2, 1, 6, "", ("8.8.8.8", 443))]), patch.object(weather.socket, "create_connection", return_value=MagicMock()), patch.object(weather.ssl, "create_default_context", return_value=MagicMock()), patch.object(weather.http.client, "HTTPSConnection", return_value=conn), self.assertRaisesRegex(PipelineError, "DECOMPRESSION_BOUND_EXCEEDED"):
            weather.request_met_fixed(weather.MET_FORECAST_URL)

    def test_met_invalid_cache_validator_rejected_before_network(self):
        with patch.object(weather.socket, "getaddrinfo") as dns:
            for validator in ("bad\r\nAuthorization: secret", format_datetime(datetime.now(timezone.utc) + timedelta(days=1))):
                with self.assertRaisesRegex(PipelineError, "INVALID_CACHE_VALIDATOR"):
                    weather.request_met_fixed(weather.MET_FORECAST_URL, modified_since=validator)
            dns.assert_not_called()

    def test_met_provider_expiry_is_honored_even_after_daily_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "runtime/prospective/met-norway-london"
            ledger.mkdir(parents=True)
            previous = {"attempted_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(), "status": "CAPTURED", "cache_expires": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}
            (ledger / "previous.json").write_text(json.dumps(previous))
            with patch.object(weather, "request_met_fixed") as request:
                result = weather.collect_met_weather_once(root)
                self.assertEqual(result["reason"], "PROVIDER_CACHE_EXPIRES")
                request.assert_not_called()

    def test_met_capture_reuses_policy_cache_and_records_headers(self):
        data, _ = self.fixture()
        terms, licence = b"reviewed met terms", b"reviewed met licence"
        current = datetime.now(timezone.utc)
        modified = format_datetime(current - timedelta(hours=1))
        expiry = format_datetime(current + timedelta(hours=1))
        def request(url, **kwargs):
            if url == weather.MET_ROBOTS_URL:
                return b"User-agent: *\nDisallow:", "text/plain", 200, {}
            self.assertEqual(url, weather.MET_FORECAST_URL)
            return json.dumps(data).encode(), "application/json", 200, {"expires": expiry, "last_modified": modified}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = weather.RawEvidenceStore(root / "runtime/raw")
            th, lh = raw.put(terms), raw.put(licence)
            with patch.object(weather, "MET_APPROVED_TERMS_SHA256", th), patch.object(weather, "MET_APPROVED_LICENSE_SHA256", lh), patch.object(weather, "MET_POLICY_REVIEWED_AT", current.isoformat()), patch.object(weather, "request_met_fixed", side_effect=request) as requester:
                result = weather.collect_met_weather_once(root)
                self.assertEqual(result["status"], "CAPTURED")
                self.assertEqual(requester.call_count, 2)
                self.assertEqual(result["last_modified"], modified)
                self.assertEqual(result["snapshot"]["source_id"], "met-norway")
                self.assertEqual(result["snapshot"]["attribution"]["license"], "CC-BY-4.0")
                self.assertEqual(weather.collect_met_weather_once(root)["status"], "NOT_DUE")


if __name__ == "__main__":
    unittest.main()
