import hashlib
import io
import json
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from shadowbane_lab.character_capture.delivery import deliver, load_connection
from shadowbane_lab.character_capture.receiver import ReportReceiver, bounded_bundle
from shadowbane_lab.character_capture.recording import Recording

TOKEN = "test-token-" + "a" * 40


def fixture(tmp_path):
    recording = Recording(tmp_path / "local", {"character_name": "Fixture"})
    recording.emit("character", {"test": True})
    recording.finish("test")
    config = tmp_path / "server.json"
    config.write_text(
        json.dumps(
            {
                "reporter_token_sha256": [hashlib.sha256(TOKEN.encode()).hexdigest()],
                "maximum_store_bytes": 1024**2,
            }
        )
    )
    receiver = ReportReceiver(tmp_path / "server", config)
    payload = (recording.path / "evidence.zip").read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    return recording, receiver, payload, digest, config


def request(receiver, payload, digest, **changes):
    env = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/v1/reports/" + digest,
        "HTTP_AUTHORIZATION": "Bearer " + TOKEN,
        "CONTENT_TYPE": "application/zip",
        "CONTENT_LENGTH": str(len(payload)),
        "wsgi.input": io.BytesIO(payload),
    }
    env.update(changes)
    return receiver.handle(env)


def test_upload_retry_has_same_durable_receipt(tmp_path):
    recording, receiver, payload, digest, _ = fixture(tmp_path)
    status, receipt = request(receiver, payload, digest)
    assert status.startswith("201")
    assert receipt["run_id"] == recording.run_id
    assert (receiver.reports / (digest + ".zip")).read_bytes() == payload
    assert request(receiver, payload, digest) == ("200 OK", receipt)
    assert len(list(receiver.reports.iterdir())) == 1


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("auth", "401"),
        ("length", "413"),
        ("truncated", "400"),
        ("checksum", "422"),
        ("bundle", "422"),
        ("quota", "507"),
    ],
)
def test_rejects_bad_reports_without_publishing(tmp_path, fault, expected):
    _, receiver, payload, digest, config = fixture(tmp_path)
    changes = {}
    if fault == "auth":
        changes["HTTP_AUTHORIZATION"] = "Bearer invalid"
    elif fault == "length":
        changes["CONTENT_LENGTH"] = str(1024**3)
    elif fault == "truncated":
        changes["CONTENT_LENGTH"] = str(len(payload) + 10)
    elif fault == "checksum":
        digest = "f" * 64
    elif fault == "bundle":
        payload = b"not a report"
        digest = hashlib.sha256(payload).hexdigest()
    else:
        value = json.loads(config.read_text())
        value["maximum_store_bytes"] = 1
        config.write_text(json.dumps(value))
    assert request(receiver, payload, digest, **changes)[0].startswith(expected)
    assert not list(receiver.reports.iterdir())
    assert not list(receiver.incoming.iterdir())


def test_missing_stored_file_is_never_acknowledged(tmp_path):
    _, receiver, payload, digest, _ = fixture(tmp_path)
    request(receiver, payload, digest)
    (receiver.reports / (digest + ".zip")).unlink()
    assert request(receiver, payload, digest)[0].startswith("503")


def test_rejects_compressed_or_bomb_shaped_upload_before_verifier(tmp_path):
    path = tmp_path / "compressed.zip"
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("bundle.json", "x" * 100000)
    with pytest.raises(ValueError):
        bounded_bundle(path)


def test_revocation_applies_without_restart(tmp_path):
    _, receiver, payload, digest, config = fixture(tmp_path)
    request(receiver, payload, digest)
    config.write_text('{"reporter_token_sha256":[]}')
    assert request(receiver, payload, digest)[0].startswith("401")


class Client:
    def __init__(self, receiver, corrupt=False):
        self.receiver, self.corrupt = receiver, corrupt
        self.body = io.BytesIO()
        self.headers = {}

    def putrequest(self, method, path):
        self.method, self.path = method, path

    def putheader(self, key, value):
        self.headers[key] = value

    def endheaders(self):
        pass

    def send(self, value):
        self.body.write(value)

    def getresponse(self):
        self.status, self.result = request(
            self.receiver, self.body.getvalue(), self.path.rsplit("/", 1)[-1]
        )
        self.status = int(self.status[:3])
        if self.corrupt:
            self.result["sha256"] = "0" * 64
        return self

    def read(self, count):
        return json.dumps(self.result).encode()[:count]

    def close(self):
        pass


def test_delivery_marks_sent_only_after_matching_receipt(tmp_path):
    recording, receiver, *_ = fixture(tmp_path)
    config = {"url": "https://private.example/shadowbane-reports", "token": TOKEN}
    with pytest.raises(RuntimeError, match="receipt"):
        deliver(recording.path, config, connection_factory=lambda: Client(receiver, corrupt=True))
    state = json.loads((recording.path / "delivery.json").read_text())
    assert state["status"] == "ready" and "token" not in state
    receipt = deliver(recording.path, config, connection_factory=lambda: Client(receiver))
    assert receipt["run_id"] == recording.run_id
    assert json.loads((recording.path / "delivery.json").read_text())["status"] == "sent"


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.example",
        "https://user:pass@example.com",
        "https://example.com?token=x",
        "https://example.com#fragment",
    ],
)
def test_connection_rejects_insecure_or_credential_urls(tmp_path, url):
    path = tmp_path / "connection.json"
    path.write_text(json.dumps({"url": url, "token": TOKEN}))
    with pytest.raises(ValueError):
        load_connection(path)
