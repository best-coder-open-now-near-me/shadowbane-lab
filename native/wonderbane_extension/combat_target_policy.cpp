#include "combat_target_policy.h"
#include <cmath>
#include <algorithm>

namespace wonderbane::extension::combat::policy {
namespace {
constexpr std::array<std::uintptr_t, 6> descriptors{
    0x1373238, 0x13732a8, 0x1373098, 0x1373080, 0x13730b0, 0x1373148};
constexpr std::uint32_t maximum_bits = 16;
bool Pointer(std::uintptr_t at, std::size_t size) noexcept {
    return at >= 0x10000 && size <= 0x7fff0000 && at <= 0x7fff0000 - size;
}
template<class T> bool Read(std::uintptr_t at, T& out) noexcept {
    if (!Pointer(at, sizeof(T))) { return false; }
    __try { std::memcpy(&out, reinterpret_cast<const void*>(at), sizeof(T)); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
bool Current(HWND window, std::uintptr_t image, const movement::NativeScene& scene) noexcept {
    DWORD process{}; std::uintptr_t actor_table{};
    return Read(scene.actor, actor_table) && actor_table == image + 0x114165c
        && scene.identity[0] && scene.identity[1] == 53 && GetWindowThreadProcessId(window, &process) == GetCurrentThreadId()
        && process == GetCurrentProcessId() && party::detail::Current(image, scene);
}
bool Pass(HWND window, std::uintptr_t image, const movement::NativeScene& scene,
    std::uintptr_t target, Key key, Object& out) noexcept {
    out = {}; out.address = target;
    if (!Current(window, image, scene) || !Pointer(target, 0x5d4) || target % 4
        || !key[0] || key[1] != 37 || key == scene.identity || target == scene.actor
        || !Read(target, out.table) || out.table != image + 0x114165c
        || !Read(target + 0x18, out.key) || out.key != key
        || !Read(target + 0x5cc, out.health) || !Read(target + 0x5d0, out.maximum)
        || !std::isfinite(out.health) || !std::isfinite(out.maximum) || out.maximum <= 0
        || out.health > out.maximum + (std::max)(0.001f, out.maximum * 0.00001f)
        || !Read(target + 0x34, out.buckets) || !Read(target + 0x38, out.bits)
        || out.bits > maximum_bits) { return false; }
    for (std::size_t i = 0; i < descriptors.size(); ++i) {
        auto& found = out.descriptors[i];
        if (!Read(image + descriptors[i] + 4, found.key) || !found.key || found.key == UINT32_MAX) { return false; }
        for (std::size_t j = 0; j < i; ++j) {
            if (out.descriptors[j].key == found.key) { return false; }
        }
    }
    // Native 141330 is a first-match keyed lookup and cannot reject duplicate
    // protected descriptors. Stream every slot instead, retaining only six
    // relevant observations. No 512 KiB table allocation or cache is needed.
    if (out.buckets) {
        const auto count = std::size_t{1} << out.bits;
        if (out.buckets % 4 || !Pointer(out.buckets, count * 8)) { return false; }
        for (std::size_t index = 0; index < count; ++index) {
            std::array<std::uint32_t, 2> bucket{};
            const auto address = out.buckets + index * 8;
            if (!Read(address, bucket)) { return false; }
            if (!bucket[0] || bucket[0] == UINT32_MAX) { continue; }
            for (std::size_t i = 0; i < out.descriptors.size(); ++i) {
                auto& found = out.descriptors[i];
                if (bucket[0] != found.key) { continue; }
                if (found.present) { return false; }
                found.present = true; found.bucket = address; found.node = bucket[1];
                if (i == static_cast<std::size_t>(Role::merchant)) { found.enabled = true; }
                else if (i == static_cast<std::size_t>(Role::pet)) {
                    if (found.node % 4 || !Read(found.node, found.owner)
                        || !found.owner[0] || !found.owner[1] || found.owner == key) { return false; }
                    found.enabled = true;
                } else {
                    std::uint8_t value{};
                    if (!Pointer(found.node, 8) || found.node % 4
                        || !Read(found.node + 4, found.value) || !Read(found.value, value)
                        || value > 1) { return false; }
                    found.enabled = value != 0;
                }
            }
        }
    }
    return Current(window, image, scene);
}
}
Outcome Capture(HWND window, std::uintptr_t image, const movement::NativeScene& scene,
    void* retained_target, Key expected, Snapshot& output) noexcept {
    output = {};
    if (!image || !Current(window, image, scene)) { return Outcome::invalid; }
    Snapshot first{}; Object second{}; party::Snapshot after{};
    const auto target = reinterpret_cast<std::uintptr_t>(retained_target);
    if (!party::Capture(image, scene, first.party) || !Pass(window, image, scene, target, expected, first.object)
        || !Pass(window, image, scene, target, expected, second) || first.object != second
        || !party::Capture(image, scene, after) || !party::Equal(first.party, after)
        || !Current(window, image, scene)) { return Outcome::invalid; }
    bool protected_target = first.object.health <= 0 || party::Protected(first.party, expected);
    for (const auto& descriptor : first.object.descriptors) { protected_target |= descriptor.enabled; }
    first.outcome = protected_target ? Outcome::protected_target : Outcome::eligible;
    output = first;
    return output.outcome;
}
}
