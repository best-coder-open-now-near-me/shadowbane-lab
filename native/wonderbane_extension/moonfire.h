#pragma once
#include <cstdint>
namespace wonderbane::extension::weapon {
struct FireSettings {
    std::uint32_t enabled=1;
    float strength=1.11F,size=1.F,spacing=.8F,pulse=.35F,hilt=1.25F,width=.86F;
};
inline bool ValidFire(const FireSettings& s) noexcept {
    return s.enabled<=1 && s.strength>=0 && s.strength<=1.5F
        && s.size>=.6F && s.size<=1.5F && s.spacing>=.8F && s.spacing<=1.5F
        && s.pulse>=0 && s.pulse<=.35F && s.hilt>=.25F && s.hilt<=2.5F
        && s.width>=.4F && s.width<=4.F;
}
// Draw immediately after the owned native weapon submission using its model matrix.
// Returns zero on success, otherwise a reason for conservative suppression.
unsigned DrawMoonfire(const FireSettings&,double seconds) noexcept;
}
