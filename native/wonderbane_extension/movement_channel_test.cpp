#include "command_channel.h"
#include <iostream>
using namespace wonderbane::extension;
namespace m = wonderbane::extension::movement;
namespace d = wonderbane::extension::command_channel_detail;
HANDLE entered = nullptr, release_worker = nullptr;
void Hold() noexcept { SetEvent(entered); WaitForSingleObject(release_worker, INFINITE); }
int main() {
    FILETIME created{}, exited{}, kernel{}, user{};
    if (!GetProcessTimes(GetCurrentProcess(), &created, &exited, &kernel, &user)) { return 1; }
    ProcessIdentity identity{GetCurrentProcessId(), (static_cast<std::uint64_t>(created.dwHighDateTime) << 32) | created.dwLowDateTime};
    entered = CreateEventW(nullptr, TRUE, FALSE, nullptr); release_worker = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    d::g_runtime.before_drain = Hold; d::g_runtime.shutdown_wait_ms = 20;
    if (StartClientActionCommandChannel(identity) != ERROR_SUCCESS || WaitForSingleObject(entered, 2000) != WAIT_OBJECT_0) { return 2; }
    auto& rt = d::g_runtime; auto* storage = rt.storage;
    storage->header.host_process_id = static_cast<LONG>(identity.process_id);
    storage->header.host_lease_generation = 7; storage->header.host_heartbeat_tick = static_cast<LONG64>(GetTickCount64());
    auto lease = d::CaptureMovementLease(rt.backing, {identity.process_id, 7, identity.creation_filetime_utc}, GetTickCount64());
    if (!lease || !lease->Current(GetTickCount64())) { return 3; }
    auto wrong = d::CaptureMovementLease(rt.backing, {identity.process_id, 7, identity.creation_filetime_utc + 1}, GetTickCount64());
    if (wrong) { return 4; }
    storage->header.schema_version = 1;
    const auto read_sequence = storage->header.command_read_sequence;
    if (DrainClientActionCommandsForTesting(*storage, GetTickCount64()) != ERROR_INVALID_DATA
        || storage->header.command_read_sequence != read_sequence) { return 5; }
    storage->header.schema_version = 2;
    std::weak_ptr<d::Backing> retained = rt.backing;
    StopClientActionCommandChannel();
    if (!rt.worker || rt.storage != storage || retained.expired() || lease->Current(GetTickCount64())
        || StartClientActionCommandChannel(identity) != ERROR_INVALID_STATE) { return 6; }
    SetEvent(release_worker);
    if (WaitForSingleObject(rt.worker, 2000) != WAIT_OBJECT_0) { return 7; }
    StopClientActionCommandChannel();
    if (rt.storage || rt.worker || retained.expired()) { return 8; }
    // Old admitted lease retains storage until its callback returns, but loses
    // all authority immediately. A replacement generation is independent.
    d::g_runtime.before_drain = nullptr;
    if (StartClientActionCommandChannel(identity) != ERROR_ALREADY_EXISTS) { return 9; }
    lease.reset(); if (!retained.expired()) { return 10; }
    if (StartClientActionCommandChannel(identity) != ERROR_SUCCESS) { return 11; }
    StopClientActionCommandChannel();
    CloseHandle(entered); CloseHandle(release_worker);
    std::cout << "held worker timeout, lease retention, cleanup and schema rejection verified\n";
    return 0;
}
