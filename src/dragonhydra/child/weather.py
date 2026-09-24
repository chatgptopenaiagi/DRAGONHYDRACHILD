"""Two bounded forecast producers for one explicit London proxy.

This is a private noncommercial experiment, not a general weather crawler. Forecast
values are external hypotheses; capturing them now does not observe future weather.
The inherited no-query fetcher remains unchanged. Each producer permits one fixed,
reviewed query and cannot accept arbitrary coordinates, query keys or destinations.
MET Norway is independent; Open-Meteo's robots block is preserved, never bypassed.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import ipaddress
import json
import math
from pathlib import Path
import socket
import ssl
import time
from urllib.parse import urlsplit, urljoin
from email.utils import parsedate_to_datetime
from uuid import uuid4
import zlib

from dragonhydra.config import PROJECT_ROOT
from dragonhydra.science.prospective import RawEvidenceStore
from dragonhydra.web.contracts import PipelineError, utcnow
from dragonhydra.web.provenance import exclusive_json
from dragonhydra.web.rate_limit import LIMITER
from dragonhydra.web.robots import evaluate_robots

SOURCE_ID = "open-meteo"
POLICY_VERSION = "child-open-meteo-private-london/1.0"
PARSER_VERSION = "open-meteo-hourly-london/1.0"
USER_AGENT = "DRAGONHYDRACHILD/0.1 private-noncommercial-research"
TERMS_URL = "https://open-meteo.com/en/terms"
LICENSE_URL = "https://open-meteo.com/en/licence"
SITE_ROBOTS = "https://open-meteo.com/robots.txt"
API_ROBOTS = "https://api.open-meteo.com/robots.txt"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast?latitude=51.5&longitude=-0.12&hourly=temperature_2m,precipitation&forecast_days=3&timezone=UTC"
ALLOWED_URLS = frozenset((TERMS_URL, LICENSE_URL, SITE_ROBOTS, API_ROBOTS, FORECAST_URL))
MET_TERMS_URL = "https://api.met.no/doc/TermsOfService"
MET_LICENSE_URL = "https://api.met.no/doc/License"
MET_ROBOTS_URL = "https://api.met.no/robots.txt"
MET_FORECAST_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=51.5&lon=-0.12"
MET_ALLOWED_URLS = frozenset((MET_TERMS_URL, MET_LICENSE_URL, MET_ROBOTS_URL, MET_FORECAST_URL))
MET_USER_AGENT = "DRAGONHYDRACHILD/0.1 https://github.com/chatgptopenaiagi/DRAGONHYDRACHILD (owner https://github.com/chatgptopenaiagi)"
MET_APPROVED_TERMS_SHA256 = "880263e39cd55329b1c021cf905827f1954fb6968f6a6b611ad1756ab88e37c2"
MET_APPROVED_LICENSE_SHA256 = "c93748340237b7850bafd371365eb194893975dca0d191401b4b83594a546b72"
MET_POLICY_REVIEWED_AT = "2026-09-24T20:48:09.491610+00:00"
MET_ATTRIBUTION = {"credit": "Forecast data from MET Norway", "url": "https://api.met.no/weatherapi/locationforecast/2.0/documentation", "license": "CC-BY-4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/", "changes": "London coordinate proxy; selected future hours and normalized temperature/precipitation units. No endorsement implied."}
MAX_BYTES = 1_000_000
# Exact official HTML reviewed 2026-09-24; changed bytes fail closed for re-review.
APPROVED_TERMS_SHA256 = "bb9858bd2e4bca0bf55bf81b6d61a7abbf82a6eca9c57f91463959392ab985bb"
APPROVED_LICENSE_SHA256 = "9da12b9f16b7b244f7560a8b42ce4dc17e7dbcdf50c760cd0804fdc670ad24a2"
ATTRIBUTION = {"credit": "Weather forecast data by Open-Meteo.com", "url": "https://open-meteo.com/", "license": "CC-BY-4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/", "changes": "Hourly rows normalized; London coordinate proxy; only still-future hours selected. No endorsement implied."}


def _request_resource(url, *, modified_since=None, redirect_budget=1):
    """Two closed provider descriptors; public DNS pinned through TLS each hop."""
    if url not in ALLOWED_URLS | MET_ALLOWED_URLS:
        raise PipelineError("WEATHER_ENDPOINT_NOT_ALLOWED")
    is_met = url in MET_ALLOWED_URLS
    if modified_since is not None:
        try:
            if not is_met or url != MET_FORECAST_URL or len(modified_since) > 100 or "\n" in modified_since or "\r" in modified_since or parsedate_to_datetime(modified_since) > datetime.now(timezone.utc):
                raise ValueError()
        except (TypeError, ValueError):
            raise PipelineError("INVALID_CACHE_VALIDATOR") from None
    parsed = urlsplit(url)
    LIMITER.wait(parsed.hostname, 2)
    conn, raw_socket = None, None
    try:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise PipelineError("NON_PUBLIC_DNS")
        conn = http.client.HTTPSConnection(parsed.hostname, timeout=15)
        raw_socket = socket.create_connection((addresses[0][4][0], 443), timeout=15)
        conn.sock = ssl.create_default_context().wrap_socket(raw_socket, server_hostname=parsed.hostname)
        deadline = time.monotonic() + 15
        target = parsed.path + ("?" + parsed.query if parsed.query else "")
        headers = {"User-Agent": MET_USER_AGENT if is_met else USER_AGENT, "Accept-Encoding": "gzip, deflate" if is_met else "identity"}
        if modified_since:
            headers["If-Modified-Since"] = modified_since
        conn.request("GET", target, headers=headers)
        response = conn.getresponse()
        status = response.status
        metadata = {"expires": response.getheader("Expires"), "last_modified": response.getheader("Last-Modified"), "status": status}
        if status == 404 and url in (SITE_ROBOTS, API_ROBOTS, MET_ROBOTS_URL):
            return b"", "text/plain", status, metadata
        if status == 304 and is_met and modified_since:
            return b"", "application/json", status, metadata
        if status in (401, 403):
            raise PipelineError("AUTH_REQUIRED")
        if status == 429:
            raise PipelineError("RATE_LIMITED")
        if 300 <= status < 400:
            destination = urljoin(url, response.getheader("Location", ""))
            if is_met and redirect_budget > 0 and destination != url and destination in MET_ALLOWED_URLS:
                return _request_resource(destination, redirect_budget=redirect_budget - 1)
            raise PipelineError("REDIRECT_BLOCKED")
        if status != 200 and not (status == 203 and is_met):
            raise PipelineError("SOURCE_OFFLINE")
        content_type = response.getheader("Content-Type", "").split(";")[0].strip().lower()
        allowed_types = {"application/json"} if url in (FORECAST_URL, MET_FORECAST_URL) else {"text/plain"} if url in (SITE_ROBOTS, API_ROBOTS, MET_ROBOTS_URL) else {"text/html"}
        if content_type not in allowed_types:
            raise PipelineError("CONTENT_TYPE_UNEXPECTED")
        encoding = response.getheader("Content-Encoding", "identity").lower()
        if encoding not in (("identity", "gzip", "deflate") if is_met else ("identity",)):
            raise PipelineError("CONTENT_ENCODING_UNSUPPORTED")
        length_header = response.getheader("Content-Length")
        if length_header is not None and (not length_header.isdigit() or int(length_header) > MAX_BYTES):
            raise PipelineError("MAX_BYTES_EXCEEDED")
        pieces, count = [], 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PipelineError("NETWORK_TIMEOUT")
            if conn.sock is not None:
                conn.sock.settimeout(remaining)
            part = response.read1(min(65536, MAX_BYTES + 1 - count))
            if not part:
                break
            count += len(part)
            if count > MAX_BYTES:
                raise PipelineError("MAX_BYTES_EXCEEDED")
            pieces.append(part)
        body = b"".join(pieces)
        if encoding != "identity":
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS if encoding == "gzip" else zlib.MAX_WBITS)
            body = decoder.decompress(body, MAX_BYTES + 1)
            if len(body) > MAX_BYTES or decoder.unconsumed_tail or not decoder.eof or decoder.unused_data:
                raise PipelineError("DECOMPRESSION_BOUND_EXCEEDED")
        if b"captcha" in body.lower() or b"cf-chl-" in body.lower():
            raise PipelineError("CAPTCHA_PRESENT")
        return body, content_type, status, metadata
    except PipelineError:
        raise
    except (OSError, ValueError, http.client.HTTPException, zlib.error):
        raise PipelineError("NETWORK_ERROR") from None
    finally:
        if conn is not None:
            conn.close()
        if raw_socket is not None:
            raw_socket.close()


def request_fixed(url):
    if url not in ALLOWED_URLS:
        raise PipelineError("WEATHER_ENDPOINT_NOT_ALLOWED")
    return _request_resource(url)[:3]


def request_met_fixed(url, *, modified_since=None):
    if url not in MET_ALLOWED_URLS:
        raise PipelineError("WEATHER_ENDPOINT_NOT_ALLOWED")
    return _request_resource(url, modified_since=modified_since)


def robots_gate(body, status, target):
    result = evaluate_robots(body.decode("utf-8"), target, USER_AGENT, status)
    if result["robots_status"] not in ("ALLOWED", "ABSENT"):
        raise PipelineError("ROBOTS_BLOCKED")
    delay = result["crawl_delay_if_any"]
    if delay is not None and delay > 2:
        # Do not silently use a scheduler/fetch cadence weaker than a site directive.
        raise PipelineError("ROBOTS_CADENCE_REVIEW_REQUIRED")
    result["content_hash"] = hashlib.sha256(body).hexdigest()
    return result


def parse_forecast(body, captured_at):
    """Preserve only still-future model hours; validate units, arrays and bounds."""
    try:
        captured = datetime.fromisoformat(captured_at)
        if captured.tzinfo is None:
            raise ValueError()
        data = json.loads(body)
        if data["utc_offset_seconds"] != 0:
            raise ValueError()
        if not (abs(float(data["latitude"]) - 51.5) < 0.15 and abs(float(data["longitude"]) + 0.12) < 0.15):
            raise ValueError()
        units = data["hourly_units"]
        if units["time"] != "iso8601" or units["temperature_2m"] != "°C" or units["precipitation"] != "mm":
            raise ValueError()
        hourly = data["hourly"]
        times, temperature, rain = (hourly[key] for key in ("time", "temperature_2m", "precipitation"))
        if any(not isinstance(values, list) for values in (times, temperature, rain)) or not 1 <= len(times) <= 72 or len(times) != len(temperature) or len(times) != len(rain):
            raise ValueError()
        rows, previous = [], None
        for target, degrees, amount in zip(times, temperature, rain):
            instant = datetime.fromisoformat(target)
            # The request fixes UTC; the provider convention uses offset-free hours.
            if instant.tzinfo is not None:
                raise ValueError()
            instant = instant.replace(tzinfo=timezone.utc)
            if previous is not None and instant <= previous:
                raise ValueError()
            previous = instant
            if any(type(value) not in (float, int) or not math.isfinite(value) for value in (degrees, amount)):
                raise ValueError()
            if not -100 <= degrees <= 70 or not 0 <= amount <= 500:
                raise ValueError()
            if instant > captured:
                rows.append({"target_at": instant.isoformat(), "temperature_c": degrees, "precipitation_mm": amount, "epistemic_state": "HYPOTHESIS", "value_kind": "EXTERNAL_WEATHER_FORECAST", "temporal_mode": "STRICT_PIT", "available_at": captured_at})
        if not rows or any(datetime.fromisoformat(row["target_at"]) > captured + timedelta(days=3) for row in rows):
            raise ValueError()
        return rows
    except (TypeError, KeyError, ValueError, UnicodeError, OverflowError):
        raise PipelineError("SCHEMA_CHANGED") from None


def policy_record(terms_hash, license_hash, reviewed_at):
    """Human-reviewed source policy. No autonomous legal interpretation."""
    return {"source_id": SOURCE_ID, "source_policy_version": POLICY_VERSION, "reviewed_at": reviewed_at, "review_basis": "Official terms/licence read by engineering agent; private personal noncommercial app allowed. Commercial uses require separate subscription/review.", "terms_url": TERMS_URL, "license_url": LICENSE_URL, "terms_status": "ALLOWED_PRIVATE_NONCOMMERCIAL", "license_status": "CC-BY-4.0", "terms_hash": terms_hash, "license_hash": license_hash, "allowed_url": FORECAST_URL, "data_classes": ["weather_forecast"], "scope": "one London proxy in Premier League context; no stadium identity claim", "attribution": ATTRIBUTION, "interval_hours": 24, "max_requests_per_attempt": 5, "retry_count": 0}


def collect_weather_once(root=PROJECT_ROOT):
    """One attempt per day, five bounded requests max; all failures are receipts.

    First capture records the reviewed official policy bytes. Subsequent captures
    require matching policy-document hashes; terms change blocks until new review.
    """
    root = Path(root)
    ledger = root / "runtime/prospective/open-meteo-london"
    ledger.mkdir(parents=True, exist_ok=True)
    lock = ledger / ".weather.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError:
        return {"status": "COLLECTOR_LOCKED", "source_id": SOURCE_ID}
    try:
        with handle:
            handle.write(utcnow())
        clock = datetime.now(timezone.utc)
        attempts = [json.loads(path.read_text("utf-8")) for path in ledger.glob("*.json")]
        if any(datetime.fromisoformat(row["attempted_at"]) > clock - timedelta(hours=24) for row in attempts):
            return {"status": "NOT_DUE", "source_id": SOURCE_ID, "attempts": len(attempts)}
        entry = {"attempt_id": uuid4().hex, "source_id": SOURCE_ID, "attempted_at": clock.isoformat(), "status": "SOURCE_UNAVAILABLE", "data_class": "weather_forecast", "requests_attempted": 0}
        raw_store = RawEvidenceStore(root / "runtime/raw")
        def obtain(url):
            entry["requests_attempted"] += 1
            return request_fixed(url)
        try:
            site_robots, _, status = obtain(SITE_ROBOTS)
            entry["site_robots_raw_hash"] = raw_store.put(site_robots) if site_robots else hashlib.sha256(b"").hexdigest()
            entry["site_robots"] = robots_gate(site_robots, status, TERMS_URL)
            robots_gate(site_robots, status, LICENSE_URL)
            terms, _, _ = obtain(TERMS_URL)
            license_bytes, _, _ = obtain(LICENSE_URL)
            terms_hash, license_hash = raw_store.put(terms), raw_store.put(license_bytes)
            if terms_hash != APPROVED_TERMS_SHA256 or license_hash != APPROVED_LICENSE_SHA256:
                raise PipelineError("TERMS_CHANGED_REVIEW_REQUIRED")
            policy = policy_record(terms_hash, license_hash, utcnow())
            prior = next((row for row in reversed(attempts) if row.get("source_policy")), None)
            if prior and (prior["source_policy"]["terms_hash"] != terms_hash or prior["source_policy"]["license_hash"] != license_hash):
                raise PipelineError("TERMS_CHANGED_REVIEW_REQUIRED")
            entry["source_policy"] = policy
            api_robots, _, status = obtain(API_ROBOTS)
            entry["api_robots_raw_hash"] = raw_store.put(api_robots) if api_robots else hashlib.sha256(b"").hexdigest()
            entry["api_robots_http_status"] = status
            entry["api_robots"] = robots_gate(api_robots, status, FORECAST_URL)
            body, media_type, _ = obtain(FORECAST_URL)
            captured = utcnow()
            artifact_hash = raw_store.put(body)
            rows = parse_forecast(body, captured)
            snapshot = {"snapshot_id": uuid4().hex, "source_id": SOURCE_ID, "source_url": FORECAST_URL, "retrieved_at": captured, "observed_at": captured, "available_at": captured, "content_hash": artifact_hash, "raw_artifact_hash": artifact_hash, "byte_count": len(body), "media_type": media_type, "parser_version": PARSER_VERSION, "source_policy_version": POLICY_VERSION, "temporal_mode": "STRICT_PIT", "epistemic_state": "HYPOTHESIS", "capture_is_observation_of_forecast_not_weather": True, "location": {"name": "London coordinate proxy", "latitude": 51.5, "longitude": -0.12, "is_stadium_location": False}, "forecast_hour_count": len(rows), "rows": rows, "attribution": ATTRIBUTION}
            entry.update(status="CAPTURED", snapshot=snapshot)
        except (PipelineError, OSError, ValueError) as exc:
            entry["reason"] = str(exc) if isinstance(exc, PipelineError) else type(exc).__name__
        exclusive_json(ledger / (entry["attempt_id"] + ".json"), entry)
        return entry
    finally:
        lock.unlink()


def parse_met_forecast(body, captured_at):
    """MET model forecasts remain HYPOTHESIS, never realized weather evidence."""
    try:
        captured = datetime.fromisoformat(captured_at)
        if captured.tzinfo is None:
            raise ValueError()
        data = json.loads(body)
        coordinates = data["geometry"]["coordinates"]
        if data["geometry"]["type"] != "Point" or abs(coordinates[0] + .12) > .15 or abs(coordinates[1] - 51.5) > .15:
            raise ValueError()
        meta = data["properties"]["meta"]
        updated = datetime.fromisoformat(meta["updated_at"].replace("Z", "+00:00"))
        if updated.tzinfo is None or updated > captured or updated < captured - timedelta(days=2):
            raise ValueError()
        if meta["units"]["air_temperature"] != "celsius" or meta["units"]["precipitation_amount"] != "mm":
            raise ValueError()
        series = data["properties"]["timeseries"]
        if not isinstance(series, list) or not 1 <= len(series) <= 300:
            raise ValueError()
        rows, prior = [], None
        for item in series:
            stamp = datetime.fromisoformat(item["time"].replace("Z", "+00:00"))
            if stamp.tzinfo is None or (prior is not None and stamp <= prior):
                raise ValueError()
            prior = stamp
            if not captured < stamp <= captured + timedelta(days=3):
                continue
            degrees = item["data"]["instant"]["details"]["air_temperature"]
            rainfall = item["data"].get("next_1_hours", {}).get("details", {}).get("precipitation_amount")
            if type(degrees) not in (int, float) or not math.isfinite(degrees) or not -100 <= degrees <= 70:
                raise ValueError()
            if rainfall is not None and (type(rainfall) not in (int, float) or not math.isfinite(rainfall) or not 0 <= rainfall <= 500):
                raise ValueError()
            rows.append({"target_at": stamp.isoformat(), "temperature_c": degrees, "precipitation_next_hour_mm": rainfall, "precipitation_missing": rainfall is None, "epistemic_state": "HYPOTHESIS", "value_kind": "EXTERNAL_WEATHER_FORECAST", "temporal_mode": "STRICT_PIT", "available_at": captured_at, "provider_model_updated_at": updated.isoformat()})
        if not rows:
            raise ValueError()
        return rows
    except (TypeError, KeyError, ValueError, UnicodeError, OverflowError, IndexError):
        raise PipelineError("SCHEMA_CHANGED") from None


def collect_met_weather_once(root=PROJECT_ROOT):
    """Independent CC-BY provider; daily + Expires gate and conditional GET.

    Open-Meteo's blocked policy remains blocked. This provider has a separate
    endpoint, robots policy, terms, attribution, parser and immutable ledger.
    """
    root = Path(root)
    ledger = root / "runtime/prospective/met-norway-london"
    ledger.mkdir(parents=True, exist_ok=True)
    lock = ledger / ".weather.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError:
        return {"source_id": "met-norway", "status": "COLLECTOR_LOCKED"}
    try:
        with handle:
            handle.write(utcnow())
        clock = datetime.now(timezone.utc)
        attempts = sorted((json.loads(path.read_text("utf-8")) for path in ledger.glob("*.json")), key=lambda row: row["attempted_at"])
        if any(datetime.fromisoformat(row["attempted_at"]) > clock - timedelta(days=1) for row in attempts):
            return {"source_id": "met-norway", "status": "NOT_DUE"}
        previous = next((row for row in reversed(attempts) if row.get("status") == "CAPTURED"), None)
        if previous and previous.get("cache_expires") and clock < datetime.fromisoformat(previous["cache_expires"]):
            return {"source_id": "met-norway", "status": "NOT_DUE", "reason": "PROVIDER_CACHE_EXPIRES"}
        entry = {"attempt_id": uuid4().hex, "attempted_at": clock.isoformat(), "source_id": "met-norway", "data_class": "weather_forecast", "status": "SOURCE_UNAVAILABLE", "requests_attempted": 0}
        raw_store = RawEvidenceStore(root / "runtime/raw")
        def obtain(url, **kwargs):
            entry["requests_attempted"] += 1
            return request_met_fixed(url, **kwargs)
        try:
            if not timedelta(0) <= clock - datetime.fromisoformat(MET_POLICY_REVIEWED_AT) <= timedelta(days=30):
                raise PipelineError("POLICY_REVIEW_EXPIRED")
            robots, _, status, _ = obtain(MET_ROBOTS_URL)
            entry["robots_raw_hash"] = raw_store.put(robots) if robots else hashlib.sha256(b"").hexdigest()
            entry["robots"] = evaluate_robots(robots.decode(), MET_FORECAST_URL, MET_USER_AGENT, status)
            if entry["robots"]["robots_status"] not in ("ALLOWED", "ABSENT") or (entry["robots"]["crawl_delay_if_any"] or 0) > 2:
                raise PipelineError("ROBOTS_BLOCKED")
            for expected, url in ((MET_APPROVED_TERMS_SHA256, MET_TERMS_URL), (MET_APPROVED_LICENSE_SHA256, MET_LICENSE_URL)):
                # Reuse the exact reviewed local policy bytes; no needless downloads.
                try:
                    raw_store.get(expected)
                except FileNotFoundError:
                    policy_robots = evaluate_robots(robots.decode(), url, MET_USER_AGENT, status)
                    if policy_robots["robots_status"] not in ("ALLOWED", "ABSENT"):
                        raise PipelineError("ROBOTS_BLOCKED")
                    body, _, _, _ = obtain(url)
                    if raw_store.put(body) != expected:
                        raise PipelineError("TERMS_CHANGED_REVIEW_REQUIRED")
            entry["source_policy"] = {"source_policy_version": "child-met-london/1.0", "terms_status": "ALLOWED_RESEARCH", "license_status": "CC-BY-4.0", "reviewed_at": MET_POLICY_REVIEWED_AT, "terms_url": MET_TERMS_URL, "license_url": MET_LICENSE_URL, "terms_hash": MET_APPROVED_TERMS_SHA256, "license_hash": MET_APPROVED_LICENSE_SHA256, "attribution": MET_ATTRIBUTION, "scope": "one London proxy; provider forecasts only; not stadium observations", "allowed_url": MET_FORECAST_URL, "interval_hours": 24, "max_requests_per_attempt": 4, "max_redirects_per_request": 1, "max_wire_requests_per_attempt": 8, "retry_count": 0, "identifying_user_agent": MET_USER_AGENT}
            modified = previous.get("last_modified") if previous else None
            body, media, status, headers = obtain(MET_FORECAST_URL, modified_since=modified)
            if status == 304:
                if not previous:
                    raise PipelineError("INVALID_NOT_MODIFIED")
                body = raw_store.get(previous["snapshot"]["raw_artifact_hash"])
            captured = utcnow()
            key = raw_store.put(body)
            rows = parse_met_forecast(body, captured)
            expires = headers.get("expires")
            entry["cache_expires"] = parsedate_to_datetime(expires).isoformat() if expires else None
            entry["last_modified"] = headers.get("last_modified") or modified
            if entry["last_modified"]:
                last_modified = parsedate_to_datetime(entry["last_modified"])
                if last_modified > datetime.fromisoformat(captured):
                    raise PipelineError("FUTURE_CACHE_VALIDATOR")
            snapshot = {"snapshot_id": uuid4().hex, "source_id": "met-norway", "source_url": MET_FORECAST_URL, "retrieved_at": captured, "observed_at": captured, "available_at": captured, "content_hash": key, "raw_artifact_hash": key, "byte_count": len(body), "media_type": media, "parser_version": "met-locationforecast/1.0", "source_policy_version": "child-met-london/1.0", "temporal_mode": "STRICT_PIT", "epistemic_state": "HYPOTHESIS", "capture_is_observation_of_forecast_not_weather": True, "location": {"name": "London coordinate proxy", "latitude": 51.5, "longitude": -.12, "is_stadium_location": False}, "forecast_hour_count": len(rows), "rows": rows, "attribution": MET_ATTRIBUTION}
            entry.update(status="CAPTURED", snapshot=snapshot, provider_http_status=status, deprecation_warning=status == 203)
        except (PipelineError, OSError, ValueError, TypeError) as exc:
            entry["reason"] = str(exc) if isinstance(exc, PipelineError) else type(exc).__name__
        exclusive_json(ledger / (entry["attempt_id"] + ".json"), entry)
        return entry
    finally:
        lock.unlink()
