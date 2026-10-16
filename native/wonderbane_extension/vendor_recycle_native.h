#pragma once
#include "vendor_native.h"
#include "vendor_production_responses.h"
#include <array>
#include <algorithm>

namespace wonderbane::extension::vendor_recycle {
constexpr std::size_t kItems = 48;
using Items = std::array<std::uint32_t, kItems>;
using Digest = std::array<unsigned char, 32>;
bool Qualified(std::uintptr_t image) noexcept;
struct Manifest {
    vendor::wire::Snapshot owner{};
    Items items{}, entries{}, instances{}, native_items{};
    std::uint32_t count = 0, gold = 0, refund = 0;
    Digest digest{};
    bool operator==(const Manifest& b) const noexcept {
        return vendor::wire::Equal(owner,b.owner) && items==b.items && entries==b.entries
            && native_items==b.native_items
            && instances==b.instances && count==b.count && gold==b.gold
            && refund==b.refund && digest==b.digest;
    }
};
// Read current owned stock, not arbitrary item pointers supplied by a host.
// Capture requires an empty production queue and empty manual selection set.
bool Capture(std::uintptr_t image, const movement::NativeScene&,
    const vendor::wire::Snapshot&, const Items&, std::uint32_t count, Manifest&) noexcept;
// Corroboration only: the caller must already hold the exact positive server
// receipt. Missing displayed items alone never complete a native command.
bool Corroborate(std::uintptr_t image,const vendor::wire::Snapshot&,
    const Items&,std::uint32_t count,std::uint32_t gold) noexcept;
using Admission = bool (*)(void*) noexcept;
// Populates the ordinary client's selection and calls its batch sender once.
// Any failed or interrupted selection/call is uncertain and must not be replayed.
vendor::wire::Outcome Invoke(std::uintptr_t image, const movement::NativeScene&,
    const Manifest&, Admission, void*) noexcept;
}
