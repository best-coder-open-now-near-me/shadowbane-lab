#pragma once
#include "combat_party.h"
#include <array>
#include <cstdint>
namespace wonderbane::extension::combat::group_chat {
inline constexpr std::size_t maximum_text = 120;
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
// Group channel only. No command parser, target/selection or user-input path.
Receipt Invoke(const Context&,State&,Receipt&) noexcept;
bool Start(std::uintptr_t image) noexcept;
bool Ready() noexcept;
}
