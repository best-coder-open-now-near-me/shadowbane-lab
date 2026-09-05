#include "movement_lifetime.h"
#include "movement_native_image.h"
#include "import_hook.h"
#include <atomic>
#include <cstring>
#include <limits>
#include <utility>
namespace wonderbane::extension::movement {
namespace {
constexpr std::size_t kSlots = 32;
using Finalizer = void* (__thiscall*)(void*, std::uint32_t);
using Free = void (__cdecl*)(void*);
struct Slot { std::uint32_t* address = nullptr; std::uint32_t original = 0, hook = 0; };
struct Notice { void* pointer = nullptr; bool world = false; Notice* next = nullptr; bool admitted = false; };
struct State {
    SRWLOCK lock = SRWLOCK_INIT;
    std::uintptr_t base = 0;
    HWND window = nullptr;
    DWORD thread = 0;
    bool started = false, alive = false;
    std::atomic<bool> binding_lost{false};
    std::atomic<bool> terminal{false};
    std::atomic<std::uint64_t> watch_generation{0};
    NativeScene scene{};
    void* actor_ref = nullptr;
    void* parent_ref = nullptr;
    // Only the exact watched pointers enter the lock on ordinary free/finalizer
    // traffic. The locked recheck below captures the current watch generation.
    std::atomic<void*> fast_actor{nullptr}, fast_parent{nullptr}, fast_world{nullptr};
    Notice* destroying = nullptr;
    std::array<Slot, kSlots> slots{};
    std::atomic<std::size_t> count{0};
    Slot free_slot{};
} state;
SRWLOCK registration_lock = SRWLOCK_INIT;
struct Registration {
    Registration() noexcept { AcquireSRWLockExclusive(&registration_lock); }
    ~Registration() { ReleaseSRWLockExclusive(&registration_lock); }
};
template<class T> bool Read(std::uintptr_t address, T& out) noexcept {
    if (address < 0x10000 || address > 0x7fff0000 - sizeof(T)) { return false; }
    __try { std::memcpy(&out, reinterpret_cast<const void*>(address), sizeof(T)); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
bool Advance() noexcept { // lock held
    state.alive = false;
    if (state.scene.epoch == std::numeric_limits<std::uint64_t>::max()) {
        state.terminal = true; return false;
    }
    ++state.scene.epoch; return true;
}
void BeginNotice(Notice& notice, void* pointer, bool world) noexcept {
    const auto generation = state.watch_generation.load();
    if (!pointer || (world ? state.fast_world.load() != pointer
        : state.fast_actor.load() != pointer && state.fast_parent.load() != pointer)) { return; }
    AcquireSRWLockExclusive(&state.lock);
    const bool matches = world ? state.scene.world == reinterpret_cast<std::uintptr_t>(pointer)
        : state.actor_ref == pointer || state.parent_ref == pointer;
    if (!state.terminal && matches && generation && state.watch_generation.load() == generation) {
        // Invalidate before destruction, within this exact captured watch. No
        // callback performs a second invalidation after original call-through.
        if (state.alive) { (void)Advance(); }
        notice = {pointer, world, state.destroying, true}; state.destroying = &notice;
    }
    ReleaseSRWLockExclusive(&state.lock);
}
void EndNotice(Notice& notice) noexcept {
    if (!notice.admitted) { return; }
    AcquireSRWLockExclusive(&state.lock);
    auto** link = &state.destroying;
    while (*link && *link != &notice) { link = &(*link)->next; }
    if (*link) { *link = notice.next; }
    ReleaseSRWLockExclusive(&state.lock);
}
template<std::size_t I> void* __fastcall Finalize(void* receiver, void*, std::uint32_t flags) {
    // Per-slot immutable original: a changed receiver vtable cannot redirect an
    // already dispatched callback. State is published before the slot exchange.
    const auto original = reinterpret_cast<Finalizer>(state.slots[I].original);
    Notice notice{}; BeginNotice(notice, receiver, false);
    void* result = nullptr;
    __try { result = original(receiver, flags); }
    __finally { EndNotice(notice); }
    return result;
}
void __cdecl Deallocate(void* allocation) {
    const auto original = reinterpret_cast<Free>(state.free_slot.original);
    Notice notice{}; BeginNotice(notice, allocation, true);
    __try { original(allocation); }
    __finally { EndNotice(notice); }
}
template<std::size_t... I> auto Hooks(std::index_sequence<I...>) noexcept {
    return std::array<std::uint32_t, sizeof...(I)>{reinterpret_cast<std::uint32_t>(&Finalize<I>)...};
}
const auto hooks = Hooks(std::make_index_sequence<kSlots>{});
bool Same(const NativeScene& a, const NativeScene& b) noexcept {
    return a.actor == b.actor && a.parent == b.parent && a.world == b.world
        && a.window == b.window && a.identity == b.identity;
}
bool OnOwningThread() noexcept {
    DWORD pid = 0;
    return state.thread && GetCurrentThreadId() == state.thread
        && GetWindowThreadProcessId(state.window, &pid) == state.thread && pid == GetCurrentProcessId();
}
bool Capture(void* receiver, NativeScene& scene) noexcept {
    std::uintptr_t position = 0, pose = 0; std::uint32_t mode = 0;
    return Read(state.base + 0x16a7bfc, scene.window) && scene.window
        && scene.window == reinterpret_cast<std::uintptr_t>(receiver)
        && Read(scene.window + 0x64, mode) && mode == 2
        && Read(state.base + 0x16a2d98, scene.actor) && scene.actor
        && Read(state.base + 0x1389028, scene.world) && scene.world
        && Read(scene.actor + 0x18, scene.identity)
        && Read(scene.actor + 0x4b0, position) && Read(position, pose) && Read(pose + 8, scene.parent);
}
bool Intact(const Slot& slot) noexcept {
    std::uint32_t actual = 0;
    return slot.address && Read(reinterpret_cast<std::uintptr_t>(slot.address), actual) && actual == slot.hook;
}
void Restore(const Slot& slot) noexcept {
    if (slot.address) { (void)ReplaceImportAddressSlot(slot.address, slot.hook, slot.original); }
}
void Fail() noexcept {
    AcquireSRWLockExclusive(&state.lock);
    (void)Advance(); state.terminal = true;
    state.fast_actor = nullptr; state.fast_parent = nullptr; state.fast_world = nullptr;
    ReleaseSRWLockExclusive(&state.lock);
    // Never overwrite a foreign replacement. Records remain pinned even when
    // install rolled back after the hook became visible to a dispatched call.
    for (std::size_t i = 0; i < state.count; ++i) { Restore(state.slots[i]); }
    Restore(state.free_slot);
}
bool WatchedReferenceIntact(void* receiver) noexcept {
    if (!receiver) { return true; }
    std::uintptr_t vtable = 0; std::uint32_t release = 0;
    if (!Read(reinterpret_cast<std::uintptr_t>(receiver), vtable)
        || !Read(vtable + 8, release) || release != state.base + 0x26f49) { return false; }
    for (std::size_t i = 0; i < state.count; ++i) {
        if (reinterpret_cast<std::uintptr_t>(state.slots[i].address) == vtable + 4) {
            return Intact(state.slots[i]);
        }
    }
    return false;
}
bool Reference(void* object, void*& receiver) noexcept {
    if (!object) { receiver = nullptr; return true; }
    const auto address = reinterpret_cast<std::uintptr_t>(object);
    std::uintptr_t vbtable = 0, vtable = 0; std::uint32_t offset = 0, release = 0, finalizer = 0;
    // This is the sealed actor/parent native reference wrapper's virtual-base
    // convention. Only a reference interface using the sealed generic Release
    // (which invokes slot +4 with ECX=this, one flags argument) is supported.
    if (!Read(address + 8, vbtable) || vbtable < state.base + 0x1141000
        || vbtable > state.base + 0x12c1000 - 8 || (vbtable & 3) || !Read(vbtable + 4, offset)
        || offset > 0x10000 || (offset & 3) || !Read(address + 8 + offset, vtable)
        || vtable < state.base + 0x1141000 || vtable > state.base + 0x12c1000 - 12 || (vtable & 3)
        || !Read(vtable + 8, release) || release != state.base + 0x26f49
        || !Read(vtable + 4, finalizer)) { return false; }
    auto* slot = reinterpret_cast<std::uint32_t*>(vtable + 4);
    for (std::size_t i = 0; i < state.count; ++i) {
        if (state.slots[i].address == slot) {
            if (!Intact(state.slots[i])) { return false; }
            receiver = reinterpret_cast<void*>(address + 8 + offset); return true;
        }
    }
    if (state.count == kSlots || finalizer < state.base + 0x1000 || finalizer >= state.base + 0x1141000) { return false; }
    auto& record = state.slots[state.count];
    record = {slot, finalizer, hooks[state.count]}; ++state.count;
    if (ReplaceImportAddressSlot(slot, record.original, record.hook) != ERROR_SUCCESS) { return false; }
    receiver = reinterpret_cast<void*>(address + 8 + offset); return true;
}
void Gap() noexcept {
    AcquireSRWLockExclusive(&state.lock);
    if (state.alive) { (void)Advance(); }
    ReleaseSRWLockExclusive(&state.lock);
}
} // namespace
bool StartNativeMovementLifetime(HWND window) noexcept {
    // Registration belongs to the same native-update owner; no loader-lock wait.
    Registration registration;
    DWORD pid = 0; const auto thread = GetWindowThreadProcessId(window, &pid);
    if (!thread || thread != GetCurrentThreadId() || pid != GetCurrentProcessId()
        || state.started || state.terminal) { return false; }
    state.started = true; state.window = window; state.thread = thread;
    if (!VerifyNativeMovementImage(state.base)) { Fail(); return false; }
    HMODULE pinned = nullptr;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
        reinterpret_cast<LPCWSTR>(&StartNativeMovementLifetime), &pinned)) { Fail(); return false; }
    const auto crt = GetModuleHandleW(L"MSVCRT.dll");
    const auto original = crt ? GetProcAddress(crt, "free") : nullptr;
    auto* slot = FindImportAddressSlot(reinterpret_cast<std::uint8_t*>(state.base), 0x1766000, "MSVCRT.dll", "free");
    if (!original || reinterpret_cast<std::uintptr_t>(slot) != state.base + 0x16b0504) { Fail(); return false; }
    state.free_slot = {slot, reinterpret_cast<std::uint32_t>(original), reinterpret_cast<std::uint32_t>(&Deallocate)};
    if (ReplaceImportAddressSlot(slot, state.free_slot.original, state.free_slot.hook) != ERROR_SUCCESS) { Fail(); return false; }
    return true;
}
bool ObserveNativeMovementLifetime(void* native_window, NativeScene& out) noexcept {
    out = {};
    if (!OnOwningThread() || !state.started || state.terminal) { return false; }
    if (state.binding_lost || !Intact(state.free_slot)) { Fail(); return false; }
    NativeScene scene{}, again{};
    if (!Capture(native_window, scene)) { Gap(); return false; }
    void* actor_ref = nullptr; void* parent_ref = nullptr;
    if (!Reference(reinterpret_cast<void*>(scene.actor), actor_ref)
        || !Reference(reinterpret_cast<void*>(scene.parent), parent_ref)) { Fail(); return false; }
    if (!Capture(native_window, again) || !Same(scene, again)) { Gap(); return false; }
    AcquireSRWLockExclusive(&state.lock);
    bool destroying = false;
    for (auto* n = state.destroying; n; n = n->next) {
        destroying = destroying || (n->world ? scene.world == reinterpret_cast<std::uintptr_t>(n->pointer)
            : actor_ref == n->pointer || parent_ref == n->pointer);
    }
    if (!state.terminal && !destroying) {
        if (!state.alive || !Same(state.scene, scene)) {
            if (Advance()) {
                scene.epoch = state.scene.epoch; state.scene = scene;
                state.actor_ref = actor_ref; state.parent_ref = parent_ref;
                state.fast_actor = actor_ref; state.fast_parent = parent_ref;
                state.fast_world = reinterpret_cast<void*>(scene.world);
                state.watch_generation = scene.epoch; state.alive = true;
            }
        }
        if (state.alive) { out = state.scene; }
    }
    ReleaseSRWLockExclusive(&state.lock);
    return out.epoch != 0;
}
bool NativeMovementLifetimeCurrent(const NativeScene& scene) noexcept {
    AcquireSRWLockExclusive(&state.lock);
    bool current = state.alive && !state.terminal && !state.binding_lost && scene.epoch
        && scene.epoch == state.scene.epoch && Same(scene, state.scene);
    if (current && (!Intact(state.free_slot) || !WatchedReferenceIntact(state.actor_ref)
        || !WatchedReferenceIntact(state.parent_ref))) {
        // Callbacks may consult Current from a different thread. Latch rejection
        // immediately; only the owning Observe/Retire performs slot cleanup.
        state.binding_lost = true; (void)Advance(); current = false;
    }
    ReleaseSRWLockExclusive(&state.lock);
    return current;
}
void RetireNativeMovementLifetime() noexcept {
    if (!OnOwningThread() || !state.started || state.terminal) { return; }
    Fail();
}
} // namespace wonderbane::extension::movement
