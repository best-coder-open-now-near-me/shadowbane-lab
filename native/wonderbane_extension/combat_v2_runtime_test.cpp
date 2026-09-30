#include "combat_v2_runtime.cpp"
#undef NDEBUG
#include <cassert>
#include <vector>
namespace c = wonderbane::extension::combat::v2;
namespace outer = wonderbane::extension::combat;
namespace f=c::wire::fence;
namespace m = wonderbane::extension::movement;
namespace {
m::NativeScene observed{0x10000, 0x20000, 0x30000, 0x40000, {91, 53}, 7};
m::Grant owner{9, 7, m::Owner::automation};
bool live = true, lease_live = true, stop_ok = true, native_activity = false, state_readable = true;
bool retired_in_attack = false, revoke_in_attack = false, defer_bind = false;
bool busy_action=false, target_ok=true, stop_during_submit=false;
std::array<char,73> last_diagnostic{};
unsigned attacks = 0, stops = 0, clears = 0, prepares=0;
f::Binding* shared_binding = nullptr;
std::vector<int> sequence;
bool Validate(void*, const m::wire::Host&, std::uint64_t) noexcept { return lease_live; }
struct Mapping {
    HANDLE mapping = nullptr, mutex = nullptr;
    f::Binding* view = nullptr;
    explicit Mapping(const f::Binding& binding) {
        const auto name = f::Name(binding);
        mutex = CreateMutexW(nullptr, FALSE, (name + L".lock").c_str()); assert(mutex);
        mapping = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0, sizeof(binding), name.c_str());
        assert(mapping && GetLastError() != ERROR_ALREADY_EXISTS);
        view = static_cast<f::Binding*>(MapViewOfFile(mapping, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(binding)));
        assert(view); *view = binding; view->state = f::State::pending; shared_binding = view;
    }
    ~Mapping() { shared_binding = nullptr; UnmapViewOfFile(view); CloseHandle(mapping); CloseHandle(mutex); }
};
c::wire::Command Command(unsigned identity, f::Binding& binding) {
    c::wire::Command command{};
    command.host = {GetCurrentProcessId(), 1, f::Creation(GetCurrentProcess())};
    command.window = 0x50000; command.grant = m::wire::Encode(owner);
    command.engagement[15]=static_cast<std::uint8_t>(identity); command.request[15]=1;
    command.action=c::wire::Action::attack; command.authority=c::wire::Authority::manual_player;
    command.actor_hint=0x30000; command.target_hint=0x60000;
    command.revision = 1; command.local_key[0] = 91; command.local_key[1] = 53;
    command.target_key[0] = 92; command.target_key[1] = 53;
    command.store.fill(1); command.owner.fill(2); command.entry.fill(3);
    command.local_name.fill(4); command.server.fill(5); command.target_name.fill(6);
    assert(c::wire::Hash(&command.grant.token, sizeof(command.grant.token), command.operation));
    binding = {}; binding.client_pid = binding.producer_pid = GetCurrentProcessId();
    binding.client_creation = binding.producer_creation = command.host.creation;
    binding.producer_generation = 1; binding.movement_generation = owner.generation;
    binding.scene = owner.scene; binding.revision = 1;
    std::memcpy(binding.engagement, command.engagement.data(), 16);
    binding.authority=1; binding.actor_hint=command.actor_hint; binding.target_hint=command.target_hint;
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
    assert(c::wire::Correlated(command,verb,result)); c::Release(pending); return result;
}
}
namespace wonderbane::extension::movement {
bool VerifyNativeMovementImage(std::uintptr_t& base) noexcept { base=0x400000; return true; }
bool NativeMovementLifetimeCurrent(const NativeScene& scene) noexcept { return live && scene.epoch==observed.epoch; }
bool ReadNativeMovementLifetime(NativeScene& scene) noexcept { scene=observed; return live; }
bool NativeOwnerActionCurrent(const NativeScene& scene,const Grant& grant,const wire::Host&) noexcept {
    return NativeMovementLifetimeCurrent(scene) && grant==owner && lease_live;
}
bool NativeOwnerStopCurrent(const NativeScene& scene,const Grant& grant) noexcept {
    return NativeMovementLifetimeCurrent(scene) && grant==owner;
}
Result BeginNativeOwnerAction(const NativeScene& scene,const Grant& grant,const wire::Host& host) noexcept {
    if(!NativeOwnerActionCurrent(scene,grant,host)) { return Result::stale; }
    sequence.push_back(1); native_activity=true; return Result::accepted;
}
Result PauseNativeOwnerAction(const NativeScene& scene,const Grant& grant) noexcept {
    if(!NativeOwnerStopCurrent(scene,grant)) { return Result::stale; }
    sequence.push_back(2);
    if(native_activity && !combat_owner_stop.load()(scene,grant,StopReason::release)) { return Result::stop_failed; }
    native_activity=false; return Result::accepted;
}
}
namespace wonderbane::extension::combat::submission {
bool Start(std::uintptr_t) noexcept { return true; }
bool Ready() noexcept { return true; }
}
namespace wonderbane::extension::combat::power {
bool Start(std::uintptr_t) noexcept { return true; }
bool Ready() noexcept { return true; }
}
namespace wonderbane::extension::combat::v2 {
bool NativeTarget::Bind(HWND) noexcept { base_=0x400000; return true; }
bool NativeTarget::Current() noexcept { return live && target_ok; }
Operation NativeTarget::Prepare(const m::NativeScene& scene,const wire::Command& command,
    Admission current,Admission append,void* context) noexcept {
    ++prepares; assert(current(context));
    scene_=scene; command_=command; current_=current; append_current_=append; context_=context;
    actor_=reinterpret_cast<void*>(scene.actor); target_=reinterpret_cast<void*>(0x60000);
    if(defer_bind) { return {wire::Outcome::deferred}; }
    return {wire::Outcome::bound};
}
Operation NativeTarget::Execute(const wire::Command& input) noexcept {
    assert(current_(context_));
    if(busy_action) { return {wire::Outcome::deferred,wire::Entry::never_entered}; }
    ++attacks; sequence.push_back(3); assert(append_current_(context_));
    if(revoke_in_attack) { shared_binding->state=f::State::entered_revoked; }
    if(retired_in_attack) { combat_owner_retire.load()(scene_.epoch); live=false; }
    if(stop_during_submit) {
        auto control=input; control.action=wire::Action::none; control.power_id=0;
        const auto stopping=runtime.controller.Execute(wire::Verb::stop,control,true,true,true,runtime);
        assert(stopping.phase==wire::Phase::stopping && !append_current_(context_));
    }
    return {wire::Outcome::client_outbound_queued,wire::Entry::entered,wire::outbound_queued};
}
bool NativeTarget::Cancel(const m::NativeScene&,Admission current,void* context,Observation& state) noexcept {
    ++stops; if(!current(context) || !stop_ok) { return false; }
    state={1,1,0,0}; return true;
}
bool NativeTarget::ReadState(const m::NativeScene&,Observation& state) const noexcept {
    state={2,busy_action?4U:1U,busy_action?1U:0U,0}; return live && state_readable;
}
bool NativeTarget::Clear() noexcept { ++clears; actor_=target_=nullptr; return true; }
}
int main() {
    owner.token.worker[0]='w'; owner.token.operation[0]='o';
    assert(outer::Start({GetCurrentProcessId(),f::Creation(GetCurrentProcess())}));
    c::runtime.Tick(reinterpret_cast<void*>(observed.window),reinterpret_cast<HWND>(0x50000));
    assert(outer::Ready());
    using V=c::wire::Verb; using O=c::wire::Outcome; using P=c::wire::Phase; using E=c::wire::Entry;
    f::Binding binding{};
    auto control=[](c::wire::Command command) { command.action=c::wire::Action::none; command.power_id=0; return command; };
    {
        auto command=Command(1,binding); Mapping mapping(binding);
        auto result=Execute(V::bind,control(command));
        assert(result.outcome==O::bound && prepares==1 && !attacks && !stops && native_activity);
        result=Execute(V::submit,command);
        assert(result.entry==E::entered && result.flags&c::wire::outbound_queued && attacks==1);
        assert((sequence==std::vector<int>{1,3}));
        (void)Execute(V::submit,command); assert(attacks==1);
        command.request[15]=2; command.action=c::wire::Action::cast; command.power_id=428918601;
        busy_action=true; result=Execute(V::submit,command);
        assert(result.outcome==O::deferred && result.entry==E::never_entered && !stops && c::runtime.active);
        busy_action=false; command.request[15]=3;
        result=Execute(V::submit,command); assert(result.entry==E::entered && attacks==2 && prepares==1);
        mapping.view->state=f::State::entered_revoked; stop_ok=false;
        result=Execute(V::stop,control(command));
        assert(result.phase==P::stopping && c::runtime.active && native_activity);
        c::runtime.ready=false; stop_ok=true;
        result=Execute(V::stop,control(command));
        assert(result.closure==c::wire::Closure::native_stopped && !c::runtime.active && !native_activity);
        result=Execute(V::action_status,command);
        assert(result.flags&c::wire::outbound_queued && result.phase==P::closed);
        c::runtime.ready=true;
    }
    {
        auto command=Command(2,binding); Mapping mapping(binding); defer_bind=true;
        const auto before=stops;
        auto result=Execute(V::bind,control(command));
        assert(result.outcome==O::deferred && result.closure==c::wire::Closure::never_bound && stops==before);
        assert(!native_activity && !c::runtime.active && mapping.view->state==f::State::pending);
        defer_bind=false;
        result=Execute(V::submit,command); assert(result.outcome==O::engagement_closed);
    }
    {
        auto command=Command(3,binding); Mapping mapping(binding); stop_during_submit=true;
        auto result=Execute(V::submit,command);
        assert(result.phase==P::closed && result.flags&c::wire::outbound_queued && !c::runtime.active);
        stop_during_submit=false;
    }
    {
        auto command=Command(4,binding); Mapping mapping(binding); retired_in_attack=true;
        auto result=Execute(V::submit,command);
        assert(result.phase==P::retired && result.flags&c::wire::outbound_queued && !(result.flags&c::wire::cleanup_required));
        live=true; retired_in_attack=false; native_activity=false;
        c::runtime.Tick(reinterpret_cast<void*>(observed.window),reinterpret_cast<HWND>(command.window));
        assert(!c::runtime.active);
    }
    {
        auto command=Command(5,binding); Mapping mapping(binding); revoke_in_attack=true;
        auto result=Execute(V::submit,command);
        assert(result.phase==P::closed && result.flags&c::wire::outbound_queued && !c::runtime.active);
        revoke_in_attack=false;
    }
    {
        auto command=Command(6,binding); Mapping mapping(binding);
        (void)Execute(V::submit,command); stop_ok=false; state_readable=false;
        c::runtime.Tick(reinterpret_cast<void*>(observed.window),reinterpret_cast<HWND>(command.window));
        assert(c::runtime.active && c::runtime.controller.Busy());
        state_readable=true; stop_ok=true;
        auto result=Execute(V::stop,control(command)); assert(result.closure==c::wire::Closure::native_stopped);
    }
}
