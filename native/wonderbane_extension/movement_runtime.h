#pragma once
#include <Windows.h>
#include "event_channel.h"
#include "movement_controls.h"
namespace wonderbane::extension::movement {
struct RuntimeSnapshot {
    ProcessIdentity process{};
    HWND window = nullptr;
    Grant grant{};
    Settings settings{};
    std::uint64_t settings_revision = 0;
    bool bindings_available = false;
    bool ready = false;
    bool camera_available = false;
    bool terminal = false;
    bool controller_api_available = false;
    bool controller_connected = false;
};
DWORD StartNativeMovementControls(const ProcessIdentity&) noexcept;
// Read-only, no automation host lease acquisition, safe for the status publisher.
bool ReadNativeMovementControls(RuntimeSnapshot&) noexcept;
// Called only by the exact client window thread; expected remains immutable
// across UI editing or queued dispatch. Stale configuration cannot stop new work.
Result ConfigureNativeMovementControls(const RuntimeSnapshot& expected, const Settings&) noexcept;
}
