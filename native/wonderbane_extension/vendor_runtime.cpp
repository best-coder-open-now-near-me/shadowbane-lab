#include "vendor_runtime.h"
#include "vendor_native.h"
#include "vendor_controller.h"
#include "vendor_command_queue.h"
#include "city_window_command_queue.h"
#include "city_window_controller.h"
#include "city_window_native.h"
#include "native_owner_services.h"
#include "vendor_navigation_command_queue.h"
#include "vendor_navigation_controller.h"
#include "vendor_navigation_native.h"
#include "building_native_target.h"
#include "movement_native_image.h"
namespace wonderbane::extension::vendor {
namespace {
std::uintptr_t image_base = 0;
Controller controller;
city_window::Controller city_controller;
vendor_navigation::Controller navigation_controller;
vendor_navigation::BuildingTarget building_target;
bool target_bind_attempted = false;
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
        if (navigation_controller.Busy() || !command_->lease || !command_->lease->Current(now) || now > command_->deadline
            || GetForegroundWindow() != window_ || IsIconic(window_)
            || !Capture(image_base, scene_, fresh, 0, present, top) || !top) { return wire::Outcome::stale; }
        fresh.revision = expected.revision;
        if (!wire::Equal(fresh, expected) || !movement::NativeMovementLifetimeCurrent(scene_)) {
            return wire::Outcome::stale;
        }
        return InvokeNative(image_base, verb, expected, item) ? wire::Outcome::submitted : wire::Outcome::uncertain;
    }
};
class CityInvoker final : public city_window::Invoker {
    const std::shared_ptr<city_window::QueuedCommand>& command_;
    const movement::NativeScene& scene_;
    HWND window_;
public:
    CityInvoker(const std::shared_ptr<city_window::QueuedCommand>& command,
        const movement::NativeScene& scene, HWND window) : command_(command), scene_(scene), window_(window) {}
    city_window::wire::Outcome Open(const city_window::wire::Snapshot& expected) noexcept override {
        using O = city_window::wire::Outcome;
        city_window::wire::Snapshot fresh{};
        const auto now = GetTickCount64();
        if (controller.Busy() || navigation_controller.Busy() || !command_->lease || !command_->lease->Current(now)
            || now > command_->deadline || GetForegroundWindow() != window_ || IsIconic(window_)
            || !city_window::Capture(image_base, scene_, fresh)) { return O::stale; }
        fresh.revision = expected.revision;
        if (!city_window::wire::Equal(fresh, expected)) { return O::stale; }
        if (!city_window::InvokeOpen(image_base, expected)) { return O::uncertain; }
        city_window::wire::Snapshot after{};
        if (!city_window::Capture(image_base, scene_, after) || after.manager != expected.manager
            || !after.hud || !after.visible || after.active_manager != after.manager) { return O::uncertain; }
        // Local window opening is verified. Loading/nearby data are observed separately.
        return O::submitted;
    }
};
class NavigationInvoker final : public vendor_navigation::Invoker {
    const std::shared_ptr<vendor_navigation::QueuedCommand>& queued_;
    const movement::NativeScene& scene_;
    HWND window_;
    const vendor_navigation::wire::Snapshot* expected_ = nullptr;
public:
    NavigationInvoker(const std::shared_ptr<vendor_navigation::QueuedCommand>& pending_command,
        const movement::NativeScene& scene, HWND window) : queued_(pending_command), scene_(scene), window_(window) {}
    static bool Admit(void* context) noexcept {
        auto& self = *static_cast<NavigationInvoker*>(context);
        const auto now = GetTickCount64();
        vendor_navigation::wire::Snapshot fresh{};
        if (controller.Busy() || !self.expected_ || !self.queued_->lease || !self.queued_->lease->Current(now)
            || now > self.queued_->deadline || GetForegroundWindow() != self.window_ || IsIconic(self.window_)
            || !vendor_navigation::Capture(image_base, self.scene_, fresh)) { return false; }
        fresh.revision = self.expected_->revision;
        return vendor_navigation::wire::Equal(fresh, *self.expected_);
    }
    vendor_navigation::wire::Outcome Open(vendor_navigation::wire::Verb verb,
        const vendor_navigation::wire::Command& command) noexcept override {
        using O = vendor_navigation::wire::Outcome;
        expected_ = &command.expected;
        if (!Admit(this)) { return O::stale; }
        if (verb == vendor_navigation::wire::Verb::building) {
            if (!target_bind_attempted) { target_bind_attempted = true; (void)building_target.Bind(window_); }
            return building_target.Open(scene_, command.building, &Admit, this);
        }
        if (verb == vendor_navigation::wire::Verb::vendor || verb == vendor_navigation::wire::Verb::guard) {
            const bool guard = verb == vendor_navigation::wire::Verb::guard;
            std::uint32_t control = 0;
            const bool found = guard
                ? vendor_navigation::FindGuardControl(image_base, command.expected, command.vendor, control)
                : vendor_navigation::FindVendorControl(image_base, command.expected, command.vendor, control);
            if (!found) {
                return O::unavailable;
            }
            if (!Admit(this)) { return O::stale; }
            const bool invoked = guard
                ? vendor_navigation::InvokeGuard(image_base, command.expected, command.vendor)
                : vendor_navigation::InvokeVendor(image_base, command.expected, command.vendor);
            return invoked ? O::submitted : O::uncertain;
        }
        return O::invalid;
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
    city_window::wire::Snapshot city_snapshot{};
    const bool city_valid = scene.window == reinterpret_cast<std::uintptr_t>(root)
        && city_window::Capture(image_base, scene, city_snapshot);
    city_controller.Observe(city_snapshot, city_valid);
    vendor_navigation::wire::Snapshot navigation_snapshot{};
    const bool navigation_valid = scene.window == reinterpret_cast<std::uintptr_t>(root)
        && vendor_navigation::Capture(image_base, scene, navigation_snapshot);
    navigation_controller.Observe(navigation_snapshot, navigation_valid, GetTickCount64());
    if (auto command = vendor_navigation::Take()) {
        const auto now = GetTickCount64();
        const bool exact_window = command->command.window == reinterpret_cast<std::uintptr_t>(window);
        const bool live = command->lease && command->lease->Current(now) && now <= command->deadline;
        const bool ready = navigation_valid && !controller.Busy() && GetForegroundWindow() == window && !IsIconic(window);
        NavigationInvoker invoker(command, scene, window);
        vendor_navigation::Complete(command, navigation_controller.Execute(
            command->verb, command->command, live && exact_window, ready, now, invoker));
    }
    if (auto command = city_window::Take()) {
        const auto now = GetTickCount64();
        const bool exact_window = command->command.window == reinterpret_cast<std::uintptr_t>(window);
        const bool live = command->lease && command->lease->Current(now) && now <= command->deadline;
        const bool ready = city_valid && !controller.Busy() && !navigation_controller.Busy() && GetForegroundWindow() == window && !IsIconic(window);
        CityInvoker invoker(command, scene, window);
        city_window::Complete(command, city_controller.Execute(
            command->verb, command->command, live && exact_window, ready, invoker));
    }
    if (auto command = Take()) {
        const auto now = GetTickCount64();
        const bool live = command->lease && command->lease->Current(now) && now <= command->deadline;
        const bool exact_window = command->command.window == reinterpret_cast<std::uintptr_t>(window);
        const bool ready = valid && !navigation_controller.Busy() && exact_window && top && GetForegroundWindow() == window && !IsIconic(window);
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
