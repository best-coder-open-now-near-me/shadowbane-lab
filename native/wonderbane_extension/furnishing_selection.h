#pragma once
#include <array>
#include <cstddef>
#include <cstdint>

namespace wonderbane::extension::furnishing {
using Address = std::uint32_t;
using Key = std::array<std::uint32_t, 2>;
// Native order: translation XYZ, quaternion WXYZ, scale XYZ.
using Transform = std::array<float, 10>;
bool ValidTransform(const Transform&) noexcept;
struct Selection {
    Address root = 0, actor = 0, structure = 0, hud = 0, manager = 0;
    Address list = 0, row = 0, entry = 0, deed = 0, model = 0, render = 0, layout = 0;
    std::uint64_t epoch = 0;
    Key building{}, item{}, asset{};
    std::uint32_t floor = 0;
    Transform building_world{};
    // The same native mapping inputs used by the floor-height method.
    std::array<std::int32_t, 2> dimensions{};
    std::array<float, 2> offset{};
    std::array<std::int32_t, 4> rectangle{};
    float zoom = 0, layout_scale = 0;
    bool SameIdentity(const Selection&) const noexcept;
};
// This is a synchronous owner-thread capture, not a lifetime lease. The caller
// supplies an already observed native lifetime and keeps/rechecks that authority
// across any following retain/clone. No native call or ownership transfer here.
class SelectionCapture {
public:
    struct Owner {
        Address root = 0, actor = 0, parent = 0;
        std::uint64_t epoch = 0;
    };
    struct Access {
        void* context = nullptr;
        bool (*read)(void*, Address, void*, std::size_t) noexcept = nullptr;
        bool (*current)(void*, const Owner&) noexcept = nullptr;
        Address base = 0; // Caller must first seal the exact reviewed image.
    };
    explicit SelectionCapture(Access access) noexcept : access_(access) {}
    bool Capture(const Owner&, Selection&) noexcept;
private:
    struct Block { Address at = 0; std::size_t size = 0; std::array<unsigned char, 40> bytes{}; };
    bool Read(Address, void*, std::size_t) noexcept;
    template<class T> bool Read(Address at, T& out) noexcept { return Read(at, &out, sizeof(out)); }
    bool Require(Address, Address) noexcept;
    bool Type(Address, Address rva) noexcept;
    bool Vector(Address, Address*, std::size_t, std::size_t&) noexcept;
    bool Hud(Address root, Address&) noexcept;
    bool LayoutName(Address) noexcept;
    bool Run(const Owner&, Selection&) noexcept;
    bool Verify() const noexcept;
    Access access_{};
    bool running_ = false;
    std::size_t count_ = 0;
    // Persistent journal avoids large callback stacks or owner-frame allocation.
    std::array<Block, 4096> blocks_{};
};
}
