#define WONDERBANE_MOVEMENT_LIFETIME_TESTING 1
#include "movement_lifetime.cpp"
#include "movement_native_stop.h"
#include <iostream>
#include <thread>
namespace wm = wonderbane::extension::movement;
namespace {
int failures = 0;
void Check(bool ok, const char* message) { if (!ok) { ++failures; std::cerr << message << '\n'; } }
std::atomic<int> free_calls{0}, ref_calls{0};
std::atomic<bool> hold_ref{false}, hold_free{false}, forwarded{true};
HANDLE entered = nullptr, release_call = nullptr;
bool fail_install = false, fail_door_install = false;
std::atomic<int> append_calls{0}, reset_calls{0}, load_calls{0};
std::atomic<bool> hold_door{false}, door_arguments{true};
void* expected_structure = nullptr;
void (*during_door_reset)() = nullptr;
void __fastcall OriginalDoorLoad(void* receiver, void*) {
    ++load_calls;
    if (receiver != expected_structure) { door_arguments = false; }
    wm::DoorCollectionAdmission::ReadLease lease;
    if (wm::state.door_admission.TryRead(lease)) { door_arguments = false; }
}
void __fastcall OriginalDoorReset(void* receiver, void*, bool load, bool force) {
    ++reset_calls;
    if (receiver != expected_structure || !load || force) { door_arguments = false; }
    if (during_door_reset) { during_door_reset(); }
    reinterpret_cast<void (__thiscall*)(void*)>(wm::state.door_slots[10].hook)(receiver);
}
void __fastcall OriginalDoorAppend(void* receiver, void*, void* door) {
    ++append_calls;
    if (receiver != expected_structure || door != expected_structure) { door_arguments = false; }
    if (hold_door) {
        SetEvent(entered);
        if (WaitForSingleObject(release_call, 5000) != WAIT_OBJECT_0) { door_arguments = false; }
    }
    if (wm::state.door_ready) {
        reinterpret_cast<void (__thiscall*)(void*, bool, bool)>(wm::state.door_slots[5].hook)(receiver, true, false);
    }
}
std::thread held_install;
void* expected_ref = nullptr;
void* expected_free = nullptr;
wm::NativeScene old_scene{};
int barrier_phase = 0;
bool barrier_free = false, barrier_hold = false;
std::uint32_t barrier_callback = 0;
std::thread barrier_thread;
void NoticeEntered() { SetEvent(entered); }
void ArmBarrier(int phase) {
    if (phase != barrier_phase) { return; }
    barrier_phase = 0;
    barrier_thread = std::thread([] {
        if (barrier_free) { wm::Deallocate(expected_free); }
        else { (void)reinterpret_cast<wm::Finalizer>(barrier_callback)(expected_ref, 1); }
    });
    if (barrier_hold || phase == 3) { Check(WaitForSingleObject(entered, 5000) == WAIT_OBJECT_0, "destruction entered during capture"); }
    else { barrier_thread.join(); }
}
void Hold(bool enabled) {
    if (enabled) {
        SetEvent(entered);
        if (WaitForSingleObject(release_call, 5000) != WAIT_OBJECT_0) { forwarded = false; }
    }
}
void* __fastcall OriginalRef(void* receiver, void*, std::uint32_t flags) {
    ++ref_calls;
    if (receiver != expected_ref || flags != 1) { forwarded = false; }
    if (old_scene.epoch && wm::NativeMovementLifetimeCurrent(old_scene)) { forwarded = false; }
    Hold(hold_ref.load()); return receiver;
}
void __cdecl OriginalFree(void* allocation) {
    ++free_calls;
    if (allocation != expected_free) { forwarded = false; }
    if (old_scene.epoch && allocation && wm::NativeMovementLifetimeCurrent(old_scene)) { forwarded = false; }
    Hold(hold_free.load());
}
void* __fastcall Foreign(void* receiver, void*, std::uint32_t) { return receiver; }
bool CallRef(std::uint32_t callback, void* receiver) {
    return reinterpret_cast<wm::Finalizer>(callback)(receiver, 1) == receiver;
}
}
namespace wonderbane::extension {
std::uint32_t* FindImportAddressSlot(std::uint8_t*, std::size_t, const char*, const char*) noexcept { return nullptr; }
DWORD ReplaceImportAddressSlot(std::uint32_t* slot, std::uint32_t expected, std::uint32_t replacement) noexcept {
    const auto before = InterlockedCompareExchange(reinterpret_cast<LONG*>(slot), static_cast<LONG>(replacement), static_cast<LONG>(expected));
    if (static_cast<std::uint32_t>(before) != expected) { return ERROR_INVALID_DATA; }
    if (fail_door_install) {
        fail_door_install = false;
        held_install = std::thread([replacement] {
            reinterpret_cast<void (__thiscall*)(void*, void*)>(replacement)(expected_structure, expected_structure);
        });
        if (WaitForSingleObject(entered, 5000) != WAIT_OBJECT_0) { door_arguments = false; }
        InterlockedCompareExchange(reinterpret_cast<LONG*>(slot), static_cast<LONG>(expected), static_cast<LONG>(replacement));
        return ERROR_ACCESS_DENIED;
    }
    if (fail_install) {
        fail_install = false;
        held_install = std::thread([replacement] { if (!CallRef(replacement, expected_ref)) { forwarded = false; } });
        if (WaitForSingleObject(entered, 5000) != WAIT_OBJECT_0) { forwarded = false; }
        // The production slot helper restores after a failed protection restore,
        // but a callback may already have fetched the briefly published hook.
        InterlockedCompareExchange(reinterpret_cast<LONG*>(slot), static_cast<LONG>(expected), static_cast<LONG>(replacement));
        return ERROR_ACCESS_DENIED;
    }
    return ERROR_SUCCESS;
}
namespace movement { bool VerifyNativeMovementImage(std::uintptr_t&) noexcept { return false; } }
}
namespace wonderbane::extension::movement {
struct NativeStopTestAccess {
    static void Bind(NativeStop& stop) {
        stop.base_ = state.base; stop.window_ = state.window; stop.thread_ = state.thread;
        stop.bound_ = true; stop.require_lifetime_ = true;
    }
    static bool Current(NativeStop& stop, const NativeScene& scene, const Grant& grant) {
        NativeStop::Target target{}; target.grant = grant; target.actor = scene.actor;
        target.world = scene.world; target.window = scene.window; target.parent = scene.parent;
        target.identity = scene.identity; return stop.SceneCurrent(target);
    }
};
}
namespace {
struct QuietActuator : wm::NativeActuator {
    bool Stop(const wm::Grant&, wm::StopReason) noexcept override { return false; }
    bool Direction(const wm::Grant&, wm::Vector2, bool) noexcept override { return false; }
    bool Destination(const wm::Grant&, wm::GroundPoint, bool) noexcept override { return false; }
    bool Camera(wm::Vector2) noexcept override { return false; }
    void Revoked(const wm::Grant&, const wm::Grant&, wm::StopReason) noexcept override {}
    void SceneRetired(std::uint64_t) noexcept override {}
};
struct Fixture {
    std::uint8_t* image = static_cast<std::uint8_t*>(VirtualAlloc(nullptr, 0x1766000, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE));
    std::array<std::uint8_t, 0x1000> actor{}, next{}, parent{};
    std::array<std::uint8_t, 0x100> window{}, pose{};
    std::uintptr_t pose_pointer = reinterpret_cast<std::uintptr_t>(pose.data());
    HWND hwnd = CreateWindowExW(0, L"STATIC", L"lifetime", 0, 0, 0, 640, 480, HWND_MESSAGE, nullptr, GetModuleHandleW(nullptr), nullptr);
    std::uint32_t free_slot = reinterpret_cast<std::uint32_t>(&OriginalFree);
    std::uint32_t* finalizer_slot = nullptr;
    template<class T> void Put(std::uintptr_t address, T value) { std::memcpy(reinterpret_cast<void*>(address), &value, sizeof(value)); }
    explicit Fixture(bool broken_release = false, bool skip_registration = false) {
        Check(image && hwnd, "fixture allocation");
        wm::EnableNativeMovementLifetimeDiagnostics(true);
        auto& s = wm::state; s.base = reinterpret_cast<std::uintptr_t>(image); s.window = hwnd;
        s.thread = GetCurrentThreadId(); s.started = true;
        s.free_slot = {&free_slot, free_slot, reinterpret_cast<std::uint32_t>(&wm::Deallocate)};
        Check(wonderbane::extension::ReplaceImportAddressSlot(&free_slot, s.free_slot.original, s.free_slot.hook) == ERROR_SUCCESS, "free registration");
        const auto vbtable = s.base + 0x1141100, vtable = s.base + 0x1141200;
        Put(vbtable + 4, std::uint32_t{0xe70});
        // The sealed-code range check accepts only game text. A harmless x86
        // jump thunk in our controlled image forwards to the test finalizer.
        const auto thunk = s.base + 0x1000;
        image[0x1000] = 0xe9;
        Put(thunk + 1, static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(&OriginalRef) - thunk - 5));
        DWORD prior = 0; Check(VirtualProtect(image + 0x1000, 0x1000, PAGE_EXECUTE_READ, &prior) != FALSE, "fixture thunk protection");
        FlushInstructionCache(GetCurrentProcess(), image + 0x1000, 5);
        Put(vtable + 4, static_cast<std::uint32_t>(thunk));
        Put(vtable + 8, static_cast<std::uint32_t>(s.base + (broken_release ? 0x26f50 : 0x26f49)));
        finalizer_slot = reinterpret_cast<std::uint32_t*>(vtable + 4);
        if (!skip_registration) { Check(wm::InstallReference(finalizer_slot, *finalizer_slot), "pre-register finalizer before any capture"); }
        for (auto* a : {actor.data(), next.data(), parent.data()}) {
            const auto ptr = reinterpret_cast<std::uintptr_t>(a);
            Put(ptr + 8, vbtable); Put(ptr + 0xe78, vtable);
            Put(ptr + 0x4b0, reinterpret_cast<std::uintptr_t>(&pose_pointer));
        }
        Put(reinterpret_cast<std::uintptr_t>(window.data()) + 0x64, std::uint32_t{2});
        Put(s.base + 0x16a7bfc, reinterpret_cast<std::uintptr_t>(window.data()));
        Put(s.base + 0x1389028, std::uintptr_t{0x12340000}); SetActor(actor.data());
        expected_ref = actor.data() + 0xe78; expected_free = reinterpret_cast<void*>(0x12340000);
    }
    void SetActor(void* a) { Put(wm::state.base + 0x16a2d98, reinterpret_cast<std::uintptr_t>(a)); }
    bool Observe(wm::NativeScene& scene) { return wm::ObserveNativeMovementLifetime(window.data(), scene); }
    // Production state and fixture backing remain process-pinned until exit.
};
void PrepareDoors(Fixture& f) {
    auto& state = wm::state;
    expected_structure = f.parent.data();
    for (std::size_t i = state.count; i < wm::kLifetimeBindings.size(); ++i) {
        auto* slot = reinterpret_cast<std::uint32_t*>(state.base + 0x1141400 + i * 16);
        *slot = static_cast<std::uint32_t>(state.base + 0x1000);
        Check(wm::InstallReference(slot, *slot), "register collection family finalizer");
    }
    const std::array<std::pair<std::uint32_t, std::uintptr_t>, 5> thunks{{
        {0xfd58, reinterpret_cast<std::uintptr_t>(&OriginalDoorAppend)},
        {0x23fdd, reinterpret_cast<std::uintptr_t>(&OriginalDoorReset)},
        {0x7cd4, reinterpret_cast<std::uintptr_t>(&OriginalDoorLoad)},
        {0x1ccdd, reinterpret_cast<std::uintptr_t>(&OriginalDoorLoad)},
        {0xea93, reinterpret_cast<std::uintptr_t>(&OriginalDoorLoad)},
    }};
    for (const auto [offset, target] : thunks) {
        f.image[offset] = 0xe9;
        f.Put(state.base + offset + 1, static_cast<std::uint32_t>(target - state.base - offset - 5));
        DWORD prior = 0;
        Check(VirtualProtect(f.image + offset, 5, PAGE_EXECUTE_READ, &prior) != FALSE, "owned door thunk executable");
        FlushInstructionCache(GetCurrentProcess(), f.image + offset, 5);
    }
    for (const auto& group : {wm::kDoorAppendBindings, wm::kDoorResetBindings, wm::kDoorLoadBindings}) {
        for (const auto binding : group) { f.Put(state.base + binding.slot, static_cast<std::uint32_t>(state.base + binding.original)); }
    }
}
Fixture* door_fixture = nullptr;
void ReplaceDoorScene() { door_fixture->SetActor(door_fixture->next.data()); }
void DoorLifetimeTest(Fixture& f, const std::string& mode) {
    PrepareDoors(f); door_fixture = &f;
    wm::NativeScene scene{};
    Check(f.Observe(scene), "scene observed before door registration");
    if (mode == "door-rollback") {
        hold_door = true; fail_door_install = true;
        Check(!wm::StartNativeDoorCollectionLifetime(), "door install rollback after callback publication");
        const auto dispatched = wm::state.door_slots[0].hook;
        Check(!wm::state.terminal && wm::NativeMovementLifetimeCurrent(scene), "optional door failure preserves movement observer");
        Check(!wm::StartNativeDoorCollectionLifetime(), "failed door binding cannot restart");
        SetEvent(release_call); held_install.join(); hold_door = false;
        reinterpret_cast<void (__thiscall*)(void*, void*)>(dispatched)(expected_structure, expected_structure);
        Check(append_calls == 2 && door_arguments, "in-flight and late captured door calls preserve immutable originals");
        return;
    }
    Check(wm::StartNativeDoorCollectionLifetime(), "complete door collection binding");
    wm::DoorCollectionAdmission::ReadLease lease;
    Check(wm::BeginNativeDoorCollectionRead(scene, lease), "production door acquisition admitted");
    const auto generation = lease.generation;
    const auto dispatched = wm::state.door_slots[0].hook;
    if (mode == "door-teardown") {
        hold_ref = true;
        const auto finalizer = wm::state.slots[10].hook;
        std::thread teardown([&] { if (!CallRef(finalizer, expected_ref)) { forwarded = false; } });
        const auto deadline = GetTickCount64() + 5000;
        while (wm::state.door_admission.Current(generation) && GetTickCount64() < deadline) { std::this_thread::yield(); }
        Check(!wm::state.door_admission.Current(generation) && ref_calls == 0,
            "existing structure finalizer waits before destroying acquired fields");
        lease.Reset();
        Check(WaitForSingleObject(entered, 5000) == WAIT_OBJECT_0, "structure finalizer starts after reader drains");
        Check(!wm::BeginNativeDoorCollectionRead(scene, lease), "teardown rejects concurrent acquisition");
        SetEvent(release_call); teardown.join(); hold_ref = false;
        Check(ref_calls == 1 && forwarded && !wm::NativeDoorCollectionCurrent(scene, generation),
            "shared finalizer preserves original and invalidates old door generation");
        wm::RetireNativeMovementLifetime(); return;
    }
    std::thread foreign_reader([&] {
        wm::DoorCollectionAdmission::ReadLease foreign;
        if (wm::BeginNativeDoorCollectionRead(scene, foreign)) { door_arguments = false; }
    });
    foreign_reader.join();
    hold_door = true;
    std::thread mutation([&] { reinterpret_cast<void (__thiscall*)(void*, void*)>(dispatched)(expected_structure, expected_structure); });
    const auto deadline = GetTickCount64() + 5000;
    while (wm::state.door_admission.Current(generation) && GetTickCount64() < deadline) { std::this_thread::yield(); }
    Check(!wm::state.door_admission.Current(generation) && append_calls == 0, "native append waits before touching held acquisition");
    lease.Reset();
    Check(WaitForSingleObject(entered, 5000) == WAIT_OBJECT_0, "native original progresses after acquisition");
    Check(!wm::BeginNativeDoorCollectionRead(scene, lease), "native call-through excludes another acquisition");
    SetEvent(release_call); mutation.join(); hold_door = false;
    Check(append_calls == 1 && reset_calls == 1 && load_calls == 1 && door_arguments,
        "native append reset and load nest without lock recursion and preserve ABI");
    Check(!wm::NativeDoorCollectionCurrent(scene, generation), "completed mutation leaves previous candidate stale");
    Check(wm::BeginNativeDoorCollectionRead(scene, lease), "new generation acquisition succeeds");
    const auto next_generation = lease.generation; lease.Reset();
    if (mode == "door-foreign") {
        auto& slot = wm::state.door_slots[5];
        *slot.address = reinterpret_cast<std::uint32_t>(&OriginalDoorReset);
        Check(!wm::NativeDoorCollectionCurrent(scene, next_generation), "foreign slot replacement retires only door acquisition");
        Check(*slot.address == reinterpret_cast<std::uint32_t>(&OriginalDoorReset), "foreign slot never overwritten by rollback");
        Check(wm::NativeMovementLifetimeCurrent(scene), "door binding loss preserves native movement");
    } else {
        during_door_reset = &ReplaceDoorScene;
        reinterpret_cast<void (__thiscall*)(void*, bool, bool)>(wm::state.door_slots[5].hook)(expected_structure, true, false);
        during_door_reset = nullptr;
        Check(!wm::NativeDoorCollectionCurrent(scene, next_generation) && !wm::BeginNativeDoorCollectionRead(scene, lease),
            "scene replacement inside native callback rejects old scene before observer republishes");
    }
    wm::RetireNativeMovementLifetime();
    Check(!wm::BeginNativeDoorCollectionRead(scene, lease), "shared retirement closes door acquisition");
    reinterpret_cast<void (__thiscall*)(void*, void*)>(dispatched)(expected_structure, expected_structure);
    Check(door_arguments, "late door callback retains original after shared retirement");
}
}
int main(int argc, char** argv) {
    const std::string mode = argc > 1 ? argv[1] : "normal";
    entered = CreateEventW(nullptr, TRUE, FALSE, nullptr); release_call = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (mode == "unsupported") {
        const auto window = CreateWindowExW(0, L"STATIC", L"unsealed", 0, 0, 0, 1, 1, HWND_MESSAGE, nullptr, GetModuleHandleW(nullptr), nullptr);
        Check(!wm::StartNativeMovementLifetime(window), "unreviewed image unavailable");
        Check(wm::state.terminal && !wm::state.free_slot.address, "unreviewed image installs nothing");
        return failures ? 1 : 0;
    }
    auto* f = new Fixture(mode == "unsupported-reference", (mode == "rollback" || mode == "rollback-batch"));
    wm::NativeScene scene{};
    if (mode.rfind("door-", 0) == 0) { DoorLifetimeTest(*f, mode); return failures ? 1 : 0; }
    if (mode == "unsupported-reference") {
        Check(!f->Observe(scene) && wm::state.terminal, "unknown native Release interface unavailable");
        Check(f->free_slot == reinterpret_cast<std::uint32_t>(&OriginalFree), "unsupported interface rolls back owned free slot");
    } else if (mode == "rollback-batch") {
        const auto original = *f->finalizer_slot;
        Check(wm::InstallReference(f->finalizer_slot, original), "first prebinding");
        auto* second = reinterpret_cast<std::uint32_t*>(wm::state.base + 0x1141300);
        auto* third = reinterpret_cast<std::uint32_t*>(wm::state.base + 0x1141400);
        *second = *third = original;
        Check(wm::InstallReference(second, original), "second prebinding");
        const auto dispatched = *second;
        *f->finalizer_slot = reinterpret_cast<std::uint32_t>(&Foreign);
        hold_ref = true; fail_install = true;
        Check(!wm::InstallReference(third, original), "later prebinding fails after visibility");
        wm::Fail();
        Check(*f->finalizer_slot == reinterpret_cast<std::uint32_t>(&Foreign), "batch rollback preserves foreign first slot");
        Check(*second == original && *third == original, "batch rollback restores remaining owned slots");
        SetEvent(release_call); held_install.join(); hold_ref = false;
        Check(CallRef(dispatched, expected_ref) && ref_calls == 2 && forwarded, "both captured callbacks retain original after batch rollback");
    } else if (mode == "rollback") {
        hold_ref = true; fail_install = true;
        Check(!wm::InstallReference(f->finalizer_slot, *f->finalizer_slot), "registration fails after visibility");
        wm::Fail();
        Check(!f->Observe(scene) && !scene.epoch && wm::state.terminal, "partial install fails closed");
        Check(*f->finalizer_slot == wm::state.slots[0].original && f->free_slot == reinterpret_cast<std::uint32_t>(&OriginalFree), "owned slots restored");
        Check(!wm::StartNativeMovementLifetime(f->hwnd), "partial install cannot restart");
        SetEvent(release_call); held_install.join();
        Check(ref_calls == 1 && forwarded, "already dispatched callback retains immutable original after rollback");
    } else if (mode.rfind("arm-", 0) == 0) {
        const bool replacement = mode.find("replacement") != std::string::npos;
        barrier_free = mode.find("free") != std::string::npos;
        barrier_hold = mode.find("held") != std::string::npos || mode.find("before") != std::string::npos;
        if (replacement) {
            Check(f->Observe(scene), "initial watch before replacement arming");
            f->SetActor(f->next.data()); expected_ref = f->next.data() + 0xe78;
            f->Put(wm::state.base + 0x1389028, std::uintptr_t{0x22340000}); expected_free = reinterpret_cast<void*>(0x22340000);
        }
        const auto previous = scene;
        barrier_callback = *f->finalizer_slot;
        hold_free = barrier_hold && barrier_free; hold_ref = barrier_hold && !barrier_free;
        const bool publication_edge = mode.find("edge") != std::string::npos;
        barrier_phase = publication_edge ? 3 : mode.find("publish") != std::string::npos ? 2 : 1;
        if (publication_edge) { wm::notice_barrier = &NoticeEntered; }
        wm::capture_barrier = &ArmBarrier;
        if (mode.find("before") != std::string::npos) { ArmBarrier(barrier_phase); }
        const bool observed = f->Observe(scene);
        if (publication_edge) {
            barrier_thread.join(); wm::notice_barrier = nullptr;
            Check(observed && !wm::NativeMovementLifetimeCurrent(scene), "late entry invalidates newly published matching watch before original");
        } else { Check(!observed && !scene.epoch, "destruction overlapping unpublished watch rejects capture"); }
        wm::LifetimeDiagnostics diagnostic{};
        Check(wm::ReadNativeMovementLifetimeDiagnostics(diagnostic), "arming diagnostic available");
        Check(diagnostic.first_invalidation.sequence != 0,
            "destruction or rejected observation retains first cause even without epoch advance");
        if (publication_edge) {
            Check(diagnostic.current.watch_generation == previous.epoch
                && diagnostic.current.previous_epoch > diagnostic.current.watch_generation
                && diagnostic.current.outcome == 0,
                "late notice distinguishes captured generation from newly invalidated watch epoch");
        } else {
            Check(diagnostic.current.cause == 9 && diagnostic.current.outcome == 1
                && diagnostic.current.failure_stage >= 10 && diagnostic.current.failure_stage <= 12,
                "arming rejection distinguishes in-flight, overlap or matching destruction");
        }
        if (barrier_hold) { SetEvent(release_call); barrier_thread.join(); }
        Check(!wm::state.terminal && !wm::state.binding_lost, "interference does not fabricate unsupported binding");
        wm::capture_barrier = nullptr;
        Check(f->Observe(scene) && scene.epoch && scene.epoch != previous.epoch, "stable post-destruction capture receives fresh epoch");
        Check(ref_calls + free_calls == 1 && forwarded, "intervening destructor forwarded exactly once");
    } else {
        Check(f->Observe(scene) && scene.epoch && wm::NativeMovementLifetimeCurrent(scene), "observe current native tuple");
        const auto first = scene;
        std::atomic<bool> foreign_result{true};
        std::thread foreign([&] { wm::NativeScene other{}; foreign_result = f->Observe(other); }); foreign.join();
        Check(!foreign_result && wm::NativeMovementLifetimeCurrent(scene), "foreign thread cannot replace watch");
        const auto callback = *f->finalizer_slot;
        if (mode == "parent-continuity") {
            f->Put(reinterpret_cast<std::uintptr_t>(f->pose.data()) + 8,
                reinterpret_cast<std::uintptr_t>(f->parent.data()));
            Check(f->Observe(scene) && wm::NativeMovementParentTransition(first, scene)
                && !wm::NativeMovementLifetimeCurrent(first),
                "direct parent-only publication proves continuity without reviving old lifetime");
            const auto parent_scene = scene;
            Check(!wm::NativeMovementParentTransition({}, scene), "missing previous scene cannot claim continuity");
            auto altered = first; ++altered.identity[0];
            Check(!wm::NativeMovementParentTransition(altered, scene), "identity mismatch rejects transition proof");
            expected_ref = f->parent.data() + 0xe78; old_scene = scene;
            Check(CallRef(callback, expected_ref) && !wm::NativeMovementParentTransition(first, parent_scene),
                "matching destruction immediately invalidates parent continuity proof");
            f->Put(reinterpret_cast<std::uintptr_t>(f->pose.data()) + 8, std::uintptr_t{0});
            Check(f->Observe(scene) && !wm::NativeMovementParentTransition(parent_scene, scene),
                "parent-only values after destruction cannot recreate continuity proof");
            const auto before_gap = scene; old_scene = {};
            f->pose_pointer = 0; Check(!f->Observe(scene), "capture gap rejected");
            f->pose_pointer = reinterpret_cast<std::uintptr_t>(f->pose.data());
            f->Put(reinterpret_cast<std::uintptr_t>(f->pose.data()) + 8,
                reinterpret_cast<std::uintptr_t>(f->parent.data()));
            Check(f->Observe(scene) && !wm::NativeMovementParentTransition(before_gap, scene),
                "capture failure cannot be hidden by subsequent parent-only values");
        } else if (mode == "diagnostics") {
            wm::LifetimeDiagnostics d{};
            const auto read = [&] { Check(wm::ReadNativeMovementLifetimeDiagnostics(d), "diagnostic nonblocking read"); };
            read(); Check(d.current.cause == 2 && d.current.outcome == 2 && !d.first_invalidation.sequence,
                "first watch records admission without fabricating invalidation");
            old_scene = scene; Check(CallRef(callback, expected_ref), "diagnostic finalizer forwarded");
            read(); const auto origin = d.first_invalidation;
            Check(origin.cause == 6 && origin.notice_role == 1 && origin.finalizer_flags == 1
                && origin.previous_epoch == first.epoch && origin.epoch > first.epoch
                && origin.observed_epoch == first.epoch && origin.watch_generation == first.epoch,
                "first invalidation captures exact notice role, flags and epoch before original");
            f->pose_pointer = 0;
            Check(!f->Observe(scene), "failed capture after destruction"); read();
            Check(d.current.cause == 4 && d.current.failure_stage == 9 && d.current.changed_fields == 0
                && d.current.valid_fields == 61 && d.current.previous_epoch == d.current.epoch
                && d.first_invalidation.sequence == origin.sequence,
                "failed partial capture reports stage without fake changed mask or replacing original cause");
            f->pose_pointer = reinterpret_cast<std::uintptr_t>(f->pose.data()); old_scene = {};
            for (int i = 0; i < 200; ++i) { Check(f->Observe(scene), "stable retry/idle observation"); }
            read(); Check(d.current.cause == 1 && d.current.outcome == 2
                && d.first_invalidation.sequence == origin.sequence && d.write_sequence > 64,
                "first cause survives successful rearm and idle ring overwrite");
            f->Put(reinterpret_cast<std::uintptr_t>(f->actor.data()) + 0x1c, std::uint32_t{31});
            Check(f->Observe(scene), "changed identity observation"); read();
            Check(d.current.cause == 3 && d.current.changed_fields == 32 && d.current.valid_fields == 63
                && d.first_invalidation.sequence == d.current.sequence,
                "new invalidation episode records precise changed identity word");
            AcquireSRWLockExclusive(&wm::state.lock);
            bool read_contended = true;
            std::thread reader([&] { wm::LifetimeDiagnostics copy{}; read_contended = wm::ReadNativeMovementLifetimeDiagnostics(copy); });
            reader.join(); ReleaseSRWLockExclusive(&wm::state.lock);
            Check(!read_contended, "publication read never blocks behind lifetime lock");
            const auto count = d.write_sequence;
            wm::EnableNativeMovementLifetimeDiagnostics(false);
            Check(f->Observe(scene) && !wm::ReadNativeMovementLifetimeDiagnostics(d), "disabled diagnostics do not alter admission");
            Check(wm::state.diagnostics.write_sequence == count, "disabled trace performs no diagnostic recording");
        } else if (mode == "established-churn") {
            // Finalization of another instance sharing our vtable is not
            // finalization of this watched actor/reference interface.
            expected_ref = f->next.data() + 0xe78;
            expected_free = reinterpret_cast<void*>(0x99990000);
            for (unsigned i = 0; i != 1000; ++i) {
                Check(CallRef(callback, expected_ref), "unrelated finalizer call-through");
                reinterpret_cast<wm::Free>(f->free_slot)(expected_free);
                Check(f->Observe(scene) && scene.epoch == first.epoch,
                    "unrelated destruction traffic cannot advance established scene");
            }
            hold_free = true;
            std::thread unrelated([f] { reinterpret_cast<wm::Free>(f->free_slot)(expected_free); });
            Check(WaitForSingleObject(entered, 5000) == WAIT_OBJECT_0, "unrelated free held in original");
            Check(f->Observe(scene) && scene.epoch == first.epoch,
                "established watch bypasses new-watch fence during unrelated held callback");
            SetEvent(release_call); unrelated.join(); hold_free = false;
            // Moving/reallocating the pose wrapper does not change the parent.
            auto alternate_pose = f->pose;
            f->pose_pointer = reinterpret_cast<std::uintptr_t>(alternate_pose.data());
            Check(f->Observe(scene) && scene.epoch == first.epoch,
                "pose storage changes with identical parent preserve scene identity");
        } else if (mode == "identity-fields") {
            const auto changed = [&](std::uint32_t mask, const char* message) {
                const auto previous = scene;
                Check(f->Observe(scene) && scene.epoch != previous.epoch
                    && !wm::NativeMovementLifetimeCurrent(previous), message);
                wm::LifetimeDiagnostics d{};
                Check(wm::ReadNativeMovementLifetimeDiagnostics(d) && d.current.changed_fields == mask
                    && d.current.valid_fields == 63 && d.current.cause == 3,
                    "complete tuple change reports only changed identity fields");
            };
            f->Put(reinterpret_cast<std::uintptr_t>(f->actor.data()) + 0x18, std::uint32_t{17});
            changed(16, "first identity word independently retires old epoch");
            f->Put(reinterpret_cast<std::uintptr_t>(f->actor.data()) + 0x1c, std::uint32_t{31});
            changed(32, "second identity word independently retires old epoch");
            f->Put(reinterpret_cast<std::uintptr_t>(f->pose.data()) + 8,
                reinterpret_cast<std::uintptr_t>(f->parent.data()));
            changed(2, "parent-only replacement retires epoch while actor remains identical");
            f->Put(wm::state.base + 0x1389028, std::uintptr_t{0x22340000});
            changed(4, "world-only replacement retires epoch while actor remains identical");
            f->SetActor(f->next.data()); changed(49, "actor replacement retires epoch");
            auto alternate_window = f->window;
            f->Put(wm::state.base + 0x16a7bfc, reinterpret_cast<std::uintptr_t>(alternate_window.data()));
            const auto previous = scene;
            Check(wm::ObserveNativeMovementLifetime(alternate_window.data(), scene)
                && scene.epoch != previous.epoch && !wm::NativeMovementLifetimeCurrent(previous),
                "native-window replacement retires epoch on the same owning HWND");
        } else if (mode == "capture-gap") {
            f->pose_pointer = 0;
            Check(!f->Observe(scene) && !scene.epoch && !wm::NativeMovementLifetimeCurrent(first),
                "unreadable parent chain retires epoch even with identical actor and world");
            f->pose_pointer = reinterpret_cast<std::uintptr_t>(f->pose.data());
            Check(f->Observe(scene) && scene.epoch != first.epoch,
                "restored identical tuple cannot revive pre-gap authority");
        } else if (mode == "actuator" || mode == "actuator-foreign" || mode == "actuator-foreign-free") {
            QuietActuator actuator; wm::Controls controls(actuator); wm::NativeStop native(controls);
            wm::NativeStopTestAccess::Bind(native);
            wm::Input input{}; input.scene = scene.epoch; controls.Tick(input);
            const auto grant = controls.Current();
            Check(!native.BeginUpdate(f->window.data()), "production backend requires an observed lifetime");
            Check(!native.BeginOwnerStop(nullptr, f->window.data(), scene), "foreign HWND cannot enter safety phase");
            Check(native.BeginOwnerStop(f->hwnd, f->window.data(), scene), "exact HWND admits observed safety phase");
            Check(wm::NativeStopTestAccess::Current(native, scene, grant), "safety phase retains lifetime validation");
            native.EndUpdate();

            Check(native.BeginUpdate(f->window.data(), scene), "observed lifetime enters native phase");
            Check(wm::NativeStopTestAccess::Current(native, scene, grant), "native callback boundary accepts current lifetime");
            if (mode != "actuator") {
                auto* slot = mode == "actuator-foreign" ? f->finalizer_slot : &f->free_slot;
                const auto foreign_callback = reinterpret_cast<std::uint32_t>(&Foreign);
                *slot = foreign_callback;
                Check(!wm::NativeStopTestAccess::Current(native, scene, grant), "mid-update foreign slot immediately rejects native current");
                Check(!native.Execute(grant), "mid-update foreign slot rejects stop without native actuation");
                Check(*slot == foreign_callback, "native current rejection preserves foreign replacement");
                *slot = mode == "actuator-foreign" ? callback : reinterpret_cast<std::uint32_t>(&wm::Deallocate);
                Check(!wm::NativeMovementLifetimeCurrent(scene), "restored slot cannot revive previously rejected lifetime");
                native.EndUpdate();
                Check(!f->Observe(scene) && wm::state.terminal, "owner cleans up latched binding loss");
                return failures ? 1 : 0;
            }
            old_scene = scene; reinterpret_cast<wm::Free>(f->free_slot)(expected_free);
            Check(!wm::NativeStopTestAccess::Current(native, scene, grant), "native callback boundary rejects destruction before next input tick");
            Check(!native.Execute(grant), "old stop cannot call native bindings after destruction");
            native.EndUpdate();
            Check(!native.BeginUpdate(f->window.data(), scene), "obsolete lifetime cannot begin a new phase");
            Check(!native.BeginOwnerStop(f->hwnd, f->window.data(), scene), "stale window safety cannot recapture replacement actor");
            Check(f->Observe(scene) && native.BeginUpdate(f->window.data(), scene), "replacement lifetime can enter next phase");
            Check(!native.Execute(grant), "old stop cannot cancel replacement with reused native addresses");
            native.EndUpdate();
        } else if (mode == "foreign-free") {
            f->free_slot = reinterpret_cast<std::uint32_t>(&OriginalFree);
            Check(!f->Observe(scene) && !wm::NativeMovementLifetimeCurrent(first), "foreign free slot invalidates observer");
            Check(f->free_slot == reinterpret_cast<std::uint32_t>(&OriginalFree), "foreign free slot preserved");
        } else if (mode == "foreign") {
            *f->finalizer_slot = reinterpret_cast<std::uint32_t>(&Foreign);
            Check(!f->Observe(scene) && !wm::NativeMovementLifetimeCurrent(first), "foreign finalizer replacement invalidates observer");
            Check(*f->finalizer_slot == reinterpret_cast<std::uint32_t>(&Foreign), "foreign finalizer preserved");
            old_scene = first; Check(CallRef(callback, expected_ref), "dispatched original survives foreign replacement");
        } else if (mode == "held" || mode == "held-free") {
            old_scene = scene; hold_ref = mode == "held"; hold_free = mode == "held-free";
            std::thread callback_thread([callback, f] {
                if (hold_free) { reinterpret_cast<wm::Free>(f->free_slot)(expected_free); }
                else if (!CallRef(callback, expected_ref)) { forwarded = false; }
            });
            Check(WaitForSingleObject(entered, 5000) == WAIT_OBJECT_0, "held original reached");
            Check(!wm::NativeMovementLifetimeCurrent(first), "epoch invalidated before held original");
            Check(!f->Observe(scene), "cannot rearm same allocation during destruction");
            f->SetActor(f->next.data());
            if (hold_free) { f->Put(wm::state.base + 0x1389028, std::uintptr_t{0x22340000}); }
            Check(f->Observe(scene), "unrelated replacement watch allowed while old original held");
            const auto replacement = scene;
            SetEvent(release_call); callback_thread.join();
            Check(wm::NativeMovementLifetimeCurrent(replacement), "old callback completion cannot invalidate replacement watch");
            Check(ref_calls + free_calls == 1 && forwarded, "held original exactly once with correct ABI");
        } else {
            expected_free = nullptr; reinterpret_cast<wm::Free>(f->free_slot)(nullptr);
            expected_free = reinterpret_cast<void*>(0x99990000); reinterpret_cast<wm::Free>(f->free_slot)(expected_free);
            Check(free_calls == 2 && wm::NativeMovementLifetimeCurrent(first), "ordinary/null free forwarded without invalidation");
            old_scene = scene; expected_free = reinterpret_cast<void*>(scene.world);
            reinterpret_cast<wm::Free>(f->free_slot)(expected_free);
            Check(!wm::NativeMovementLifetimeCurrent(first) && forwarded, "watched world invalidates before original free");
            Check(f->Observe(scene) && scene.epoch != first.epoch, "same-address world ABA requires new epoch");
            old_scene = scene; Check(CallRef(callback, expected_ref), "actor finalizer result preserved");
            Check(!wm::NativeMovementLifetimeCurrent(old_scene) && f->Observe(scene) && scene.epoch != old_scene.epoch, "same-address actor ABA invalidates old scene");
            f->Put(reinterpret_cast<std::uintptr_t>(f->pose.data()) + 8, reinterpret_cast<std::uintptr_t>(f->parent.data()));
            Check(f->Observe(scene), "parent reference interface tracked"); old_scene = scene;
            expected_ref = f->parent.data() + 0xe78; Check(CallRef(callback, expected_ref), "parent finalizer forwarded");
            Check(!wm::NativeMovementLifetimeCurrent(old_scene) && f->Observe(scene), "parent finalizer invalidates parent frame");
            old_scene = {}; const auto before_gap = scene;
            f->Put(reinterpret_cast<std::uintptr_t>(f->window.data()) + 0x64, std::uint32_t{1});
            Check(!f->Observe(scene) && !wm::NativeMovementLifetimeCurrent(before_gap), "nonplayable gap retires prior epoch");
            f->Put(reinterpret_cast<std::uintptr_t>(f->window.data()) + 0x64, std::uint32_t{2});
            Check(f->Observe(scene) && scene.epoch != before_gap.epoch, "return to same tuple requires fresh epoch");
            wm::RetireNativeMovementLifetime();
            Check(!wm::NativeMovementLifetimeCurrent(scene) && !f->Observe(scene), "terminal retirement closes observer");
            Check(CallRef(callback, expected_ref) && forwarded, "callback fetched before retirement still forwards");
        }
    }
    Check(forwarded, "native arguments/results preserved");
    return failures ? 1 : 0;
}
