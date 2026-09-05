#include "movement_controls.h"
#include <cmath>
#include <cstring>
#include <iostream>
#include <limits>
#include <vector>

using namespace wonderbane::extension::movement;
namespace {
int failures = 0;
void Check(bool ok, const char* name) { if (!ok) { std::cerr << name << '\n'; ++failures; } }
bool Near(float a, float b) { return std::abs(a - b) < 0.0001F; }
struct Event { char kind; Grant grant; Vector2 vector; bool start; };
struct Actuator final : NativeActuator {
    std::vector<Event> events;
    Grant revoked_old{}, revoked_next{};
    bool stop_ok = true;
    bool move_ok = true;
    bool camera_ok = true;
    bool Stop(const Grant& g, StopReason) noexcept override {
        events.push_back({'s', g, {}, false}); return stop_ok;
    }
    bool Direction(const Grant& g, Vector2 v, bool start) noexcept override {
        events.push_back({'d', g, v, start}); return move_ok;
    }
    bool Destination(const Grant& g, GroundPoint p, bool start) noexcept override {
        events.push_back({'p', g, {p.x, p.z}, start}); return move_ok;
    }
    bool Camera(Vector2 v) noexcept override {
        events.push_back({'c', {}, v, false}); return camera_ok;
    }
    void Revoked(const Grant& old, const Grant& next, StopReason) noexcept override {
        revoked_old = old; revoked_next = next;
        events.push_back({'r', old, {}, false});
    }
    void SceneRetired(std::uint64_t scene) noexcept override {
        Grant g{}; g.scene = scene; events.push_back({'e', g, {}, false});
    }
    std::size_t Count(char kind) const {
        std::size_t n = 0; for (const auto& e : events) { if (e.kind == kind) ++n; } return n;
    }
};
Token Identity(const char* op) {
    Token t{}; std::memcpy(t.worker.data(), "worker-one", 10);
    std::memcpy(t.operation.data(), op, std::strlen(op)); return t;
}
struct Fixture {
    Actuator actuator;
    Controls controls{actuator};
    Settings settings;
    Input input;
    Fixture() {
        settings.enabled = true; settings.controller = true;
        (void)controls.Configure(settings);
        input.scene = 11; input.native_available = true; input.exact_foreground = true;
        input.camera_basis_valid = true; input.camera_forward = {0, 1};
        input.camera_right = {1, 0}; input.controller_connected = true;
        input.capture_valid = true; input.pointer_in_world = true;
        input.ground_valid = true; input.ground = {3, 4, 5};
        Step(); actuator.events.clear();
    }
    void Step(std::uint64_t milliseconds = 16) { input.tick_ms += milliseconds; controls.Tick(input); }
    Grant Automate(const char* op = "operation-one") {
        Grant g{};
        Check(controls.AcquireAutomation(controls.Current().generation, Identity(op), g)
              == Result::accepted, "acquire automation");
        Check(controls.AutomationDestination(g, {10, 0, 20}) == Result::accepted, "automation move");
        return g;
    }
};
void Interpretation() {
    Fixture f;
    f.input.keys[0x57] = f.input.keys[0x53] = true; f.Step();
    Check(f.actuator.Count('d') == 0, "opposing keys cancel");
    f.input.keys[0x53] = false; f.input.keys[0x44] = true; f.Step();
    const auto e = f.actuator.events.back();
    Check(e.kind == 'd' && Near(e.vector.x, std::sqrt(0.5F))
          && Near(e.vector.y, std::sqrt(0.5F)), "diagonals normalized");
    f.input.keys[0x44] = false; f.input.camera_forward = {-1, 0};
    f.input.camera_right = {0, 1}; f.Step();
    Check(Near(f.actuator.events.back().vector.x, -1), "camera relative forward");
    f.input.keys[0x57] = false; f.Step();
    Check(f.actuator.events.back().kind == 's', "key release invokes stop");
    f.input.left_stick = {0.3F, 0.4F}; f.Step();
    Check(Near(f.actuator.events.back().vector.x, -0.8F)
          && Near(f.actuator.events.back().vector.y, 0.6F), "analog direction retained, no invented speed");
    f.input.left_stick = {}; f.Step();
    f.input.keys[0x57] = true; f.input.camera_basis_valid = false; f.Step();
    Check(f.actuator.events.back().kind == 's', "invalid camera basis cannot move");
}
void Ownership() {
    Fixture f; const auto old = f.Automate(); f.actuator.events.clear();
    f.input.left_stick = {0.01F, 0.01F}; f.input.right_stick = {1, 0}; f.Step();
    Check(f.controls.Current() == old, "camera and dead-zone noise retain route");
    Check(f.actuator.Count('s') == 0, "camera does not stop route");
    f.input.keys[0x57] = true; f.Step(); const auto manual = f.controls.Current();
    Check(manual.generation > old.generation && manual.owner == Owner::manual, "manual takeover");
    Check(f.actuator.Count('s') == 1, "takeover stops active old movement");
    const auto count = f.actuator.events.size();
    Check(f.controls.AutomationDestination(old, {}) == Result::stale, "delayed old movement rejected");
    Check(f.controls.Stop(old) == Result::stale, "delayed old stop rejected");
    Grant delayed{};
    Check(f.controls.AcquireAutomation(old.generation, Identity("delayed"), delayed) == Result::stale,
          "delayed acquisition cannot retake ownership");
    Check(f.actuator.events.size() == count, "stale requests never reach native actuator");
    f.input.keys[0x57] = false; f.input.right_stick = {}; f.Step();
    Check(f.controls.Current().owner == Owner::manual, "release cannot resume route");
    const auto next = f.Automate("explicit-new-operation");
    Check(f.controls.Stop(manual) == Result::stale, "old manual stop cannot cancel new route");
    Check(f.controls.Current() == next, "new route retains ownership");
}
void CameraFailure() {
    Fixture f; const auto route = f.Automate(); f.actuator.events.clear();
    f.actuator.camera_ok = false;
    f.input.right_stick = {1, 0}; f.Step();
    Check(f.controls.Current() == route && f.actuator.Count('s') == 0,
          "camera failure cannot revoke movement ownership");
    Check(!f.controls.CameraReady() && f.controls.Ready(), "camera capability fails independently");
    f.Step(); Check(f.actuator.Count('c') == 1, "camera failure is latched without repeat calls");
    f.input.keys[0x57] = true; f.Step();
    Check(f.controls.Current().owner == Owner::manual && f.actuator.Count('d') == 1,
          "movement remains available after camera failure");
}
void Gates() {
    Fixture f; f.input.keys[0x57] = true; f.Step();
    f.input.exact_foreground = false; f.Step();
    Check(f.actuator.events.back().kind == 'r', "focus loss revokes owner");
    const auto count = f.actuator.Count('d');
    f.input.exact_foreground = true; f.Step();
    Check(f.actuator.Count('d') == count, "held key cannot resume after focus restoration");
    f.input.keys[0x57] = false; f.Step(); f.input.keys[0x57] = true; f.Step();
    Check(f.actuator.Count('d') == count + 1, "neutral re-arms keyboard");
    f.input.ui_owns_input = true; f.Step();
    Check(!f.controls.ConsumesKey(0x57), "text input keeps bound key");
    f.input.ui_owns_input = false; f.Step();
    Check(f.actuator.Count('d') == count + 1, "text exit does not resume held key");
    f.input.keys[0x57] = false; f.Step(); f.input.keys[0x57] = true; f.Step(251);
    Check(f.actuator.Count('d') == count + 1, "stall requires neutral input");
    f.settings.enabled = false; (void)f.controls.Configure(f.settings); f.Step();
    Check(!f.controls.ConsumesKey(0x57) && !f.controls.ConsumesDrag(), "disabled preserves native input");
    Fixture other;
    Check(other.actuator.Count('d') == 0, "separate client never moves from first client input");
    other.input.exact_foreground = false; other.input.left_stick = {1, 0}; other.Step();
    Check(other.actuator.Count('d') == 0, "background client rejects same controller");
}
void Devices() {
    Fixture f; f.input.left_stick = {1, 0}; f.Step();
    f.input.controller_connected = false; f.Step();
    Check(f.actuator.events.back().kind == 's', "disconnect stops movement");
    const auto count = f.actuator.Count('d');
    f.input.controller_connected = true; f.Step();
    Check(f.actuator.Count('d') == count, "reconnect held stick inhibited");
    f.input.left_stick = {}; f.input.right_stick = {1, 0}; f.Step();
    Check(f.actuator.Count('c') == 0, "both sticks must be neutral to rearm");
    f.input.right_stick = {}; f.Step(); f.input.left_stick = {0, 1}; f.Step();
    Check(f.actuator.Count('d') == count + 1, "neutral reconnect rearmed");
    f.input.controller_slot = 1; f.Step();
    Check(f.actuator.events.back().kind == 's', "unselected slot cannot continue movement");
}
void Drag() {
    Fixture f; f.input.keys[5] = true; f.Step();
    Check(!f.controls.ConsumesDrag() && f.actuator.Count('p') == 0, "ordinary click retained");
    f.input.pointer_x = 5; f.Step(); Check(!f.controls.ConsumesDrag(), "drag below threshold");
    f.input.pointer_x = 7; f.Step();
    Check(f.controls.ConsumesDrag() && f.actuator.events.back().kind == 'p', "world drag starts");
    f.input.ground_valid = false; f.Step();
    Check(f.actuator.events.back().kind == 's', "invalid terrain pick stops, no plane fallback");
    f.input.ground_valid = true; f.Step();
    f.input.capture_valid = false; f.Step();
    Check(!f.controls.ConsumesDrag() && f.actuator.events.back().kind == 's', "lost capture stops");
    const auto count = f.actuator.Count('p');
    f.input.capture_valid = true; f.Step();
    Check(f.actuator.Count('p') == count, "held drag does not resume after lost capture");
    f.input.keys[5] = false; f.Step(); f.input.pointer_in_world = false;
    f.input.keys[5] = true; f.Step(); f.input.pointer_x = 50; f.Step();
    Check(f.actuator.Count('p') == count, "UI-origin drag never captured");
}
void FailureAndScene() {
    Fixture f; const auto old = f.Automate(); f.actuator.stop_ok = false;
    f.input.keys[0x57] = true; f.Step();
    Check(!f.controls.Ready() && f.actuator.Count('d') == 0, "failed stop blocks new writer");
    Check(f.controls.Stop(old) == Result::stale, "failed stop still revokes old automation");
    f.input.scene = 22; const auto stops = f.actuator.Count('s'); f.Step();
    Check(f.actuator.Count('s') == stops, "scene transition never stops replacement actor");
    Check(f.actuator.Count('d') == 0, "scene transition requires neutral");
    Check(f.actuator.revoked_old.scene == 11 && f.actuator.revoked_next.scene == 22,
          "revocation preserves both scene identities");
    Check(f.controls.Stop(old) == Result::stale, "retired scene stop stays stale");
    Fixture partial; partial.actuator.move_ok = false;
    partial.input.keys[0x57] = true; partial.Step();
    Check(partial.actuator.Count('s') == 2 && !partial.controls.Ready(), "partial native failure stopped");
    partial.input.keys[0x57] = false; partial.Step(); partial.input.keys[0x57] = true; partial.Step();
    Check(partial.actuator.Count('d') == 1, "binding failure latched until explicit configure");
}
// Policy-contract regression: force the adapter stop even without a tracked move.
// Actual native follow retirement must still be verified in the adapter.
void NativeIntentTakeover() {
    for (const int method : {0, 1, 2}) {
        Fixture f;
        const auto native_owner = f.controls.Current();
        // Neither a camera gesture nor a sub-threshold click may retire native follow.
        f.input.right_stick = {1, 0}; f.Step();
        f.input.keys[5] = true; f.Step();
        Check(f.actuator.Count('s') == 0 && f.controls.Current() == native_owner,
              "camera and ordinary click preserve untracked native intent");
        if (method == 0) { f.input.keys[0x57] = true; }
        if (method == 1) { f.input.left_stick = {1, 0}; }
        if (method == 2) { f.input.pointer_x = 7; }
        f.Step();
        const auto& events = f.actuator.events;
        std::size_t stop = events.size(), move = events.size();
        for (std::size_t i = 0; i < events.size(); ++i) {
            if (events[i].kind == 's') { stop = i; }
            if (events[i].kind == 'd' || events[i].kind == 'p') { move = i; }
        }
        Check(stop < move && events[stop].grant == native_owner,
              "all manual methods retire untracked native intent before moving");
        const auto manual = f.controls.Current();
        f.input.keys.fill(false); f.input.left_stick = {}; f.input.right_stick = {}; f.Step();
        const auto after_release = f.actuator.events.size(); f.Step();
        Check(f.controls.Current() == manual && f.actuator.events.size() == after_release,
              "manual release and later update cannot reacquire retired intent");
        Check(f.controls.Stop(native_owner) == Result::stale,
              "untracked old owner stop cannot reach replacement actor");
    }
    Fixture blocked; blocked.actuator.stop_ok = false;
    blocked.input.keys[0x57] = true; blocked.Step();
    Check(blocked.actuator.Count('s') == 1 && blocked.actuator.Count('d') == 0
          && !blocked.controls.Ready(), "failed untracked-intent stop excludes manual writer");
    blocked.actuator.stop_ok = true; blocked.Step();
    Check(blocked.controls.Ready() && blocked.actuator.Count('d') == 1,
          "retained exact stop completes before manual submission");
}
void EmergencyStops() {
    for (const auto reason : {StopReason::focus, StopReason::capture_lost, StopReason::ui}) {
        Fixture f; const auto old = f.Automate();
        const auto before = f.actuator.Count('s');
        Check(f.controls.EmergencyStop(old, reason) == Result::accepted,
              "window safety stop does not wait for an input tick");
        Check(f.actuator.Count('s') == before + 1 && f.controls.Current().owner == Owner::none,
              "window safety stop retires exact native intent immediately");
        const auto after = f.actuator.events.size();
        Check(f.controls.EmergencyStop(old, reason) == Result::stale && f.actuator.events.size() == after,
              "duplicate queued safety event cannot stop a replacement generation");
        f.input.keys[0x57] = true; f.input.left_stick = {1, 0}; f.Step();
        Check(f.actuator.Count('d') == 0, "focus restoration requires neutral manual controls");
        f.input.keys.fill(false); f.input.left_stick = {}; f.Step();
        f.input.keys[0x57] = true; f.Step(); const auto manual = f.controls.Current();
        const auto moved = f.actuator.events.size();
        Check(f.controls.EmergencyStop(old, reason) == Result::stale
            && f.controls.Current() == manual && f.actuator.events.size() == moved,
            "old safety stop cannot cancel newly accepted manual movement");
    }
    Fixture f; const auto old = f.Automate(); f.actuator.stop_ok = false;
    Check(f.controls.EmergencyStop(old, StopReason::focus) == Result::stop_failed
        && !f.controls.Ready(), "failed emergency native stop excludes a new writer");
    Grant next{};
    Check(f.controls.AcquireAutomation(f.controls.Current().generation, Identity("next"), next)
        != Result::accepted, "failed window stop cannot admit automation");
    f.input.scene = 12; f.Step();
    Check(!f.controls.AuthorizesNativeStop(old), "scene replacement discards old emergency stop authority");
}
void FrameRatesAndSettings() {
    for (const int hz : {20, 30, 60, 144, 240}) {
        Fixture f; f.input.right_stick = {1, 0};
        const auto start = f.input.tick_ms;
        for (int n = 1; n <= hz; ++n) {
            f.input.tick_ms = start + static_cast<std::uint64_t>(n * 1000 / hz);
            f.controls.Tick(f.input);
        }
        float angle = 0; for (const auto& e : f.actuator.events) if (e.kind == 'c') angle += e.vector.x;
        Check(Near(angle, 2), "camera integrates elapsed time across frame rates");
    }
    Fixture f; f.settings.keys = {0x49, 0x4b, 0x4a, 0x4c};
    f.settings.invert_camera_x = true; (void)f.controls.Configure(f.settings); f.Step();
    Check(!f.controls.ConsumesKey(0x57) && f.controls.ConsumesKey(0x49), "remapped suppression");
    f.input.right_stick = {1, 0}; f.Step();
    Check(f.actuator.events.back().vector.x < 0, "camera inversion");
    f.settings.keys[1] = f.settings.keys[0];
    Check(f.controls.Configure(f.settings) == Result::invalid, "conflicting bindings rejected");
    Check(!ValidSettings(Settings{.movement_dead_zone = std::numeric_limits<float>::quiet_NaN()}),
          "nonfinite settings rejected");
}
}
int main() {
    Interpretation(); Ownership(); CameraFailure(); Gates(); Devices(); Drag(); FailureAndScene(); NativeIntentTakeover(); EmergencyStops(); FrameRatesAndSettings();
    return failures ? 1 : 0;
}
