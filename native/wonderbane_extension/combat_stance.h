#pragma once
#include <cstdint>

namespace wonderbane::extension::combat::stance {
using Admission = bool (*)(void*) noexcept;
using Getter = std::uint32_t (__thiscall*)(void*);
using Toggle = void (__thiscall*)(void*, bool, bool);
struct Calls { Getter mode{}; Toggle toggle{}; };
inline Calls Native(std::uintptr_t image) noexcept {
    return {reinterpret_cast<Getter>(image + 0x613c0),
        reinterpret_cast<Toggle>(image + 0x4f100)};
}
// Ordinary 1551 enters combat only from peace mode1. Preserve its getter / forced
// native toggle / getter sequence; callers apply their own native mode predicate.
// The caller must own cleanup BEFORE this potentially mutating prerequisite.
inline bool Prepare(void* actor, const Calls& calls, Admission current, void* owner,
    std::uint32_t& resulting_mode) {
    if (!actor || !calls.mode || !calls.toggle || !current || !current(owner)) { return false; }
    if (calls.mode(actor) == 1) {
        if (!current(owner)) { return false; }
        calls.toggle(actor, true, true);
    }
    if (!current(owner)) { return false; }
    resulting_mode = calls.mode(actor);
    return current(owner);
}
}
