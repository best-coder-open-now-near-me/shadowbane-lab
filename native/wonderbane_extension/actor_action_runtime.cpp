#include "combat_runtime.h"
#include "item_application_trace.h"
#include "actor_action_native.h"
#include "actor_action_controller.h"
#include "actor_action_command_queue.h"
#include "actor_publication.h"
#include "movement_runtime.h"
#include "movement_native_image.h"
#include "native_owner_services.h"

namespace wonderbane::extension::actor {
namespace {
using O=wire::Outcome;using P=wire::Phase;using C=wire::Closure;
class Runtime final:public Invoker {
public:
    Controller controller;
    NativeActor native;
    actor_actions::ApplicationJournal journal;
    publication::Writer publisher;
    selectors::Manifest manifest{};
    wire::Digest manifest_digest{};
    wire::Id actor_lifetime{};
    ProcessIdentity process{};
    movement::NativeScene scene{};
    movement::Grant grant{};
    HWND window{};
    std::uintptr_t base{};
    wire::Command owner_command{},child_command{};
    fence::ActorBinding parent{};
    fence::ContextBinding child{};
    fence::Ticket<fence::ActorBinding> parent_ticket;
    fence::Ticket<fence::ContextBinding> child_ticket;
    std::shared_ptr<movement::CommandLease> lease;
    std::shared_ptr<QueuedCommand> executing;
    std::atomic<bool> ready{false},cancelled{false},child_cancelled{false};
    bool updating{},retired{},active{},preparing{},dispatching{},stopping{};
    bool parent_admitted{},child_admitted{},attaching{},has_manifest{},quarantined{},admission_blocked{};

