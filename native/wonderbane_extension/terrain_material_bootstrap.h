#pragma once

#if defined(_WIN32)
#include <windows.h>
#else
using HMODULE = void*;
#endif

namespace wonderbane::extension::terrain_material {

// Loader-lock-safe entry: queues a worker and returns immediately. The worker
// pins the full-renderer DLL before installing hooks, preventing an explicit
// unload from leaving client code pointed at freed extension text.
[[nodiscard]] bool QueueTerrainMaterialRepairStartup(
    HMODULE extension_module) noexcept;

}  // namespace wonderbane::extension::terrain_material
