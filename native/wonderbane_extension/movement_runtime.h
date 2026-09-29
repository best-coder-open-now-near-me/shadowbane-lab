#pragma once
#include <Windows.h>
#include "event_channel.h"
#include "movement_controls.h"
#include "movement_lifetime.h"
#include "movement_wire.h"
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
// Owner-service phase only. Published status cannot substitute for these gates.
// Action admission includes fresh UI/focus and the exact acquisition host lease.
bool NativeOwnerActionCurrent(const NativeScene&, const Grant&, const wire::Host&) noexcept;
Result BeginNativeOwnerAction(const NativeScene&, const Grant&, const wire::Host&) noexcept;
// Cleanup may run after lease/focus loss, but never against a replacement Grant.
bool NativeOwnerStopCurrent(const NativeScene&, const Grant&) noexcept;
Result PauseNativeOwnerAction(const NativeScene&, const Grant&) noexcept;
DWORD StartNativeMovementControls(const ProcessIdentity&) noexcept;
// Read-only, no automation host lease acquisition, safe for the status publisher.
bool ReadNativeMovementControls(RuntimeSnapshot&) noexcept;
// Called only by the exact client window thread; expected remains immutable
// across UI editing or queued dispatch. Stale configuration cannot stop new work.
Result ConfigureNativeMovementControls(const RuntimeSnapshot& expected, const Settings&) noexcept;
}
