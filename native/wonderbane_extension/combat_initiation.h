#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
namespace wonderbane::extension::combat::initiation {
// Protocol bookkeeping, not effect lifetime, hit confirmation or buff consumption.
constexpr std::size_t maximum_ids = 256;
struct Snapshot {
    std::uint32_t state{};
    std::array<std::uint32_t, maximum_ids> ids{};
    std::uint32_t count{};
    bool Clear() const noexcept { return state >= 1 && state <= 7 && state != 6 && count == 0; }
    bool Only(std::uint32_t id) const noexcept {
        return id && count >= 1 && count <= 2 && ids[0] == id && (count == 1 || ids[1] == id);
    }
    bool operator==(const Snapshot&) const = default;
};
// The caller supplies an owner-thread bounded read and verifies actor/scene lifetime.
// Two complete captures detect changed geometry/data; no remote ABA claim is made.
template<class Reader>
bool Capture(std::uintptr_t actor, std::uintptr_t state, Snapshot& out, Reader read) noexcept {
    using Header = std::array<std::uint32_t, 3>;
    const auto once = [&](Snapshot& value, Header& header) noexcept {
        if (!read(state + 0x10, value.state) || value.state < 1 || value.state > 7
            || !read(actor + 0x65c, header)) { return false; }
        const auto begin = header[0], end = header[1], capacity = header[2];
        if (!begin) { return !end && !capacity; }
        if (begin < 0x10000 || begin % 4 || end % 4 || capacity % 4
            || end < begin || capacity < end || capacity > 0x7fff0000
            || capacity - begin > maximum_ids * 4) { return false; }
        value.count = (end - begin) / 4;
        for (std::uint32_t i = 0; i < value.count; ++i) {
            if (!read(begin + i * 4, value.ids[i]) || !value.ids[i]) { return false; }
        }
        return true;
    };
    Snapshot first{}, second{}; Header before{}, after{}, final{};
    if (!once(first, before) || !once(second, after) || before != after || first != second
        || !read(actor + 0x65c, final) || final != before) { return false; }
    out = first; return true;
}
}
