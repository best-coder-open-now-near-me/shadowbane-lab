#include "command_channel.h"
#include <fstream>
#include <string>
#undef NDEBUG
#include <cassert>
namespace d = wonderbane::extension::command_channel_detail;
namespace v = wonderbane::extension::combat::v2;
namespace f=v::wire::fence;
namespace outer=wonderbane::extension::combat;
using namespace wonderbane::extension;
namespace wonderbane::extension::combat {
std::atomic<bool> test_ready{false};
bool Ready() noexcept { return test_ready.load(); }
}
namespace {
HANDLE entered = nullptr, release_worker = nullptr;
void Hold() noexcept { SetEvent(entered); WaitForSingleObject(release_worker, INFINITE); }
}
int main(int argc, char** argv) {
    assert(argc == 2);
    std::ifstream file(argv[1]); std::string hex; v::wire::Command prototype{};
    assert(std::getline(file, hex) && hex.size() == sizeof(prototype) * 2);
    auto* bytes = reinterpret_cast<unsigned char*>(&prototype);
    for (std::size_t i = 0; i < sizeof(prototype); ++i) {
        bytes[i] = static_cast<unsigned char>(std::stoul(hex.substr(i * 2, 2), nullptr, 16));
    }
    f::Binding prototype_binding{};
    assert(v::wire::BindingFor(prototype, 1234, 0x1020304050607080ULL, prototype_binding));
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
    std::uint64_t sequence = 0;
    auto publish = [&](v::wire::Verb verb, bool wrong_lease = false, bool corrupt = false) {
        ++sequence;
        auto& slot = storage.commands[(sequence - 1) % kClientActionCommandCapacity];
        slot = {};
        slot.command_id = sequence; slot.kind = static_cast<unsigned>(verb); slot.payload_version = 1;
        slot.created_tick = now; slot.deadline_tick = now + 100;
        auto payload = prototype; auto binding = prototype_binding;
        if(!v::wire::ActionVerb(verb)) { payload.action=v::wire::Action::none; payload.power_id=0; }
        payload.host = {identity.process_id, wrong_lease ? 8U : 7U, identity.creation_filetime_utc};
        std::memcpy(payload.request.data(), &sequence, sizeof(sequence));
        binding.client_pid = identity.process_id; binding.client_creation = identity.creation_filetime_utc;
        binding.producer_pid = payload.host.process; binding.producer_creation = payload.host.creation;
        binding.producer_generation = payload.host.generation;

        assert(v::wire::Hash(&binding, sizeof(binding), payload.binding_digest));
        assert(v::wire::BindingFor(payload, identity.process_id, identity.creation_filetime_utc, binding));
        if (corrupt) { payload.version = 1; }
        std::memcpy(&slot.movement, &payload, sizeof(payload));
        InterlockedExchange64(&slot.committed_sequence, static_cast<LONG64>(sequence));
        InterlockedExchange64(&storage.header.command_write_sequence, static_cast<LONG64>(sequence));
    };
    auto last_result = [&]() -> const ClientActionResultSlot& {
        const auto write = InterlockedCompareExchange64(&storage.header.result_write_sequence, 0, 0);
        assert(write > 0); return storage.results[static_cast<std::size_t>((write - 1) % kClientActionResultCapacity)];
    };
    auto returned = [&] {
        v::wire::Receipt receipt{}; std::memcpy(&receipt, &last_result().movement, sizeof(receipt)); return receipt;
    };
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_SUCCESS);
    assert(!(storage.header.capability_flags & kNativeCombatCapability));
    publish(v::wire::Verb::submit);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_SUCCESS);
    assert(!v::Take() && last_result().stage == static_cast<unsigned>(ClientActionResultStage::failed));
    assert(last_result().error == ERROR_NOT_SUPPORTED);

    combat_owner_ready.store(&outer::Ready, std::memory_order_release);
    outer::test_ready = true;
    storage.header.capability_flags|=8U;
    d::RefreshCombatCapability(storage);
    publish(v::wire::Verb::submit);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_IO_PENDING);
    assert(storage.header.capability_flags & kNativeCombatCapability);
    assert(kNativeCombatCapability==16U && !(storage.header.capability_flags&8U));
    assert(runtime.combat_pending && !runtime.pending && storage.header.command_read_sequence == 1);
    auto command = v::Take(); assert(command && command->lease->Current(now));
    assert(!v::Take());
    auto receipt = v::wire::Reply(command->command, command->verb, v::wire::Outcome::uncertain);
    receipt.flags = v::wire::cleanup_required | v::wire::outbound_queued;
    receipt.entry=v::wire::Entry::entered;
    receipt.phase = v::wire::Phase::stopping;
    std::array<char,73> diagnostic{}; strcpy_s(diagnostic.data(),diagnostic.size(),"combat_v2:dispatch:o7:d1n2q1");
    v::Complete(command, receipt, diagnostic);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_SUCCESS);
    assert(!runtime.combat_pending && storage.header.command_read_sequence == 2);
    assert(last_result().stage == static_cast<unsigned>(ClientActionResultStage::submitted_to_client));
    assert(last_result().error == ERROR_SUCCESS && last_result().consumer_thread_id == GetCurrentThreadId());
    auto response = returned(); assert(!std::memcmp(&receipt, &response, sizeof(receipt)));
    assert(std::string(last_result().detail, last_result().detail_length)
        == "combat_v2:dispatch:o7:d1n2q1");

    outer::test_ready = false;
    publish(v::wire::Verb::cancel_action);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_IO_PENDING);
    assert(!(storage.header.capability_flags & kNativeCombatCapability));
    command = v::Take(); assert(command && command->verb == v::wire::Verb::cancel_action);
    receipt = v::wire::Reply(command->command, command->verb, v::wire::Outcome::pending);
    receipt.flags = v::wire::cleanup_required; receipt.phase = v::wire::Phase::stopping;
    v::Complete(command, receipt);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_SUCCESS);
    assert(returned().outcome == v::wire::Outcome::pending);
    assert(last_result().stage == static_cast<unsigned>(ClientActionResultStage::submitted_to_client));

    publish(v::wire::Verb::action_status);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_IO_PENDING);
    command = v::Take(); assert(command && command->verb == v::wire::Verb::action_status);
    assert(d::DrainCommands(storage, runtime.result_signal, now + 101) == ERROR_IO_PENDING);
    receipt = v::wire::Reply(command->command, command->verb, v::wire::Outcome::stale);
    v::Complete(command, receipt);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_SUCCESS);
    assert(returned().outcome == v::wire::Outcome::stale);
    assert(last_result().stage == static_cast<unsigned>(ClientActionResultStage::submitted_to_client));

    publish(v::wire::Verb::cancel_action);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_IO_PENDING);
    assert(d::DrainCommands(storage, runtime.result_signal, now + 101) == ERROR_SUCCESS);
    assert(!v::Take() && returned().outcome == v::wire::Outcome::stale);
    assert(returned().flags == 0); // Expiry never invents a local-cancellation acknowledgment.

    publish(v::wire::Verb::cancel_action, true);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_SUCCESS);
    assert(!v::Take() && last_result().stage == static_cast<unsigned>(ClientActionResultStage::failed));
    publish(v::wire::Verb::action_status, false, true);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_SUCCESS);
    assert(!v::Take() && last_result().stage == static_cast<unsigned>(ClientActionResultStage::failed));

    publish(v::wire::Verb::action_status);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_IO_PENDING);
    command = v::Take(); assert(command);
    receipt = v::wire::Reply(command->command, command->verb, v::wire::Outcome::observed);
    ++receipt.revision;
    v::Complete(command, receipt, diagnostic);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_SUCCESS);
    assert(last_result().stage == static_cast<unsigned>(ClientActionResultStage::failed));
    assert(movement::wire::Zero(&last_result().movement, sizeof(last_result().movement)));
    assert(std::string(last_result().detail, last_result().detail_length) == "");

    publish(v::wire::Verb::action_status);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_IO_PENDING);
    command = v::Take(); assert(command);
    receipt = v::wire::Reply(command->command, command->verb, v::wire::Outcome::observed);
    v::Complete(command, receipt);
    const auto previous_read = storage.header.command_read_sequence;
    const auto result_write = storage.header.result_write_sequence;
    InterlockedExchange64(&storage.header.result_write_sequence, result_write + kClientActionResultCapacity);
    InterlockedExchange64(&storage.header.result_read_sequence, result_write);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_NOT_ENOUGH_QUOTA);
    assert(runtime.combat_pending && storage.header.command_read_sequence == previous_read && !v::Take());
    InterlockedExchange64(&storage.header.result_read_sequence, storage.header.result_write_sequence);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_SUCCESS);
    assert(!runtime.combat_pending && storage.header.command_read_sequence == static_cast<LONG64>(sequence));
    assert(returned().request == receipt.request);

    for(auto verb:{v::wire::Verb::engagement_status,v::wire::Verb::stop}) {
        publish(verb);
        assert(d::DrainCommands(storage,runtime.result_signal,now)==ERROR_IO_PENDING);
        command=v::Take(); assert(command && command->command.action==v::wire::Action::none);
        receipt=v::wire::Reply(command->command,verb,v::wire::Outcome::observed);
        v::Complete(command,receipt);
        assert(d::DrainCommands(storage,runtime.result_signal,now)==ERROR_SUCCESS);
        assert(returned().verb==verb);
    }
    for(unsigned legacy=34;legacy<=36;++legacy) {
        publish(static_cast<v::wire::Verb>(legacy));
        assert(d::DrainCommands(storage,runtime.result_signal,now)==ERROR_SUCCESS);
        assert(!v::Take() && last_result().stage==static_cast<unsigned>(ClientActionResultStage::failed));
    }
    publish(v::wire::Verb::bind);
    assert(d::DrainCommands(storage,runtime.result_signal,now)==ERROR_SUCCESS);
    assert(last_result().error==ERROR_NOT_SUPPORTED);
    outer::test_ready=true;
    publish(v::wire::Verb::bind);
    assert(d::DrainCommands(storage,runtime.result_signal,now)==ERROR_IO_PENDING);
    command=v::Take(); assert(command);
    receipt=v::wire::Reply(command->command,command->verb,v::wire::Outcome::bound);
    receipt.phase=v::wire::Phase::bound; receipt.flags=v::wire::cleanup_required;
    v::Complete(command,receipt);
    assert(d::DrainCommands(storage,runtime.result_signal,now)==ERROR_SUCCESS);
    assert(returned().outcome==v::wire::Outcome::bound);
    publish(v::wire::Verb::cancel_action);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_IO_PENDING);
    command = v::Take(); assert(command && command->lease->Current(now));
    SetEvent(release_worker);
    StopClientActionCommandChannel();
    assert(!command->lease->Current(GetTickCount64()) && !v::Take());
    combat_owner_ready.store(nullptr, std::memory_order_release);
    assert(!NativeCombatReady());
    CloseHandle(entered); CloseHandle(release_worker);
}
