#include "world_map_projection.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>

namespace wonderbane::extension {

bool ProjectWorldMapDestination(
    const WorldMapProjection& projection,
    const POINT client_origin,
    const POINT desktop_point,
    ResolvedWorldMapDestination* const destination
) noexcept {
    if (
        destination == nullptr
        || !projection.open
        || projection.right <= projection.left
        || projection.bottom <= projection.top
        || projection.left_padding < 0
        || projection.top_padding < 0
        || projection.right_padding < 0
        || projection.bottom_padding < 0
        || !std::isfinite(projection.zoom)
        || projection.zoom <= 0.0F
        || !std::isfinite(projection.world_length)
        || !std::isfinite(projection.world_width)
        || projection.world_length <= 0.0
        || projection.world_width <= 0.0
    ) {
        return false;
    }
    const std::int64_t client_x =
        static_cast<std::int64_t>(desktop_point.x) - client_origin.x;
    const std::int64_t client_y =
        static_cast<std::int64_t>(desktop_point.y) - client_origin.y;
    if (
        client_x < std::numeric_limits<std::int32_t>::min()
        || client_x > std::numeric_limits<std::int32_t>::max()
        || client_y < std::numeric_limits<std::int32_t>::min()
        || client_y > std::numeric_limits<std::int32_t>::max()
    ) {
        return false;
    }
    const auto local_x = static_cast<std::int32_t>(client_x);
    const auto local_y = static_cast<std::int32_t>(client_y);
    if (
        local_x < projection.left
        || local_x >= projection.right
        || local_y < projection.top
        || local_y >= projection.bottom
    ) {
        return false;
    }
    const double content_width = static_cast<double>(
        projection.right
        - projection.left
        - projection.left_padding
        - projection.right_padding
    );
    const double content_height = static_cast<double>(
        projection.bottom
        - projection.top
        - projection.top_padding
        - projection.bottom_padding
    );
    if (content_width <= 0.0 || content_height <= 0.0) {
        return false;
    }
    const double map_x = static_cast<double>(local_x - projection.left);
    const double map_y = static_cast<double>(local_y - projection.top);
    const double projected_x = (
        (map_x + projection.horizontal_pan) / projection.zoom
        - projection.left_padding
    ) / content_width;
    const double projected_y = (
        (map_y + projection.vertical_pan) / projection.zoom
        - projection.top_padding
    ) / content_height;
    const double lt = projected_x * projection.world_length;
    const double lg = (1.0 - projected_y) * projection.world_width;
    const double tolerance = std::max(
        projection.world_length,
        projection.world_width
    ) * 1e-6;
    if (
        !std::isfinite(lt)
        || !std::isfinite(lg)
        || lt < -tolerance
        || lg < -tolerance
        || lt > projection.world_length + tolerance
        || lg > projection.world_width + tolerance
    ) {
        return false;
    }
    *destination = ResolvedWorldMapDestination{
        std::clamp(lt, 0.0, projection.world_length),
        std::clamp(lg, 0.0, projection.world_width),
        local_x,
        local_y,
    };
    return true;
}

}  // namespace wonderbane::extension
