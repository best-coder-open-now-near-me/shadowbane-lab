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
bool fail_install = false;
std::thread held_install;
void* expected_ref = nullptr;
void* expected_free = nullptr;
wm::NativeScene old_scene{};
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
    explicit Fixture(bool broken_release = false) {
        Check(image && hwnd, "fixture allocation");
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
    auto* f = new Fixture(mode == "unsupported-reference");
    wm::NativeScene scene{};
    if (mode == "unsupported-reference") {
        Check(!f->Observe(scene) && wm::state.terminal, "unknown native Release interface unavailable");
        Check(f->free_slot == reinterpret_cast<std::uint32_t>(&OriginalFree), "unsupported interface rolls back owned free slot");
    } else if (mode == "rollback") {
        hold_ref = true; fail_install = true;
        Check(!f->Observe(scene) && !scene.epoch && wm::state.terminal, "partial install fails closed");
        Check(*f->finalizer_slot == wm::state.slots[0].original && f->free_slot == reinterpret_cast<std::uint32_t>(&OriginalFree), "owned slots restored");
        Check(!wm::StartNativeMovementLifetime(f->hwnd), "partial install cannot restart");
        SetEvent(release_call); held_install.join();
        Check(ref_calls == 1 && forwarded, "already dispatched callback retains immutable original after rollback");
    } else {
        Check(f->Observe(scene) && scene.epoch && wm::NativeMovementLifetimeCurrent(scene), "observe current native tuple");
        const auto first = scene;
        std::atomic<bool> foreign_result{true};
        std::thread foreign([&] { wm::NativeScene other{}; foreign_result = f->Observe(other); }); foreign.join();
        Check(!foreign_result && wm::NativeMovementLifetimeCurrent(scene), "foreign thread cannot replace watch");
        const auto callback = *f->finalizer_slot;
        if (mode == "actuator" || mode == "actuator-foreign" || mode == "actuator-foreign-free") {
            QuietActuator actuator; wm::Controls controls(actuator); wm::NativeStop native(controls);
            wm::NativeStopTestAccess::Bind(native);
            wm::Input input{}; input.scene = scene.epoch; controls.Tick(input);
            const auto grant = controls.Current();
            Check(!native.BeginUpdate(f->window.data()), "production backend requires an observed lifetime");
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
