#include "combat_runtime.h"
#include "combat_controller.h"
#include "combat_native.h"
#include "combat_command_queue.h"
#include "movement_runtime.h"
#include "movement_native_image.h"
#include "native_owner_services.h"

namespace wonderbane::extension::combat {
namespace {
using O = wire::Outcome;
class Runtime final : public Invoker {
public:
    Controller controller;
    NativeTarget target;
    ProcessIdentity process{};
    std::uintptr_t base = 0;
    HWND window = nullptr;
    std::atomic<bool> ready{false};
    bool bind_attempted = false, updating = false, active = false, starting = false;
    bool priming = false, stopping = false, retired = false, entered = false;
    bool queued = false;
    std::atomic<bool> cancelled{false};
    movement::NativeScene scene{};
    movement::Grant grant{};
    wire::Command command{};
    fence::Binding binding{};
    fence::Ticket ticket;
    std::shared_ptr<movement::CommandLease> lease;
    std::shared_ptr<QueuedCommand> executing;

    wire::Receipt Receipt(O outcome, wire::Phase phase, bool cleanup,
                          const NativeTarget::State& state = {}) const noexcept {
        auto result = wire::Reply(command, outcome);
        result.phase = phase;
        result.flags = (cleanup ? wire::cleanup_required : 0U)
            | (queued ? wire::outbound_queued : 0U)
            | (outcome == O::local_cancelled ? wire::local_cancelled : 0U);
        result.mode = state.mode; result.action_state = state.action;
        result.combat_target_present = state.target;
        return result;
    }
    static bool Current(void* context) noexcept {
        auto& self = *static_cast<Runtime*>(context);
        if (!self.active || self.retired || self.cancelled.load(std::memory_order_acquire)
            || !self.lease || !self.lease->Current(GetTickCount64())
            || (self.starting && (!self.executing || GetTickCount64() > self.executing->deadline))
            || !submission::Ready()) { return false; }
        fence::State state{};
        if (self.ticket.Inspect(state) != fence::Result::not_pending
            || state != (self.entered ? fence::State::entered : fence::State::pending)) { return false; }
        return movement::NativeOwnerActionCurrent(self.scene, self.grant, self.command.host)
            && !self.retired && !self.cancelled.load(std::memory_order_acquire);
    }
    static bool Enter(void* context) noexcept {
        auto& self = *static_cast<Runtime*>(context);
        if (!Current(context) || self.entered) { return false; }
        self.entered = self.ticket.TryEnter(self.binding) == fence::Result::admitted;
        return self.entered;
    }
    static bool AppendCurrent(void* context) noexcept {
        const auto& self = *static_cast<Runtime*>(context);
        // D0 has already won full entry. This cannot take any extension lock.
        return self.active && self.entered && !self.retired
            && !self.cancelled.load(std::memory_order_acquire);
    }
    struct StopContext { const movement::NativeScene* scene; const movement::Grant* grant; };
    static bool StopCurrent(void* context) noexcept {
        const auto& stop = *static_cast<StopContext*>(context);
        return movement::NativeOwnerStopCurrent(*stop.scene, *stop.grant);
    }
    static bool Stop(const movement::NativeScene& scene, const movement::Grant& grant,
                     movement::StopReason reason) noexcept;
    static void Retire(std::uint64_t epoch) noexcept;
    static void Update(void* root, HWND window) noexcept;

