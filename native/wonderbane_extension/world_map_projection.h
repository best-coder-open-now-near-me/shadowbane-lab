#pragma once

#include <Windows.h>

#include <cstdint>

namespace wonderbane::extension {

struct WorldMapProjection {
    bool open;
    std::int32_t left;
    std::int32_t top;
    std::int32_t right;
    std::int32_t bottom;
    std::int32_t left_padding;
    std::int32_t top_padding;
    std::int32_t right_padding;
    std::int32_t bottom_padding;
    float zoom;
    std::int32_t horizontal_pan;
    std::int32_t vertical_pan;
    double world_length;
    double world_width;
};

struct ResolvedWorldMapDestination {
    double lt;
    double lg;
    std::int32_t client_x;
    std::int32_t client_y;
};

bool ProjectWorldMapDestination(
    const WorldMapProjection& projection,
    POINT client_origin,
    POINT desktop_point,
    ResolvedWorldMapDestination* destination
) noexcept;

}  // namespace wonderbane::extension
