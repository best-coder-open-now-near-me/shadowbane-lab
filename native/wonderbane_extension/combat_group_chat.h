#pragma once
#include "combat_party.h"
#include "actor_action_fence.h"
#include <array>
#include <cstdint>
namespace wonderbane::extension::combat::group_chat {
inline constexpr std::size_t maximum_text = 88;
enum class Result { denied, queued, uncertain };
struct Receipt {
    Result result=Result::denied;
    bool native_entered=false, append_observed=false, ownership_quarantined=false;
};
// Per immutable command; persists through native exceptions. Never retry a
// quarantined constructor/send/destructor or reuse its potentially owned data.
struct State {
    std::array<std::uint32_t,6> text{};
    void* message=nullptr;
    bool attempted=false, text_constructed=false, message_constructed=false, quarantined=false;
};
struct Context {
    std::uintptr_t image{},writer{},container{};
    party::Snapshot group{};
    std::array<char,maximum_text+1> text{};
    bool (*current)(void*) noexcept=nullptr;
    bool (*append_current)(void*) noexcept=nullptr;
    void* owner=nullptr;
};
// Observed roster context, not a server group/session nonce. Preserve native
// list order and object identities; names/resources never grant recipient authority.
inline bool Identity(const party::Snapshot& group,actor::fence::Digest& out) noexcept {
    if(!group.valid||!group.count||group.count>party::kMaximumMembers)return false;
    std::array<std::uint32_t,55> words{0x315047U,static_cast<std::uint32_t>(group.scene.window),
        static_cast<std::uint32_t>(group.manager),static_cast<std::uint32_t>(group.sentinel),
        static_cast<std::uint32_t>(group.count)};
    for(std::size_t i=0;i<group.count;++i){const auto& m=group.members[i];const auto j=5+5*i;
        words[j]=static_cast<std::uint32_t>(m.node);words[j+1]=static_cast<std::uint32_t>(m.entry);
        words[j+2]=m.key[0];words[j+3]=m.key[1];words[j+4]=m.role;
    }
    return actor::fence::Hash(words.data(),(5+5*group.count)*sizeof(words[0]),out);
}
// Group channel only. No command parser, target/selection or user-input path.
Receipt Invoke(const Context&,State&,Receipt&) noexcept;
bool Start(std::uintptr_t image) noexcept;
bool Ready() noexcept;
}
