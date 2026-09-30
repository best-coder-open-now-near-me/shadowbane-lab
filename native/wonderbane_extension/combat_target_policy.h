#pragma once
#include "combat_party.h"

namespace wonderbane::extension::combat::policy {
using Key = party::Key;
enum class Outcome { invalid, protected_target, eligible };
enum class Role : std::size_t { merchant, shopkeeper, banker, trainer, minion, pet, count };
struct Descriptor {
    std::uint32_t key{};
    std::uintptr_t bucket{}, node{}, value{};
    Key owner{};
    bool present{}, enabled{};
    bool operator==(const Descriptor&) const = default;
};
struct Object {
    std::uintptr_t address{}, table{}, buckets{};
    Key key{};
    std::uint32_t bits{};
    float health{}, maximum{};
    std::array<Descriptor, static_cast<std::size_t>(Role::count)> descriptors{};
    bool operator==(const Object&) const = default;
};
struct Snapshot {
    Object object{};
    party::Snapshot party{};
    Outcome outcome = Outcome::invalid;
};
// Exact reviewed image and an already retained object are caller preconditions.
// Owner-update thread only; two complete bounded captures, no allocation/native
// callback. Never run under an outbound queue lock. This establishes conservative
// NPC admission, not complete hostility, ownership, or native combat legality.
Outcome Capture(HWND owner_window, std::uintptr_t image, const movement::NativeScene& scene,
    void* retained_target, Key expected, Snapshot& output) noexcept;
}
