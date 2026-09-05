#pragma once
#include "graphics_status.h"
#include <array>
#include <cstdint>
namespace wonderbane::extension::sky {
struct Vec { float x=0,y=0,z=0; };
struct Settings {
    std::uint32_t enabled=0;
    float orientation=0, intensity=1, horizon_height=0, horizon_width=0.22F;
    float clouds=0.7F, sun=0.6F, fog_match=1;
};
struct Cloud { Vec direction,right; float width,height,opacity; };
struct Asset {
    std::uint32_t magic,version,count,size;
    Vec zenith,horizon,nadir,sun,sun_color,cloud_color;
    std::array<Cloud,12> clouds;
};
static_assert(sizeof(Asset)==520);
static_assert(sizeof(Settings)==32);
bool Valid(const Settings&) noexcept;
bool ValidAsset(const Asset&) noexcept;
Vec Ray(const GraphicsCameraState&,float x,float y,float orientation) noexcept;
Vec Shade(const Asset&,const Settings&,Vec direction,Vec fog,bool fog_enabled) noexcept;
// Fresh upload proof is distinct from final scene-camera publication.
struct Authority {
    std::array<float,16> view{};
    std::uintptr_t context=0;
    std::uint64_t generation=0;
    bool fresh=false,painted=false;
    void Reset() noexcept { *this={}; }
    void Upload(const float*,std::uintptr_t,std::uint64_t) noexcept;
    bool Consume(const GraphicsCameraState*,std::uintptr_t,std::uint64_t,bool scene) noexcept;
};
bool Render(const Asset&,const Settings&,const GraphicsCameraState&) noexcept;
}
