#include "combat_runtime.h"
#include "combat_v2_native.h"
#include "combat_v2_command_queue.h"
#include "movement_runtime.h"
#include "movement_native_image.h"
#include "native_owner_services.h"

namespace wonderbane::extension::combat::v2 {
namespace {
using O=wire::Outcome;
using P=wire::Phase;
using C=wire::Closure;
class Runtime final:public Invoker {
public:
    Controller controller;
    NativeTarget target;
    ProcessIdentity process{};
    std::uintptr_t base{};
    HWND window{};
    std::atomic<bool> ready{false},cancelled{false};
    bool bind_attempted=false,updating=false,active=false,preparing=false;
    bool stopping=false,retired=false,admitted=false,dispatching=false;
    movement::NativeScene scene{};
    movement::Grant grant{};
    wire::Command command{};
    wire::fence::Binding binding{};
    wire::fence::Ticket ticket;
    std::shared_ptr<movement::CommandLease> lease;
    std::shared_ptr<QueuedCommand> executing;

    State StateNow(P phase=P::bound) const noexcept {
        if(retired) { return {P::retired,C::scene_retired}; }
        NativeTarget::Observation observed{};
        if(!target.ReadState(scene,observed)) { return {P::blocked}; }
        return {phase,C::none,observed.mode,observed.action,observed.target?1U:0U};
    }
    static bool Current(void* context) noexcept {
        auto& self=*static_cast<Runtime*>(context);
        if((!self.active && !self.preparing) || self.retired || self.cancelled.load(std::memory_order_acquire)
            || !self.lease || !self.lease->Current(GetTickCount64())
            || ((self.preparing || self.dispatching) && (!self.executing || GetTickCount64()>self.executing->deadline))
            || !submission::Ready() || !power::Ready()) { return false; }
        wire::fence::State state{};
        if(self.ticket.Inspect(state)!=wire::fence::Result::not_pending
            || state!=(self.admitted?wire::fence::State::entered:wire::fence::State::pending)) { return false; }
        return movement::NativeOwnerActionCurrent(self.scene,self.grant,self.command.host)
            && !self.retired && !self.cancelled.load(std::memory_order_acquire);
    }
    static bool AppendCurrent(void* context) noexcept {
        const auto& self=*static_cast<Runtime*>(context);
        // Queue-lock boundary: no mutexes, callbacks, allocations or ledger access.
        return self.active && self.admitted && self.dispatching && !self.retired
            && !self.cancelled.load(std::memory_order_acquire);
    }
    void RevokeAdmission(const wire::Command& input) noexcept override {
        if(wire::SameEngagement(input,command)) { cancelled.store(true,std::memory_order_release); }
    }
    struct StopContext { const movement::NativeScene* scene; const movement::Grant* grant; };
    static bool StopCurrent(void* context) noexcept {
        const auto& stop=*static_cast<StopContext*>(context);
        return movement::NativeOwnerStopCurrent(*stop.scene,*stop.grant);
    }
    static bool StopOwner(const movement::NativeScene&,const movement::Grant&,movement::StopReason) noexcept;
    static void Retire(std::uint64_t) noexcept;
    static void Update(void*,HWND) noexcept;

