#include "world_map_projection.h"

#include <Windows.h>

#include <cstdio>

namespace {

int Fail(const wchar_t* operation) noexcept {
    ::fwprintf(stderr, L"%s failed\n", operation);
    return 1;
}

}  // namespace

int wmain() {
    const wonderbane::extension::WorldMapProjection projection{
        true,
        0,
        0,
        1000,
        1000,
        0,
        0,
        0,
        0,
        1.0F,
        0,
        0,
        200000.0,
        100000.0,
    };
    wonderbane::extension::ResolvedWorldMapDestination destination{};
    if (!wonderbane::extension::ProjectWorldMapDestination(
            projection,
            POINT{10, 20},
            POINT{510, 520},
            &destination
        )) {
        return Fail(L"center projection");
    }
    if (
        destination.lt != 100000.0
        || destination.lg != 50000.0
        || destination.client_x != 500
        || destination.client_y != 500
    ) {
        return Fail(L"center destination validation");
    }
    if (wonderbane::extension::ProjectWorldMapDestination(
            projection,
            POINT{10, 20},
            POINT{9, 19},
            &destination
        )) {
        return Fail(L"outside projection rejection");
    }
    auto closed = projection;
    closed.open = false;
    if (wonderbane::extension::ProjectWorldMapDestination(
            closed,
            POINT{10, 20},
            POINT{510, 520},
            &destination
        )) {
        return Fail(L"closed map rejection");
    }
    auto panned = projection;
    panned.zoom = 2.0F;
    panned.horizontal_pan = 500;
    panned.vertical_pan = 500;
    if (!wonderbane::extension::ProjectWorldMapDestination(
            panned,
            POINT{10, 20},
            POINT{510, 520},
            &destination
        )) {
        return Fail(L"pan and zoom projection");
    }
    if (destination.lt != 100000.0 || destination.lg != 50000.0) {
        return Fail(L"pan and zoom destination validation");
    }
    return 0;
}
