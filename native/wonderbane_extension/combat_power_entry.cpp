#include "combat_power_entry.h"
#include "combat_stance.h"
#include <Windows.h>
#include <algorithm>
#include <cstring>
#include <cmath>
namespace wonderbane::extension::combat::power {
namespace {
bool Read(void* out, std::uintptr_t at, std::size_t size) noexcept {
    __try { std::memcpy(out, reinterpret_cast<const void*>(at), size); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
using Definition = void*(__cdecl*)(std::uint32_t);
using Rank = int(__thiscall*)(void*, std::uint32_t);
using Use = bool(__cdecl*)(std::uint32_t, int, void*, void*, const float*, Key);
using AvailabilityReader = Availability(*)(std::uintptr_t,std::uintptr_t,std::uint32_t) noexcept;
struct Calls { Definition definition; Rank rank; Use use; stance::Calls stance; AvailabilityReader availability; };
Availability NativeAvailability(std::uintptr_t image,std::uintptr_t actor,std::uint32_t id) noexcept {
    return readiness::Observe(image,actor,id,[](std::uintptr_t at,auto& value) noexcept {
        return Read(&value,at,sizeof(value));
    });
}
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
    static void Observe(Scope& scope, std::uintptr_t definition, std::uint32_t required_mode) noexcept {
        const auto error=GetLastError();
        auto& value=scope.receipt_.observation;
        std::uint16_t flags{};
        if(Read(&flags,definition+0x274,sizeof(flags))){
            value.definition_known=true;value.required_mode=required_mode;value.definition_flags=flags;
        }
        std::uintptr_t state{},after{};std::array<std::uint32_t,4> first{},second{};
        if(Read(&state,scope.context_.actor+0xad0,sizeof(state))&&state>=0x10000&&state<=0x7fff0000-0x20
            &&!(state&3)&&Read(first.data(),state+0x10,sizeof(first))&&Read(second.data(),state+0x10,sizeof(second))
            &&first==second&&Read(&after,scope.context_.actor+0xad0,sizeof(after))&&state==after){
            value.state_known=true;value.initiation_state=first[0];value.actor_mode=first[2];value.state_aux=first[3];
        }
        scope.PublishObservation();SetLastError(error);
    }
    static bool Call(Scope& scope, Use use, std::uint32_t rank, const float* position) {
        const auto& c = scope.context_;
        const Invocation invocation{use,c.power_id,rank,reinterpret_cast<void*>(c.actor),
            reinterpret_cast<void*>(c.Recipient()),position,Key{},&scope.native_frame_,&scope.native_return_};
        scope.receipt_.observation.use_called=true;scope.PublishObservation();
        const bool result=Bridge(&invocation);
        const auto error=GetLastError();
        scope.receipt_.observation.use_returned=true;scope.receipt_.observation.use_value=result;
        scope.PublishObservation();SetLastError(error);return result;
    }
};
}
namespace {
bool CurrentScope(void* scope) noexcept { return static_cast<Scope*>(scope)->Current(); }
bool InvokeBound(Scope& scope, const Calls& calls) {
    const auto& c = scope.Binding();
    if (!scope.CanEnter()) { return false; }
    // The manager owns definitions. Lookup and use occur on one admitted native
    // owner callback; never retain them as ArcObjects or cache learned records.
    const auto definition = reinterpret_cast<std::uintptr_t>(calls.definition(c.power_id));
    const int learned = calls.rank(reinterpret_cast<void*>(c.actor), c.power_id);
    std::uint32_t id{}, category{}, target_mode{}, delivery{}, required_mode{};
    if (!definition || learned <= 0
        || !Read(&id, definition + 0x138, sizeof(id)) || id != c.power_id
        || !Read(&category, definition + 0x204, sizeof(category)) || category > 1
        || !Read(&target_mode, definition + 0x1a8, sizeof(target_mode))
        || !Read(&delivery, definition + 0x1b4, sizeof(delivery))
        || !Read(&required_mode, definition + 0x1f0, sizeof(required_mode))) { return false; }
    if (c.target_mode == TargetMode::self) {
        if (target_mode != 2 || delivery != 0) { return false; }
    } else if (c.target_mode != TargetMode::engagement_object
        || target_mode == 2 || target_mode == 3 || delivery == 2) { return false; }
    const auto rank = static_cast<std::uint32_t>(std::min(learned, 9999));
    // Qualified refusal before ANY stance/Use effects. Later native refusal stays
    // entered uncertainty; neither a return bool nor a timer guesses no entry.
    const auto availability_epoch=InitiationEpoch();
    if (!calls.availability || !scope.AdmitAvailability(
            calls.availability(c.image,c.actor,c.power_id),availability_epoch)) { return false; }
    // Native PreparePower4e0be..4e133 uses +1f0: 1 requires signed mode>=2,
    // 2 requires mode<=1, 3 permits either. Only the first requires combat stance;
    // category0/self also includes unrelated buffs and is not a stance classifier.
    // Record entry BEFORE the native toggle, which can mutate and reenter even if
    // later power admission fails. No-entry retry must never hide that mutation.
    detail::Entry::Observe(scope,definition,required_mode);
    if (!scope.Enter(definition, rank)) { return false; }
    if (required_mode == 1) {
        std::uint32_t mode{};
        if (!stance::Prepare(reinterpret_cast<void*>(c.actor), calls.stance,
                CurrentScope, &scope, mode) || static_cast<std::int32_t>(mode) < 2) { return false; }
    }
    if (!scope.Current()) { return false; }
    // Ordinary object caller supplies zero cursor position and a native zero key.
    // Key(0) is exactly {0,0}; its reviewed destructor is a no-op. A nonzero
    // key here would skip native target validation, so never prefill target_key.
    const float position[3]{};
    return detail::Entry::Call(scope, calls.use, rank, position);
}
}
bool ReadSelfInitiation(std::uintptr_t image, std::uintptr_t actor, std::uint32_t id,
    InitiationDefinition& out) {
    using Curve = double(__thiscall*)(void*, std::uint32_t, std::uint32_t);
    const auto lookup = reinterpret_cast<Definition>(image + 0x16d8a0);
    const auto rank = reinterpret_cast<Rank>(image + 0x9b400);
    const auto curve = reinterpret_cast<Curve>(image + 0x1725b0);
    const auto definition = reinterpret_cast<std::uintptr_t>(lookup(id));
    const int learned = rank(reinterpret_cast<void*>(actor), id);
    std::uint32_t actual{}, category{}, recipient{}, delivery{};
    if (!id || !definition || learned <= 0
        || !Read(&actual, definition + 0x138, 4) || actual != id
        || !Read(&category, definition + 0x204, 4) || category > 1
        || !Read(&recipient, definition + 0x1a8, 4) || recipient != 2
        || !Read(&delivery, definition + 0x1b4, 4) || delivery != 0) { return false; }
    const auto capped = static_cast<std::uint32_t>(std::min(learned, 9999));
    const double seconds = curve(reinterpret_cast<void*>(definition), 3, capped);
    if (!std::isfinite(seconds) || seconds < 0 || lookup(id) != reinterpret_cast<void*>(definition)
        || rank(reinterpret_cast<void*>(actor), id) != learned) { return false; }
    out = {definition, capped, seconds}; return true;
}
bool Invoke(Scope& scope) {
    const auto image = scope.Binding().image;
    return InvokeBound(scope, {reinterpret_cast<Definition>(image + 0x16d8a0),
        reinterpret_cast<Rank>(image + 0x9b400), reinterpret_cast<Use>(image + 0x9bbf0),
        stance::Native(image),NativeAvailability});
}
}
