#pragma once
#include "movement_lifetime_bindings.h"
namespace wonderbane::extension::movement {
// Primary vtable slots in the authenticated client. These callbacks extend the
// existing lifetime observer; they do not own movement or action dispatch.
inline constexpr std::array<LifetimeBinding, 5> kDoorAppendBindings{{
    {0x1143930, 0xfd58}, {0x115af78, 0xfd58}, {0x115b1bc, 0xfd58},
    {0x115b400, 0xfd58}, {0x1177d20, 0xfd58},
}};
inline constexpr std::array<LifetimeBinding, 5> kDoorResetBindings{{
    {0x11438c4, 0x23fdd}, {0x115af0c, 0x23fdd}, {0x115b150, 0x23fdd},
    {0x115b394, 0x23fdd}, {0x1177cb4, 0x23fdd},
}};
inline constexpr std::array<LifetimeBinding, 5> kDoorLoadBindings{{
    {0x1143828, 0x7cd4}, {0x115ae70, 0x1ccdd}, {0x115b0b4, 0x1ccdd},
    {0x115b2f8, 0x1ccdd}, {0x1177c18, 0xea93},
}};
constexpr bool DoorCollectionFinalizer(std::uint32_t slot) noexcept {
    return slot == 0x11437ac || slot == 0x1143ec4 || slot == 0x115adf4
        || slot == 0x115b038 || slot == 0x115b27c || slot == 0x1177b9c;
}
}
