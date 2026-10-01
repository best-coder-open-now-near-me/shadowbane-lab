#include "command_channel.h"
#include "actor_action_controller.h"
#include <cstdio>
#include <fstream>
#include <string>
#undef NDEBUG
#include <cassert>
namespace d = wonderbane::extension::command_channel_detail;
namespace v = wonderbane::extension::actor;
namespace f=v::fence;
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

// Real cross-process transport and ledger fixture; Invoker deliberately performs
// no game action. Native power legality is covered by the separate image probe.
namespace {
struct ReadinessInvoker final : v::Invoker {
    unsigned opens{}, binds{}, powers{}, attacks{}, stops{};
    f::ActorBinding parent{}; f::ContextBinding child{};
    f::Ticket<f::ActorBinding> owner_ticket; f::Ticket<f::ContextBinding> child_ticket;
    void Revoke(const v::wire::Command&,bool) noexcept override {}
    v::Operation Open(const v::wire::Command& c) noexcept override {
        ++opens;
        assert(f::ReadBinding(c.parent_digest,parent) && v::wire::Bindings(c,parent));
        assert(owner_ticket.Open(parent,parent) && owner_ticket.TryAdmit(parent,false)==f::Result::admitted);
        v::Operation result; result.outcome=v::wire::Outcome::bound; result.state.phase=v::wire::Phase::bound; return result;
    }
    v::Operation Attach(const v::wire::Command& c) noexcept override {
        ++binds;
        assert(f::ReadBinding(c.context_digest,child) && v::wire::Bindings(c,parent,&child));
        assert(child_ticket.Open(child,parent) && child_ticket.TryAdmit(child,false)==f::Result::admitted);
        v::Operation result; result.outcome=v::wire::Outcome::bound; result.state.phase=v::wire::Phase::bound; return result;
    }
    v::Operation Submit(const v::wire::Command& command) noexcept override {
        assert(v::wire::Bindings(command,parent,&child));
        assert(owner_ticket.TryAdmit(parent,true)==f::Result::admitted && child_ticket.TryAdmit(child,true)==f::Result::admitted);
        v::Operation result; result.state.phase=v::wire::Phase::bound;
        if(command.action==v::wire::Action::self_power) {
            ++powers; result.outcome=v::wire::Outcome::power_reuse_blocked;
            result.reason=v::wire::Reason::power_reuse; return result;
        }
        assert(command.action==v::wire::Action::attack);
        ++attacks; outer::test_ready=false;
        result.outcome=v::wire::Outcome::queued; result.entry=v::wire::Entry::entered;
        result.history=v::wire::outbound_queued; return result;
    }
    v::State Stop(const v::wire::Command&,bool) noexcept override {
        ++stops; return {v::wire::Phase::closed,v::wire::Closure::native_stopped,1,2,0};
    }
};
int ReadinessIpc() {
    FILETIME created{},exited{},kernel{},user{};
    assert(GetProcessTimes(GetCurrentProcess(),&created,&exited,&kernel,&user));
    ProcessIdentity identity{GetCurrentProcessId(),
        (static_cast<std::uint64_t>(created.dwHighDateTime)<<32)|created.dwLowDateTime};
    combat_owner_ready.store(&outer::Ready,std::memory_order_release);
    outer::test_ready=true;
    assert(StartClientActionCommandChannel(identity)==ERROR_SUCCESS);
    d::RefreshCombatCapability(*d::g_runtime.storage);
    std::printf("%lu %llu\n",identity.process_id,
        static_cast<unsigned long long>(identity.creation_filetime_utc));
    std::fflush(stdout);
    v::Controller controller; ReadinessInvoker invoker;
    const auto deadline=GetTickCount64()+10000;
    bool done=false;
    while(GetTickCount64()<deadline) {
        if(auto pending=v::Take()) {
            const auto receipt=controller.Execute(pending->verb,pending->command,true,
                pending->lease->Current(GetTickCount64()),true,invoker);
            v::Complete(pending,receipt);
        }
        DWORD available{};
        if(PeekNamedPipe(GetStdHandle(STD_INPUT_HANDLE),nullptr,0,nullptr,&available,nullptr)
            && available) { done=std::getchar()=='d'; break; }
        Sleep(1);
    }
    StopClientActionCommandChannel();
    combat_owner_ready.store(nullptr,std::memory_order_release);
    std::printf("%u %u %u %u %u\n",invoker.opens,invoker.binds,invoker.powers,invoker.attacks,invoker.stops);
    std::fflush(stdout);
    return done && invoker.opens==1 && invoker.binds==1 && invoker.powers==1 && invoker.attacks==1
        && invoker.stops==2 ? 0 : 2;
}
}

