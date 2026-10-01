#pragma once
#include "actor_effects_native.h"
#include "actor_inventory_native.h"
#include <array>
#include <cstdint>

namespace wonderbane::extension::actor_buffs {
inline constexpr std::size_t kMaxActions = 32, kMaxDescriptors = 64;
inline constexpr std::size_t kMaxPublicationDescriptors = 256;
using Key = actor_effects::Key;
enum class CoverageKind : std::uint32_t { all_descriptors, transform_marker };
enum class Coverage : std::uint32_t { unknown, missing, partial, present };
enum class Readiness : std::uint32_t {
    unknown, ready, not_learned, initiation_pending, global_recovery,
    power_reuse, stance_ineligible, unsupported, item_unavailable
};
enum class Unknown : std::uint32_t {
    none, request, effects, identity, read_fault, geometry, changed, unsupported, inventory
};
struct Intent {
    std::uint32_t action_index{}, group_index{}, power_id{};
    Key item_template{};
    // Explicit configured association for items, never inferred from their name.
    std::uint32_t coverage_power_id{};
    CoverageKind coverage_kind{};
    bool operator==(const Intent&) const = default;
};
struct Request {
    std::uint32_t count{};
    std::array<Intent,kMaxActions> actions{};
    bool operator==(const Request&) const = default;
};
struct Descriptor {
    std::uint32_t id{}, action_id{};
    actor_effects::ActionClass action_class{};
    std::uint8_t local_add_suppression{};
    bool present{};
    bool operator==(const Descriptor&) const = default;
};
struct ActionFacts {
    Intent intent{};
    std::uint32_t learned_rank{}, category{}, target_mode{}, delivery{}, required_mode{};
    std::uint32_t descriptor_count{};
    std::array<Descriptor,kMaxDescriptors> descriptors{};
    Coverage coverage = Coverage::unknown;
    Readiness readiness = Readiness::unknown;
    Key item_key{}, item_template{};
    std::uint32_t item_quantity{}, item_type{}, item_flags{};
    // Echo-only hints: never sufficient authority. State owns the references;
    // ItemOperand revalidates that exact retained publication before dispatch.
    std::uint32_t item_hint{},template_hint{};
    bool operator==(const ActionFacts&) const = default;
};
struct State {
    State() noexcept = default;
    State(const State&) = delete;
    State& operator=(const State&) = delete;
    bool Quarantined() const noexcept { return quarantined_; }
private:
    std::array<combat::inventory::State,kMaxActions> inventory_{};
    std::array<combat::inventory::Observation,kMaxActions> observations_{};
    std::uint64_t generation_{};
    bool occupied_{},quarantined_{};
    friend struct Access;
};
struct Publication {
    Unknown unknown = Unknown::effects;
    Key actor_key{};
    std::uint64_t scene{}, effect_epoch{};
    std::uint32_t count{}, actor_mode{};
    bool initiation_clear{};
    std::array<ActionFacts,kMaxActions> actions{};
    bool Complete() const noexcept { return unknown==Unknown::none && effect_epoch && scene; }
    std::span<const actor_effects::Effect> Effects() const noexcept {
        return {effects_.effects.data(),Complete()?effects_.count:0};
    }
private:
    // Parent assigns its own publication revision. This private seal concerns
    // native lifetime/mutation identity and must never be serialized.
    actor_effects::Snapshot effects_{};
    Request request_{};
    State* state_{};
    std::uint64_t state_generation_{};
    friend Unknown Capture(const actor_effects::Context&,const Request&,State&,Publication&) noexcept;
    friend bool Revalidate(const actor_effects::Context&,State&,const Publication&) noexcept;
};
// Read-only native owner-service operations. Complete refers to requested local
// coverage facts, not all server effects. No timer is interpreted as effect life.
// State keeps canonical item references alive until explicit Release. Do not
// destroy quarantined State or attempt a second native release after a fault.
Unknown Capture(const actor_effects::Context&,const Request&,State&,Publication&) noexcept;
bool Revalidate(const actor_effects::Context&,State&,const Publication&) noexcept;
bool ItemOperand(const actor_effects::Context&,State&,const Publication&,std::uint32_t action_index,
    combat::inventory::Facts&) noexcept;
bool Release(State&) noexcept;
}
