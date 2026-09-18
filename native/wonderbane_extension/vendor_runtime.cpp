#include "vendor_runtime.h"
#include "guard_upgrade_native.h"
#include "guard_funding_native.h"
#include "guard_funding_controller.h"
#include "guard_funding_command_queue.h"
#include "guard_upgrade_controller.h"
#include "guard_upgrade_command_queue.h"
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
guard_upgrade::Controller guard_controller;
guard_funding::Controller funding_controller;
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
        if (funding_controller.Busy() || guard_controller.Busy() || navigation_controller.Busy() || !command_->lease || !command_->lease->Current(now) || now > command_->deadline
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
        if (funding_controller.Busy() || guard_controller.Busy() || controller.Busy() || navigation_controller.Busy() || !command_->lease || !command_->lease->Current(now)
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
    vendor_navigation::wire::Key warehouse_{};
public:
    NavigationInvoker(const std::shared_ptr<vendor_navigation::QueuedCommand>& pending_command,
        const movement::NativeScene& scene, HWND window) : queued_(pending_command), scene_(scene), window_(window) {}
    static bool Admit(void* context) noexcept {
        auto& self = *static_cast<NavigationInvoker*>(context);
        const auto now = GetTickCount64();
        vendor_navigation::wire::Snapshot fresh{};
        if (funding_controller.Busy() || guard_controller.Busy() || controller.Busy() || !self.expected_ || !self.queued_->lease || !self.queued_->lease->Current(now)
            || now > self.queued_->deadline || GetForegroundWindow() != self.window_ || IsIconic(self.window_)
            || !vendor_navigation::Capture(image_base, self.scene_, fresh)) { return false; }
        fresh.revision = self.expected_->revision;
        std::uint32_t row = 0;
        return vendor_navigation::wire::Equal(fresh, *self.expected_)
            && (!self.warehouse_[0] || vendor_navigation::FindVendorControl(
                image_base, fresh, self.warehouse_, row));
    }
    vendor_navigation::wire::Outcome Open(vendor_navigation::wire::Verb verb,
        const vendor_navigation::wire::Command& command) noexcept override {
        using O = vendor_navigation::wire::Outcome;
        expected_ = &command.expected;
        warehouse_ = verb == vendor_navigation::wire::Verb::warehouse ? command.vendor : vendor_navigation::wire::Key{};
        if (!Admit(this)) { return O::stale; }
        if (verb == vendor_navigation::wire::Verb::warehouse) {
            if (!target_bind_attempted) { target_bind_attempted = true; (void)building_target.Bind(window_); }
            return building_target.OpenWarehouse(scene_, command.vendor,
                {command.expected.warehouse_hud, command.expected.warehouse_object}, &Admit, this);
        }
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
                ? vendor_navigation::InvokeGuard(image_base, command.expected, command.vendor, &Admit, this)
                : vendor_navigation::InvokeVendor(image_base, command.expected, command.vendor, &Admit, this);
            return invoked ? O::submitted : O::uncertain;
        }
        return O::invalid;
    }
};
class GuardInvoker final : public guard_upgrade::Invoker {
    const std::shared_ptr<guard_upgrade::QueuedCommand>& queued_;
    const movement::NativeScene& scene_;
    HWND window_;
    const guard_upgrade::wire::Snapshot* reopen_expected_ = nullptr;
    const guard_upgrade::ReturnSnapshot* reopen_returned_ = nullptr;
public:
    GuardInvoker(const std::shared_ptr<guard_upgrade::QueuedCommand>& command,
        const movement::NativeScene& scene, HWND window) : queued_(command), scene_(scene), window_(window) {}
    guard_upgrade::wire::Outcome Upgrade(const guard_upgrade::wire::Snapshot& expected) noexcept override {
        using O = guard_upgrade::wire::Outcome;
        guard_upgrade::wire::Snapshot fresh{}; bool top = false;
        const auto now = GetTickCount64();
        if (funding_controller.Busy() || controller.Busy() || navigation_controller.Busy() || !queued_->lease || !queued_->lease->Current(now)
            || now > queued_->deadline || GetForegroundWindow() != window_ || IsIconic(window_)
            || !guard_upgrade::Capture(image_base, scene_, fresh, top) || !top) { return O::stale; }
        fresh.navigation.revision = expected.navigation.revision;
        if (!guard_upgrade::wire::Equal(fresh, expected) || !movement::NativeMovementLifetimeCurrent(scene_)) {
            return O::stale;
        }
        return guard_upgrade::Invoke(image_base, expected) ? O::submitted : O::uncertain;
    }
    static bool AdmitReopen(void* context) noexcept {
        auto& self = *static_cast<GuardInvoker*>(context);
        const auto now = GetTickCount64();
        guard_upgrade::ReturnSnapshot fresh{};
        if (!self.reopen_expected_ || !self.reopen_returned_
            || funding_controller.Busy() || controller.Busy() || navigation_controller.Busy()
            || self.queued_->verb != guard_upgrade::wire::Verb::inspect
            || !self.queued_->lease || !self.queued_->lease->Current(now) || now > self.queued_->deadline
            || GetForegroundWindow() != self.window_ || IsIconic(self.window_)
            || !guard_upgrade::CaptureReturn(image_base, self.scene_, *self.reopen_expected_, fresh)) {
            return false;
        }
        const auto& returned = *self.reopen_returned_;
        return vendor_navigation::wire::Equal(fresh.navigation, returned.navigation)
            && fresh.guard == returned.guard && fresh.rank == returned.rank
            && fresh.funds == returned.funds && movement::NativeMovementLifetimeCurrent(self.scene_);
    }
    guard_upgrade::wire::Outcome Reopen(const guard_upgrade::wire::Snapshot& expected,
        const guard_upgrade::ReturnSnapshot& returned) noexcept override {
        using O = guard_upgrade::wire::Outcome;
        reopen_expected_ = &expected; reopen_returned_ = &returned;
        if (!AdmitReopen(this)) { return O::stale; }
        return vendor_navigation::InvokeGuard(image_base, returned.navigation, expected.navigation.vendor,
            &AdmitReopen, this) ? O::submitted : O::uncertain;
    }
};
class FundingInvoker final : public guard_funding::Invoker {
    const std::shared_ptr<guard_funding::QueuedCommand>& queued_;
    const movement::NativeScene& scene_;
    HWND window_;
public:
    FundingInvoker(const std::shared_ptr<guard_funding::QueuedCommand>& command,
        const movement::NativeScene& scene, HWND window) : queued_(command), scene_(scene), window_(window) {}
    static bool Admit(void* context) noexcept {
        auto& self = *static_cast<FundingInvoker*>(context); const auto now = GetTickCount64();
        return !guard_controller.Busy() && !controller.Busy() && !navigation_controller.Busy()
            && self.queued_->lease && self.queued_->lease->Current(now) && now <= self.queued_->deadline
            && GetForegroundWindow() == self.window_ && !IsIconic(self.window_)
            && movement::NativeMovementLifetimeCurrent(self.scene_);
    }
    guard_funding::wire::Outcome Transfer(guard_funding::wire::Verb verb, const guard_funding::wire::Command& c) noexcept override {
        using O = guard_funding::wire::Outcome;
        if (!Admit(this)) { return O::stale; }
        guard_funding::wire::Snapshot fresh{}; bool top = false;
        if (!guard_funding::Capture(image_base, scene_, c.direction, fresh, top) || !top) { return O::stale; }
        fresh.revision = c.expected.revision;
        if (!guard_funding::wire::Equal(fresh, c.expected)) { return O::stale; }
        const bool invoked = verb == guard_funding::wire::Verb::open_quote
            ? guard_funding::InvokeOpen(image_base, scene_, c, &Admit, this)
            : guard_funding::Invoke(image_base, scene_, c, &Admit, this);
        return invoked ? O::submitted : O::uncertain;
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
    guard_upgrade::wire::Snapshot guard_snapshot{}; bool guard_top = false;
    const bool guard_valid = scene.window == reinterpret_cast<std::uintptr_t>(root)
        && guard_upgrade::Capture(image_base, scene, guard_snapshot, guard_top);
    guard_controller.Observe(guard_snapshot, guard_valid && guard_top, GetTickCount64());
    guard_upgrade::ReturnSnapshot returned{};
    const auto* pending_guard = guard_controller.PendingReturn();
    const bool returned_valid = pending_guard && scene.window == reinterpret_cast<std::uintptr_t>(root)
        && guard_upgrade::CaptureReturn(image_base, scene, *pending_guard, returned);
    guard_controller.ObserveReturn(returned, returned_valid);
    auto funding_command = guard_funding::Take();
    std::array<bool, 2> funding_valid{}, funding_top{};
    // The inventory accessor is demand-driven, not traversed on every idle frame.
    for (std::uint32_t direction = 1; direction <= 2; ++direction) {
        if (funding_controller.NeedsObservation(direction) || (funding_command && funding_command->command.direction == direction)) {
            guard_funding::wire::Snapshot funding_snapshot{};
            funding_valid[direction - 1] = scene.window == reinterpret_cast<std::uintptr_t>(root)
                && guard_funding::Capture(image_base, scene, direction, funding_snapshot, funding_top[direction - 1]);
            funding_controller.Observe(direction, funding_snapshot, funding_valid[direction - 1], GetTickCount64());
        }
    }
    if (funding_command) {
        const auto now = GetTickCount64(); const auto direction = funding_command->command.direction;
        const bool exact_window = funding_command->command.window == reinterpret_cast<std::uintptr_t>(window);
        const bool live = funding_command->lease && funding_command->lease->Current(now) && now <= funding_command->deadline;
        const bool ready = guard_funding::wire::DirectionValid(direction) && funding_valid[direction - 1] && funding_top[direction - 1]
            && !guard_controller.Busy() && !controller.Busy() && !navigation_controller.Busy()
            && GetForegroundWindow() == window && !IsIconic(window);
        FundingInvoker invoker(funding_command, scene, window);
        guard_funding::Complete(funding_command, funding_controller.Execute(
            funding_command->verb, funding_command->command, live && exact_window, ready, now, invoker));
    }
    if (auto command = guard_upgrade::Take()) {
        const auto now = GetTickCount64();
        const bool exact_window = command->command.window == reinterpret_cast<std::uintptr_t>(window);
        const bool live = command->lease && command->lease->Current(now) && now <= command->deadline;
        const bool ready = guard_valid && guard_top && !funding_controller.Busy() && !controller.Busy() && !navigation_controller.Busy()
            && GetForegroundWindow() == window && !IsIconic(window);
        GuardInvoker invoker(command, scene, window);
        guard_upgrade::Complete(command, guard_controller.Execute(
            command->verb, command->command, live && exact_window, ready, now, invoker));
    }
    if (auto command = vendor_navigation::Take()) {
        const auto now = GetTickCount64();
        const bool exact_window = command->command.window == reinterpret_cast<std::uintptr_t>(window);
        const bool live = command->lease && command->lease->Current(now) && now <= command->deadline;
        const bool ready = navigation_valid && !funding_controller.Busy() && !guard_controller.Busy() && !controller.Busy() && GetForegroundWindow() == window && !IsIconic(window);
        NavigationInvoker invoker(command, scene, window);
        vendor_navigation::Complete(command, navigation_controller.Execute(
            command->verb, command->command, live && exact_window, ready, now, invoker));
    }
    if (auto command = city_window::Take()) {
        const auto now = GetTickCount64();
        const bool exact_window = command->command.window == reinterpret_cast<std::uintptr_t>(window);
        const bool live = command->lease && command->lease->Current(now) && now <= command->deadline;
        const bool ready = city_valid && !funding_controller.Busy() && !guard_controller.Busy() && !controller.Busy() && !navigation_controller.Busy() && GetForegroundWindow() == window && !IsIconic(window);
        CityInvoker invoker(command, scene, window);
        city_window::Complete(command, city_controller.Execute(
            command->verb, command->command, live && exact_window, ready, invoker));
    }
    if (auto command = Take()) {
        const auto now = GetTickCount64();
        const bool live = command->lease && command->lease->Current(now) && now <= command->deadline;
        const bool exact_window = command->command.window == reinterpret_cast<std::uintptr_t>(window);
        const bool ready = valid && !funding_controller.Busy() && !guard_controller.Busy() && !navigation_controller.Busy() && exact_window && top && GetForegroundWindow() == window && !IsIconic(window);
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
