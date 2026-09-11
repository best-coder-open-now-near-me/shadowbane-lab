#include "movement_lifetime.h"
#include "movement_native_image.h"
#include "movement_lifetime_bindings.h"
#include "import_hook.h"
#include <atomic>
#include <cstring>
#include <limits>
#include <utility>
namespace wonderbane::extension::movement {
namespace {
constexpr std::size_t kSlots = kLifetimeBindings.size();
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
    std::atomic<bool> arming{false};
    std::atomic<std::uint32_t> callbacks_active{0};
    bool arming_dirty = false;
    std::atomic<bool> terminal{false};
    std::atomic<std::uint64_t> watch_generation{0};
    NativeScene scene{};
    std::atomic<bool> diagnostics_enabled{false};
    LifetimeDiagnostics diagnostics{};
    bool diagnostic_episode = false;
    std::uint64_t observed_epoch = 0;
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
std::uint32_t Changed(const NativeScene& a, const NativeScene& b) noexcept {
    return (a.actor != b.actor ? 1U : 0U) | (a.parent != b.parent ? 2U : 0U)
        | (a.world != b.world ? 4U : 0U) | (a.window != b.window ? 8U : 0U)
        | (a.identity[0] != b.identity[0] ? 16U : 0U) | (a.identity[1] != b.identity[1] ? 32U : 0U);
}
void Diagnostic(LifetimeCause cause, std::uint64_t previous, std::uint32_t outcome = 0,
    LifetimeStage stage = LifetimeStage::none, std::uint32_t changed = 0,
    std::uint32_t valid = 0, std::uint32_t role = 0, std::uint32_t flags = 0,
    std::uint64_t observed = 0, std::uint64_t captured_generation = UINT64_MAX) noexcept { // state.lock held
    if (!state.diagnostics_enabled || state.diagnostics.write_sequence == MAXLONGLONG) { return; }
    auto& d = state.diagnostics;
    LifetimeRecord r{};
    r.sequence = ++d.write_sequence; r.tick_ms = GetTickCount64();
    r.previous_epoch = previous; r.epoch = state.scene.epoch;
    r.observed_epoch = outcome == 2 ? observed : state.observed_epoch;
    r.watch_generation = captured_generation == UINT64_MAX ? state.watch_generation.load() : captured_generation;
    r.cause = static_cast<std::uint32_t>(cause); r.outcome = outcome;
    r.failure_stage = static_cast<std::uint32_t>(stage); r.changed_fields = changed;
    r.valid_fields = valid; r.notice_role = role; r.finalizer_flags = flags;
    r.thread_id = GetCurrentThreadId(); d.current = r;
    const bool disruption = cause != LifetimeCause::stable && cause != LifetimeCause::first_watch && cause != LifetimeCause::rearmed;
    if (disruption && !state.diagnostic_episode) {
        d.first_invalidation = r; state.diagnostic_episode = true;
    }
    if (outcome == 2) {
        if (state.alive && observed == state.scene.epoch) { state.diagnostic_episode = false; }
        state.observed_epoch = observed;
    }
    else if (outcome == 1) { state.observed_epoch = 0; }
    d.events[(r.sequence - 1) % d.events.size()] = r;
}
#ifdef WONDERBANE_MOVEMENT_LIFETIME_TESTING
void (*notice_barrier)() = nullptr;
#endif
void BeginNotice(Notice& notice, void* pointer, bool world, std::uint32_t flags = 0) noexcept {
    const bool arming = state.arming.load();
    const auto generation = state.watch_generation.load();
    if (!arming && (!pointer || (world ? state.fast_world.load() != pointer
        : state.fast_actor.load() != pointer && state.fast_parent.load() != pointer))) { return; }
#ifdef WONDERBANE_MOVEMENT_LIFETIME_TESTING
    if (notice_barrier) { notice_barrier(); }
#endif
    AcquireSRWLockExclusive(&state.lock);
    // Interference only rejects an unpublished snapshot; an arbitrary free is
    // never authority to assign a scene or invalidate an unrelated live watch.
    if (state.arming) { state.arming_dirty = true; }
    const bool matches = world ? state.scene.world == reinterpret_cast<std::uintptr_t>(pointer)
        : state.actor_ref == pointer || state.parent_ref == pointer;
    // A callback entering after the publisher's active-count check waits on
    // this lock. Its original has not run: if its pointer is now watched, it
    // invalidates that just-published watch before destruction. Completed old
    // callbacks never revisit BeginNotice and cannot take this path.
    if (!state.terminal && pointer && matches && (arming || (generation && state.watch_generation.load() == generation))) {
        // Invalidate before destruction, within this exact captured watch. No
        // callback performs a second invalidation after original call-through.
        const auto previous = state.scene.epoch;
        if (state.alive) { (void)Advance(); }
        const auto role = world ? 4U : (state.actor_ref == pointer ? 1U : 0U) | (state.parent_ref == pointer ? 2U : 0U);
        Diagnostic(world ? LifetimeCause::world_notice : LifetimeCause::reference_notice,
            previous, 0, LifetimeStage::none, 0, 0, role, flags, 0, generation);
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
    ++state.callbacks_active;
    const auto original = reinterpret_cast<Finalizer>(state.slots[I].original);
    Notice notice{}; BeginNotice(notice, receiver, false, flags);
    void* result = nullptr;
    __try { result = original(receiver, flags); }
    __finally { EndNotice(notice); --state.callbacks_active; }
    return result;
}
void __cdecl Deallocate(void* allocation) {
    ++state.callbacks_active;
    const auto original = reinterpret_cast<Free>(state.free_slot.original);
    Notice notice{}; BeginNotice(notice, allocation, true);
    __try { original(allocation); }
    __finally { EndNotice(notice); --state.callbacks_active; }
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
struct CaptureInfo { LifetimeStage stage = LifetimeStage::none; std::uint32_t valid = 0; };
bool Capture(void* receiver, NativeScene& scene, CaptureInfo& info) noexcept {
    std::uintptr_t position = 0, pose = 0; std::uint32_t mode = 0;
    info = {}; info.stage = LifetimeStage::window;
    if (!Read(state.base + 0x16a7bfc, scene.window) || !scene.window) { return false; }
    info.valid |= 8; info.stage = LifetimeStage::receiver;
    if (scene.window != reinterpret_cast<std::uintptr_t>(receiver)) { return false; }
    info.stage = LifetimeStage::mode;
    if (!Read(scene.window + 0x64, mode) || mode != 2) { return false; }
    info.stage = LifetimeStage::actor;
    if (!Read(state.base + 0x16a2d98, scene.actor) || !scene.actor) { return false; }
    info.valid |= 1; info.stage = LifetimeStage::world;
    if (!Read(state.base + 0x1389028, scene.world) || !scene.world) { return false; }
    info.valid |= 4; info.stage = LifetimeStage::identity;
    if (!Read(scene.actor + 0x18, scene.identity)) { return false; }
    info.valid |= 48; info.stage = LifetimeStage::position;
    if (!Read(scene.actor + 0x4b0, position)) { return false; }
    info.stage = LifetimeStage::pose;
    if (!Read(position, pose)) { return false; }
    info.stage = LifetimeStage::parent;
    if (!Read(pose + 8, scene.parent)) { return false; }
    info.valid |= 2; info.stage = LifetimeStage::none; return true;
}
bool Intact(const Slot& slot) noexcept {
    std::uint32_t actual = 0;
    return slot.address && Read(reinterpret_cast<std::uintptr_t>(slot.address), actual) && actual == slot.hook;
}
void Restore(const Slot& slot) noexcept {
    if (slot.address) { (void)ReplaceImportAddressSlot(slot.address, slot.hook, slot.original); }
}
void Fail(LifetimeCause cause = LifetimeCause::binding_lost, LifetimeStage stage = LifetimeStage::binding) noexcept {
    AcquireSRWLockExclusive(&state.lock);
    const auto previous = state.scene.epoch;
    (void)Advance(); state.terminal = true;
    Diagnostic(cause, previous, 1, stage);
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
    // No new type can enter between capture and registration: every supported
    // slot must already have been installed by Start.
    return false;
}
bool InstallReference(std::uint32_t* slot, std::uint32_t original) noexcept {
    const auto index = state.count.load();
    if (index == kSlots) { return false; }
    auto& record = state.slots[index];
    record = {slot, original, hooks[index]}; state.count = index + 1;
    return ReplaceImportAddressSlot(slot, record.original, record.hook) == ERROR_SUCCESS;
}
bool UnrecordedCallbacks() noexcept { // lock held
    std::uint32_t recorded = 0;
    for (auto* notice = state.destroying; notice; notice = notice->next) { ++recorded; }
    // Already watched originals have exact object notices. A replacement with
    // disjoint pointers may proceed while those calls are held. Any callback
    // without a published notice makes a new snapshot uncertain.
    return state.callbacks_active.load() != recorded;
}
struct Arm {
    bool admitted = false;
    Arm() noexcept {
        AcquireSRWLockExclusive(&state.lock);
        state.arming_dirty = false; state.arming = true;
        admitted = !state.terminal && !UnrecordedCallbacks();
        if (!admitted) {
            state.arming = false;
            Diagnostic(LifetimeCause::arm_rejected, state.scene.epoch, 1, LifetimeStage::unrecorded_callbacks);
        }
        ReleaseSRWLockExclusive(&state.lock);
    }
    ~Arm() {
        if (!admitted) { return; }
        AcquireSRWLockExclusive(&state.lock);
        state.arming = false;
        ReleaseSRWLockExclusive(&state.lock);
    }
};
#ifdef WONDERBANE_MOVEMENT_LIFETIME_TESTING
void (*capture_barrier)(int) = nullptr;
void CaptureBarrier(int phase) { if (capture_barrier) { capture_barrier(phase); } }
#else
void CaptureBarrier(int) noexcept {}
#endif

void Gap(const CaptureInfo& info, LifetimeCause cause = LifetimeCause::capture_failed,
    std::uint32_t changed = 0) noexcept {
    AcquireSRWLockExclusive(&state.lock);
    const auto previous = state.scene.epoch;
    if (state.alive) { (void)Advance(); }
    Diagnostic(cause, previous, 1, info.stage, changed, info.valid);
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
    for (const auto binding : kLifetimeBindings) {
        auto* finalizer_slot = reinterpret_cast<std::uint32_t*>(state.base + binding.slot);
        std::uint32_t release = 0;
        if (!Read(state.base + binding.slot + 4, release) || release != state.base + 0x26f49
            || !InstallReference(finalizer_slot, static_cast<std::uint32_t>(state.base + binding.original))) {
            Fail(); return false;
        }
    }
    return true;
}
bool ObserveNativeMovementLifetime(void* native_window, NativeScene& out) noexcept {
    out = {};
    if (!OnOwningThread()) { return false; }
    if (!state.started || state.terminal) {
        if (state.diagnostics_enabled) {
            AcquireSRWLockExclusive(&state.lock);
            Diagnostic(LifetimeCause::terminal, state.scene.epoch, 1);
            ReleaseSRWLockExclusive(&state.lock);
        }
        return false;
    }
    if (state.binding_lost || !Intact(state.free_slot)) { Fail(); return false; }
    NativeScene scene{}, again{}; CaptureInfo info{};
    if (!Capture(native_window, scene, info)) { Gap(info); return false; }
    // The existing watch already observes destruction. Only first/replacement
    // arming needs the conservative short fence around native snapshot reads.
    AcquireSRWLockShared(&state.lock);
    if (state.alive && Same(state.scene, scene)) { scene.epoch = state.scene.epoch; }
    ReleaseSRWLockShared(&state.lock);
    if (scene.epoch && NativeMovementLifetimeCurrent(scene)) {
        out = scene;
        if (state.diagnostics_enabled) {
            AcquireSRWLockExclusive(&state.lock);
            Diagnostic(LifetimeCause::stable, state.scene.epoch, 2, LifetimeStage::none, 0, 63, 0, 0, scene.epoch);
            ReleaseSRWLockExclusive(&state.lock);
        }
        return true;
    }
    if (state.binding_lost) { Fail(); return false; }
    Arm arm;
    if (!arm.admitted) { return false; }
    if (!Capture(native_window, scene, info)) { Gap(info); return false; }
    CaptureBarrier(1);
    void* actor_ref = nullptr; void* parent_ref = nullptr;
    if (!Reference(reinterpret_cast<void*>(scene.actor), actor_ref)
        || !Reference(reinterpret_cast<void*>(scene.parent), parent_ref)) {
        Fail(LifetimeCause::binding_lost, LifetimeStage::reference); return false;
    }
    if (!Capture(native_window, again, info)) { Gap(info); return false; }
    if (!Same(scene, again)) { Gap(info, LifetimeCause::capture_changed, Changed(scene, again)); return false; }
    CaptureBarrier(2);
    AcquireSRWLockExclusive(&state.lock);
    auto stage = state.arming_dirty ? LifetimeStage::overlapping_callback : LifetimeStage::unrecorded_callbacks;
    bool destroying = state.arming_dirty || UnrecordedCallbacks();
    for (auto* n = state.destroying; n; n = n->next) {
        const bool matching = n->world ? scene.world == reinterpret_cast<std::uintptr_t>(n->pointer)
            : actor_ref == n->pointer || parent_ref == n->pointer;
        if (matching) { destroying = true; stage = LifetimeStage::matching_destruction; }
    }
    CaptureBarrier(3);
    const auto previous = state.scene.epoch;
    const auto changed = Changed(state.scene, scene);
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
        Diagnostic(out.epoch ? (previous == 0 ? LifetimeCause::first_watch
                : changed ? LifetimeCause::tuple_changed : LifetimeCause::rearmed)
            : LifetimeCause::exhausted, previous, out.epoch ? 2U : 1U,
            LifetimeStage::none, changed, 63, 0, 0, out.epoch);
    } else {
        Diagnostic(LifetimeCause::arm_rejected, previous, 1, stage, changed, 63);
    }
    state.arming = false;
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
        const auto previous = state.scene.epoch;
        state.binding_lost = true; (void)Advance(); current = false;
        Diagnostic(LifetimeCause::binding_lost, previous, 0, LifetimeStage::binding);
    }
    ReleaseSRWLockExclusive(&state.lock);
    return current;
}
void RetireNativeMovementLifetime() noexcept {
    if (!OnOwningThread() || !state.started || state.terminal) { return; }
    Fail(LifetimeCause::terminal);
}
void EnableNativeMovementLifetimeDiagnostics(bool enabled) noexcept { state.diagnostics_enabled = enabled; }
bool ReadNativeMovementLifetimeDiagnostics(LifetimeDiagnostics& out) noexcept {
    if (!state.diagnostics_enabled || !TryAcquireSRWLockShared(&state.lock)) { return false; }
    out = state.diagnostics;
    ReleaseSRWLockShared(&state.lock); return true;
}
} // namespace wonderbane::extension::movement
