#include "door_collection_admission.h"
#include <atomic>
#include <iostream>
#include <thread>
#include <type_traits>
using namespace wonderbane::extension::movement;
static_assert(!std::is_copy_constructible_v<DoorCollectionAdmission>);
static_assert(!std::is_move_constructible_v<DoorCollectionAdmission>);
namespace {
int failures = 0;
void Check(bool value, const char* label) { if (!value) { ++failures; std::cerr << label << '\n'; } }
}
int main() {
    DoorCollectionAdmission gate;
    DoorCollectionAdmission::ReadLease reader, other;
    Check(gate.TryRead(reader), "first acquisition admitted");
    const auto before = reader.generation;
    Check(!gate.TryRead(reader), "active lease cannot be overwritten");
    std::atomic<bool> entered{false}, original{false}, finish{false};
    std::thread writer([&] {
        entered = true;
        gate.BeginMutation();
        original = true;
        // Recursive mutation calls never encounter a held extension lock.
        gate.BeginMutation(); gate.EndMutation();
        while (!finish.load()) { std::this_thread::yield(); }
        gate.EndMutation();
    });
    while (!entered.load()) { std::this_thread::yield(); }
    const auto deadline = GetTickCount64() + 5000;
    while (gate.Current(before) && GetTickCount64() < deadline) { std::this_thread::yield(); }
    Check(!gate.Current(before), "writer invalidates old candidate before call-through");
    Check(!original.load(), "growth or teardown cannot run during pointer acquisition");
    Check(!gate.TryRead(other), "pending writer excludes new acquisition");
    reader.Reset();
    while (!original.load() && GetTickCount64() < deadline) { std::this_thread::yield(); }
    Check(original.load(), "mutation progresses when bounded acquisition releases");
    Check(!gate.TryRead(other), "original callback remains exclusive after SRW unlock");
    std::atomic<bool> concurrent_original{false};
    std::thread concurrent_writer([&] {
        gate.BeginMutation(); concurrent_original = true; gate.EndMutation();
    });
    const auto concurrent_deadline = GetTickCount64() + 5000;
    while (!concurrent_original.load() && GetTickCount64() < concurrent_deadline) { std::this_thread::yield(); }
    Check(concurrent_original.load(), "admission excludes readers but does not serialize native writers");
    finish = true; writer.join(); concurrent_writer.join();
    Check(gate.TryRead(other) && other.generation != before, "fresh post-mutation acquisition has a new generation");
    const auto after = other.generation; other.Reset();
    Check(gate.Current(after), "completed fresh snapshot is current");
    gate.BeginMutation(); gate.EndMutation();
    Check(!gate.Current(after), "nested or later mutation rejects stale indication");
    gate.Retire();
    Check(!gate.TryRead(other), "retirement permanently closes acquisition");
    gate.BeginMutation(); gate.EndMutation();
    Check(!gate.Current(after), "retirement preserves original mutation call-through without reviving a candidate");
    return failures ? 1 : 0;
}
