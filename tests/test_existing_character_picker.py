"""Existing-client selection across passive identity, dashboard and live facade."""

import http.client
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_manager_application import (
    NODE_ID,
    _application,
    _client,
    _manifest,
    _RecordingSession,
    _RecordingWorkerController,
    _slot,
)

from shadowbane_lab.manager.character_choice import CharacterChoice, NativeCharacterChoices
from shadowbane_lab.manager.dashboard import DashboardError, DashboardServer
from shadowbane_lab.manager.live_configuration import LiveConfiguredManagerApplication
from shadowbane_lab.manager.manifest import parse_manager_manifest
from shadowbane_lab.manager.model import ClientRegistrySnapshot
from shadowbane_lab.manager.session import ManagerSessionSnapshot


def choices():
    return SimpleNamespace(
        inspect=lambda c: CharacterChoice(
            "Umbra" if c.process_id == 101 else "Praeda", "Test server", str(c.process_id)[0] * 64
        )
    )


def app_pair():
    session = _RecordingSession(
        ManagerSessionSnapshot(node_id=NODE_ID, slots=(_slot("client-01"), _slot("client-02")))
    )
    controller = _RecordingWorkerController()
    app, registry = _application(
        session,
        _client("instance-101", 101),
        _client("instance-202", 202),
        worker_controller=controller,
    )
    app._character_choices = choices()
    return app, registry, session, controller


def test_exact_choice_attaches_only_selected_client_without_game_launch():
    app, _, session, controller = app_pair()
    status = app.status()
    candidate = status["slots"][0]["candidates"][1]
    assert candidate["character"]["name"] == "Praeda"
    app.execute(
        "attach",
        client_id="client-01",
        instance_id=candidate["instance_id"],
        selection={"character_token": candidate["character"]["token"]},
    )
    assert session.calls == [("attach", "client-01", "instance-202")]
    assert controller.starts == [("client-01", "instance-202")]


@pytest.mark.parametrize("change", ["character", "missing", "unavailable", "foreign-path"])
def test_stale_choice_rejected_before_worker_or_lifecycle_side_effect(change):
    app, registry, session, controller = app_pair()
    if change == "character":
        app._character_choices = SimpleNamespace(
            inspect=lambda c: CharacterChoice("New", "S", "f" * 64)
        )
    elif change == "unavailable":
        app._character_choices = SimpleNamespace(inspect=lambda c: CharacterChoice())
    else:
        registry.snapshot = ClientRegistrySnapshot(
            node_id=NODE_ID,
            clients=(
                ()
                if change == "missing"
                else (_client("instance-101", 101, directory=r"C:\Other"),)
            ),
        )
    with pytest.raises(DashboardError, match="changed"):
        app.execute(
            "attach",
            client_id="client-01",
            instance_id="instance-101",
            selection={"character_token": "1" * 64},
        )
    assert session.calls == [] and controller.starts == [] and controller.stops == []
    assert registry.worker_supervisor.revocations == []


def test_bound_client_cannot_be_replaced_by_stale_browser():
    app, registry, session, controller = app_pair()
    app.execute(
        "attach",
        client_id="client-01",
        instance_id="instance-101",
        selection={"character_token": "1" * 64},
    )
    before = (
        list(session.calls),
        list(controller.stops),
        list(registry.worker_supervisor.revocations),
    )
    with pytest.raises(DashboardError, match="already in use"):
        app.execute(
            "attach",
            client_id="client-01",
            instance_id="instance-202",
            selection={"character_token": "2" * 64},
        )
    assert before == (session.calls, controller.stops, registry.worker_supervisor.revocations)


def test_same_instance_cannot_be_claimed_by_second_slot():
    app, _, _, _ = app_pair()
    app.execute("attach", client_id="client-01", instance_id="instance-101")
    with pytest.raises(DashboardError, match="already in use"):
        app.execute("attach", client_id="client-02", instance_id="instance-101")


@pytest.mark.parametrize("receipt", [None, SimpleNamespace(state=SimpleNamespace(terminal=False))])
def test_unfinished_operation_on_unbound_slot_prevents_attachment(receipt):
    app, registry, session, _ = app_pair()
    app._operation_status = SimpleNamespace(
        inspect_slot=lambda _: [SimpleNamespace(receipt=receipt)]
    )
    with pytest.raises(DashboardError, match="Finish the current operation"):
        app.execute("attach", client_id="client-01", instance_id="instance-101")
    assert not session.calls and not registry.worker_supervisor.revocations


