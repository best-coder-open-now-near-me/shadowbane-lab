#include "combat_power_entry.h"
#include <Windows.h>
#include <algorithm>
#include <cstring>
namespace wonderbane::extension::combat::power {
namespace {
bool Read(void* out, std::uintptr_t at, std::size_t size) noexcept {
    __try { std::memcpy(out, reinterpret_cast<const void*>(at), size); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
using Definition = void*(__cdecl*)(std::uint32_t);
using Rank = int(__thiscall*)(void*, std::uint32_t);
using Use = bool(__cdecl*)(std::uint32_t, int, void*, void*, const float*, Key);
struct Calls { Definition definition; Rank rank; Use use; };
struct Invocation {
    Use function;
    std::uint32_t id, rank;
    void* actor;
    void* target;
    const float* position;
    Key key;
    std::uintptr_t* frame;
    std::uintptr_t* returned;
};
static_assert(sizeof(Invocation) == 40);
// The bridge owns this stack shape. Neither host commands nor Scope::Enter can
// manufacture native frame authority. No synthetic native return address is used.
__declspec(naked) bool __cdecl Bridge(const Invocation*) {
    __asm {
        push ebp
        mov ebp, esp
        push esi
        mov esi, dword ptr [ebp + 8]
        lea eax, [ebp - 40]
        mov edx, dword ptr [esi + 32]
        mov dword ptr [edx], eax
        mov eax, offset NativeReturned
        mov edx, dword ptr [esi + 36]
        mov dword ptr [edx], eax
        push dword ptr [esi + 28]
        push dword ptr [esi + 24]
        push dword ptr [esi + 20]
        push dword ptr [esi + 16]
        push dword ptr [esi + 12]
        push dword ptr [esi + 8]
        push dword ptr [esi + 4]
        call dword ptr [esi]
    NativeReturned:
        add esp, 28
        mov edx, dword ptr [esi + 32]
        mov dword ptr [edx], 0
        mov edx, dword ptr [esi + 36]
        mov dword ptr [edx], 0
        pop esi
        mov esp, ebp
        pop ebp
        ret
    }
}
}
namespace detail {
struct Entry {
    static bool Call(Scope& scope, Use use, std::uint32_t rank, const float* position) {
        const auto& c = scope.context_;
        const Invocation invocation{use,c.power_id,rank,reinterpret_cast<void*>(c.actor),
            reinterpret_cast<void*>(c.target),position,Key{},&scope.native_frame_,&scope.native_return_};
        return Bridge(&invocation);
    }
};
}
namespace {
bool InvokeBound(Scope& scope, const Calls& calls) {
    const auto& c = scope.Binding();
    if (!scope.CanEnter()) { return false; }
    // The manager owns definitions. Lookup and use occur on one admitted native
    // owner callback; never retain them as ArcObjects or cache learned records.
    const auto definition = reinterpret_cast<std::uintptr_t>(calls.definition(c.power_id));
    const int learned = calls.rank(reinterpret_cast<void*>(c.actor), c.power_id);
    std::uint32_t id{}, category{}, target_mode{}, delivery{};
    if (!definition || learned <= 0
        || !Read(&id, definition + 0x138, sizeof(id)) || id != c.power_id
        || !Read(&category, definition + 0x204, sizeof(category)) || category > 1
        || !Read(&target_mode, definition + 0x1a8, sizeof(target_mode))
        || target_mode == 2 || target_mode == 3
        || !Read(&delivery, definition + 0x1b4, sizeof(delivery)) || delivery == 2) { return false; }
    const auto rank = static_cast<std::uint32_t>(std::min(learned, 9999));
    if (!scope.Enter(definition, rank)) { return false; }
    // Ordinary object caller supplies zero cursor position and a native zero key.
    // Key(0) is exactly {0,0}; its reviewed destructor is a no-op. A nonzero
    // key here would skip native target validation, so never prefill target_key.
    const float position[3]{};
    return detail::Entry::Call(scope, calls.use, rank, position);
}
}
bool Invoke(Scope& scope) {
    const auto image = scope.Binding().image;
    return InvokeBound(scope, {reinterpret_cast<Definition>(image + 0x16d8a0),
        reinterpret_cast<Rank>(image + 0x9b400), reinterpret_cast<Use>(image + 0x9bbf0)});
}
}
