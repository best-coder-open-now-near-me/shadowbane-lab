#include "combat_melee_entry.h"
#include "combat_stance.h"
#include <array>
#include <stdexcept>

namespace wonderbane::extension::combat::melee {
namespace {
template<class T> T& At(void* object, std::uintptr_t offset) {
    return *reinterpret_cast<T*>(reinterpret_cast<std::uintptr_t>(object) + offset);
}
void* VirtualBase(void* object, std::uintptr_t slot) {
    const auto table = At<std::uintptr_t>(object, 8);
    const auto offset = *reinterpret_cast<const std::int32_t*>(table + slot);
    return reinterpret_cast<void*>(reinterpret_cast<std::uintptr_t>(object) + 8 + offset);
}
template<class F> F Function(std::uintptr_t image, std::uintptr_t rva) {
    return reinterpret_cast<F>(image + rva);
}
using Getter = std::uint32_t (__thiscall*)(void*);
using Predicate = bool (__thiscall*)(void*);
using Mask = bool (__thiscall*)(void*, std::uint32_t);
using Iterator = std::array<std::uintptr_t, 3>;
using End = Iterator* (__thiscall*)(void*, Iterator*);
using Find = Iterator* (__thiscall*)(void*, Iterator*, const std::uint32_t*);
using Key = std::array<std::uint32_t, 2>;
using ReadKey = Key* (__thiscall*)(void*, Key*);
using Retain = void (__thiscall*)(void*, void**);
using Sender = void (__thiscall*)(void*, void*);
using Controller = void* (__cdecl*)();
}
void Release(void*& request) {
    auto* object = request;
    request = nullptr; // The native release consumes this reference exactly once.
    if (!object || object == reinterpret_cast<void*>(static_cast<std::uintptr_t>(-1))) { return; }
    using Drop = void (__thiscall*)(void*, void**);
    reinterpret_cast<Drop>(At<std::uintptr_t*>(object, 0)[2])(object, &request);
}
bool Invoke(std::uintptr_t image, void* actor, void* target, submission::Scope& scope,
    void*& request, void*& transfer, Admission current, void* context) {
    if (!image || !actor || !target || !current || request || transfer || !current(context)) {
        return false;
    }
    // Exact 1.3.38.12/13 ordinary1551 guard sequence (7d3c10..7d3e85).
    // Only its two selected-global reads become this independently held target.
    // Keep native mask, stance, actor-state and peace/property semantics intact.
    const auto mask = Function<Mask>(image, 0xc9c80);
    if (mask(VirtualBase(target, 0xc), 0x20) || !current(context)) { return false; }
    std::uint32_t mode{};
    if (!stance::Prepare(actor, stance::Native(image), current, context, mode)
        || mode != 2 || At<std::uintptr_t>(actor, 0xb04)
        || Function<Getter>(image, 0x611d0)(actor) == 1 || !current(context)
        || !mask(VirtualBase(target, 0xc), 0x2000)) { return false; }
    if (mask(VirtualBase(target, 0xc), 0x10)) {
        bool check_peace = true;
        if (At<unsigned char>(target, 0x680)) {
            // target+34 is a property map, not a name. Compare native iterator
            // positions exactly; the special property key's meaning is not guessed.
            Iterator end{}, found{};
            auto* properties = reinterpret_cast<void*>(reinterpret_cast<std::uintptr_t>(target) + 0x34);
            Function<End>(image, 0x83920)(properties, &end);
            Function<Find>(image, 0x141330)(properties, &found,
                reinterpret_cast<const std::uint32_t*>(image + 0x137314c));
            check_peace = found[0] != end[0];
        }
        if (!current(context)) { return false; }
        if (check_peace) {
            const auto actor_peace = reinterpret_cast<Predicate>(At<std::uintptr_t*>(actor, 0)[0xdc / 4]);
            const auto target_peace = reinterpret_cast<Predicate>(At<std::uintptr_t*>(target, 0)[0xdc / 4]);
            if (actor_peace(actor) || !current(context) || target_peace(target)) { return false; }
        }
    }
    if (!current(context)) { return false; }
    // These native compatibility guards are qualified no-ops, not locks.
    Function<Predicate>(image, 0x12dd80)(VirtualBase(target, 8));
    Key key{};
    Function<ReadKey>(image, 0x1125d0)(target, &key);
    Function<Predicate>(image, 0x12ddc0)(VirtualBase(target, 8));
    if (!current(context)) { return false; }
    if (scope.Factory(actor, &request, target, key.data(), true) != &request) {
        throw std::runtime_error("native melee factory changed owned-output ABI");
    }
    if (!current(context)) { return false; }
    transfer = request;
    if (transfer && transfer != reinterpret_cast<void*>(static_cast<std::uintptr_t>(-1))) {
        Function<Retain>(image, 0x131190)(transfer, &transfer);
    }
    if (!current(context)) { return false; }
    auto* controller = Function<Controller>(image, 0x7f4490)();
    if (!current(context)) { return false; }
    auto* argument = transfer; transfer = nullptr;
    Function<Sender>(image, 0x7f4da0)(controller, argument);
    Release(request); // Factory ownership survives the entire queue append.
    if (!current(context)) { return false; }
    scope.Followup(actor);
    return true;
}
}
