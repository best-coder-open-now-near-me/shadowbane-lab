#pragma once
#include "movement_lifetime.h"
#include <cstring>

namespace wonderbane::extension::combat::party {
using Key = std::array<std::uint32_t, 2>;
inline constexpr std::size_t kMaximumMembers = 10;
struct Member {
    std::uintptr_t node = 0, next = 0, previous = 0, entry = 0;
    Key key{};
    std::uint32_t role = 0;
    bool operator==(const Member&) const = default;
};
struct Snapshot {
    movement::NativeScene scene{};
    std::uintptr_t manager = 0, sentinel = 0, head = 0, tail = 0;
    std::array<Member, kMaximumMembers> members{};
    std::size_t count = 0;
    bool valid = false;
};
inline bool Equal(const Snapshot& a, const Snapshot& b) noexcept {
    return a.valid && b.valid && a.scene.actor == b.scene.actor
        && a.scene.parent == b.scene.parent && a.scene.world == b.scene.world
        && a.scene.window == b.scene.window && a.scene.identity == b.scene.identity
        && a.scene.epoch == b.scene.epoch && a.manager == b.manager
        && a.sentinel == b.sentinel && a.head == b.head && a.tail == b.tail
        && a.count == b.count && a.members == b.members;
}
inline bool Protected(const Snapshot& snapshot, Key key) noexcept {
    if (!snapshot.valid || snapshot.count > kMaximumMembers || !key[0] || !key[1]
        || key == snapshot.scene.identity) { return true; }
    for (std::size_t i = 0; i < snapshot.count; ++i) {
        if (snapshot.members[i].key == key) { return true; }
    }
    return false;
}
namespace detail {
inline bool Pointer(std::uintptr_t at, std::size_t size) noexcept {
    return at >= 0x10000 && size <= 0x7fff0000 && at <= 0x7fff0000 - size && at % 4 == 0;
}
template<class T> bool Read(std::uintptr_t at, T& out) noexcept {
    if (!Pointer(at, sizeof(T))) { return false; }
    __try { std::memcpy(&out, reinterpret_cast<const void*>(at), sizeof(T)); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
inline bool Current(std::uintptr_t base, const movement::NativeScene& scene) noexcept {
    std::uintptr_t window = 0, actor = 0, world = 0;
    Key key{};
    return scene.epoch && Pointer(scene.window, 0x9c) && Pointer(scene.actor, 0x20)
        && scene.identity[0] && scene.identity[1] && movement::NativeMovementLifetimeCurrent(scene)
        && Read(base + 0x16a7bfc, window) && window == scene.window
        && Read(base + 0x16a2d98, actor) && actor == scene.actor
        && Read(base + 0x1389028, world) && world == scene.world
        && Read(actor + 0x18, key) && key == scene.identity;
}
inline bool Pass(std::uintptr_t base, const movement::NativeScene& scene, Snapshot& out) noexcept {
    if (!Current(base, scene)) { return false; }
    out = {}; out.scene = scene;
    // Same calibrated ArcGroupManager layout as native-group.json. Only keys
    // and roster structure grant protection; names/resources never grant attack.
    if (!Read(scene.window + 0x98, out.manager) || !Pointer(out.manager, 0xa0)
        || !Read(out.manager + 0x9c, out.sentinel) || !Pointer(out.sentinel, 12)
        || !Read(out.sentinel, out.head) || !Read(out.sentinel + 4, out.tail)) { return false; }
    auto node = out.head;
    auto previous = out.sentinel;
    std::size_t leaders = 0;
    while (node != out.sentinel) {
        if (out.count == kMaximumMembers || !Pointer(node, 12)) { return false; }
        Member member{}; member.node = node;
        if (!Read(node, member.next) || !Read(node + 4, member.previous)
            || member.previous != previous || !Read(node + 8, member.entry)
            || !Pointer(member.entry, 0x78) || !Read(member.entry + 0x10, member.key)
            || !member.key[0] || !member.key[1] || !Read(member.entry + 0x74, member.role)
            || (member.role != 0 && member.role != 0x15 && member.role != 0x16)) { return false; }
        if (member.role == 0x16 && ++leaders > 1) { return false; }
        for (std::size_t i = 0; i < out.count; ++i) {
            if (out.members[i].node == node || out.members[i].entry == member.entry
                || out.members[i].key == member.key) { return false; }
        }
        out.members[out.count++] = member;
        previous = node; node = member.next;
    }
    if (out.tail != previous) { return false; }
    out.valid = true;
    return true;
}
}
// Owner-update thread only, after exact image verification. No client callbacks,
// allocation, retries, or fallback to a partial/previous roster. The caller must
// recapture immediately before native admission; a snapshot is not a lease.
inline bool Capture(std::uintptr_t image_base, const movement::NativeScene& scene,
                    Snapshot& out) noexcept {
    out = {};
    if (!detail::Pointer(image_base, 0x16a7c00)) { return false; }
    Snapshot first{}, second{};
    if (!detail::Pass(image_base, scene, first) || !detail::Pass(image_base, scene, second)
        || !Equal(first, second) || !detail::Current(image_base, scene)) { return false; }
    out = second;
    return true;
}
}
