#include "command_channel.h"
#undef NDEBUG
#include <cassert>
namespace d = wonderbane::extension::command_channel_detail;
namespace v = wonderbane::extension::vendor;
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
    auto publish = [&](std::uint64_t sequence, bool wrong_lease, unsigned kind = 8, bool multiple = false) {
        auto& slot = storage.commands[sequence - 1];
        slot = {};
        slot.command_id = sequence; slot.kind = kind; slot.payload_version = 1;
        slot.created_tick = now; slot.deadline_tick = now + 100;
        v::wire::Command payload{};
        payload.host = {identity.process_id, wrong_lease ? 8U : 7U, identity.creation_filetime_utc};
        payload.window = 123; payload.request[0] = static_cast<unsigned char>(sequence);
        if(kind==32) {
            auto& s=payload.expected; s.scene=s.revision=1; s.root=100; s.manager=200; s.menu=300;
            s.recipe=400; s.hireling=500; s.building=600; s.vendor=700; s.item_template=5051080;
            s.table=16; s.mode=1; s.prefix=s.suffix=3362971591U; s.quantity=1; s.multiple=multiple;
            s.count=1; s.slots[0].entry=800;
        }
        std::memcpy(&slot.movement, &payload, sizeof(payload));
        InterlockedExchange64(&slot.committed_sequence, static_cast<LONG64>(sequence));
        InterlockedExchange64(&storage.header.command_write_sequence, static_cast<LONG64>(sequence));
    };
    publish(1, false);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_IO_PENDING);
    assert(runtime.vendor_pending && !runtime.pending && storage.header.command_read_sequence == 0);
    auto command = v::Take(); assert(command && command->lease->Current(now));
    assert(!v::Take()); // Worker cannot execute it a second time.
    v::wire::Receipt receipt{};
    receipt.host = command->command.host; receipt.request = command->command.request;
    receipt.window = command->command.window; receipt.outcome = 0;
    v::Complete(command, receipt);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_SUCCESS);
    assert(!runtime.vendor_pending && storage.header.command_read_sequence == 1);
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
    for(unsigned kind:{33U,32U}) {
        const std::uint64_t sequence=kind==33?4:5;
        publish(sequence,false,kind);
        assert(d::DrainCommands(storage,runtime.result_signal,now)==ERROR_IO_PENDING);
        auto extended=v::Take(); assert(extended && static_cast<unsigned>(extended->verb)==kind);
        v::wire::Receipt done{}; done.host=extended->command.host; done.request=extended->command.request;
        done.window=extended->command.window; done.outcome=kind==33?0:1;
        v::Complete(extended,done);
        assert(d::DrainCommands(storage,runtime.result_signal,now)==ERROR_SUCCESS);
        assert(storage.header.command_read_sequence==static_cast<LONG64>(sequence));
    }
    publish(6,false,32,true);
    assert(d::DrainCommands(storage,runtime.result_signal,now)==ERROR_SUCCESS);
    assert(!v::Take() && storage.results[5].stage==static_cast<unsigned>(ClientActionResultStage::failed));
    SetEvent(release_worker);
    StopClientActionCommandChannel();
    CloseHandle(entered); CloseHandle(release_worker);
}