    bool StopOwned(const movement::NativeScene& expected, const movement::Grant& owner,
                   movement::StopReason reason) noexcept {
        if (!target.Available() || stopping || !movement::NativeOwnerStopCurrent(expected, owner)) { return false; }
        if (active && (grant != owner || scene.epoch != expected.epoch)) { return false; }
        const bool baseline = priming && reason == movement::StopReason::release;
        if (active && !baseline) { cancelled.store(true, std::memory_order_release); }
        stopping = true;
        StopContext context{&expected, &owner}; NativeTarget::State state{};
        bool stopped = target.Cancel(expected, StopCurrent, &context, state);
        if (stopped && active && !baseline) {
            stopped = target.Clear();
            if (stopped) {
                ticket.Close(); lease.reset(); active = false;
                (void)controller.Update(Receipt(O::local_cancelled, wire::Phase::idle, false, state));
            }
        }
        if (!target.Available()) { ready.store(false, std::memory_order_release); }
        stopping = false;
        return stopped;
    }
    wire::Receipt Start(const wire::Command& input) noexcept override {
        if (active) { return wire::Reply(input, O::unavailable); }
        if (!executing || !Ready()) {
            auto result = wire::Reply(input, O::local_cancelled);
            result.flags = wire::local_cancelled; return result;
        }
        command = input; queued = entered = retired = false;
        cancelled.store(false, std::memory_order_release);
        if (!movement::wire::Decode(command.grant, grant)
            || !wire::BindingFor(command, process.process_id, process.creation_filetime_utc, binding)) {
            auto result = wire::Reply(command, O::local_cancelled); result.flags = wire::local_cancelled; return result;
        }
        try {
            if (!ticket.Open(binding)) {
                auto result = wire::Reply(command, O::local_cancelled); result.flags = wire::local_cancelled; return result;
            }
        } catch (...) {
            ticket.Close(); auto result = wire::Reply(command, O::local_cancelled);
            result.flags = wire::local_cancelled; return result;
        }
        lease = executing->lease; active = starting = true;
        if (!Current(this)) {
            ticket.Close(); lease.reset(); active = starting = false;
            return Receipt(O::local_cancelled, wire::Phase::idle, false);
        }
        if (movement::BeginNativeOwnerAction(scene, grant, command.host) != movement::Result::accepted) {
            ticket.Close(); lease.reset(); active = starting = false;
            return Receipt(O::local_cancelled, wire::Phase::idle, false);
        }
        // Establish native combat/movement cleanup independently of host preflight.
        priming = true;
        const auto paused = movement::PauseNativeOwnerAction(scene, grant);
        priming = false;
        NativeTarget::Result result{O::stale};
        if (paused == movement::Result::accepted && Current(this)
            && movement::BeginNativeOwnerAction(scene, grant, command.host) == movement::Result::accepted) {
            result = target.Attack(scene, command, Current, Enter, AppendCurrent, this);
            queued = result.queued;
        }
        starting = false;
        if (retired) { return Receipt(O::observed, wire::Phase::retired, false); }
        if (result.outcome == O::client_outbound_queued && Current(this)) {
            NativeTarget::State state{};
            if (target.ReadState(scene, state)) { return Receipt(result.outcome, wire::Phase::engaged, true, state); }
        }
        cancelled.store(true, std::memory_order_release);
        return Cancel(command);
    }
    wire::Receipt Cancel(const wire::Command& input) noexcept override {
        if (std::memcmp(&input, &command, sizeof(command))) { return wire::Reply(input, O::invalid); }
        if (retired) { return Receipt(O::observed, wire::Phase::retired, false); }
        cancelled.store(true, std::memory_order_release);
        if (active && movement::PauseNativeOwnerAction(scene, grant) == movement::Result::accepted && !active) {
            NativeTarget::State state{};
            // StopOwned already verified this state before releasing its references.
            state.mode = state.action = 1;
            return Receipt(O::local_cancelled, wire::Phase::idle, false, state);
        }
        return Receipt(O::pending, wire::Phase::cancelling, true);
    }
    void Tick(void* root, HWND owner_window) noexcept {
        if (updating) { return; }
        updating = true;
        window = owner_window;
        if (!bind_attempted) {
            bind_attempted = true;
            ready.store(target.Bind(window) && submission::Ready(), std::memory_order_release);
        }
        if (active && retired) {
            if (!target.Clear()) { ready.store(false, std::memory_order_release); }
            ticket.Close(); lease.reset(); active = false;
        }
        movement::NativeScene fresh{};
        const bool valid_scene = movement::ReadNativeMovementLifetime(fresh)
            && fresh.window == reinterpret_cast<std::uintptr_t>(root)
            && movement::NativeMovementLifetimeCurrent(fresh);
        if (active && !retired) {
            NativeTarget::State state{};
            const bool observed_state = target.ReadState(scene, state);
            const bool done = observed_state && state.mode == 1 && state.action == 1 && !state.target;
            if (!observed_state || !Current(this) || !target.Current() || !target.CombatTargetCurrent() || done) {
                (void)controller.Update(Cancel(command));
            }
        }
        if (auto pending = Take()) {
            executing = pending;
            fence::Binding expected{};
            const bool valid = wire::BindingFor(pending->command, process.process_id,
                process.creation_filetime_utc, expected)
                && pending->command.window == reinterpret_cast<std::uintptr_t>(window);
            const bool live = valid_scene && Ready() && pending->lease
                && pending->lease->Current(GetTickCount64()) && GetTickCount64() <= pending->deadline;
            if (!active) { scene = fresh; }
            Complete(pending, controller.Execute(pending->verb, pending->command, valid, live, *this));
            executing.reset();
        }
        updating = false;
    }
};
Runtime runtime;
bool Runtime::Stop(const movement::NativeScene& scene, const movement::Grant& grant,
                   movement::StopReason reason) noexcept { return runtime.StopOwned(scene, grant, reason); }
void Runtime::Retire(std::uint64_t epoch) noexcept {
    if (runtime.active && runtime.scene.epoch == epoch) {
        runtime.retired = true; runtime.cancelled.store(true, std::memory_order_release);
    }
    runtime.controller.Retire(epoch);
}
void Runtime::Update(void* root, HWND window) noexcept { runtime.Tick(root, window); }
}
bool Ready() noexcept {
    return runtime.ready.load(std::memory_order_acquire) && submission::Ready()
        && combat_owner_service.load(std::memory_order_acquire) == &Runtime::Update
        && combat_owner_stop.load(std::memory_order_acquire) == &Runtime::Stop
        && combat_owner_retire.load(std::memory_order_acquire) == &Runtime::Retire;
}
bool Start(const ProcessIdentity& process) noexcept {
    if (process.process_id != GetCurrentProcessId()
        || process.creation_filetime_utc != fence::Creation(GetCurrentProcess())
        || !movement::VerifyNativeMovementImage(runtime.base) || !submission::Start(runtime.base)) { return false; }
    runtime.process = process;
    combat_owner_stop.store(&Runtime::Stop, std::memory_order_release);
    combat_owner_retire.store(&Runtime::Retire, std::memory_order_release);
    combat_owner_ready.store(&Ready, std::memory_order_release);
    combat_owner_service.store(&Runtime::Update, std::memory_order_release);
    return true;
}
}
