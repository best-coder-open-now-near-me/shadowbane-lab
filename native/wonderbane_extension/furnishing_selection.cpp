#include "furnishing_selection.h"
#include <algorithm>
#include <cmath>
#include <cstring>

namespace wonderbane::extension::furnishing {
namespace {
bool Pointer(Address p) noexcept { return p >= 0x10000 && p < 0x7fff0000 && p % 4 == 0; }
bool ValidKey(Key k, Address type) noexcept { return k[0] && k[0] != 0xffffffff && k[1] == type; }
}
bool ValidTransform(const Transform& t) noexcept {
    for (float v : t) { if (!std::isfinite(v)) { return false; } }
    const double norm = double(t[3])*t[3] + double(t[4])*t[4] + double(t[5])*t[5] + double(t[6])*t[6];
    return norm >= 0.999 && norm <= 1.001 && t[7] != 0 && t[8] != 0 && t[9] != 0;
}
bool Selection::SameIdentity(const Selection& s) const noexcept {
    return root == s.root && actor == s.actor && structure == s.structure && hud == s.hud
        && manager == s.manager && list == s.list && row == s.row && entry == s.entry
        && deed == s.deed && model == s.model && render == s.render && layout == s.layout
        && epoch == s.epoch && building == s.building && item == s.item && asset == s.asset && floor == s.floor;
}
bool SelectionCapture::Read(Address at, void* out, std::size_t size) noexcept {
    if (!Pointer(at) || !size || size > 40 || at > 0x7fff0000 - size
        || count_ == blocks_.size() || !access_.read) { return false; }
    auto& block = blocks_[count_];
    if (!access_.read(access_.context, at, block.bytes.data(), size)) { return false; }
    block.at = at; block.size = size; ++count_;
    std::memcpy(out, block.bytes.data(), size); return true;
}
bool SelectionCapture::Require(Address at, Address expected) noexcept {
    Address value = 0; return Read(at, value) && value == expected;
}
bool SelectionCapture::Type(Address at, Address rva) noexcept { return Require(at, access_.base + rva); }
bool SelectionCapture::Vector(Address at, Address* out, std::size_t limit, std::size_t& count) noexcept {
    std::array<Address, 3> v{}; count = 0;
    if (!Read(at, v)) { return false; }
    if (v == std::array<Address, 3>{}) { return true; }
    if (!Pointer(v[0]) || !Pointer(v[1]) || !Pointer(v[2]) || v[0] > v[1]
        || v[1] > v[2] || (v[1] - v[0]) / 4 > limit) { return false; }
    for (Address p = v[0]; p < v[1]; p += 4) {
        Address value = 0;
        if (!Read(p, value) || !Pointer(value) || std::find(out, out + count, value) != out + count) { return false; }
        out[count++] = value;
    }
    return true;
}
bool SelectionCapture::Hud(Address root, Address& result) noexcept {
    Address head = 0; std::array<Address, 2> ends{};
    if (!Read(root + 0x20, head) || !Read(head, ends)) { return false; }
    std::array<Address, 128> nodes{}, huds{};
    auto at = ends[0], previous = head; std::size_t count = 0; result = 0;
    while (at != head) {
        std::array<Address, 3> node{}; Address table = 0;
        if (count == nodes.size() || std::find(nodes.begin(), nodes.begin() + count, at) != nodes.begin() + count
            || !Read(at, node) || node[1] != previous || !Pointer(node[2])
            || std::find(huds.begin(), huds.begin() + count, node[2]) != huds.begin() + count
            || !Read(node[2], table)) { return false; }
        nodes[count] = at; huds[count++] = node[2];
        if (table == access_.base + 0x1167c68) {
            if (result) { return false; } result = node[2];
        }
        previous = at; at = node[0];
    }
    return previous == ends[1] && result;
}
bool SelectionCapture::LayoutName(Address layout) noexcept {
    std::array<Address, 3> s{};
    // ArcString stores UTF-16 begin/end/capacity after its allocator word.
    constexpr char16_t name[] = u"BTNPROPLAYOUT";
    static_assert(sizeof(name) == 28);
    if (!Read(layout + 0x168, s) || !Pointer(s[0]) || s[1] < s[0] || s[1] - s[0] != 26
        || s[2] < s[1] || s[2] >= 0x7fff0000 || s[2] % 2) { return false; }
    std::array<char16_t, 13> actual{};
    return Read(s[0], actual) && std::memcmp(actual.data(), name, 26) == 0;
}
bool SelectionCapture::Run(const Owner& owner, Selection& s) noexcept {
    s.root = owner.root; s.actor = owner.actor; s.structure = owner.parent; s.epoch = owner.epoch;
    Address component = 0, pose = 0;
    if (!owner.epoch || !Type(s.root, 0x1174884) || !Require(s.root + 0x64, 2)
        || !Require(access_.base + 0x16a7bfc, s.root) || !Require(access_.base + 0x16a2d98, s.actor)
        || !Type(s.actor, 0x114165c) || !Read(s.actor + 0x4b0, component) || !Read(component, pose)
        || !Require(pose + 8, s.structure) || !Type(s.structure, 0x1177c0c)
        || !Read(s.structure + 0x18, s.building) || !ValidKey(s.building, 8)
        || !Hud(s.root, s.hud) || !Read(s.root + 0xa4, s.manager) || !Type(s.manager, 0x1171adc)
        || !Require(s.hud + 0x104, s.manager) || !Require(s.manager + 0xa8, s.hud)
        || !Require(s.hud + 0x64c, s.structure)) { return false; }
    std::array<Address, 512> children{}; std::size_t count = 0;
    if (!Vector(s.hud + 0x54, children.data(), children.size(), count)
        || !Read(s.hud + 0x524, s.list) || !Read(s.hud + 0x648, s.layout)
        || std::find(children.begin(), children.begin() + count, s.list) == children.begin() + count
        || std::find(children.begin(), children.begin() + count, s.layout) == children.begin() + count
        || !Type(s.list, 0x116acf0) || !Require(s.list + 0x3bc, s.hud)
        || !Require(s.layout + 0x3bc, s.hud) || !LayoutName(s.layout)
        || !Read(s.hud + 0x660, s.entry) || !Pointer(s.entry)) { return false; }
    std::array<Address, 128> rows{}, entries{}; Address selected = 0;
    if (!Vector(s.list + 0x408, rows.data(), rows.size(), count) || !Read(s.list + 0x404, selected)) { return false; }
    for (std::size_t i = 0; i < count; ++i) {
        Address entry = 0;
        if (!Type(rows[i], 0x116aebc) || !Require(rows[i] + 0x3bc, s.hud)
            || !Require(rows[i] + 0x458, s.list) || !Read(rows[i] + 0x44c, entry)
            || !Type(entry, 0x1169908) || !Require(entry + 8, 0x25)
            || std::find(entries.begin(), entries.begin() + i, entry) != entries.begin() + i) { return false; }
        entries[i] = entry; if (entry == s.entry) { s.row = rows[i]; }
    }
    if (!s.row || (selected && selected != s.row) || !Read(s.entry + 0x10, s.item) || !ValidKey(s.item, 30)
        || !Read(s.entry + 0x20, s.deed) || !Type(s.deed, 0x1142468)
        || !Read(s.deed + 0x7b8, s.asset) || !ValidKey(s.asset, 0)
        || !Read(s.entry + 0x24, s.model) || !Type(s.model, 0x1143540)
        || !Type(s.model + 0x44, 0x114350c) || !Read(s.model + 0xc0, s.render)
        || !Type(s.render, 0x1149dbc) || !Type(s.render + 0x30, 0x1149d94)
        || !Read(s.hud + 0x628, s.floor)) { return false; }
    // The selected floor must belong to the very structure occupied by the actor.
    std::array<Address, 2> floors{};
    if (!Read(s.structure + 0x734, floors) || !Pointer(floors[0]) || !Pointer(floors[1])
        || floors[0] > floors[1] || (floors[1] - floors[0]) / 4 > 256
        || s.floor >= (floors[1] - floors[0]) / 4
        || !Read(s.structure + 0x4b0, component) || !Read(component, pose)
        || !Read(pose + 0x20, s.building_world) || !ValidTransform(s.building_world)
        || !Read(s.hud + 0x630, s.dimensions) || s.dimensions[0] <= 0 || s.dimensions[1] <= 0
        || !Read(s.hud + 0x638, s.offset) || !std::isfinite(s.offset[0]) || !std::isfinite(s.offset[1])
        || !Read(s.hud + 0x37c, s.zoom) || !std::isfinite(s.zoom) || s.zoom <= 0) { return false; }
    return true;
}
bool SelectionCapture::Verify() const noexcept {
    std::array<unsigned char, 40> actual{};
    for (auto i = count_; i > 0; --i) {
        const auto& block = blocks_[i - 1];
        if (!access_.read(access_.context, block.at, actual.data(), block.size)
            || std::memcmp(actual.data(), block.bytes.data(), block.size)) { return false; }
    }
    return true;
}
bool SelectionCapture::Capture(const Owner& owner, Selection& out) noexcept {
    out = {};
    if (running_) { return false; }
    running_ = true;
    if (!access_.current || !access_.current(access_.context, owner)
        || !Pointer(access_.base) || access_.base > 0x7d000000) { running_ = false; return false; }
    count_ = 0; Selection candidate{};
    const bool ok = Run(owner, candidate) && Verify() && access_.current(access_.context, owner);
    if (ok) { out = candidate; }
    running_ = false; return ok;
}
}
