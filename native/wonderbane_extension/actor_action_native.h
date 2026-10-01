#pragma once
#include "actor_action_wire.h"
#include "actor_buff_observation.h"
#include "combat_initiation.h"
#include "combat_item_entry.h"
#include "combat_melee_entry.h"
#include "combat_party.h"
#include "combat_power_entry.h"
#include "combat_target_policy.h"
#include "movement_lifetime.h"

namespace wonderbane::extension::actor {
class NativeActor final {
public:
    using Admission = bool (*)(void*) noexcept;
    struct Gates {
        Admission current{}, append_current{};
        void* context{};
    };
    struct Observation {
        std::uint32_t mode{}, action_state{}, animation_event_index{};
        std::uintptr_t target{};
        combat::initiation::Snapshot initiation{};
        bool ClearInitiation() const noexcept { return initiation.Clear(); }
        bool operator==(const Observation&) const = default;
    };
    struct Operation {
        wire::Outcome outcome = wire::Outcome::unavailable;
        wire::Entry entry = wire::Entry::never_entered;
        wire::LocalSettlement local_settlement = wire::LocalSettlement::settled;
        std::uint32_t history{}; // outbound_queued / uncertain_history only
        wire::Reason reason = wire::Reason::none;
        wire::Closure closure = wire::Closure::none;
        Observation state{};
        std::array<char,72> detail{};
    };
    // Retains the canonical local actor using the native owned registry lookup.
    // scene_current proves the outermost owner thread/lifetime, independently of
    // any parent Grant; publication and remote application history outlive parents.
    bool BindScene(const movement::NativeScene&, HWND, Admission scene_current, void*) noexcept;
    bool Available() const noexcept;
    bool SceneCurrent() const noexcept;
    bool MatchesIdentity(const wire::Digest& local_name,const wire::Digest& server) const noexcept;
    const movement::NativeScene& Scene() const noexcept { return scene_; }
    // Only after confirmed lifetime retirement, with no in-flight native frame.
    // No old actor action is invoked; only known owned references are released.
    bool ReleaseScene() noexcept;
    bool ValidateParent(const fence::ActorBinding&, Gates) noexcept;
    Operation Attach(const fence::ContextBinding&, Gates) noexcept;
    Operation Submit(const wire::Command&) noexcept;
    // Polls only the exact outstanding local action; never invokes new work.
    Operation Poll() noexcept;
    bool PendingCommand(wire::Command&) const noexcept;
    bool ReadState(Observation&) const noexcept;
    bool CombatTargetCurrent() const noexcept;
    // Read-only continuation of the retained child: no UI selection requirement.
    // Null AF8 is valid for a pending cast; a non-null foreign AF8 is not.
    bool ContinueContext() noexcept;
    // Cleanup gates are separately supplied: revoked admission is not a reason
    // to abandon exact owned cleanup. These never clear the application journal.
    Operation StopContext(const fence::ContextBinding&, Admission, void*) noexcept;
    Operation StopOwner(const fence::ActorBinding&, Admission, void*) noexcept;
    // Immediate scalar prohibition; cannot be reset on repeated action requests.
    void Revoke() noexcept;
    // Scene-owned read-only publication. Parent close does not invalidate it.
    actor_buffs::Unknown Publish(const actor_buffs::Request&, actor_buffs::Publication&) noexcept;
    bool RevalidatePublication(const actor_buffs::Publication&) noexcept;
    const actor_buffs::Publication& Publication() const noexcept { return publication_; }
private:
    struct Calls {
        void** (__thiscall* lookup)(void*,void**,const std::uint32_t*){};
        void (__thiscall* release)(void**,void*){};
        decltype(&combat::melee::Invoke) attack{};
        decltype(&combat::power::Invoke) power{};
        decltype(&combat::power::ReadSelfInitiation) self_initiation{};
        decltype(&combat::item::Invoke) item{};
        bool (__cdecl* dispatch)(const void*,void*){};
    } calls_{};
    bool Owner() const noexcept;
    bool RawCurrent() const noexcept;
    bool ActorIdentity() const noexcept;
    bool TargetIdentity() const noexcept;
    bool Current(bool child) noexcept;
    static bool Gate(void*) noexcept;
    static bool AppendGate(void*) noexcept;
    static bool SceneGate(void*) noexcept;
    bool ReleaseTarget();
    bool ReleaseMessages();
    bool ReleaseAll();
    Operation AttachImpl();
    Operation SubmitImpl();
    Operation PollImpl();
    Operation StopImpl(bool owner,Admission,void*);
    Operation RunCxx(unsigned operation,Admission=nullptr,void* = nullptr) noexcept;
    Operation Guarded(unsigned operation,Admission=nullptr,void* = nullptr) noexcept;
    bool BindCxx() noexcept;
    bool ClearCxx() noexcept;
    actor_buffs::Unknown PublishImpl(const actor_buffs::Request&,actor_buffs::Publication&) noexcept;
    bool RevalidatePublicationImpl(const actor_buffs::Publication&) noexcept;
    void ClearInstant() noexcept;
    std::uintptr_t image_{};
    HWND window_{};
    DWORD thread_{};
    movement::NativeScene scene_{};
    Admission scene_current_{};
    void* scene_context_{};
    Gates parent_gates_{}, child_gates_{};
    fence::ActorBinding parent_{};
    fence::ContextBinding child_{};
    wire::Command command_{}, pending_command_{};
    Operation pending_operation_{};
    combat::party::Snapshot party_{};
    combat::submission::Receipt melee_receipt_{};
    combat::power::Receipt power_receipt_{};
    combat::item::Receipt item_receipt_{};
    combat::item::State item_state_{};
    actor_buffs::State observation_state_{};
    actor_buffs::Publication publication_{};
    std::uint32_t instant_self_id_{}, pre_entry_self_id_{};
    std::uint64_t instant_self_epoch_{}, pre_entry_epoch_{}, pending_epoch_{};
    combat::power::InitiationDefinition instant_definition_{};
    void* actor_{};
    void* target_{};
    void* request_{};
    void* transfer_{};
    bool faulted_{}, running_{}, parent_bound_{}, child_bound_{}, revoked_{};
    bool pending_{}, pending_saw_initiation_{}, pending_owned_followup_{}, dispatched_{};
    bool local_owner_work_{}, local_context_work_{};
    const char* stage_="none";
    friend struct NativeActorTestAccess;
};
}
