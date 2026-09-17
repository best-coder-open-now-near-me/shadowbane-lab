#include "command_channel.h"
#undef NDEBUG
#include <cassert>
namespace d = wonderbane::extension::command_channel_detail;
namespace v = wonderbane::extension::guard_funding;
using namespace wonderbane::extension;
HANDLE entered = nullptr, release_worker = nullptr;
void Hold() noexcept { SetEvent(entered); WaitForSingleObject(release_worker, INFINITE); }
int main() {
    FILETIME created{}, exited{}, kernel{}, user{};
    assert(GetProcessTimes(GetCurrentProcess(), &created, &exited, &kernel, &user));
    ProcessIdentity identity{GetCurrentProcessId(),
        (static_cast<std::uint64_t>(created.dwHighDateTime) << 32) | created.dwLowDateTime};
    entered = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    release_worker = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    d::g_runtime.before_drain = Hold;
    assert(StartClientActionCommandChannel(identity) == ERROR_SUCCESS);
    assert(WaitForSingleObject(entered, 2000) == WAIT_OBJECT_0);
    auto& runtime = d::g_runtime; auto& storage = *runtime.storage;
    storage.header.host_process_id = static_cast<LONG>(identity.process_id);
    storage.header.host_lease_generation = 7;
    const auto now = GetTickCount64();
    storage.header.host_heartbeat_tick = static_cast<LONG64>(now);
    auto publish = [&](std::uint64_t sequence, bool wrong_lease, unsigned kind = 19) {
        auto& slot = storage.commands[sequence - 1];
        slot = {};
        slot.command_id = sequence; slot.kind = kind; slot.payload_version = 1;
        slot.created_tick = now; slot.deadline_tick = now + 100;
        v::wire::Command payload{};
        payload.host = {identity.process_id, wrong_lease ? 8U : 7U, identity.creation_filetime_utc};
        payload.window = 123; payload.request[0] = static_cast<unsigned char>(sequence);
        payload.direction = 1;
        if (kind != 19) {
            auto& s = payload.expected;
            s.scene = s.revision = 1; s.root = 100; s.actor = 200; s.character = {300, 1};
            s.manager = 400; s.hud = 500; s.source_object = 600; s.source = {700, 42};
            s.direction = 1; s.resource = 800; s.balance = 1000; s.reserve = 50;
            s.purse = 500; s.quote = 900; s.limit = 950; s.entered = 950;
            s.accept = 1100; s.cancel = 1200; s.helper = 1300;
            payload.amount = kind == 21 ? 951 : 100;
            slot.kind = 20;
        }
        std::memcpy(&slot.movement, &payload, sizeof(payload));
        InterlockedExchange64(&slot.committed_sequence, static_cast<LONG64>(sequence));
        InterlockedExchange64(&storage.header.command_write_sequence, static_cast<LONG64>(sequence));
    };
    publish(1, false);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_IO_PENDING);
    assert(runtime.guard_funding_pending && !runtime.pending && storage.header.command_read_sequence == 0);
    auto command = v::Take(); assert(command && command->lease->Current(now));
    assert(!v::Take()); // Worker cannot execute it a second time.
    v::wire::Receipt receipt{};
    receipt.host = command->command.host; receipt.request = command->command.request;
    receipt.window = command->command.window; receipt.outcome = 0;
    v::Complete(command, receipt);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_SUCCESS);
    assert(!runtime.guard_funding_pending && storage.header.command_read_sequence == 1);
    v::wire::Receipt returned{};
    std::memcpy(&returned, &storage.results[0].movement, sizeof(returned));
    assert(returned.signature == v::wire::magic && returned.request == receipt.request);
    publish(2, false);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_IO_PENDING);
    assert(d::DrainCommands(storage, runtime.result_signal, now + 101) == ERROR_SUCCESS);
    assert(!v::Take() && storage.header.command_read_sequence == 2);
    std::memcpy(&returned, &storage.results[1].movement, sizeof(returned));
    assert(returned.outcome == static_cast<unsigned>(v::wire::Outcome::stale));
    publish(3, true);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_SUCCESS);
    assert(!v::Take() && storage.results[2].stage == static_cast<unsigned>(ClientActionResultStage::failed));
    publish(4, false, 20);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_IO_PENDING);
    command = v::Take();
    assert(command && command->verb == v::wire::Verb::transfer && command->command.expected.source[1] == 42);
    receipt.request = command->command.request;
    v::Complete(command, receipt);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_SUCCESS);
    assert(!v::Take() && storage.header.command_read_sequence == 4);
    std::memcpy(&returned, &storage.results[3].movement, sizeof(returned));
    assert(returned.request == receipt.request);
    publish(5, false, 21); // An excessive withdrawal never reaches the owning thread.
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_SUCCESS);
    assert(!v::Take() && storage.results[4].stage == static_cast<unsigned>(ClientActionResultStage::failed));
    SetEvent(release_worker);
    StopClientActionCommandChannel();
    CloseHandle(entered); CloseHandle(release_worker);
}
