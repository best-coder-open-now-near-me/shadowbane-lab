"""Localhost-only HTTP dashboard for reviewed manager lifecycle operations."""

from __future__ import annotations

import hmac
import json
import math
import re
import secrets
import socket
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import NoReturn, Protocol, runtime_checkable
from urllib.parse import urlsplit

LOOPBACK_HOST = "127.0.0.1"
MAX_ACTION_BODY_BYTES = 4_096
DEFAULT_MAX_CONCURRENT_REQUESTS = 16
DEFAULT_HEADER_TIMEOUT_SECONDS = 2.0
DEFAULT_BODY_TIMEOUT_SECONDS = 2.0

_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_GLOBAL_ACTIONS = frozenset({"add-client", "start-all", "refresh", "tile-all"})
_CLIENT_ACTIONS_WITHOUT_INSTANCE = frozenset({"start"})
_CLIENT_ACTIONS_WITH_INSTANCE = frozenset({"attach", "tile", "pause", "resume", "detach", "close"})
_ALL_ACTIONS = (
    _GLOBAL_ACTIONS
    | _CLIENT_ACTIONS_WITHOUT_INSTANCE
    | _CLIENT_ACTIONS_WITH_INSTANCE
)


class DashboardError(RuntimeError):
    """A public, structured dashboard operation error."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: HTTPStatus = HTTPStatus.CONFLICT,
    ) -> None:
        if not _IDENTIFIER_PATTERN.fullmatch(code):
            raise ValueError("dashboard error code must be a canonical identifier")
        if not isinstance(message, str) or not message:
            raise ValueError("dashboard error message must be non-empty")
        if not isinstance(status, HTTPStatus) or status.value < 400:
            raise ValueError("dashboard error status must be an HTTP error status")
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@runtime_checkable
class DashboardService(Protocol):
    """Operational manager facade consumed by the local dashboard."""

    def status(self) -> dict[str, object]: ...

    def execute(
        self,
        action: str,
        *,
        client_id: str | None = None,
        instance_id: str | None = None,
    ) -> dict[str, object]: ...

@dataclass(frozen=True, slots=True)
class _DashboardContext:
    service: DashboardService
    authorization_token: str
    authorization_token_bytes: bytes
    html_template: bytes
    header_timeout_seconds: float
    body_timeout_seconds: float


class _ConnectionDeadline:
    """Close one connection when a strict wall-clock deadline expires."""

    def __init__(self, connection: socket.socket, timeout_seconds: float) -> None:
        self.expired = threading.Event()
        self._cancelled = threading.Event()
        self._connection = connection
        self._timer = threading.Timer(timeout_seconds, self._expire)
        self._timer.daemon = True

    def start(self) -> _ConnectionDeadline:
        self._timer.start()
        return self

    def cancel(self) -> None:
        self._cancelled.set()
        self._timer.cancel()

    def _expire(self) -> None:
        if self._cancelled.is_set():
            return
        self.expired.set()
        try:
            self._connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


class _DashboardHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(
        self,
        address: tuple[str, int],
        context: _DashboardContext,
        *,
        max_concurrent_requests: int,
    ) -> None:
        self.dashboard_context = context
        self._worker_slots = threading.BoundedSemaphore(max_concurrent_requests)
        self._worker_wait_seconds = max(
            context.header_timeout_seconds,
            context.body_timeout_seconds,
        )
        super().__init__(address, _DashboardRequestHandler)

    def process_request(self, request: socket.socket, client_address: object) -> None:
        if not self._worker_slots.acquire(timeout=self._worker_wait_seconds):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._worker_slots.release()
            self.shutdown_request(request)

    def process_request_thread(self, request: socket.socket, client_address: object) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._worker_slots.release()

    def handle_error(self, request: object, client_address: object) -> None:
        """Suppress connection tracebacks, which may include authorization material."""


class _RequestError(Exception):
    def __init__(self, status: HTTPStatus, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _request_error(status: HTTPStatus, code: str, message: str) -> NoReturn:
    raise _RequestError(status, code, message)


def _reject_duplicate_json_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _request_error(
                HTTPStatus.BAD_REQUEST,
                "duplicate-field",
                f"JSON object contains duplicate field {key!r}.",
            )
        result[key] = value
    return result


def _require_identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_PATTERN.fullmatch(value):
        _request_error(
            HTTPStatus.BAD_REQUEST,
            "invalid-field",
            f"{field_name} must be a canonical identifier of at most 128 characters.",
        )
    return value


def _validate_action_payload(
    payload: object,
) -> tuple[str, str | None, str | None]:
    if not isinstance(payload, dict) or any(not isinstance(key, str) for key in payload):
        _request_error(
            HTTPStatus.BAD_REQUEST,
            "invalid-json-shape",
            "The action body must be a JSON object.",
        )

    action = payload.get("action")
    if not isinstance(action, str) or action not in _ALL_ACTIONS:
        _request_error(
            HTTPStatus.BAD_REQUEST,
            "unknown-action",
            "The requested manager action is not allowed.",
        )

    if action in _GLOBAL_ACTIONS:
        expected_fields = {"action"}
    elif action in _CLIENT_ACTIONS_WITHOUT_INSTANCE:
        expected_fields = {"action", "client_id"}
    else:
        expected_fields = {"action", "client_id", "instance_id"}

    actual_fields = set(payload)
    if actual_fields != expected_fields:
        missing = sorted(expected_fields - actual_fields)
        extra = sorted(actual_fields - expected_fields)
        details: list[str] = []
        if missing:
            details.append(f"missing fields: {', '.join(missing)}")
        if extra:
            details.append(f"unknown fields: {', '.join(extra)}")
        _request_error(
            HTTPStatus.BAD_REQUEST,
            "invalid-fields",
            "Action payload has invalid fields (" + "; ".join(details) + ").",
        )

    client_id = (
        _require_identifier(payload["client_id"], "client_id") if "client_id" in payload else None
    )
    instance_id = (
        _require_identifier(payload["instance_id"], "instance_id")
        if "instance_id" in payload
        else None
    )
    return action, client_id, instance_id


class _DashboardRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ShadowbaneManagerDashboard"
    sys_version = ""

    @property
    def _context(self) -> _DashboardContext:
        server = self.server
        assert isinstance(server, _DashboardHttpServer)
        return server.dashboard_context

    def version_string(self) -> str:
        return self.server_version

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(self._context.header_timeout_seconds)

    def handle_one_request(self) -> None:
        """Parse one request under a strict total header deadline."""

        deadline = _ConnectionDeadline(
            self.connection,
            self._context.header_timeout_seconds,
        ).start()
        try:
            try:
                self.raw_requestline = self.rfile.readline(65_537)
                if deadline.expired.is_set():
                    self.close_connection = True
                    return
                if len(self.raw_requestline) > 65_536:
                    self.requestline = ""
                    self.request_version = ""
                    self.command = ""
                    self.send_error(HTTPStatus.REQUEST_URI_TOO_LONG.value)
                    self.close_connection = True
                    return
                if not self.raw_requestline:
                    self.close_connection = True
                    return
                if not self.parse_request() or deadline.expired.is_set():
                    self.close_connection = True
                    return
            except (TimeoutError, ConnectionError, OSError):
                self.close_connection = True
                return
        finally:
            deadline.cancel()

        method = getattr(self, f"do_{self.command}", None)
        try:
            if method is None:
                self._method_not_allowed()
            else:
                method()
            self.wfile.flush()
        except (TimeoutError, ConnectionError, OSError):
            self.close_connection = True

    def log_message(self, _format: str, *args: object) -> None:
        """Disable request logging so authorization material cannot leak."""

    def do_GET(self) -> None:
        path = self._strict_path()
        if path == "/":
            self._serve_dashboard()
            return
        if path == "/api/v1/status":
            if not self._authorized():
                self._send_error(
                    HTTPStatus.UNAUTHORIZED,
                    "unauthorized",
                    "A valid dashboard bearer token is required.",
                    extra_headers={"WWW-Authenticate": "Bearer"},
                )
                return
            self._serve_status()
            return
        self._send_error(HTTPStatus.NOT_FOUND, "not-found", "Route not found.")

    def do_POST(self) -> None:
        path = self._strict_path()
        if path != "/api/v1/actions":
            self._send_error(HTTPStatus.NOT_FOUND, "not-found", "Route not found.")
            return
        if not self._authorized():
            self._send_error(
                HTTPStatus.UNAUTHORIZED,
                "unauthorized",
                "A valid dashboard bearer token is required.",
                extra_headers={"WWW-Authenticate": "Bearer"},
            )
            return
        try:
            action, client_id, instance_id = self._read_action_request()
        except _RequestError as exc:
            self._send_error(exc.status, exc.code, exc.message)
            return
        try:
            result = self._context.service.execute(
                action,
                client_id=client_id,
                instance_id=instance_id,
            )
            self._require_service_result(result)
        except DashboardError as exc:
            self._send_error(exc.status, exc.code, exc.message)
            return
        except Exception:
            self._send_error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "service-failure",
                "The manager could not complete the requested action.",
            )
            return
        self._send_json(HTTPStatus.OK, result)

    def do_OPTIONS(self) -> None:
        self._method_not_allowed()

    def do_HEAD(self) -> None:
        self._method_not_allowed()

    def do_PUT(self) -> None:
        self._method_not_allowed()

    def do_PATCH(self) -> None:
        self._method_not_allowed()

    def do_DELETE(self) -> None:
        self._method_not_allowed()

    def do_TRACE(self) -> None:
        self._method_not_allowed()

    def do_CONNECT(self) -> None:
        self._method_not_allowed()

    def _strict_path(self) -> str:
        parsed = urlsplit(self.path)
        if parsed.query or parsed.fragment or not parsed.path.startswith("/"):
            return ""
        return parsed.path

    def _authorized(self) -> bool:
        values = self.headers.get_all("Authorization", failobj=[])
        supplied_token = b""
        valid_shape = len(values) == 1
        if valid_shape:
            try:
                header = values[0].encode("ascii", errors="strict")
            except UnicodeEncodeError:
                valid_shape = False
            else:
                prefix = b"Bearer "
                valid_shape = header.startswith(prefix)
                if valid_shape:
                    supplied_token = header[len(prefix) :]

        expected = self._context.authorization_token_bytes
        normalized = (supplied_token[: len(expected)] + (b"\0" * len(expected)))[: len(expected)]
        token_matches = hmac.compare_digest(normalized, expected)
        return valid_shape and len(supplied_token) == len(expected) and token_matches

    def _serve_dashboard(self) -> None:
        nonce = secrets.token_urlsafe(24)
        marker = b"__CSP_NONCE__"
        if marker not in self._context.html_template:
            self._send_error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "dashboard-template-invalid",
                "The dashboard resource is unavailable.",
            )
            return
        body = self._context.html_template.replace(marker, nonce.encode("ascii"))
        csp = (
            "default-src 'none'; "
            f"script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
            "connect-src 'self'; img-src 'self' data:; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        )
        self._send_response(
            HTTPStatus.OK,
            body,
            content_type="text/html; charset=utf-8",
            content_security_policy=csp,
        )

    def _serve_status(self) -> None:
        try:
            result = self._context.service.status()
            self._require_service_result(result)
        except DashboardError as exc:
            self._send_error(exc.status, exc.code, exc.message)
            return
        except Exception:
            self._send_error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "service-failure",
                "The manager could not read current status.",
            )
            return
        self._send_json(HTTPStatus.OK, result)

    def _read_action_request(self) -> tuple[str, str | None, str | None]:
        if self.headers.get("Transfer-Encoding") is not None:
            _request_error(
                HTTPStatus.BAD_REQUEST,
                "unsupported-transfer-encoding",
                "Transfer-Encoding is not accepted.",
            )
        content_lengths = self.headers.get_all("Content-Length", failobj=[])
        if len(content_lengths) != 1:
            _request_error(
                HTTPStatus.LENGTH_REQUIRED,
                "content-length-required",
                "Exactly one Content-Length header is required.",
            )
        content_length_text = content_lengths[0]
        if re.fullmatch(r"[0-9]+", content_length_text) is None:
            _request_error(
                HTTPStatus.BAD_REQUEST,
                "invalid-content-length",
                "Content-Length must be a non-negative decimal integer.",
            )
        content_length = int(content_length_text)
        if content_length > MAX_ACTION_BODY_BYTES:
            _request_error(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "body-too-large",
                f"Action bodies may not exceed {MAX_ACTION_BODY_BYTES} bytes.",
            )
        content_type = self.headers.get("Content-Type", "")
        media_type, separator, parameters = content_type.partition(";")
        accepted_parameters = {"charset=utf-8", 'charset="utf-8"'}
        if media_type.strip().casefold() != "application/json" or (
            separator and parameters.strip().casefold() not in accepted_parameters
        ):
            _request_error(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                "unsupported-media-type",
                "Content-Type must be application/json with optional UTF-8 charset.",
            )
        source = self._read_request_body(content_length)
        try:
            payload = json.loads(
                source,
                object_pairs_hook=_reject_duplicate_json_fields,
                parse_constant=lambda value: _request_error(
                    HTTPStatus.BAD_REQUEST,
                    "invalid-json",
                    f"JSON constant {value!r} is not accepted.",
                ),
            )
        except _RequestError:
            raise
        except (json.JSONDecodeError, UnicodeDecodeError):
            _request_error(
                HTTPStatus.BAD_REQUEST,
                "invalid-json",
                "The action body must contain valid UTF-8 JSON.",
            )
        return _validate_action_payload(payload)

    def _read_request_body(self, content_length: int) -> bytes:
        self.connection.settimeout(self._context.body_timeout_seconds)
        deadline = _ConnectionDeadline(
            self.connection,
            self._context.body_timeout_seconds,
        ).start()
        try:
            try:
                source = self.rfile.read(content_length)
            except (TimeoutError, ConnectionError, OSError) as exc:
                raise ConnectionError("request body read failed") from exc
        finally:
            deadline.cancel()
        if deadline.expired.is_set():
            raise ConnectionError("request body deadline expired")
        if len(source) != content_length:
            _request_error(
                HTTPStatus.BAD_REQUEST,
                "incomplete-body",
                "The request body ended before Content-Length bytes were received.",
            )
        return source

    @staticmethod
    def _require_service_result(result: object) -> None:
        if not isinstance(result, dict) or any(not isinstance(key, str) for key in result):
            raise TypeError("dashboard service results must be string-keyed dictionaries")

    def _method_not_allowed(self) -> None:
        self._send_error(
            HTTPStatus.METHOD_NOT_ALLOWED,
            "method-not-allowed",
            "Only reviewed GET and POST routes are available.",
            extra_headers={"Allow": "GET, POST"},
        )

    def _send_error(
        self,
        status: HTTPStatus,
        code: str,
        message: str,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._send_json(
            status,
            {"ok": False, "error": {"code": code, "message": message}},
            extra_headers=extra_headers,
        )

    def _send_json(
        self,
        status: HTTPStatus,
        payload: dict[str, object],
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        try:
            body = json.dumps(
                payload,
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        except (TypeError, ValueError):
            if status is HTTPStatus.INTERNAL_SERVER_ERROR:
                body = (
                    b'{"error":{"code":"service-failure","message":'
                    b'"The manager returned an invalid response."},"ok":false}'
                )
            else:
                self._send_error(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "service-failure",
                    "The manager returned an invalid response.",
                )
                return
        self._send_response(
            status,
            body,
            content_type="application/json; charset=utf-8",
            content_security_policy="default-src 'none'; frame-ancestors 'none'",
            extra_headers=extra_headers,
        )

    def _send_response(
        self,
        status: HTTPStatus,
        body: bytes,
        *,
        content_type: str,
        content_security_policy: str,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", content_security_policy)
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Pragma", "no-cache")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Connection", "close")
        if extra_headers is not None:
            for name, value in extra_headers.items():
                self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True


def _load_dashboard_html() -> bytes:
    resource = resources.files("shadowbane_lab.manager").joinpath("static/dashboard.html")
    return resource.read_bytes()


def _require_timeout(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a positive finite number")
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError(f"{field_name} must be a positive finite number")
    return parsed


class DashboardServer:
    """Own a loopback-only dashboard listener without opening a browser."""

    def __init__(
        self,
        service: DashboardService,
        *,
        port: int = 0,
        max_concurrent_requests: int = DEFAULT_MAX_CONCURRENT_REQUESTS,
        header_timeout_seconds: float = DEFAULT_HEADER_TIMEOUT_SECONDS,
        body_timeout_seconds: float = DEFAULT_BODY_TIMEOUT_SECONDS,
    ) -> None:
        if not isinstance(service, DashboardService):
            raise ValueError("service must implement DashboardService")
        if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65_535:
            raise ValueError("port must be an integer from 0 through 65535")
        if (
            isinstance(max_concurrent_requests, bool)
            or not isinstance(max_concurrent_requests, int)
            or max_concurrent_requests <= 0
        ):
            raise ValueError("max_concurrent_requests must be a positive integer")
        header_timeout = _require_timeout(header_timeout_seconds, "header_timeout_seconds")
        body_timeout = _require_timeout(body_timeout_seconds, "body_timeout_seconds")
        token = secrets.token_urlsafe(32)
        context = _DashboardContext(
            service=service,
            authorization_token=token,
            authorization_token_bytes=token.encode("ascii"),
            html_template=_load_dashboard_html(),
            header_timeout_seconds=header_timeout,
            body_timeout_seconds=body_timeout,
        )
        self._authorization_token = token
        self._server = _DashboardHttpServer(
            (LOOPBACK_HOST, port),
            context,
            max_concurrent_requests=max_concurrent_requests,
        )
        self._thread: threading.Thread | None = None
        self._closed = False

    @property
    def authorization_token(self) -> str:
        """Return the in-memory token for trusted launcher integration."""

        return self._authorization_token

    @property
    def host(self) -> str:
        return LOOPBACK_HOST

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    @property
    def suggested_url(self) -> str:
        """Return a fragment-token URL; fragments are not sent in HTTP requests."""

        return f"http://{LOOPBACK_HOST}:{self.port}/#token={self._authorization_token}"

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    def start(self) -> DashboardServer:
        if self._closed:
            raise RuntimeError("dashboard server is closed")
        if self.is_running:
            return self
        thread = threading.Thread(
            target=self._server.serve_forever,
            kwargs={"poll_interval": 0.05},
            name="shadowbane-manager-dashboard",
            daemon=True,
        )
        self._thread = thread
        thread.start()
        return self

    def stop(self) -> None:
        if self._closed:
            return
        thread = self._thread
        if thread is not None and thread.is_alive():
            self._server.shutdown()
            thread.join(timeout=2.0)
        self._server.server_close()
        self._thread = None
        self._closed = True

    def __enter__(self) -> DashboardServer:
        return self.start()

    def __exit__(self, *_: object) -> None:
        self.stop()


__all__ = [
    "DEFAULT_BODY_TIMEOUT_SECONDS",
    "DEFAULT_HEADER_TIMEOUT_SECONDS",
    "DEFAULT_MAX_CONCURRENT_REQUESTS",
    "LOOPBACK_HOST",
    "MAX_ACTION_BODY_BYTES",
    "DashboardError",
    "DashboardServer",
    "DashboardService",
]
