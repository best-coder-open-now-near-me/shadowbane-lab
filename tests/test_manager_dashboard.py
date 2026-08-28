import base64
import contextlib
import http.client
import io
import json
import socket
import time
import unittest
from http import HTTPStatus
from urllib.parse import parse_qs, urlsplit

from shadowbane_lab.manager.dashboard import (
    LOOPBACK_HOST,
    MAX_ACTION_BODY_BYTES,
    DashboardError,
    DashboardServer,
)


class _RecordingService:
    def __init__(self) -> None:
        self.status_calls = 0
        self.execute_calls: list[tuple[str, str | None, str | None]] = []
        self.status_error: Exception | None = None
        self.execute_error: Exception | None = None

    def status(self) -> dict[str, object]:
        self.status_calls += 1
        if self.status_error is not None:
            raise self.status_error
        return {
            "ok": True,
            "node_id": "gaming-pc-east",
            "slots": [
                {
                    "client_id": "front-left",
                    "state": "attached",
                    "binding": {"instance_id": "client-abc", "process_id": 101},
                }
            ],
        }

    def execute(
        self,
        action: str,
        *,
        client_id: str | None = None,
        instance_id: str | None = None,
    ) -> dict[str, object]:
        self.execute_calls.append((action, client_id, instance_id))
        if self.execute_error is not None:
            raise self.execute_error
        return {"ok": True, "action": action}


class DashboardServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = _RecordingService()
        self.server = DashboardServer(self.service, port=0).start()

    def tearDown(self) -> None:
        self.server.stop()

    def _restart_server(self, **options: object) -> None:
        self.server.stop()
        self.server = DashboardServer(self.service, port=0, **options).start()

    def _raw_connection(self) -> socket.socket:
        connection = socket.create_connection(
            (self.server.host, self.server.port),
            timeout=2,
        )
        connection.settimeout(2)
        return connection

    @staticmethod
    def _read_raw_response(connection: socket.socket) -> bytes:
        chunks: list[bytes] = []
        while True:
            chunk = connection.recv(65_536)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | str | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[HTTPStatus, dict[str, str], bytes]:
        connection = http.client.HTTPConnection(
            self.server.host,
            self.server.port,
            timeout=3,
        )
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        status = HTTPStatus(response.status)
        response_headers = {name.casefold(): value for name, value in response.getheaders()}
        response_body = response.read()
        connection.close()
        return status, response_headers, response_body

    @property
    def _authorization(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.server.authorization_token}"}

    def test_binds_only_ipv4_loopback_and_generates_a_256_bit_fragment_token(self) -> None:
        self.assertEqual(LOOPBACK_HOST, self.server.host)
        self.assertGreater(self.server.port, 0)
        token = self.server.authorization_token
        decoded = base64.urlsafe_b64decode(token + ("=" * (-len(token) % 4)))
        self.assertGreaterEqual(len(decoded), 32)

        suggested = urlsplit(self.server.suggested_url)
        self.assertEqual("http", suggested.scheme)
        self.assertEqual(LOOPBACK_HOST, suggested.hostname)
        self.assertEqual(self.server.port, suggested.port)
        self.assertEqual("/", suggested.path)
        self.assertEqual("", suggested.query)
        self.assertEqual([token], parse_qs(suggested.fragment)["token"])

    def test_public_html_has_strict_security_headers_and_no_embedded_token(self) -> None:
        status, headers, body = self._request("GET", "/")
        source = body.decode("utf-8")

        self.assertEqual(HTTPStatus.OK, status)
        self.assertEqual("DENY", headers["x-frame-options"])
        self.assertEqual("nosniff", headers["x-content-type-options"])
        self.assertEqual("no-store", headers["cache-control"])
        self.assertEqual("no-referrer", headers["referrer-policy"])
        self.assertIn("default-src 'none'", headers["content-security-policy"])
        self.assertIn("frame-ancestors 'none'", headers["content-security-policy"])
        self.assertIn("script-src 'nonce-", headers["content-security-policy"])
        self.assertNotIn("access-control-allow-origin", headers)
        self.assertNotIn(self.server.authorization_token, source)
        self.assertNotIn("__CSP_NONCE__", source)
        self.assertIn("window.history.replaceState", source)
        self.assertNotIn("localStorage", source)
        self.assertNotIn("sessionStorage", source)

    def test_status_requires_exact_bearer_authorization(self) -> None:
        for authorization in (None, "", "Basic abc", "bearer wrong", "Bearer wrong"):
            headers = {} if authorization is None else {"Authorization": authorization}
            with self.subTest(authorization=authorization):
                status, response_headers, body = self._request(
                    "GET",
                    "/api/v1/status",
                    headers=headers,
                )
                payload = json.loads(body)
                self.assertEqual(HTTPStatus.UNAUTHORIZED, status)
                self.assertEqual("Bearer", response_headers["www-authenticate"])
                self.assertEqual("unauthorized", payload["error"]["code"])
        self.assertEqual(0, self.service.status_calls)

        status, _, body = self._request(
            "GET",
            "/api/v1/status",
            headers=self._authorization,
        )

        self.assertEqual(HTTPStatus.OK, status)
        self.assertEqual("gaming-pc-east", json.loads(body)["node_id"])
        self.assertEqual(1, self.service.status_calls)

    def test_non_ascii_duplicate_and_wrong_length_authorization_return_401(self) -> None:
        authorization_values = (
            b"Bearer \xff",
            b"Bearer " + (b"x" * 1_000),
            b"Basic " + self.server.authorization_token.encode("ascii"),
        )
        captured = io.StringIO()

        with contextlib.redirect_stderr(captured):
            for authorization in authorization_values:
                with self.subTest(authorization=authorization[:20]):
                    connection = self._raw_connection()
                    try:
                        connection.sendall(
                            b"GET /api/v1/status HTTP/1.1\r\n"
                            b"Host: 127.0.0.1\r\n"
                            b"Authorization: " + authorization + b"\r\nConnection: close\r\n\r\n"
                        )
                        response = self._read_raw_response(connection)
                    finally:
                        connection.close()
                    self.assertIn(b"HTTP/1.1 401 Unauthorized", response)

            connection = self._raw_connection()
            try:
                token = self.server.authorization_token.encode("ascii")
                connection.sendall(
                    b"GET /api/v1/status HTTP/1.1\r\n"
                    b"Host: 127.0.0.1\r\n"
                    b"Authorization: Bearer "
                    + token
                    + b"\r\nAuthorization: Bearer "
                    + token
                    + b"\r\nConnection: close\r\n\r\n"
                )
                response = self._read_raw_response(connection)
            finally:
                connection.close()

        self.assertIn(b"HTTP/1.1 401 Unauthorized", response)
        self.assertEqual(0, self.service.status_calls)
        self.assertEqual("", captured.getvalue())

    def test_incomplete_headers_expire_without_blocking_a_normal_request(self) -> None:
        self._restart_server(
            max_concurrent_requests=3,
            header_timeout_seconds=0.2,
            body_timeout_seconds=0.2,
        )
        stalled = [self._raw_connection(), self._raw_connection()]
        try:
            for connection in stalled:
                connection.sendall(
                    b"GET /api/v1/status HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization:"
                )

            started_at = time.monotonic()
            status, _, _ = self._request(
                "GET",
                "/api/v1/status",
                headers=self._authorization,
            )
            elapsed = time.monotonic() - started_at

            self.assertEqual(HTTPStatus.OK, status)
            self.assertLess(elapsed, 0.5)
            for connection in stalled:
                self.assertEqual(b"", connection.recv(1))
        finally:
            for connection in stalled:
                connection.close()

    def test_incomplete_body_expires_without_blocking_a_normal_request(self) -> None:
        self._restart_server(
            max_concurrent_requests=2,
            header_timeout_seconds=0.3,
            body_timeout_seconds=0.2,
        )
        stalled = self._raw_connection()
        token = self.server.authorization_token.encode("ascii")
        try:
            stalled.sendall(
                b"POST /api/v1/actions HTTP/1.1\r\n"
                b"Host: 127.0.0.1\r\n"
                b"Authorization: Bearer " + token + b"\r\nContent-Type: application/json\r\n"
                b"Content-Length: 64\r\nConnection: close\r\n\r\n{"
            )

            status, _, _ = self._request(
                "GET",
                "/api/v1/status",
                headers=self._authorization,
            )

            self.assertEqual(HTTPStatus.OK, status)
            self.assertEqual(b"", stalled.recv(1))
            self.assertEqual([], self.service.execute_calls)
        finally:
            stalled.close()

    def test_incomplete_body_eof_returns_structured_error_without_dispatch(self) -> None:
        self._restart_server(body_timeout_seconds=0.5)
        connection = self._raw_connection()
        token = self.server.authorization_token.encode("ascii")
        try:
            connection.sendall(
                b"POST /api/v1/actions HTTP/1.1\r\n"
                b"Host: 127.0.0.1\r\n"
                b"Authorization: Bearer " + token + b"\r\nContent-Type: application/json\r\n"
                b"Content-Length: 30\r\nConnection: close\r\n\r\n{}"
            )
            connection.shutdown(socket.SHUT_WR)
            response = self._read_raw_response(connection)
        finally:
            connection.close()

        self.assertIn(b"HTTP/1.1 400 Bad Request", response)
        self.assertIn(b'"code":"incomplete-body"', response)
        self.assertEqual([], self.service.execute_calls)

    def test_worker_limit_lets_deadlines_release_a_slot_for_a_normal_request(self) -> None:
        self._restart_server(
            max_concurrent_requests=2,
            header_timeout_seconds=0.2,
            body_timeout_seconds=0.2,
        )
        stalled = [self._raw_connection(), self._raw_connection()]
        try:
            for connection in stalled:
                connection.sendall(b"GET /api/v1/status HTTP/1.1\r\nHost:")
            time.sleep(0.05)

            started_at = time.monotonic()
            status, _, _ = self._request(
                "GET",
                "/api/v1/status",
                headers=self._authorization,
            )
            elapsed = time.monotonic() - started_at

            self.assertEqual(HTTPStatus.OK, status)
            self.assertLess(elapsed, 0.6)
        finally:
            for connection in stalled:
                connection.close()

    def test_all_reviewed_action_shapes_dispatch_exact_arguments(self) -> None:
        requests = [
            ({"action": action}, (action, None, None))
            for action in ("start-all", "refresh", "tile-all")
        ]
        requests.append(
            (
                {"action": "start", "client_id": "front-left"},
                (
                    "start",
                    "front-left",
                    None,
                ),
            )
        )
        requests.extend(
            (
                {
                    "action": action,
                    "client_id": "front-left",
                    "instance_id": "client-abc",
                },
                (action, "front-left", "client-abc"),
            )
            for action in ("attach", "tile", "pause", "resume", "detach", "close")
        )

        for payload, expected_call in requests:
            with self.subTest(action=payload["action"]):
                headers = {**self._authorization, "Content-Type": "application/json"}
                status, _, body = self._request(
                    "POST",
                    "/api/v1/actions",
                    body=json.dumps(payload),
                    headers=headers,
                )
                self.assertEqual(HTTPStatus.OK, status, body)
                self.assertEqual(expected_call, self.service.execute_calls[-1])

    def test_action_endpoint_rejects_unknown_missing_and_extra_fields(self) -> None:
        invalid_payloads = (
            ({}, "unknown-action"),
            ({"action": "retarget"}, "unknown-action"),
            ({"action": "start", "client_id": "slot", "instance_id": "client-1"}, "invalid-fields"),
            ({"action": "close", "client_id": "slot"}, "invalid-fields"),
            ({"action": "refresh", "client_id": "slot"}, "invalid-fields"),
            ({"action": "start", "client_id": "../slot"}, "invalid-field"),
        )
        headers = {**self._authorization, "Content-Type": "application/json"}

        for payload, expected_code in invalid_payloads:
            with self.subTest(payload=payload):
                status, _, body = self._request(
                    "POST",
                    "/api/v1/actions",
                    body=json.dumps(payload),
                    headers=headers,
                )
                self.assertEqual(HTTPStatus.BAD_REQUEST, status)
                self.assertEqual(expected_code, json.loads(body)["error"]["code"])
        self.assertEqual([], self.service.execute_calls)

    def test_action_endpoint_enforces_json_contract_and_size_cap(self) -> None:
        authorization = self._authorization
        cases = (
            (
                b'{"action":"refresh","action":"tile-all"}',
                {**authorization, "Content-Type": "application/json"},
                HTTPStatus.BAD_REQUEST,
                "duplicate-field",
            ),
            (
                b"not json",
                {**authorization, "Content-Type": "application/json"},
                HTTPStatus.BAD_REQUEST,
                "invalid-json",
            ),
            (
                b'{"action":"refresh"}',
                {**authorization, "Content-Type": "text/plain"},
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                "unsupported-media-type",
            ),
            (
                b" " * (MAX_ACTION_BODY_BYTES + 1),
                {**authorization, "Content-Type": "application/json"},
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "body-too-large",
            ),
        )

        for body_source, headers, expected_status, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                status, _, body = self._request(
                    "POST",
                    "/api/v1/actions",
                    body=body_source,
                    headers=headers,
                )
                self.assertEqual(expected_status, status)
                self.assertEqual(expected_code, json.loads(body)["error"]["code"])
        self.assertEqual([], self.service.execute_calls)

    def test_route_and_method_allowlists_return_structured_errors_without_cors(self) -> None:
        cases = (
            ("GET", "/favicon.ico", HTTPStatus.NOT_FOUND, "not-found"),
            ("GET", "/api/v1/status?token=x", HTTPStatus.NOT_FOUND, "not-found"),
            ("POST", "/api/v2/actions", HTTPStatus.NOT_FOUND, "not-found"),
            ("OPTIONS", "/api/v1/actions", HTTPStatus.METHOD_NOT_ALLOWED, "method-not-allowed"),
            ("TRACE", "/", HTTPStatus.METHOD_NOT_ALLOWED, "method-not-allowed"),
        )

        for method, path, expected_status, expected_code in cases:
            with self.subTest(method=method, path=path):
                status, headers, body = self._request(
                    method,
                    path,
                    headers={"Origin": "https://example.invalid"},
                )
                self.assertEqual(expected_status, status)
                self.assertEqual(expected_code, json.loads(body)["error"]["code"])
                self.assertNotIn("access-control-allow-origin", headers)

    def test_service_errors_are_structured_without_exposing_unexpected_details(self) -> None:
        self.service.execute_error = DashboardError(
            "invalid-transition",
            "The slot is already paused.",
        )
        headers = {**self._authorization, "Content-Type": "application/json"}
        status, _, body = self._request(
            "POST",
            "/api/v1/actions",
            body='{"action":"pause","client_id":"slot-1","instance_id":"client-1"}',
            headers=headers,
        )
        payload = json.loads(body)
        self.assertEqual(HTTPStatus.CONFLICT, status)
        self.assertEqual("invalid-transition", payload["error"]["code"])
        self.assertEqual("The slot is already paused.", payload["error"]["message"])

        self.service.status_error = RuntimeError("secret internal detail")
        status, _, body = self._request(
            "GET",
            "/api/v1/status",
            headers=self._authorization,
        )
        self.assertEqual(HTTPStatus.INTERNAL_SERVER_ERROR, status)
        self.assertNotIn("secret internal detail", body.decode("utf-8"))

    def test_request_logging_is_disabled_even_when_path_contains_token(self) -> None:
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            status, _, _ = self._request(
                "GET",
                f"/{self.server.authorization_token}",
            )

        self.assertEqual(HTTPStatus.NOT_FOUND, status)
        self.assertNotIn(self.server.authorization_token, captured.getvalue())

    def test_dashboard_ui_contains_only_operational_controls_and_confirmations(self) -> None:
        _, _, body = self._request("GET", "/")
        source = body.decode("utf-8").casefold()

        for action in (
            "start-all",
            "refresh",
            "tile-all",
            "attach",
            "pause",
            "resume",
            "detach",
            "close",
        ):
            self.assertIn(action, source)
        self.assertGreaterEqual(source.count("window.confirm"), 2)
        self.assertNotIn("caller", source)
        self.assertNotIn("tactical", source)

    def test_stop_is_idempotent_and_closed_server_cannot_restart(self) -> None:
        self.assertTrue(self.server.is_running)

        self.server.stop()
        self.server.stop()

        self.assertFalse(self.server.is_running)
        with self.assertRaisesRegex(RuntimeError, "closed"):
            self.server.start()


if __name__ == "__main__":
    unittest.main()