int main(int argc, char** argv) {
    if(argc==2 && std::string(argv[1])=="--ipc-readiness") { return ReadinessIpc(); }
    assert(argc == 2);
    std::ifstream file(argv[1]); std::string hex; v::wire::Command prototype{};
    assert(std::getline(file, hex) && hex.size() == sizeof(prototype) * 2);
    auto* bytes = reinterpret_cast<unsigned char*>(&prototype);
    for (std::size_t i = 0; i < sizeof(prototype); ++i) {
        bytes[i] = static_cast<unsigned char>(std::stoul(hex.substr(i * 2, 2), nullptr, 16));
    }
    assert(v::wire::Valid(prototype));
    prototype.action=v::wire::Action::self_power; prototype.power_id=563795161;
    prototype.item_key[0]=prototype.item_key[1]=prototype.template_key[0]=prototype.template_key[1]=0;
    prototype.item_hint=prototype.template_hint=0;
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
        auto payload = prototype;
        if(!v::wire::ActionVerb(verb)) { payload.action=v::wire::Action::none; payload.power_id=0; payload.recipient=v::wire::Recipient::none; }
        if(v::wire::ContextVerb(verb)) {payload.context_id.back()=1;payload.context_digest.fill(2);}
        if(v::wire::ReadVerb(verb)) {payload.parent_id={};payload.parent_digest={};payload.grant={};}
        payload.host = {identity.process_id, wrong_lease ? 8U : 7U, identity.creation_filetime_utc};
        std::memcpy(payload.request.data(), &sequence, sizeof(sequence));
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
    assert(!(storage.header.capability_flags & kNativeActorCapability));
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
    assert(kNativeActorCapability==128U && (storage.header.capability_flags&kNativeActorCapability));
    assert(!(storage.header.capability_flags & (8U|16U|32U|64U)));
    assert(runtime.combat_pending && !runtime.pending && storage.header.command_read_sequence == 1);
    auto command = v::Take(); assert(command && command->lease->Current(now));
    assert(!v::Take());
    auto receipt = v::wire::Reply(command->command, command->verb, v::wire::Outcome::uncertain);
    receipt.flags = v::wire::owner_cleanup | v::wire::outbound_queued;
    receipt.entry=v::wire::Entry::entered; receipt.local_settlement=v::wire::LocalSettlement::pending;
    receipt.owner_phase = v::wire::Phase::stopping;
    std::array<char,73> diagnostic{}; strcpy_s(diagnostic.data(),diagnostic.size(),"actor:dispatch:uncertain");
    v::Complete(command, receipt, diagnostic);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_SUCCESS);
    assert(!runtime.combat_pending && storage.header.command_read_sequence == 2);
    assert(last_result().stage == static_cast<unsigned>(ClientActionResultStage::submitted_to_client));
    assert(last_result().error == ERROR_SUCCESS && last_result().consumer_thread_id == GetCurrentThreadId());
    auto response = returned(); assert(!std::memcmp(&receipt, &response, sizeof(receipt)));
    assert(std::string(last_result().detail, last_result().detail_length)
        == "actor:dispatch:uncertain");

    outer::test_ready = false;
    publish(v::wire::Verb::cancel_action);
    assert(d::DrainCommands(storage, runtime.result_signal, now) == ERROR_IO_PENDING);
    assert(!(storage.header.capability_flags & kNativeActorCapability));
    command = v::Take(); assert(command && command->verb == v::wire::Verb::cancel_action);
    receipt = v::wire::Reply(command->command, command->verb, v::wire::Outcome::pending);
    receipt.flags = v::wire::owner_cleanup; receipt.owner_phase = v::wire::Phase::stopping;
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
    ++receipt.command_digest[0];
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

    for(auto verb:{v::wire::Verb::owner_status,v::wire::Verb::stop_owner,v::wire::Verb::context_status,v::wire::Verb::stop_context,v::wire::Verb::observe_actor,v::wire::Verb::register_selectors}) {
        publish(verb);
        assert(d::DrainCommands(storage,runtime.result_signal,now)==ERROR_IO_PENDING);
        command=v::Take(); assert(command && command->command.action==v::wire::Action::none);
        receipt=v::wire::Reply(command->command,verb,v::wire::Outcome::observed);
        v::Complete(command,receipt);
        assert(d::DrainCommands(storage,runtime.result_signal,now)==ERROR_SUCCESS);
        assert(returned().verb==verb);
    }
    for(unsigned legacy=34;legacy<=42;++legacy) {
        publish(static_cast<v::wire::Verb>(legacy));
        assert(d::DrainCommands(storage,runtime.result_signal,now)==ERROR_SUCCESS);
        assert(!v::Take() && last_result().stage==static_cast<unsigned>(ClientActionResultStage::failed));
    }
    publish(v::wire::Verb::open_owner);
    assert(d::DrainCommands(storage,runtime.result_signal,now)==ERROR_SUCCESS);
    assert(last_result().error==ERROR_NOT_SUPPORTED);
    outer::test_ready=true;
    publish(v::wire::Verb::open_owner);
    assert(d::DrainCommands(storage,runtime.result_signal,now)==ERROR_IO_PENDING);
    command=v::Take(); assert(command);
    receipt=v::wire::Reply(command->command,command->verb,v::wire::Outcome::bound);
    receipt.owner_phase=v::wire::Phase::bound; receipt.flags=v::wire::owner_cleanup;
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