def test_actual_one_tileless_slot_two_clients_http_status_and_attach(tmp_path):
    payload = _manifest().to_dict()
    payload["clients"] = payload["clients"][:1]
    payload["clients"][0].pop("window_tile", None)
    manifest = parse_manager_manifest(payload)
    path = tmp_path / "manager.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    app, registry, session, _ = app_pair()
    app._manifest = manifest
    app._configs = {c.client_id: c for c in manifest.clients}
    session.snapshot_value = ManagerSessionSnapshot(NODE_ID, (_slot("client-01"),))
    live = LiveConfiguredManagerApplication(path, manifest, lambda m: app)
    server = DashboardServer(live, port=0).start()

    def request(method, endpoint, body=None):
        connection = http.client.HTTPConnection(server.host, server.port, timeout=5)
        headers = {"Authorization": "Bearer " + server.authorization_token}
        if body is not None:
            headers["Content-Type"] = "application/json"
        connection.request(method, endpoint, None if body is None else json.dumps(body), headers)
        response = connection.getresponse()
        data = json.loads(response.read())
        connection.close()
        return response.status, data

    try:
        code, status = request("GET", "/api/v1/status")
        assert code == 200 and status["bound_count"] == 0
        assert len(status["slots"]) == 1
        candidates = status["slots"][0]["candidates"]
        assert [c["character"]["name"] for c in candidates] == ["Umbra", "Praeda"]
        assert not any(call[0] == "attach" for call in session.calls)
        session.calls.clear()
        selected = candidates[1]
        code, _ = request(
            "POST",
            "/api/v1/actions",
            {
                "action": "attach",
                "client_id": "client-01",
                "instance_id": selected["instance_id"],
                "selection": {"character_token": selected["character"]["token"]},
            },
        )
        assert code == 200
        assert session.snapshot().slots[0].instance_id == "instance-202"
        assert all(call[0] not in {"start", "start-all"} for call in session.calls)
        assert json.loads(path.read_text()) == payload
    finally:
        server.stop()


def native_session(client):
    identity = SimpleNamespace(character_name="<Umbra>", server_name="Test", player_pointer=1234)
    binding = SimpleNamespace(
        process_id=client.process_id,
        process_creation_filetime_utc=client.process_started_at_100ns,
        executable_path=Path(client.executable_path),
        identity=identity,
        as_dict=lambda: {"key": [123, 37], "name": identity.character_name},
    )
    session = Mock()
    session.binding = binding
    session.__enter__ = Mock(return_value=session)
    session.__exit__ = Mock(return_value=False)
    return session


def test_native_labels_are_current_exact_process_and_character(monkeypatch):
    client = _client("instance-101", 101)
    session = native_session(client)
    monkeypatch.setattr(
        "shadowbane_lab.manager.character_choice.open_native_character_session",
        lambda **kwargs: session,
    )
    reader = NativeCharacterChoices()
    first = reader.inspect(client)
    assert first.name == "<Umbra>" and first.server == "Test" and len(first.token) == 64
    session.require_current.assert_called_once()
    session.binding.identity.player_pointer += 4
    assert reader.inspect(client).token != first.token
    assert (
        reader.inspect(replace(client, window_handle=client.window_handle + 1)).token != first.token
    )


@pytest.mark.parametrize("mismatch", ["pid", "creation", "path", "unreadable"])
def test_native_labels_fail_closed_without_using_title(monkeypatch, mismatch):
    client = _client("instance-101", 101)
    session = native_session(client)
    if mismatch == "pid":
        session.binding.process_id += 1
    if mismatch == "creation":
        session.binding.process_creation_filetime_utc += 1
    if mismatch == "path":
        session.binding.executable_path = Path(r"C:\Other\sb.exe")
    if mismatch == "unreadable":
        session.require_current.side_effect = RuntimeError("loading")
    monkeypatch.setattr(
        "shadowbane_lab.manager.character_choice.open_native_character_session",
        lambda **kwargs: session,
    )
    assert NativeCharacterChoices().inspect(client) == CharacterChoice()
    session.__exit__.assert_called_once()


def test_picker_renderer_disables_unknown_and_sends_exact_selection():
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the dashboard renderer")
    html = (
        Path(__file__).parents[1] / "src/shadowbane_lab/manager/static/dashboard.html"
    ).read_text(encoding="utf-8")
    script = html.split('<script nonce="__CSP_NONCE__">', 1)[1].split("</script>", 1)[0]
    subprocess.run(
        [node, "--check"],
        input=script,
        text=True,
        encoding="utf-8",
        check=True,
        capture_output=True,
    )
    renderer = script[
        script.index("function renderCharacterChoices") : script.index("const renderSlot")
    ]
    code = (
        """
const assert = require('assert');
const sent = [];
const execute = value => sent.push(value);
function element() { return {children: [], textContent: '',
 append(...xs) {this.children.push(...xs)},
 addEventListener(event, callback) {this[event] = callback},
 set innerHTML(value) {throw Error('unsafe label rendering')}}; }
const document = {createElement: element};
"""
        + renderer
        + """
const root = element();
const token = 'a'.repeat(64);
renderCharacterChoices(root, {client_id: 'slot', candidates: [
 {instance_id:'one', process_id:101, character:{state:'available', name:'<Umbra>',
 server:'Server', token}},
 {instance_id:'two', process_id:102, character:{state:'unavailable', token:null}}]});
const rows = root.children[0].children;
assert(rows[0].children[0].textContent.includes('<Umbra>'));
assert(rows[0].children[0].textContent.includes('Server'));
assert.equal(rows[0].children[1].textContent, 'Use this character');
assert.equal(rows[0].children[1].disabled, false);
assert.equal(rows[1].children[1].disabled, true);
rows[0].children[1].click();
assert.deepStrictEqual(sent, [{action:'attach', client_id:'slot', instance_id:'one',
 selection:{character_token:token}}]);
"""
    )
    subprocess.run([node], input=code, text=True, encoding="utf-8", check=True, capture_output=True)
