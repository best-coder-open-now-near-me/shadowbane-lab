#include "movement_native_stop.h"
#include <array>
#include <cmath>
#include <limits>
#include <cstring>
#include <iostream>
#include <thread>
#include <vector>
using namespace wonderbane::extension::movement;
namespace {
int failures = 0;
void Check(bool value, const char* message) { if (!value) { ++failures; std::cerr << message << '\n'; } }
template<class T> void Put(void* memory, std::size_t offset, const T& value) {
    std::memcpy(static_cast<unsigned char*>(memory) + offset, &value, sizeof(value));
}
template<class T> T Get(const void* memory, std::size_t offset) {
    T value{}; std::memcpy(&value, static_cast<const unsigned char*>(memory) + offset, sizeof(value)); return value;
}
struct Fixture;
Fixture* current = nullptr;
}
namespace wonderbane::extension::movement {
struct NativeStopTestAccess {
    using Node = NativeStop::Node; using Map = NativeStop::Map; using Vector = NativeStop::Vector;
    static void Bind(NativeStop&, void*, HWND);
    static void** __fastcall Retain(void**, void*, void*);
    static void __fastcall Release(void**, void*);
    static void __fastcall Clear(void*, void*, const NativeStop::Identity*);
    static Node** __fastcall Find(void*, void*, Node**, const NativeStop::Identity*);
    static Node* __cdecl Detach(Node*, Node**, Node**, Node**);
    static void __fastcall Destroy(NativeStop::Identity*, void*);
    static void __cdecl Pool(void*, std::uint32_t);
    static void* __fastcall Erase(void*, void*, void*, void*);
    static void __fastcall Continuation(void*, void*);
    static GroundPoint* __fastcall Position(void*, void*, GroundPoint*);
    static void __fastcall Destination(void*, void*, const GroundPoint*);
    static void __fastcall Waypoint(void*, void*, std::uint32_t, std::uint32_t);
    static void** __fastcall State(void*, void*, void**, bool, std::uint32_t, bool);
    static void __fastcall Send(void*, void*, void*);
    static void __fastcall Camera(void*, void*, float, float, float, bool);
    static void __fastcall PacketRelease(void*, void*, void**);
};
}
namespace {
using Access = NativeStopTestAccess;
struct Actuator : NativeActuator {
    NativeStop* native = nullptr;
    bool Stop(const Grant& grant, StopReason) noexcept override { return native->Execute(grant); }
    bool Direction(const Grant&, Vector2, bool) noexcept override;
    bool Destination(const Grant&, GroundPoint, bool) noexcept override;
    bool Camera(Vector2 radians) noexcept override { return native->RotateCamera(radians); }
    void Revoked(const Grant&, const Grant&, StopReason) noexcept override {}
    void SceneRetired(std::uint64_t scene) noexcept override { native->SceneRetired(scene); }
};
struct Fixture {
    Actuator actuator;
    Controls controls{actuator};
    NativeStop stop{controls};
    void* base = VirtualAlloc(nullptr, 0x16c0000, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    HWND window = CreateWindowExW(0, L"STATIC", L"native stop test", 0, 0, 0, 1, 1, HWND_MESSAGE, nullptr, nullptr, nullptr);
    std::array<unsigned char, 0xc30> actor{}, replacement{};
    std::array<unsigned char, 0x200> world{};
    std::array<unsigned char, 0x100> game_window{};
    std::array<unsigned char, 0x40> state{};
    std::array<unsigned char, 48> path{};
    struct Request { std::uint32_t state = 0; std::uint8_t usable = 1; } request, alternate_request;
    std::array<unsigned char, 0x200> alternate_world{};
    Access::Node active_sentinel{}, scheduled_sentinel{}, active_node{}, scheduled_node{};
    std::array<std::uintptr_t, 3> packet_table{0, 0, reinterpret_cast<std::uintptr_t>(&Access::PacketRelease)};
    struct Packet { const std::uintptr_t* table; int references; } packet{packet_table.data(), 0};
    Input input{};
    int retains = 0, releases = 0, clears = 0, pools = 0, sends = 0, state_calls = 0, moves = 0, follow_moves = 0;
    int position_calls = 0, destination_calls = 0, waypoint_calls = 0;
    int camera_calls = 0;
    bool camera_fault = false;
    int callback_mode = 0;
    Result nested = Result::accepted;
    bool missing_message = false, raise_fault = false;
    GroundPoint destination{};
    Fixture() {
        current = this; Check(base && window, "test process fixtures created");
        actuator.native = &stop; Access::Bind(stop, base, window);
        const std::array<std::uint32_t, 2> id{17, 31};
        Put(actor.data(), 0x18, id);
        Put(actor.data(), 0xad0, reinterpret_cast<std::uintptr_t>(state.data()));
        Put(base, 0x16a2d98, reinterpret_cast<std::uintptr_t>(actor.data()));
        Put(base, 0x1389028, reinterpret_cast<std::uintptr_t>(world.data()));
        Put(base, 0x16a7bfc, reinterpret_cast<std::uintptr_t>(game_window.data()));
        Put(base, 0x16a1c00, reinterpret_cast<std::uintptr_t>(&request));
        Put(base, 0x16ab88c, std::uintptr_t{1});
        Put(game_window.data(), 0x64, std::uint32_t{2});
        active_node.identity = scheduled_node.identity = id;
        active_sentinel.left = active_sentinel.right = &active_sentinel;
        scheduled_sentinel.left = scheduled_sentinel.right = &scheduled_sentinel;
        Put(world.data(), 0xb8, Access::Map{&active_sentinel, 0});
        Put(world.data(), 0xe8, Access::Map{&scheduled_sentinel, 0});
        Put(base, 0x1163250, 1.5707963705062866F);
        Put(base, 0x1163300, 0.05F);
        Put(base, 0x1163254, 0.7853981852531433F);
        Put(base, 0x16a2c10 + 0x7c, 15.0F);
        Arm(true);
        Settings settings; settings.enabled = true; settings.controller = true;
        Check(controls.Configure(settings) == Result::accepted, "configure controls");
        input.scene = 1; input.native_available = input.exact_foreground = true;
        input.camera_basis_valid = true; input.camera_forward = {0, 1}; input.camera_right = {1, 0};
        input.controller_connected = true; input.capture_valid = input.pointer_in_world = input.ground_valid = true;
        Step();
    }
    ~Fixture() { if (window) { DestroyWindow(window); } if (base) { VirtualFree(base, 0, MEM_RELEASE); } current = nullptr; }
    void Step() { input.tick_ms += 16; controls.Tick(input); }
    void Arm(bool follow) {
        Put(actor.data(), 0xc1c, static_cast<std::uint16_t>(follow ? 0x0101 : 0));
        Put(actor.data(), 0xc1e, std::uint8_t{1});
        Put(actor.data(), 0xc10, Access::Vector{path.data(), path.data() + path.size(), path.data() + path.size()});
        Put(state.data(), 0x10, std::uint32_t{7});
        auto* pending = Get<Request*>(base, 0x16a1c00);
        if (!pending) { pending = &request; Put(base, 0x16a1c00, reinterpret_cast<std::uintptr_t>(pending)); }
        pending->state = 0; pending->usable = 1;
        active_sentinel.parent = &active_node;
        scheduled_sentinel.parent = &scheduled_node;
        Put(world.data(), 0xb8, Access::Map{&active_sentinel, 1});
        Put(world.data(), 0xe8, Access::Map{&scheduled_sentinel, 1});
    }
    void FollowUpdate() {
        if (Get<std::uint16_t>(actor.data(), 0xc1c)) { ++follow_moves; Arm(true); }
    }
    void WorldUpdate() {
        FollowUpdate();
        const auto p = Get<Access::Vector>(actor.data(), 0xc10);
        const auto* pending = Get<Request*>(base, 0x16a1c00);
        if ((pending && pending->state == 0) || p.begin != p.end || Get<Access::Map>(world.data(), 0xb8).size
            || Get<Access::Map>(world.data(), 0xe8).size) { ++moves; }
    }
};
bool Actuator::Direction(const Grant&, Vector2, bool) noexcept { ++current->moves; current->Arm(false); return true; }
bool Actuator::Destination(const Grant&, GroundPoint, bool) noexcept { ++current->moves; current->Arm(false); return true; }
}
namespace wonderbane::extension::movement {
void NativeStopTestAccess::Bind(NativeStop& stop, void* base, HWND window) {
    stop.base_ = reinterpret_cast<std::uintptr_t>(base); stop.window_ = window;
    stop.thread_ = GetCurrentThreadId(); stop.bound_ = true; stop.in_update_ = true;
    auto& c = stop.calls_;
    c.retain = reinterpret_cast<decltype(c.retain)>(&Retain); c.release = reinterpret_cast<decltype(c.release)>(&Release);
    c.clear_actions = reinterpret_cast<decltype(c.clear_actions)>(&Clear); c.find = reinterpret_cast<decltype(c.find)>(&Find);
    c.detach = &Detach; c.destroy_identity = reinterpret_cast<decltype(c.destroy_identity)>(&Destroy); c.pool_return = &Pool;
    c.erase_path = reinterpret_cast<decltype(c.erase_path)>(&Erase);
    c.clear_continuation = reinterpret_cast<decltype(c.clear_continuation)>(&Continuation);
    c.position = reinterpret_cast<decltype(c.position)>(&Position); c.destination = reinterpret_cast<decltype(c.destination)>(&Destination);
    c.clear_waypoint = reinterpret_cast<decltype(c.clear_waypoint)>(&Waypoint);
    c.camera = reinterpret_cast<decltype(c.camera)>(&Camera);
    c.state = reinterpret_cast<decltype(c.state)>(&State); c.send = reinterpret_cast<decltype(c.send)>(&Send);
}
void __fastcall NativeStopTestAccess::Camera(void* camera, void*, float pitch, float yaw, float distance, bool relative) {
    ++current->camera_calls;
    Check(!relative && distance == 15.0F, "camera setter preserves distance and parent-relative offset");
    if (current->camera_fault) { RaiseException(EXCEPTION_ACCESS_VIOLATION, 0, 0, nullptr); }
    Put(camera, 0x70, pitch); Put(camera, 0x68, yaw); Put(camera, 0x7c, distance);
    Put(camera, 0x134, std::uint8_t{1});
}
void** __fastcall NativeStopTestAccess::Retain(void** output, void*, void* actor) {
    ++current->retains; *output = actor;
    if (current->callback_mode == 13) {
        Put(current->base, 0x16a1c00, reinterpret_cast<std::uintptr_t>(&current->alternate_request));
    }
    return output;
}
void __fastcall NativeStopTestAccess::Release(void** output, void*) { ++current->releases; *output = nullptr; }
void __fastcall NativeStopTestAccess::Clear(void*, void*, const NativeStop::Identity*) {
    ++current->clears;
    if (current->raise_fault) { RaiseException(0xc0000005, 0, 0, nullptr); }
    current->active_sentinel.parent = nullptr;
    Put(current->world.data(), 0xb8, Map{&current->active_sentinel, 0});
    if (current->callback_mode == 5) {
        Put(current->base, 0x16a1c00, reinterpret_cast<std::uintptr_t>(&current->alternate_request));
    } else if (current->callback_mode == 7) {
        current->replacement = current->actor;
        Put(current->replacement.data(), 0xc1c, std::uint16_t{0x0101});
        Put(current->base, 0x16a2d98, reinterpret_cast<std::uintptr_t>(current->replacement.data()));
        current->input.scene = 2;
    }
}
NativeStopTestAccess::Node** __fastcall NativeStopTestAccess::Find(void* receiver, void*, Node** output, const NativeStop::Identity* id) {
    const auto& map = *static_cast<Map*>(receiver);
    *output = map.size && map.sentinel->parent->identity == *id ? map.sentinel->parent : map.sentinel; return output;
}
NativeStopTestAccess::Node* __cdecl NativeStopTestAccess::Detach(Node* node, Node** root, Node** minimum, Node** maximum) {
    *root = nullptr; *minimum = *maximum = &current->scheduled_sentinel; return node;
}
void __fastcall NativeStopTestAccess::Destroy(NativeStop::Identity*, void*) {}
void __cdecl NativeStopTestAccess::Pool(void*, std::uint32_t size) { Check(size == 40, "correct native scheduled-node pool size"); ++current->pools; }
void* __fastcall NativeStopTestAccess::Erase(void* receiver, void*, void* first, void*) {
    static_cast<Vector*>(receiver)->end = first;
    if (current->callback_mode == 6) {
        Put(current->base, 0x16a1c00, reinterpret_cast<std::uintptr_t>(&current->alternate_request));
    }
    return first;
}
void __fastcall NativeStopTestAccess::Continuation(void* receiver, void*) { Put(receiver, 0xc1e, std::uint8_t{0}); }
GroundPoint* __fastcall NativeStopTestAccess::Position(void*, void*, GroundPoint* output) {
    ++current->position_calls; *output = {100, 0, 200};
    if (current->callback_mode == 9) {
        Put(current->base, 0x16a1c00, reinterpret_cast<std::uintptr_t>(&current->alternate_request));
    }
    return output;
}
void __fastcall NativeStopTestAccess::Destination(void*, void*, const GroundPoint* position) {
    ++current->destination_calls; current->destination = *position;
    if (current->callback_mode == 10) {
        Put(current->base, 0x16a1c00, reinterpret_cast<std::uintptr_t>(&current->alternate_request));
    }
}
void __fastcall NativeStopTestAccess::Waypoint(void*, void*, std::uint32_t a, std::uint32_t b) {
    ++current->waypoint_calls; Check(!a && !b, "native waypoint cleared");
    if (current->callback_mode == 11) {
        Put(current->base, 0x16a1c00, reinterpret_cast<std::uintptr_t>(&current->alternate_request));
    }
}
void** __fastcall NativeStopTestAccess::State(void*, void*, void** output, bool update, std::uint32_t value, bool build) {
    auto& f = *current; ++f.state_calls;
    Check(update && build && value == 5 && Get<std::uint32_t>(f.state.data(), 0x10) == 7,
        "idle packet built on native moving-state transition");
    Put(f.state.data(), 0x10, value);
    f.packet.references = f.missing_message ? 0 : 1; *output = f.missing_message ? nullptr : &f.packet;
    if (f.callback_mode == 12) {
        Put(f.base, 0x16a1c00, reinterpret_cast<std::uintptr_t>(&f.alternate_request));
    } else if (f.callback_mode == 1) {
        Token token{}; std::memcpy(token.worker.data(), "worker", 6); std::memcpy(token.operation.data(), "reentrant", 9);
        Grant grant{};
        f.nested = f.controls.AcquireAutomation(f.controls.Current().generation, token, grant);
    } else if (f.callback_mode == 8) {
        f.alternate_world = f.world;
        Put(f.base, 0x1389028, reinterpret_cast<std::uintptr_t>(f.alternate_world.data()));
        Put(f.base, 0x16a1c00, reinterpret_cast<std::uintptr_t>(&f.alternate_request));
        f.input.scene = 2;
    } else if (f.callback_mode == 3) {
        f.controls.Shutdown();
    } else if (f.callback_mode == 2) {
        f.replacement = f.actor;
        Put(f.base, 0x16a2d98, reinterpret_cast<std::uintptr_t>(f.replacement.data()));
        f.input.scene = 2; f.controls.Tick(f.input);
    }
    return output;
}
void __fastcall NativeStopTestAccess::Send(void* receiver, void*, void* packet) {
    Check(receiver == static_cast<unsigned char*>(current->base) + 0x16ab888 && packet == &current->packet,
        "native send uses captured outgoing reference");
    ++current->sends; --current->packet.references;
    if (current->callback_mode == 4) {
        current->replacement = current->actor;
        Put(current->base, 0x16a2d98, reinterpret_cast<std::uintptr_t>(current->replacement.data()));
        current->input.scene = 2;
    }
}
void __fastcall NativeStopTestAccess::PacketRelease(void*, void*, void** output) { --current->packet.references; *output = nullptr; }
}
namespace {
void ManualMethods() {
    for (int method = 0; method < 3; ++method) {
        Fixture f; f.input.right_stick = {1, 0}; f.Step();
        Check(f.clears == 0 && Get<std::uint16_t>(f.actor.data(), 0xc1c) == 0x0101,
            "camera-only preserves native follow and ownership");
        f.input.right_stick = {};
        if (method == 0) { f.input.keys[0x57] = true; }
        if (method == 1) { f.input.left_stick = {1, 0}; }
        if (method == 2) { f.input.keys[5] = true; f.Step(); f.input.pointer_x = 7; }
        f.Step(); const auto manual = f.controls.Current();
        Check(manual.owner == Owner::manual && f.moves == 1 && f.sends == 1,
            "manual method composes native stop before new movement");
        f.FollowUpdate(); Check(f.follow_moves == 0, "later follow update cannot revive retired follow");
        f.input.keys.fill(false); f.input.left_stick = {}; f.Step();
        const auto count = f.moves; f.WorldUpdate(); f.Step(); f.WorldUpdate();
        Check(f.moves == count && f.follow_moves == 0 && f.sends == 2 && f.packet.references == 0,
            "release clears all native movement sources and consumes each outgoing reference once");
        Check(f.retains == f.releases && f.retains == 2, "actor retained across each complete stop");
        Check(f.controls.Current() == manual, "release does not resume old route");
        Token token{}; std::memcpy(token.worker.data(), "worker", 6); std::memcpy(token.operation.data(), "explicit", 8);
        Grant next{};
        Check(f.controls.AcquireAutomation(manual.generation, token, next) == Result::accepted,
            "explicit automation restart accepted");
        const auto calls = f.clears;
        Check(!f.stop.Execute(manual) && f.controls.Stop(manual) == Result::stale && f.clears == calls,
            "old native and policy stop cannot touch a newer owner");
    }
}
void StatesAndFailures() {
    { Fixture f; Put(f.base, 0x16a1c00, std::uintptr_t{0});
      Check(f.stop.Execute(f.controls.Current()) && f.request.state == 0,
          "absent current-player request does not touch an unrelated request object");
      const auto moves = f.moves; f.WorldUpdate(); Check(f.moves == moves, "world driver reads only current-player request slot"); }
    { Fixture f; f.input.keys[0x57] = true; f.Step(); f.input.keys[0x57] = false; f.Step();
      const auto grant = f.controls.Current();
      Put(f.base, 0x16a1c00, reinterpret_cast<std::uintptr_t>(&f.alternate_request));
      f.input.keys[0x57] = true; f.Step(); f.input.keys[0x57] = false; f.Step();
      Check(f.controls.Current() == grant && f.controls.Ready() && f.stop.Available()
          && f.alternate_request.state == 1 && f.alternate_request.usable == 0,
          "new stop transaction in same manual grant seals its own current request"); }
    { Fixture f; Put(f.base, 0x16ab88c, std::uintptr_t{0});
      f.input.keys[0x57] = true; f.Step();
      Check(f.sends == 0 && f.packet.references == 0 && !f.stop.Available() && !f.controls.Ready()
          && f.moves == 0 && f.retains == f.releases,
          "missing connection fails unavailable after local cleanup and reference release"); }
    { Fixture f; f.stop.EndUpdate();
      Check(!f.stop.Execute(f.controls.Current()) && f.clears == 0, "outside native update cannot stop");
      Check(!f.stop.BeginUpdate(f.actor.data()), "wrong native update receiver rejected");
      Check(f.stop.BeginUpdate(f.game_window.data()) && !f.stop.BeginUpdate(f.game_window.data()),
          "exact native update receiver admitted without nested phase");
      Check(f.stop.Execute(f.controls.Current()), "admitted native update may stop"); }

    for (const std::uint32_t state : {0U, 1U, 2U, 3U, 4U, 5U, 6U, 8U, 15U}) {
        Fixture f; Put(f.state.data(), 0x10, state);
        Check(f.stop.Execute(f.controls.Current()) && Get<std::uint32_t>(f.state.data(), 0x10) == state
            && f.state_calls == 0 && f.sends == 0, "restricted or nonmoving state preserved");
    }
    { Fixture f; bool accepted = true;
      std::thread other([&] { accepted = f.stop.Execute(f.controls.Current()); }); other.join();
      Check(!accepted && f.clears == 0 && f.stop.Available(), "wrong thread cannot enter native stop"); }
    { Fixture f; f.missing_message = true; f.input.keys[0x57] = true; f.Step();
      const auto calls = f.clears; f.Step();
      Check(!f.stop.Available() && !f.controls.Ready() && f.moves == 0 && f.sends == 0 && f.clears == calls,
          "missing outgoing message fails closed without retrying an idle transition"); }
    { Fixture f; f.raise_fault = true; f.input.keys[0x57] = true; f.Step();
      Check(!f.stop.Available() && !f.controls.Ready() && f.moves == 0 && f.retains == 1 && f.releases == 0,
          "native exception retains ambiguous actor ownership and blocks new writer"); }
}
void CameraComposition() {
    for (const std::uint64_t interval : {5ULL, 10ULL, 20ULL, 40ULL, 100ULL}) {
        Fixture f;
        Token token{}; std::memcpy(token.worker.data(), "worker", 6); std::memcpy(token.operation.data(), "camera", 6);
        Grant grant{};
        Check(f.controls.AcquireAutomation(f.controls.Current().generation, token, grant) == Result::accepted,
            "camera test acquires route");
        const auto clears = f.clears;
        Put(f.base, 0x16a2c10 + 0x138, 0.031F); Put(f.base, 0x16a2c10 + 0x13c, -0.019F);
        f.input.right_stick = {1, 0};
        for (std::uint64_t elapsed = 0; elapsed < 1000; elapsed += interval) {
            f.input.tick_ms += interval; f.controls.Tick(f.input);
        }
        Check(std::abs(Get<float>(f.base, 0x16a2c10 + 0x68) - 2.0F) < 0.00001F
            && f.controls.Current() == grant && f.clears == clears && f.moves == 0,
            "production policy and camera executor apply elapsed-time yaw without revoking route");
        Check(Get<float>(f.base, 0x16a2c10 + 0x138) == 0.031F
            && Get<float>(f.base, 0x16a2c10 + 0x13c) == -0.019F,
            "controller camera leaves existing native mouse inertia untouched");
        f.input.right_stick = {}; f.Step();
        const auto count = f.camera_calls; f.Step();
        Check(f.camera_calls == count, "neutral camera sends no new rotation");
    }
    { Fixture f;
      Check(f.stop.RotateCamera({0, 100}) && std::abs(Get<float>(f.base, 0x16a2c10 + 0x70) - 1.4922565F) < 0.00001F,
          "camera upper pitch matches native gesture limit");
      Check(f.stop.RotateCamera({0, -100}) && std::abs(Get<float>(f.base, 0x16a2c10 + 0x70) + 0.7853982F) < 0.00001F,
          "camera lower pitch matches native gesture limit");
      const auto count = f.camera_calls;
      Check(!f.stop.RotateCamera({std::numeric_limits<float>::quiet_NaN(), 0}), "nonfinite camera input rejected");
      bool accepted = true; std::thread other([&] { accepted = f.stop.RotateCamera({1, 0}); }); other.join();
      Check(!accepted && f.camera_calls == count, "wrong client thread cannot rotate camera");
      f.stop.EndUpdate(); Check(!f.stop.RotateCamera({1, 0}) && f.camera_calls == count,
          "camera requires admitted native update"); }
    { Fixture f; f.camera_fault = true; f.input.right_stick = {1, 0}; f.Step();
      Check(!f.controls.CameraReady() && f.controls.Ready() && f.stop.Available(),
          "native camera fault disables camera independently from movement");
      const auto count = f.camera_calls; f.Step(); Check(f.camera_calls == count, "uncertain camera call never retried");
      f.input.right_stick = {}; f.input.keys[0x57] = true; f.Step();
      Check(f.moves == 1, "camera failure leaves native stop and manual movement usable"); }
}
void ReentryAndScene() {
    // Boundary fault injection also covers sealed retain/position helpers; this
    // does not claim those reviewed native routines invoke gameplay callbacks.
    for (const int mode : {9, 10, 11, 12, 13}) {
        Fixture f; f.callback_mode = mode; f.input.keys[0x57] = true; f.Step();
        Check(f.alternate_request.state == 0 && f.alternate_request.usable == 1
            && f.sends == 0 && f.moves == 0 && f.retains == f.releases && f.packet.references == 0,
            "replaced request is untouched and old stop references are released");
        Check(f.position_calls == (mode == 13 ? 0 : 1)
            && f.destination_calls == (mode >= 10 && mode <= 12 ? 1 : 0)
            && f.waypoint_calls == (mode == 11 || mode == 12 ? 1 : 0)
            && f.state_calls == (mode == 12 ? 1 : 0)
            && f.clears == (mode == 13 ? 0 : 1),
            "request replacement prevents every subsequent destination/UI/state mutation");
        Check(!f.stop.Available() && !f.controls.Ready(), "request invalidation excludes a replacement writer");
    }
    for (const int mode : {5, 6}) {
        Fixture f; f.callback_mode = mode; f.input.keys[0x57] = true; f.Step();
        Check(f.alternate_request.state == 0 && f.alternate_request.usable == 1
            && f.moves == 0 && f.sends == 0 && !f.stop.Available(),
            "callback replacement request never adopted or cancelled");
        Check(f.request.state == (mode == 5 ? 0U : 1U), "only captured request may be retired");
    }
    { Fixture f; f.callback_mode = 7; f.input.keys[0x57] = true; f.Step();
      Check(f.pools == 0 && f.request.state == 0 && f.sends == 0 && f.moves == 0
          && Get<std::uint16_t>(f.replacement.data(), 0xc1c) == 0x0101,
          "actor replacement in action destructor prevents subsequent cleanup of new actor"); }
    { Fixture f; f.callback_mode = 8; f.input.keys[0x57] = true; f.Step();
      Check(f.clears == 1 && f.alternate_request.state == 0 && f.alternate_request.usable == 1
          && f.sends == 0 && f.packet.references == 0 && f.moves == 0,
          "world/request replacement in state callback cannot receive old stop or packet"); }
    { Fixture f; f.callback_mode = 3; f.input.keys[0x57] = true; f.Step();
      Check(f.moves == 0 && !f.controls.Ready(), "shutdown during takeover cannot submit one last move"); }
    { Fixture f; f.callback_mode = 4; f.input.keys[0x57] = true; f.Step();
      Check(f.sends == 1 && f.packet.references == 0 && f.moves == 0,
          "scene transition during send prevents subsequent movement submission"); }
    { Fixture f; f.callback_mode = 3;
      Token token{}; std::memcpy(token.worker.data(), "worker", 6); std::memcpy(token.operation.data(), "shutdown", 8);
      Grant output{};
      Check(f.controls.AcquireAutomation(f.controls.Current().generation, token, output) == Result::inhibited,
          "deferred callback shutdown cannot admit automation");
      f.Step(); Check(!f.controls.Ready() && f.moves == 0, "shutdown remains disabled on later update"); }
    { Fixture f; f.callback_mode = 1; f.input.keys[0x57] = true; f.Step();
      Check(f.nested == Result::inhibited && f.controls.Current().owner == Owner::manual && f.moves == 1,
          "callback cannot admit competing owner during native stop"); }
    { Fixture f; f.callback_mode = 2; f.input.keys[0x57] = true; f.Step();
      Check(f.sends == 0 && f.packet.references == 0 && f.moves == 0 && f.retains == f.releases,
          "actor replacement during state callback releases old references without sending stale state");
      const auto calls = f.clears; f.Step();
      Check(f.controls.Current().scene == 2 && f.clears == calls && f.moves == 0,
          "next scene discards old stop and requires neutral rearm"); }
}
}
int main() {
    { Fixture f; NativeStop unbound(f.controls); Check(!unbound.Bind(f.window), "unsupported executable stays unavailable"); }
    ManualMethods(); StatesAndFailures(); CameraComposition(); ReentryAndScene();
    return failures ? 1 : 0;
}