    static bool SceneGate(void* context) noexcept {
        const auto& self=*static_cast<Runtime*>(context);
        return (self.updating||self.stopping)&&!self.retired&&!self.quarantined
            &&movement::NativeMovementLifetimeCurrent(self.scene);
    }
    static bool Current(void* context) noexcept {
        auto& self=*static_cast<Runtime*>(context);
        if((!self.active&&!self.preparing)||self.admission_blocked||!SceneGate(context)||self.cancelled.load(std::memory_order_acquire)
            ||!self.lease||!self.lease->Current(GetTickCount64())
            ||((self.preparing||self.dispatching||self.attaching)&&(!self.executing||GetTickCount64()>self.executing->deadline))){return false;}
        fence::State state{};
        return self.parent_ticket.Inspect(state)==fence::Result::not_pending
            &&state==(self.parent_admitted?fence::State::entered:fence::State::pending)
            &&movement::NativeOwnerActionCurrent(self.scene,self.grant,self.owner_command.host)
            &&!self.cancelled.load(std::memory_order_acquire)&&!self.retired;
    }
    static bool ChildCurrent(void* context) noexcept {
        auto& self=*static_cast<Runtime*>(context);fence::State state{};
        return Current(context)&&!self.child_cancelled.load(std::memory_order_acquire)
            &&self.child_ticket.Inspect(state)==fence::Result::not_pending
            &&state==(self.child_admitted?fence::State::entered:fence::State::pending);
    }
    static bool AppendCurrent(void* context) noexcept {
        const auto& self=*static_cast<Runtime*>(context);
        // Queue-lock boundary: immutable/scalar admission only, no IPC mutex.
        return self.active&&self.parent_admitted&&self.dispatching&&!self.retired
            &&!self.quarantined&&!self.cancelled.load(std::memory_order_acquire);
    }
    static bool ChildAppendCurrent(void* context) noexcept {
        const auto& self=*static_cast<Runtime*>(context);
        return AppendCurrent(context)&&self.child_admitted&&!self.child_cancelled.load(std::memory_order_acquire);
    }
    static bool StopCurrent(void* context) noexcept {
        const auto& self=*static_cast<Runtime*>(context);
        return (self.updating||self.stopping)&&!self.retired&&movement::NativeOwnerStopCurrent(self.scene,self.grant);
    }
    static State Observed(const NativeActor::Observation& state,P phase=P::bound,C closure=C::none) noexcept {
        return {phase,closure,state.mode,state.action_state,state.target?1U:0U};
    }
    static Operation Converted(const NativeActor::Operation& source) noexcept {
        Operation result;result.outcome=source.outcome;result.entry=source.entry;result.local=source.local_settlement;
        result.history=source.history;result.reason=source.reason;result.state=Observed(source.state);
        std::memcpy(result.detail.data(),source.detail.data(),source.detail.size());return result;
    }
    Operation Refused(O outcome=O::stale,wire::Reason reason=wire::Reason::none) noexcept {
        Operation result;result.outcome=outcome;result.reason=reason;
        NativeActor::Observation observed{};if(native.ReadState(observed)){result.state=Observed(observed);}return result;
    }
    State StateNow(P phase=P::bound) noexcept {
        NativeActor::Observation observed{};
        return native.ReadState(observed)?Observed(observed,phase):State{phase};
    }
    void Revoke(const wire::Command& input,bool owner) noexcept override {
        if(input.parent_id!=owner_command.parent_id||input.parent_digest!=owner_command.parent_digest){return;}
        if(owner){cancelled.store(true,std::memory_order_release);native.Revoke();}
        else if(input.context_id==child_command.context_id&&input.context_digest==child_command.context_digest){child_cancelled.store(true,std::memory_order_release);}
    }
    std::size_t JournalIndex(const wire::Command& command) const noexcept {
        wire::Digest digest{};if(!wire::HashCommand(command,digest)){return actor_actions::ApplicationJournal::invalid;}
        const auto& records=journal.Records();for(std::size_t i=0;i<records.size();++i){if(records[i].reserved&&records[i].command==digest){return i;}}
        return actor_actions::ApplicationJournal::invalid;
    }
    bool RecordApplication(const wire::Command& command,Operation& result) noexcept {
        const auto index=JournalIndex(command);
        if(index==actor_actions::ApplicationJournal::invalid){return true;}
        wire::Digest digest{};(void)wire::HashCommand(command,digest);
        const auto entry=result.entry==wire::Entry::entered?actor_actions::ApplicationEntry::entered:
            result.entry==wire::Entry::never_entered?actor_actions::ApplicationEntry::never_entered:actor_actions::ApplicationEntry::uncertain;
        if(!journal.Record(index,digest,entry,(result.history&wire::outbound_queued)!=0,result.local==wire::LocalSettlement::settled)){return false;}
        const auto state=journal.Records()[index].state;
        result.application=state==actor_actions::ApplicationState::pending?wire::Application::pending:
            state==actor_actions::ApplicationState::observed?wire::Application::observed:wire::Application::none;
        return true;
    }
    void SettleApplication(const wire::Command& command) noexcept {
        const auto index=JournalIndex(command);if(index==actor_actions::ApplicationJournal::invalid){return;}
        const auto record=journal.Records()[index];
        if(!journal.Record(index,record.command,record.entry,record.queued,true)){admission_blocked=true;}
    }
    bool ManifestPendingCompatible(const selectors::Manifest& proposed) const noexcept {
        for(const auto& record:journal.Records()){
            if(!record.reserved||(record.local_settled&&record.state!=actor_actions::ApplicationState::pending)){continue;}
            bool found=false;for(std::uint32_t group=0;group<proposed.groups;++group){wire::Digest digest{};
                if(selectors::GroupDigest(proposed,group,digest)&&digest==record.intent){found=true;break;}}
            if(!found){return false;}
        }return !journal.Faulted();
    }
    std::uint32_t ArbiterBlocks() const noexcept {
        return (!controller.ContextAllowsEntry()||(child_admitted&&child_cancelled.load(std::memory_order_acquire))?admission::child_cleanup:0U)
            |(journal.LocalPending()?admission::local_action:0U);
    }
    Operation AdmissionRefused(std::uint32_t blocks) noexcept {
        if(has_manifest){if(blocks){(void)publisher.ObserveAdmission(blocks);}else{(void)publisher.InvalidateAdmission();}}
        return Refused(O::deferred,wire::AdmissionReason(blocks));
    }
    bool Refresh() noexcept {
        if(!has_manifest||!native.SceneCurrent()){if(has_manifest){(void)publisher.Unknown(3);}return false;}
        actor_buffs::Request request{};request.count=manifest.count;
        for(std::uint32_t i=0;i<manifest.count;++i){const auto& selector=manifest.records[i];
            request.actions[i]={i,selector.group,selector.power,{selector.template_id,selector.template_zero},
                selector.coverage_power,static_cast<actor_buffs::CoverageKind>(selector.coverage_kind)};}
        actor_buffs::Publication facts{};
        if(native.Publish(request,facts)!=actor_buffs::Unknown::none||!native.RevalidatePublication(facts)){
            (void)publisher.Unknown(static_cast<std::uint32_t>(facts.unknown)?static_cast<std::uint32_t>(facts.unknown):6U);return false;}
        facts.admission_blocks|=ArbiterBlocks();
        publication::Frame frame{};
        if(!publication::Encode(manifest,facts,journal,frame)||!publisher.Publish(frame)||!publisher.Current(frame)){(void)publisher.Unknown(6);return false;}
        for(std::uint32_t group=0;group<manifest.groups;++group){
            bool present=false;
            for(std::uint32_t i=0;i<facts.count;++i){if(facts.actions[i].intent.group_index==group&&facts.actions[i].coverage==actor_buffs::Coverage::present){present=true;}}
            wire::Digest digest{};
            if(!selectors::GroupDigest(manifest,group,digest)||!journal.Observe(digest,frame.revision,true,present)){(void)publisher.Unknown(10);return false;}
        }
        for(const auto& record:journal.Records()){
            if(record.reserved&&record.state==actor_actions::ApplicationState::observed){(void)controller.ObserveApplication(record.command);}
        }
        // Observation may resolve application history. Publish that transition
        // separately so callers submit against the latest exact factual revision.
        if(!native.RevalidatePublication(native.Publication())
            ||facts.admission_blocks!=(native.Publication().admission_blocks|ArbiterBlocks())
            ||!publication::Encode(manifest,facts,journal,frame)||!publisher.Publish(frame)){(void)publisher.Unknown(6);return false;}
        return true;
    }
    wire::Receipt Read(wire::Verb verb,const wire::Command& input,bool live) noexcept {
        auto result=wire::Reply(input,verb,O::unavailable);
        if(!live||!native.SceneCurrent()){return result;}
        if(verb==wire::Verb::register_selectors){
            selectors::Manifest proposed{};
            if(!selectors::Read(input.manifest_digest,proposed)||proposed.client_pid!=process.process_id
                ||proposed.client_creation!=process.creation_filetime_utc||proposed.producer_pid!=input.host.process
                ||proposed.producer_creation!=input.host.creation||proposed.producer_generation!=input.host.generation
                ||!native.MatchesIdentity(proposed.local_name,proposed.server)){result.outcome=O::invalid;return result;}
            if(has_manifest&&input.manifest_digest!=manifest_digest){(void)Refresh();}
            if(!ManifestPendingCompatible(proposed)){result.outcome=O::deferred;result.reason=wire::Reason::observation;return result;}
            if(!has_manifest||input.manifest_digest!=manifest_digest){
                if(has_manifest){(void)publisher.Unknown(6);publisher.Close();has_manifest=false;}
                publication::Header header{};header.client_pid=process.process_id;header.client_creation=process.creation_filetime_utc;
                header.actor_lifetime=actor_lifetime;header.manifest=input.manifest_digest;header.actor_key[0]=scene.identity[0];header.actor_key[1]=scene.identity[1];
                header.actor_address=static_cast<std::uint32_t>(scene.actor);header.scene=scene.epoch;
                auto floor=publisher.Revision();
                for(const auto& record:journal.Records()){if(record.reserved){floor=(std::max)(floor,(std::max)(record.submitted_revision,record.observed_revision));}}
                if(!publisher.Open(header,floor,publisher.AdmissionRevision())){return result;}
                manifest=proposed;manifest_digest=input.manifest_digest;has_manifest=true;
            }
        }else if(!has_manifest||input.manifest_digest!=manifest_digest){return result;}
        result.outcome=Refresh()?O::observed:O::unavailable;return result;
    }
    Operation Open(const wire::Command& input) noexcept override {
        auto result=Refused(O::unavailable);result.state={};
        if(active||preparing||!executing||!native.SceneCurrent()||!fence::ReadBinding(input.parent_digest,parent)
            ||!wire::Bindings(input,parent)||!movement::wire::Decode(input.grant,grant)){return result;}
        owner_command=input;parent_admitted=false;cancelled.store(false,std::memory_order_release);
        try{if(!parent_ticket.Open(parent,parent)){return result;}}catch(...){return result;}
        lease=executing->lease;preparing=true;
        const bool bound=Current(this)&&native.ValidateParent(parent,{Current,AppendCurrent,this});
        if(bound&&Current(this)){
            parent_admitted=parent_ticket.TryAdmit(parent,false)==fence::Result::admitted;
            if(parent_admitted&&Current(this)&&movement::BeginNativeOwnerAction(scene,grant,input.host)==movement::Result::accepted){
                active=true;preparing=false;result.outcome=O::bound;result.state=StateNow();return result;
            }
        }
        if(bound){
            const auto clean=native.StopOwner(parent,StopCurrent,this);
            if(clean.outcome!=O::closed){active=true;preparing=false;result.state=StateNow(P::blocked);return result;}
        }
        preparing=false;parent_ticket.Close();lease.reset();return result;
    }
    Operation Attach(const wire::Command& input) noexcept override {
        auto result=Refused(O::unavailable);result.state={};
        if(!active||attaching||child_admitted||!Current(this)||!fence::ReadBinding(input.context_digest,child)
            ||!wire::Bindings(input,parent,&child)){return result;}
        child_command=input;child_cancelled.store(false,std::memory_order_release);
        try{if(!child_ticket.Open(child,parent)){return result;}}catch(...){return result;}
        attaching=true;
        if(ChildCurrent(this)){
            const auto native_result=native.Attach(child,{ChildCurrent,ChildAppendCurrent,this});
            result=Converted(native_result);
            if(native_result.closure==C::local_released&&result.outcome!=O::bound
                &&result.entry==wire::Entry::never_entered&&result.local==wire::LocalSettlement::settled){result.state={};}
            if(result.outcome==O::bound&&ChildCurrent(this)){
                child_admitted=child_ticket.TryAdmit(child,false)==fence::Result::admitted;
                if(child_admitted&&ChildCurrent(this)){attaching=false;result.state=StateNow();return result;}
            }
        }
        if(result.entry==wire::Entry::never_entered&&result.local==wire::LocalSettlement::settled
            &&result.state.phase==P::unknown){attaching=false;child_ticket.Close();child_admitted=false;return result;}
        const auto clean=native.StopContext(child,StopCurrent,this);attaching=false;
        if(clean.outcome==O::closed){child_ticket.Close();child_admitted=false;result.state={};}
        else {result.state=StateNow(P::blocked);}
        return result;
    }
    Operation Submit(const wire::Command& input) noexcept override {
        const bool targeted=wire::Any(input.context_id);
        if(!active||!wire::Bindings(input,parent,targeted?&child:nullptr)||!(targeted?ChildCurrent(this):Current(this))){return Refused();}
        // Child cleanup occupies the shared local arbiter even after its last
        // action settled. Actor-only preparation cannot bypass that obligation.
        if(journal.Faulted()){return AdmissionRefused(0);}
        if(const auto blocks=ArbiterBlocks()){return AdmissionRefused(blocks);}
        if(!targeted){
            std::uint32_t blocks{};
            if(!native.ReadAdmission(blocks)){return AdmissionRefused(0);}
            if(blocks){return AdmissionRefused(blocks);}
            publication::Frame frame{};
            if(!has_manifest||input.manifest_digest!=manifest_digest||input.selector_index>=manifest.count
                ||!publisher.Current(frame)||!frame.complete||frame.revision!=input.publication_revision||frame.snapshot!=input.snapshot_id){return Refused(O::deferred,wire::Reason::observation);}
            if(!native.RevalidatePublication(native.Publication())){return AdmissionRefused(0);}
            const auto& facts=native.Publication();
            const auto group=manifest.records[input.selector_index].group;
            if(input.selector_index>=facts.count||facts.actions[input.selector_index].readiness!=actor_buffs::Readiness::ready){return Refused(O::deferred,wire::Reason::observation);}
            for(std::uint32_t i=0;i<facts.count;++i){
                if(facts.actions[i].intent.group_index==group&&facts.actions[i].coverage!=actor_buffs::Coverage::missing){return Refused(O::deferred,wire::Reason::observation);}
            }
            wire::Digest intent{},command{};
            if(!selectors::GroupDigest(manifest,manifest.records[input.selector_index].group,intent)||!wire::HashCommand(input,command)
                ||journal.Reserve(intent,command,frame.revision)==actor_actions::ApplicationJournal::invalid){return Refused(O::deferred,wire::Reason::observation);}
        }
        dispatching=true;Operation result=Refused();
        if((targeted?ChildCurrent(this):Current(this))&&parent_ticket.TryAdmit(parent,true)==fence::Result::admitted
            &&(!targeted||child_ticket.TryAdmit(child,true)==fence::Result::admitted)){
            const auto submitted=native.Submit(input);result=Converted(submitted);
            // Observation after native return, outside the queue lock. Never application authority.
            item_trace::OwnedReturn(input,scene,result.outcome,result.entry,result.local,result.history,&submitted.power_diagnostic);
            if(!targeted&&result.outcome==O::deferred&&result.entry==wire::Entry::never_entered){
                if(submitted.admission_blocks){(void)publisher.ObserveAdmission(submitted.admission_blocks);}
                else if(result.reason==wire::Reason::admission_changed){(void)publisher.InvalidateAdmission();}
            }
        }
        dispatching=false;
        if(!RecordApplication(input,result)){admission_blocked=true;cancelled.store(true,std::memory_order_release);}
        return result;
    }
    bool StopOwned(const movement::NativeScene& expected,const movement::Grant& expected_grant) noexcept {
        if(!active&&!preparing){return true;}
        if(stopping||retired||expected.epoch!=scene.epoch||expected_grant!=grant||!movement::NativeOwnerStopCurrent(expected,expected_grant)){return false;}
        cancelled.store(true,std::memory_order_release);native.Revoke();stopping=true;
        wire::Command pending{};const bool pending_before=native.PendingCommand(pending);
        const auto result=native.StopOwner(parent,StopCurrent,this);
        if(result.outcome==O::closed&&result.local_settlement==wire::LocalSettlement::settled){
            if(pending_before){SettleApplication(pending);}
            active=preparing=false;parent_admitted=child_admitted=false;
            parent_ticket.Close();child_ticket.Close();lease.reset();
            (void)controller.UpdateScope(owner_command,Observed(result.state,P::closed,result.closure),true);
        }
        stopping=false;return result.outcome==O::closed&&result.local_settlement==wire::LocalSettlement::settled;
    }
    State Stop(const wire::Command& input,bool owner) noexcept override {
        if(input.parent_id!=owner_command.parent_id||input.parent_digest!=owner_command.parent_digest){return {P::blocked};}
        Revoke(input,owner);
        if(owner){
            if(StopOwned(scene,grant)){
                // Release the movement owner's external-work bit only after the
                // exact owned native action is locally settled.
                (void)movement::PauseNativeOwnerAction(scene,grant);
                // StopOwned publishes the exact closure to the controller.
                return StateNow(P::stopping);
            }return StateNow(P::stopping);
        }
        if(input.context_id!=child_command.context_id||input.context_digest!=child_command.context_digest){return {P::blocked};}
        wire::Command pending{};const bool pending_before=native.PendingCommand(pending)&&wire::Any(pending.context_id);
        const auto result=native.StopContext(child,StopCurrent,this);
        if(result.outcome==O::closed&&result.local_settlement==wire::LocalSettlement::settled){
            if(pending_before){SettleApplication(pending);}
            child_ticket.Close();child_admitted=false;return Observed(result.state,P::closed,result.closure);
        }return Observed(result.state,P::stopping);
    }
    void Poll() noexcept {
        wire::Command pending{};
        if(native.PendingCommand(pending)){
            auto result=Converted(native.Poll());
            const auto index=JournalIndex(pending);
            if(index!=actor_actions::ApplicationJournal::invalid){
                const auto application=journal.Records()[index].state;
                result.application=application==actor_actions::ApplicationState::pending?wire::Application::pending:
                    application==actor_actions::ApplicationState::observed?wire::Application::observed:wire::Application::none;
            }
            if(!controller.UpdateAction(pending,result)||!RecordApplication(pending,result)
                ||!controller.UpdateAction(pending,result)){admission_blocked=true;cancelled.store(true,std::memory_order_release);}
        }
    }
    static bool StopOwner(const movement::NativeScene&,const movement::Grant&,movement::StopReason) noexcept;
    static void Retire(std::uint64_t) noexcept;
    static void Update(void*,HWND) noexcept;
    void Tick(void* root,HWND owner_window) noexcept {
        if(updating){return;}updating=true;window=owner_window;
        movement::NativeScene fresh{};
        const bool valid_scene=movement::ReadNativeMovementLifetime(fresh)&&fresh.window==reinterpret_cast<std::uintptr_t>(root)
            &&movement::NativeMovementLifetimeCurrent(fresh);
        if(scene.epoch&&(retired||!movement::NativeMovementLifetimeCurrent(scene))){
            retired=true;cancelled.store(true,std::memory_order_release);native.Revoke();
            if(has_manifest){(void)publisher.Unknown(3);}
            if(native.ReleaseScene()){
                (void)controller.UpdateScope(owner_command,{P::retired,C::scene_retired},true);
                publisher.Close();has_manifest=false;manifest={};manifest_digest={};actor_lifetime={};journal={};
                parent_ticket.Close();child_ticket.Close();lease.reset();active=preparing=parent_admitted=child_admitted=false;admission_blocked=false;scene={};
            }else {quarantined=true;}
        }
        if(!scene.epoch&&valid_scene&&!quarantined){
            scene=fresh;retired=false;
            if(BCryptGenRandom(nullptr,actor_lifetime.data(),static_cast<ULONG>(actor_lifetime.size()),BCRYPT_USE_SYSTEM_PREFERRED_RNG)<0
                ||!wire::Any(actor_lifetime)||!native.BindScene(scene,window,SceneGate,this)){quarantined=true;}
        }
        ready.store(!quarantined&&!admission_blocked&&native.Available()&&valid_scene&&fresh.epoch==scene.epoch&&!retired,std::memory_order_release);
        if(active&&!retired){
            Poll();
            if(!Current(this)){(void)Stop(owner_command,true);}
            else if(child_admitted&&(!ChildCurrent(this)||!native.ContinueContext())){
                const auto state=Stop(child_command,false);(void)controller.UpdateScope(child_command,state,false);
            }
        }
        if(auto pending=Take()){
            executing=pending;
            const bool timely=GetTickCount64()<=pending->deadline;
            const bool producer=pending->lease&&pending->lease->Current(GetTickCount64());
            const bool window_ok=pending->command.window==reinterpret_cast<std::uintptr_t>(window);
            wire::Receipt receipt{};
            if(wire::ReadVerb(pending->verb)){
                receipt=Read(pending->verb,pending->command,timely&&producer&&window_ok&&valid_scene&&!quarantined);
            }else{
                movement::Grant requested{};
                const bool valid=window_ok&&movement::wire::Decode(pending->command.grant,requested);
                const bool current=valid&&producer&&valid_scene&&movement::NativeOwnerActionCurrent(fresh,requested,pending->command.host);
                receipt=controller.Execute(pending->verb,pending->command,valid,timely&&current&&ready.load(),current,*this);
            }
            Complete(pending,receipt,controller.Diagnose(pending->command));executing.reset();
        }
        updating=false;
    }
};
Runtime runtime;
bool Runtime::StopOwner(const movement::NativeScene& scene,const movement::Grant& grant,movement::StopReason) noexcept{return runtime.StopOwned(scene,grant);}
void Runtime::Retire(std::uint64_t epoch) noexcept {
    if(runtime.scene.epoch==epoch){runtime.retired=true;runtime.cancelled.store(true,std::memory_order_release);runtime.native.Revoke();}
}
void Runtime::Update(void* root,HWND window) noexcept{runtime.Tick(root,window);}
}
}
namespace wonderbane::extension::combat {
bool Ready() noexcept {
    return actor::runtime.ready.load(std::memory_order_acquire)&&submission::Ready()&&power::Ready()
        &&combat_owner_service.load(std::memory_order_acquire)==&actor::Runtime::Update
        &&combat_owner_stop.load(std::memory_order_acquire)==&actor::Runtime::StopOwner
        &&combat_owner_retire.load(std::memory_order_acquire)==&actor::Runtime::Retire;
}
bool Start(const ProcessIdentity& process) noexcept {
    if(process.process_id!=GetCurrentProcessId()||process.creation_filetime_utc!=actor::fence::Creation(GetCurrentProcess())
        ||!movement::VerifyNativeMovementImage(actor::runtime.base)||!submission::Start(actor::runtime.base)||!power::Start(actor::runtime.base)
        ||!item::Start(actor::runtime.base)||!inventory::Start(actor::runtime.base)){return false;}
    actor::runtime.process=process;
    combat_owner_stop.store(&actor::Runtime::StopOwner,std::memory_order_release);
    combat_owner_retire.store(&actor::Runtime::Retire,std::memory_order_release);
    combat_owner_ready.store(&Ready,std::memory_order_release);
    combat_owner_service.store(&actor::Runtime::Update,std::memory_order_release);return true;
}
}
