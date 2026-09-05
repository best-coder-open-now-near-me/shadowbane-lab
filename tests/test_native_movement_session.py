import os
import subprocess
import uuid
from dataclasses import replace
from pathlib import Path

import pytest

from shadowbane_lab.client_extension import action_channel as channel
from shadowbane_lab.client_extension.movement_session import NativeMovementSession
from shadowbane_lab.client_extension.movement_wire import Owner


def test_real_producer_mutex_native_owner_completion_and_readonly_snapshot():
    configured = os.environ.get("WONDERBANE_MOVEMENT_RUNTIME_TEST")
    if not configured:
        pytest.skip("set WONDERBANE_MOVEMENT_RUNTIME_TEST to the built native runtime fixture")
    binary = Path(configured)
    assert binary.is_file(), "required native IPC fixture is missing"
    process = subprocess.Popen(
        [str(binary), "ipc"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        assert process.stdout is not None
        pid, creation, window = map(int, process.stdout.readline().split())
        identity = channel.NativeClientProcessIdentity(pid, creation)
        session = NativeMovementSession(identity, window, timeout_ms=1500)
        before = session.snapshot()
        assert session._transport is None  # observation cannot take the producer lease
        assert before.grant.owner == Owner.NONE
        key = str(uuid.uuid4())
        grant = session.acquire(before, "worker", "route", key)
        assert grant.ownership.owner == Owner.AUTOMATION
        retried = session.acquire(before, "worker", "route", key)
        assert retried == grant
        with pytest.raises(ValueError):
            session.acquire(replace(before, revision=before.revision + 1), "worker", "route", key)
        assert not before.settings.enabled
        session.move(grant, (30.0, 0.0, -40.0), str(uuid.uuid4()))
        session.pause(grant, str(uuid.uuid4()))
        assert session.snapshot().grant == grant.ownership
        session.renew(grant)
        session.move(grant, (31.0, 0.0, -41.0), str(uuid.uuid4()))
        session.stop(grant, str(uuid.uuid4()))
        session.close()
        output, error = process.communicate(timeout=5)
        assert process.returncode == 0, output + error
    finally:
        if session is not None:
            session.close()
        if process.poll() is None:
            process.kill()
            process.communicate()


def test_snapshot_mixed_schema_and_odd_publication_never_claim_lease():
    import mmap
    import struct

    from shadowbane_lab.client_extension.movement_session import read_snapshot
    from shadowbane_lab.client_extension.movement_wire import Grant, Settings, Snapshot

    identity = channel.NativeClientProcessIdentity(os.getpid(), uuid.uuid4().int & ((1 << 63) - 1))
    memory = mmap.mmap(-1, channel.CLIENT_ACTION_CHANNEL_SIZE, tagname=identity.mapping_name)
    try:
        header = bytearray(128)
        struct.pack_into(
            "<8s8IQ",
            header,
            0,
            channel.CLIENT_ACTION_CHANNEL_MAGIC,
            2,
            128,
            768,
            32,
            512,
            64,
            identity.process_id,
            1,
            identity.creation_filetime_utc,
        )
        struct.pack_into("<iiq", header, 96, 1234, 7, 17)
        memory[:128] = header
        offset = channel.CLIENT_ACTION_STATUS_OFFSET
        memory[offset : offset + 512] = Snapshot(
            2,
            identity.process_id,
            7,
            identity.creation_filetime_utc,
            1,
            Grant(1, 1),
            Settings(),
            1,
            20,
        ).encode()
        assert read_snapshot(identity, 1).sequence == 2
        assert memory[:128] == header
        for schema, command_size in ((1, 768), (2, 192)):
            changed = bytearray(header)
            struct.pack_into("<I", changed, 8, schema)
            struct.pack_into("<I", changed, 16, command_size)
            memory[:128] = changed
            with pytest.raises(channel.NativeActionChannelUnavailable):
                read_snapshot(identity, 1)
            assert memory[:128] == changed
        memory[:128] = header
        memory[offset : offset + 8] = struct.pack("<q", 3)
        with pytest.raises(channel.NativeActionChannelUnavailable):
            read_snapshot(identity, 1)
        assert memory[:128] == header
    finally:
        memory.close()