    bool StopOwned(const movement::NativeScene& expected,const movement::Grant& owner) noexcept {
        if(stopping || !target.Available() || !movement::NativeOwnerStopCurrent(expected,owner)
            || (active && (owner!=grant || expected.epoch!=scene.epoch))) { return false; }
        if(active) { cancelled.store(true,std::memory_order_release); }
        stopping=true;
        StopContext context{&expected,&owner}; NativeTarget::Observation observed{};
        bool stopped=target.Cancel(expected,StopCurrent,&context,observed);
        if(stopped && active) {
            stopped=target.Clear();
            if(stopped) {
                ticket.Close(); lease.reset(); active=false;
                (void)controller.Update(command,{P::closed,C::native_stopped,observed.mode,observed.action,0});
            }
        }
        if(!target.Available()) { ready.store(false,std::memory_order_release); }
        stopping=false; return stopped;
    }
    Operation Bind(const wire::Command& input) noexcept override {
        Operation result{O::unavailable};
        if(active || preparing || !executing || !combat::Ready()) { return result; }
        command=input; admitted=retired=false; cancelled.store(false,std::memory_order_release);
        if(!movement::wire::Decode(command.grant,grant)
            || !wire::BindingFor(command,process.process_id,process.creation_filetime_utc,binding)) {
            result.outcome=O::invalid; return result;
        }
        try { if(!ticket.Open(binding)) { return result; } }
        catch(...) { ticket.Close(); return result; }
        lease=executing->lease; preparing=true;
        if(Current(this)) { result=target.Prepare(scene,command,Current,AppendCurrent,this); }
        if(result.outcome==O::bound && Current(this)) {
            admitted=ticket.TryAdmit(binding,false)==wire::fence::Result::admitted;
            if(admitted && Current(this)) {
                const auto begin=movement::BeginNativeOwnerAction(scene,grant,command.host);
                if(begin==movement::Result::accepted) {
                    active=true; preparing=false;
                    result.state=StateNow();
                    if(!Current(this) || !target.Current()) { result.state.phase=P::blocked; }
                    return result;
                }
                result.outcome=O::stale;
                (void)std::snprintf(result.detail.data(),result.detail.size(),"combat_v2:owner_begin:m%u",static_cast<unsigned>(begin));
            } else { result.outcome=O::stale; }
        }
        preparing=false;
        if(result.outcome==O::bound) { result.outcome=O::stale; }
        if(!target.Clear()) { ready.store(false,std::memory_order_release); }
        ticket.Close(); lease.reset(); result.state={};
        return result;
    }
    Operation Submit(const wire::Command& input) noexcept override {
        Operation result{O::stale,wire::Entry::never_entered};
        if(!active || !wire::SameEngagement(input,command)) { return result; }
        result.state=StateNow();
        dispatching=true;
        if(Current(this) && target.Current()
            && ticket.TryAdmit(binding,true)==wire::fence::Result::admitted && Current(this)) {
            result=target.Execute(input);
        }
        dispatching=false;
        result.state=StateNow(cancelled.load(std::memory_order_acquire)?P::stopping:P::bound);
        if(!retired && (!Current(this) || !target.Current())) {
            cancelled.store(true,std::memory_order_release);
            result.state=Stop(command);
        }
        if(!target.Available()) { ready.store(false,std::memory_order_release); }
        return result;
    }
    State Stop(const wire::Command& input) noexcept override {
        if(!wire::SameEngagement(input,command)) { return {P::blocked}; }
        if(retired) { return {P::retired,C::scene_retired}; }
        cancelled.store(true,std::memory_order_release);
        if(active && movement::PauseNativeOwnerAction(scene,grant)==movement::Result::accepted && !active) {
            return {P::closed,C::native_stopped,1,1,0};
        }
        return StateNow(P::stopping);
    }
    void Tick(void* root,HWND owner_window) noexcept {
        if(updating) { return; }
        updating=true; window=owner_window;
        if(!bind_attempted) {
            bind_attempted=true;
            ready.store(target.Bind(window) && submission::Ready() && power::Ready(),std::memory_order_release);
        }
        if(active && retired) {
            if(!target.Clear()) { ready.store(false,std::memory_order_release); }
            ticket.Close(); lease.reset(); active=false;
        }
        movement::NativeScene fresh{};
        const bool valid_scene=movement::ReadNativeMovementLifetime(fresh)
            && fresh.window==reinterpret_cast<std::uintptr_t>(root) && movement::NativeMovementLifetimeCurrent(fresh);
        if(active && !retired) {
            NativeTarget::Observation observed{};
            // A cast may own local action state with AF8 null. UI selection and
            // projectile/animation state neither close nor redirect ownership.
            if(!Current(this) || !target.Current() || !target.ReadState(scene,observed)
                || (observed.target && observed.target!=target.TargetAddress())) {
                (void)controller.Update(command,Stop(command));
            }
        }
        if(auto pending=Take()) {
            executing=pending;
            wire::fence::Binding expected{}; movement::Grant requested{};
            const bool valid=wire::BindingFor(pending->command,process.process_id,process.creation_filetime_utc,expected)
                && pending->command.window==reinterpret_cast<std::uintptr_t>(window)
                && movement::wire::Decode(pending->command.grant,requested);
            const bool current=valid && valid_scene && pending->lease && pending->lease->Current(GetTickCount64())
                && movement::NativeOwnerActionCurrent(fresh,requested,pending->command.host);
            const bool live=current && combat::Ready() && GetTickCount64()<=pending->deadline;
            if(!active) { scene=fresh; }
            const auto receipt=controller.Execute(pending->verb,pending->command,valid,live,current,*this);
            Complete(pending,receipt,controller.Diagnose(pending->command)); executing.reset();
        }
        updating=false;
    }
};
Runtime runtime;
bool Runtime::StopOwner(const movement::NativeScene& scene,const movement::Grant& grant,movement::StopReason) noexcept {
    return runtime.StopOwned(scene,grant);
}
void Runtime::Retire(std::uint64_t epoch) noexcept {
    if((runtime.active || runtime.preparing) && runtime.scene.epoch==epoch) {
        runtime.retired=true; runtime.cancelled.store(true,std::memory_order_release);
    }
    runtime.controller.Retire(epoch);
}
void Runtime::Update(void* root,HWND window) noexcept { runtime.Tick(root,window); }
}
}
namespace wonderbane::extension::combat {
bool Ready() noexcept {
    return v2::runtime.ready.load(std::memory_order_acquire) && submission::Ready() && power::Ready()
        && combat_owner_service.load(std::memory_order_acquire)==&v2::Runtime::Update
        && combat_owner_stop.load(std::memory_order_acquire)==&v2::Runtime::StopOwner
        && combat_owner_retire.load(std::memory_order_acquire)==&v2::Runtime::Retire;
}
bool Start(const ProcessIdentity& process) noexcept {
    if(process.process_id!=GetCurrentProcessId()
        || process.creation_filetime_utc!=v3::fence::Creation(GetCurrentProcess())
        || !movement::VerifyNativeMovementImage(v2::runtime.base)
        || !submission::Start(v2::runtime.base) || !power::Start(v2::runtime.base)) { return false; }
    v2::runtime.process=process;
    combat_owner_stop.store(&v2::Runtime::StopOwner,std::memory_order_release);
    combat_owner_retire.store(&v2::Runtime::Retire,std::memory_order_release);
    combat_owner_ready.store(&Ready,std::memory_order_release);
    combat_owner_service.store(&v2::Runtime::Update,std::memory_order_release);
    return true;
}
}
