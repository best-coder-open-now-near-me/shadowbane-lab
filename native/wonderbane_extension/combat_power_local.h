#pragma once
#include <array>
#include <cstdint>
#include <limits>
namespace wonderbane::extension::combat::power {
enum class LocalInitiationState { unavailable, pending, retired };
// A local protocol container lifetime, not a server response/request nonce.
// Synchronization and qualified native captures are supplied by the observer.
struct LocalInitiation {
    std::uint64_t generation{};
    std::uintptr_t actor{},state{},begin{},capacity{};
    std::array<std::uint32_t,2> key{};
    std::uint32_t power{},thread{};
    bool invalid{},removed{};
    std::uint64_t Arm(std::uintptr_t object,std::array<std::uint32_t,2> identity,
        std::uint32_t id,std::uint32_t owner_thread) noexcept {
        if(generation==std::numeric_limits<std::uint64_t>::max()) { invalid=true;return 0; }
        ++generation;state=begin=capacity=0;actor=object;key=identity;power=id;thread=owner_thread;invalid=false;removed=false;
        if(!actor||!key[0]||key[1]!=53||!power||!thread) { invalid=true;return 0; }
        return generation;
    }
    std::uint64_t Publish(std::uint64_t token,std::uintptr_t actor_state,
        std::uintptr_t vector_begin,std::uintptr_t vector_capacity) noexcept {
        // Armed before all native captures/call-through. A mutation cannot be
        // lost between capture and publication: invalidators share this lock.
        if(!token||token!=generation||invalid||removed||state||!actor_state
            ||!vector_begin||vector_capacity<vector_begin+4) { return 0; }
        state=actor_state;begin=vector_begin;capacity=vector_capacity;return token;
    }
    void Invalidate(std::uintptr_t object) noexcept {
        if(actor==object&&!removed) { invalid=true; }
    }
    void Removal(std::uint64_t token,std::uintptr_t object,std::array<std::uint32_t,2> identity,
        std::uint32_t id,std::uint32_t owner_thread,bool coherent,bool returned,
        std::uint32_t before,std::uint32_t after) noexcept {
        if(!token||token!=generation||object!=actor||id!=power||invalid||removed) { return; }
        if(!state) { invalid=true;return; }
        if(identity!=key||owner_thread!=thread||!coherent) { invalid=true;return; }
        if(!returned) { if(before!=after) { invalid=true; } return; }
        if(before!=1||after!=0) { invalid=true;return; }
        if(!after) { removed=true; }
    }
    LocalInitiationState State(std::uint64_t token,std::uintptr_t object,
        std::array<std::uint32_t,2> identity,std::uint32_t id) const noexcept {
        if(!token||token!=generation||object!=actor||identity!=key||id!=power||invalid||!state) { return LocalInitiationState::unavailable; }
        return removed?LocalInitiationState::retired:LocalInitiationState::pending;
    }
};
}
