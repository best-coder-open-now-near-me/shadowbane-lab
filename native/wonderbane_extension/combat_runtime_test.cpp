#include "combat_runtime.cpp"
#undef NDEBUG
#include <cassert>
#include <vector>
namespace c = wonderbane::extension::combat;
namespace m = wonderbane::extension::movement;
namespace {
m::NativeScene observed{0x10000, 0x20000, 0x30000, 0x40000, {91, 53}, 7};
m::Grant owner{9, 7, m::Owner::automation};
bool live = true, lease_live = true, stop_ok = true, native_activity = false, state_readable = true;
bool retired_in_attack = false, revoke_in_attack = false, rejected_attack = false;
bool selection_current = true, combat_target_current = true;
c::Diagnostic last_diagnostic{};
unsigned attacks = 0, stops = 0, clears = 0;
c::fence::Binding* shared_binding = nullptr;
std::vector<int> sequence;
bool Validate(void*, const m::wire::Host&, std::uint64_t) noexcept { return lease_live; }
struct Mapping {
    HANDLE mapping = nullptr, mutex = nullptr;
    c::fence::Binding* view = nullptr;
    explicit Mapping(const c::fence::Binding& binding) {
        const auto name = c::fence::Name(binding);
        mutex = CreateMutexW(nullptr, FALSE, (name + L".lock").c_str()); assert(mutex);
        mapping = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0, sizeof(binding), name.c_str());
        assert(mapping && GetLastError() != ERROR_ALREADY_EXISTS);
        view = static_cast<c::fence::Binding*>(MapViewOfFile(mapping, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(binding)));
        assert(view); *view = binding; view->state = c::fence::State::pending; shared_binding = view;
    }
    ~Mapping() { shared_binding = nullptr; UnmapViewOfFile(view); CloseHandle(mapping); CloseHandle(mutex); }
};
c::wire::Command Command(unsigned identity, c::fence::Binding& binding) {
    c::wire::Command command{};
    command.host = {GetCurrentProcessId(), 1, c::fence::Creation(GetCurrentProcess())};
    command.window = 0x50000; command.grant = m::wire::Encode(owner);
    command.request[0] = static_cast<std::uint8_t>(identity); command.request[15] = 71;
    command.revision = 1; command.local_key[0] = 91; command.local_key[1] = 53;
    command.target_key[0] = 92; command.target_key[1] = 53;
    command.store.fill(1); command.owner.fill(2); command.entry.fill(3);
    command.local_name.fill(4); command.server.fill(5); command.target_name.fill(6);
    assert(c::wire::Hash(&command.grant.token, sizeof(command.grant.token), command.operation));
    binding = {}; binding.client_pid = binding.producer_pid = GetCurrentProcessId();
    binding.client_creation = binding.producer_creation = command.host.creation;
    binding.producer_generation = 1; binding.movement_generation = owner.generation;
    binding.scene = owner.scene; binding.revision = 1;
    std::memcpy(binding.request, command.request.data(), 16);
    std::memcpy(binding.store, command.store.data(), 32); std::memcpy(binding.owner, command.owner.data(), 32);
    std::memcpy(binding.entry, command.entry.data(), 32); std::memcpy(binding.operation, command.operation.data(), 32);
    std::memcpy(binding.local_key, command.local_key, 8); std::memcpy(binding.target_key, command.target_key, 8);
    std::memcpy(binding.target_name, command.target_name.data(), 32);
    assert(c::wire::Hash(&binding, sizeof(binding), command.binding_digest));
    return command;
}
c::wire::Receipt Execute(c::wire::Verb verb, const c::wire::Command& command) {
    auto pending = std::make_shared<c::QueuedCommand>(); pending->command = command; pending->verb = verb;
    pending->deadline = GetTickCount64() + 10000;
    pending->lease = std::make_shared<m::CommandLease>(); pending->lease->host = command.host;
    pending->lease->process = OpenProcess(SYNCHRONIZE, FALSE, GetCurrentProcessId()); assert(pending->lease->process);
    pending->lease->validate = Validate;
    assert(c::Queue(pending));
    c::runtime.Tick(reinterpret_cast<void*>(observed.window), reinterpret_cast<HWND>(command.window));
    assert(pending->state.load() == 2); auto result = pending->receipt;
    last_diagnostic = pending->diagnostic;
    assert(c::wire::Valid(result)); c::Release(pending); return result;
}
}
namespace wonderbane::extension::movement {
bool VerifyNativeMovementImage(std::uintptr_t& base) noexcept { base = 0x400000; return true; }
bool NativeMovementLifetimeCurrent(const NativeScene& scene) noexcept { return live && scene.epoch == observed.epoch; }
bool ReadNativeMovementLifetime(NativeScene& scene) noexcept { scene = observed; return live; }
bool NativeOwnerActionCurrent(const NativeScene& scene, const Grant& grant, const wire::Host&) noexcept {
    return NativeMovementLifetimeCurrent(scene) && grant == owner && lease_live;
}
bool NativeOwnerStopCurrent(const NativeScene& scene, const Grant& grant) noexcept {
    return NativeMovementLifetimeCurrent(scene) && grant == owner;
}
Result BeginNativeOwnerAction(const NativeScene& scene, const Grant& grant, const wire::Host& host) noexcept {
    if (!NativeOwnerActionCurrent(scene, grant, host)) { return Result::stale; }
    sequence.push_back(1); native_activity = true; return Result::accepted;
}
Result PauseNativeOwnerAction(const NativeScene& scene, const Grant& grant) noexcept {
    if (!NativeOwnerStopCurrent(scene, grant)) { return Result::stale; }
    sequence.push_back(2);
    if (native_activity && !combat_owner_stop.load()(scene, grant, StopReason::release)) { return Result::stop_failed; }
    native_activity = false; return Result::accepted;
}
}
namespace wonderbane::extension::combat::submission {
bool Start(std::uintptr_t) noexcept { return true; }
bool Ready() noexcept { return true; }
}
namespace wonderbane::extension::combat {
bool NativeTarget::Bind(HWND) noexcept { base_ = 0x400000; return true; }
bool NativeTarget::Current() noexcept { return live; }
bool NativeTarget::CombatTargetCurrent() const noexcept { return live && combat_target_current; }
// The target fixture separately exercises actual native pointers, ownership and ABI.
NativeTarget::Result NativeTarget::Attack(const m::NativeScene& scene, const wire::Command&,
    Admission current, Admission enter, Admission append, void* context) noexcept {
    ++attacks; sequence.push_back(3);
    assert(current(context) && enter(context) && append(context));
    if (revoke_in_attack) { shared_binding->state = fence::State::entered_revoked; }
    if (retired_in_attack) { combat_owner_retire.load()(scene.epoch); live = false; }
    if (rejected_attack) { return {wire::Outcome::native_rejected, false,
        {Stage::dispatch, wire::Outcome::native_rejected, true}}; }
    return {wire::Outcome::client_outbound_queued, true,
        {Stage::dispatch, wire::Outcome::client_outbound_queued, true, true, true, true}};
}
bool NativeTarget::Cancel(const m::NativeScene&, Admission current, void* context, State& state) noexcept {
    ++stops; if (!current(context) || !stop_ok) { return false; }
    state = {1, 1, false}; return true;
}
bool NativeTarget::ReadState(const m::NativeScene&, State& state) const noexcept {
    state = {2, 4, true}; return live && state_readable;
}
bool NativeTarget::Clear() noexcept { ++clears; return true; }
}
int main() {
    owner.token.worker[0] = 'w'; owner.token.operation[0] = 'o';
    assert(c::Start({GetCurrentProcessId(), c::fence::Creation(GetCurrentProcess())}));
    c::runtime.Tick(reinterpret_cast<void*>(observed.window), reinterpret_cast<HWND>(0x50000));
    assert(c::Ready());
    using V = c::wire::Verb; using O = c::wire::Outcome;
    c::fence::Binding binding{};
    {
        const auto command = Command(1, binding); Mapping mapping(binding);
        auto receipt = Execute(V::start, command);
        assert(receipt.outcome == O::client_outbound_queued && attacks == 1 && stops == 0);
        assert((sequence == std::vector<int>{1, 3}));
        assert(mapping.view->state == c::fence::State::entered);
        receipt = Execute(V::start, command); assert(attacks == 1 && receipt.flags & c::wire::outbound_queued);
        mapping.view->state = c::fence::State::entered_revoked;
        stop_ok = false; receipt = Execute(V::cancel, command);
        assert(receipt.outcome == O::pending && receipt.flags & c::wire::cleanup_required && c::runtime.active);
        stop_ok = true; receipt = Execute(V::cancel, command);
        assert(receipt.outcome == O::local_cancelled && !c::runtime.active && !native_activity);
        assert(receipt.flags & c::wire::outbound_queued);
        assert(last_diagnostic.stage == c::Stage::dispatch && last_diagnostic.appended);
        receipt = Execute(V::start, command); assert(receipt.outcome == O::local_cancelled && attacks == 1);
    }
    {
        const auto command = Command(2, binding); Mapping mapping(binding);
        mapping.view->state = c::fence::State::revoked;
        auto receipt = Execute(V::start, command);
        assert(receipt.outcome == O::local_cancelled && attacks == 1 && !c::runtime.active);
    }
    {
        const auto command = Command(3, binding); Mapping mapping(binding);
        retired_in_attack = true;
        auto receipt = Execute(V::start, command);
        assert(receipt.phase == c::wire::Phase::retired && !(receipt.flags & c::wire::cleanup_required)
            && (receipt.flags & c::wire::outbound_queued));
        assert(last_diagnostic.stage == c::Stage::dispatch && last_diagnostic.appended);
        live = true; retired_in_attack = false;
        c::runtime.Tick(reinterpret_cast<void*>(observed.window), reinterpret_cast<HWND>(0x50000));
        assert(!c::runtime.active);
    }
    {
        const auto command = Command(4, binding); Mapping mapping(binding);
        revoke_in_attack = true;
        auto receipt = Execute(V::start, command);
        assert(receipt.outcome == O::local_cancelled && receipt.flags & c::wire::outbound_queued);
        revoke_in_attack = false;
    }
    {
        const auto command = Command(5, binding); Mapping mapping(binding);
        const auto before = attacks, stopped = stops; stop_ok = false;
        auto receipt = Execute(V::start, command);
        assert(receipt.outcome == O::client_outbound_queued && attacks == before + 1
            && stops == stopped && native_activity);
        assert(last_diagnostic.stage == c::Stage::dispatch && last_diagnostic.appended);
        assert(mapping.view->state == c::fence::State::entered);
        // Stop failure cannot create a startup pause, but an explicit cancel
        // retains the exact owner and cleanup obligation until it succeeds.
        receipt = Execute(V::cancel, command);
        assert(receipt.outcome == O::pending && c::runtime.active && native_activity);
        stop_ok = true;
        receipt = Execute(V::cancel, command);
        assert(receipt.outcome == O::local_cancelled && !native_activity);
        assert(last_diagnostic.stage == c::Stage::dispatch && last_diagnostic.appended);
    }
    {
        const auto command = Command(6, binding); Mapping mapping(binding);
        assert(Execute(V::start, command).outcome == O::client_outbound_queued);
        auto replacement = owner; ++replacement.generation;
        const auto before = stops;
        assert(!c::Runtime::Stop(observed, replacement, m::StopReason::takeover) && stops == before);
        lease_live = false;
        c::runtime.Tick(reinterpret_cast<void*>(observed.window), reinterpret_cast<HWND>(0x50000));
        assert(!c::runtime.active && !native_activity);
        lease_live = true;
        assert(Execute(V::status, command).outcome == O::local_cancelled);
    }
    {
        const auto command = Command(7, binding); Mapping mapping(binding);
        c::runtime.ready.store(false);
        const auto before = attacks;
        assert(Execute(V::start, command).outcome == O::stale && attacks == before);
        c::runtime.ready.store(true);
        assert(Execute(V::cancel, command).outcome == O::local_cancelled);
    }
    {
        const auto command = Command(8, binding); Mapping mapping(binding);
        assert(Execute(V::start, command).outcome == O::client_outbound_queued);
        state_readable = false; stop_ok = false;
        auto receipt = Execute(V::status, command);
        assert(receipt.outcome == O::pending && c::runtime.active && native_activity);
        state_readable = stop_ok = true;
        receipt = Execute(V::status, command);
        assert(receipt.outcome == O::local_cancelled && !c::runtime.active);
    }
    {
        const auto command = Command(9, binding); Mapping mapping(binding);
        rejected_attack = true;
        auto receipt = Execute(V::start, command);
        assert(receipt.outcome == O::local_cancelled && receipt.flags == c::wire::local_cancelled);
        assert(receipt.mode == 1 && receipt.action_state == 1 && !receipt.combat_target_present);
        assert(last_diagnostic.stage == c::Stage::dispatch
            && last_diagnostic.outcome == O::native_rejected && last_diagnostic.dispatched
            && !last_diagnostic.native_entered && !last_diagnostic.appended);
        receipt = Execute(V::status, command);
        assert(last_diagnostic.outcome == O::native_rejected && receipt.outcome == O::local_cancelled);
        receipt = Execute(V::cancel, command);
        assert(last_diagnostic.outcome == O::native_rejected && receipt.flags == c::wire::local_cancelled);
        auto forged = command; ++forged.revision;
        receipt = Execute(V::status, forged);
        assert(receipt.outcome == O::invalid && last_diagnostic.stage == c::Stage::none);
        rejected_attack = false;
    }
    {
        const auto command = Command(10, binding); Mapping mapping(binding);
        assert(Execute(V::start, command).outcome == O::client_outbound_queued);
        assert(last_diagnostic.outcome == O::client_outbound_queued && last_diagnostic.native_entered);
        const auto before = stops;
        selection_current = false;
        auto receipt = Execute(V::status, command);
        assert(c::runtime.active && native_activity && stops == before);
        assert(receipt.flags & c::wire::outbound_queued);
        combat_target_current = false;
        receipt = Execute(V::status, command);
        assert(receipt.outcome == O::local_cancelled && !c::runtime.active && stops > before);
        selection_current = combat_target_current = true;
    }

}
