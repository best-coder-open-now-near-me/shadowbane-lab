#include "vendor_runtime.h"
#include "vendor_native.h"
#include "vendor_controller.h"
#include "vendor_command_queue.h"
#include "native_owner_services.h"
#include "movement_native_image.h"
namespace wonderbane::extension::vendor {
namespace {
std::uintptr_t image_base = 0;
Controller controller;
bool busy = false;
class NativeInvoker final : public Invoker {
    const std::shared_ptr<QueuedCommand>& command_;
    const movement::NativeScene& scene_;
    HWND window_;
public:
    NativeInvoker(const std::shared_ptr<QueuedCommand>& command,
        const movement::NativeScene& scene, HWND window) : command_(command), scene_(scene), window_(window) {}
    wire::Outcome Invoke(wire::Verb verb, const wire::Snapshot& expected, std::uint32_t item) noexcept override {
        wire::Snapshot fresh{}; bool present = false, top = false;
        const auto now = GetTickCount64();
        if (!command_->lease || !command_->lease->Current(now) || now > command_->deadline
            || GetForegroundWindow() != window_ || IsIconic(window_)
            || !Capture(image_base, scene_, fresh, 0, present, top) || !top) { return wire::Outcome::stale; }
        fresh.revision = expected.revision;
        if (!wire::Equal(fresh, expected) || !movement::NativeMovementLifetimeCurrent(scene_)) {
            return wire::Outcome::stale;
        }
        return InvokeNative(image_base, verb, expected, item) ? wire::Outcome::submitted : wire::Outcome::uncertain;
    }
};
void Update(void* root, HWND window) noexcept {
    if (busy || !image_base) { return; }
    DWORD pid = 0;
    if (GetWindowThreadProcessId(window, &pid) != GetCurrentThreadId() || pid != GetCurrentProcessId()) { return; }
    busy = true;
    movement::NativeScene scene{};
    wire::Snapshot snapshot{}; bool present = false, top = false;
    const bool valid = movement::ReadNativeMovementLifetime(scene) && scene.window == reinterpret_cast<std::uintptr_t>(root)
        && Capture(image_base, scene, snapshot, controller.PendingKeep(), present, top);
    controller.Observe(snapshot, valid, present);
    if (auto command = Take()) {
        const auto now = GetTickCount64();
        const bool live = command->lease && command->lease->Current(now) && now <= command->deadline;
        const bool exact_window = command->command.window == reinterpret_cast<std::uintptr_t>(window);
        const bool ready = valid && exact_window && top && GetForegroundWindow() == window && !IsIconic(window);
        NativeInvoker invoker(command, scene, window);
        Complete(command, controller.Execute(command->verb, command->command, live && exact_window, ready, invoker));
    }
    busy = false;
}
}
bool Start() noexcept {
    std::uintptr_t base = 0;
    if (!movement::VerifyNativeMovementImage(base)) { return false; }
    image_base = base;
    vendor_owner_service.store(&Update, std::memory_order_release);
    return true;
}
}

