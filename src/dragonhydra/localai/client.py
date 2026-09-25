"""Authenticated loopback-only client for the recovered bounded LocalAI gateway."""

import http.client
from pathlib import Path
import socket
import threading
import time
from urllib.parse import urlsplit

from .contracts import (AnalysisRequest, AnalysisResponse, ContractError, MAX_REQUEST_BYTES,
                        MAX_RESPONSE_BYTES, SCHEMA_VERSION, Snapshot, canonical_bytes,
                        strict_json, utc_now, _hash, _identifier)


PROJECT_RUNTIME = Path(__file__).resolve().parents[3] / "runtime"


class LocalAIClient:
    """No DNS, environment proxies, redirects, filesystem ingestion or tool calls.

    The token is explicit configuration and never appears in receipts or repr.
    Audit storage is project-local. The caller supplies controlled Snapshot data.
    """

    def __init__(self, base_url, *, model_id, model_hash, runtime_id, token,
                 audit_dir, timeout_seconds=30):
        parts = urlsplit(base_url)
        try:
            port = parts.port
        except ValueError as exc:
            raise ContractError() from exc
        if (parts.scheme != "http" or parts.hostname != "127.0.0.1" or parts.username is not None
                or parts.password is not None or parts.query or parts.fragment or parts.path not in ("", "/")
                or port is None or not 1024 <= port <= 65535 or parts.netloc != f"127.0.0.1:{port}"):
            raise ContractError()
        _identifier(model_id)
        _hash(model_hash)
        _identifier(runtime_id)
        if (type(token) is not str or not 24 <= len(token) <= 256 or not token.isascii()
                or any(not (c.isalnum() or c in "-_.") for c in token)):
            raise ContractError()
        if type(timeout_seconds) not in (int, float) or not 0.01 <= timeout_seconds <= 300:
            raise ContractError()
        self.port = port
        self.model_id, self.model_hash, self.runtime_id = model_id, model_hash, runtime_id
        self._token = token
        self.timeout_seconds = timeout_seconds
        self.audit_dir = Path(audit_dir).resolve()
        if not self.audit_dir.is_relative_to(PROJECT_RUNTIME.resolve()) or self.audit_dir == PROJECT_RUNTIME.resolve():
            raise ContractError()

    def __repr__(self):
        return f"LocalAIClient(port={self.port}, model_id={self.model_id!r})"

    def _exchange(self, method, path, payload=None):
        """Only fixed internal method/path calls reach the transport boundary."""
        raw = None if payload is None else canonical_bytes(payload)
        if raw is not None and len(raw) > MAX_REQUEST_BYTES:
            raise ContractError("REQUEST_TOO_LARGE")
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=self.timeout_seconds)
        expired = threading.Event()
        live_socket = None
        def expire():
            expired.set()
            if live_socket is not None:
                try:
                    live_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        # A socket timeout alone resets on incoming bytes. This total deadline
        # also interrupts a local endpoint that slowly dribbles headers/body.
        deadline = threading.Timer(self.timeout_seconds, expire)
        deadline.daemon = True
        deadline.start()
        try:
            connection.connect()
            live_socket = connection.sock
            if expired.is_set():
                raise ContractError("TIMEOUT")
            connection.request(method, path, body=raw, headers={
                "Authorization": "Bearer " + self._token, "Accept": "application/json",
                "Content-Type": "application/json", "Connection": "close"})
            response = connection.getresponse()
            if response.status != 200:
                raise ContractError("LOCALAI_UNAVAILABLE" if response.status in (401, 403, 503) else "INVALID_RESPONSE")
            media_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
            if media_type != "application/json":
                raise ContractError("INVALID_RESPONSE")
            length = response.getheader("Content-Length")
            if length is not None:
                try:
                    if not 0 <= int(length) <= MAX_RESPONSE_BYTES:
                        raise ContractError("INVALID_RESPONSE")
                except ValueError as exc:
                    raise ContractError("INVALID_RESPONSE") from exc
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise ContractError("INVALID_RESPONSE")
            if expired.is_set():
                raise ContractError("TIMEOUT")
            return strict_json(body)
        except ContractError as exc:
            if expired.is_set():
                raise ContractError("TIMEOUT") from exc
            raise
        except (socket.timeout, TimeoutError) as exc:
            raise ContractError("TIMEOUT") from exc
        except (OSError, http.client.HTTPException) as exc:
            raise ContractError("TIMEOUT" if expired.is_set() else "LOCALAI_UNAVAILABLE") from exc
        finally:
            deadline.cancel()
            connection.close()

    def _identity(self, payload, *, health=False):
        keys = {"schema_version", "model_id", "model_hash", "runtime_id"}
        if health:
            keys.add("status")
        if type(payload) is not dict or set(payload) != keys or payload["schema_version"] != SCHEMA_VERSION:
            raise ContractError("INVALID_RESPONSE")
        if any(payload[key] != getattr(self, key) for key in ("model_id", "model_hash", "runtime_id")):
            raise ContractError("MODEL_HASH_MISMATCH")
        if health and payload["status"] not in ("READY", "UNAVAILABLE"):
            raise ContractError("INVALID_RESPONSE")
        return payload

    def health(self):
        """Return validated health or a bounded failure record, never raw errors."""
        try:
            return self._identity(self._exchange("GET", "/health"), health=True)
        except ContractError as exc:
            return {"schema_version": SCHEMA_VERSION, "status": "UNAVAILABLE", "failure_state": exc.reason_code}

    def model(self):
        try:
            return self._identity(self._exchange("GET", "/model"))
        except ContractError as exc:
            return {"schema_version": SCHEMA_VERSION, "status": "UNAVAILABLE", "failure_state": exc.reason_code}

    def _audit(self, request, response):
        # Resolve again to reject a redirected existing directory before each write.
        root = PROJECT_RUNTIME.resolve()
        if not self.audit_dir.resolve().is_relative_to(root):
            raise OSError("AUDIT_FAILURE")
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        receipt = {"schema_version": SCHEMA_VERSION, "created_at": utc_now(), "request_id": request.request_id,
                   "state_hash": request.snapshot.state_hash, "input_hash": request.input_hash,
                   "response": response.to_dict(), "capability": "ANALYZE_ONLY"}
        destination = self.audit_dir / f"{request.request_id}-{response.output_hash}.json"
        with destination.open("xb") as handle:
            handle.write(canonical_bytes(receipt))

    def analyze(self, snapshot: Snapshot, task_kind, *, request_id=None, created_at=None):
        """Invalid local contracts raise ContractError; transport failures are typed.

        A malformed request cannot be assigned a truthful valid input hash/identity,
        so it is rejected before transport instead of fabricating a response.
        """
        request = AnalysisRequest.create(snapshot, task_kind, self.model_id, self.model_hash, self.runtime_id,
                                         request_id=request_id, created_at=created_at)
        started = time.monotonic()
        try:
            payload = self._exchange("POST", "/analyze", request.to_dict())
            try:
                response = AnalysisResponse.from_dict(payload).validate_for(request)
            except (ContractError, TypeError, KeyError) as exc:
                reason = exc.reason_code if isinstance(exc, ContractError) else "INVALID_RESPONSE"
                raise ContractError("MODEL_HASH_MISMATCH" if reason == "MODEL_HASH_MISMATCH" else "INVALID_RESPONSE") from exc
        except ContractError as exc:
            response = AnalysisResponse.failure(request, exc.reason_code, (time.monotonic() - started) * 1000)
        try:
            self._audit(request, response)
        except OSError:
            # Never claim a fully successful operation when its mandatory receipt failed.
            return AnalysisResponse.failure(request, "AUDIT_FAILURE", (time.monotonic() - started) * 1000)
        return response
