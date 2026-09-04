#include "terrain_material_bootstrap.h"

#include "terrain_material_runtime.h"

#include <atomic>

#if defined(WB_ENABLE_TERRAIN_MATERIAL_REPAIR) && defined(_WIN32) && !defined(_WIN64)
#include <windows.h>
#endif

namespace wonderbane::extension::terrain_material {
namespace {

std::atomic<bool> g_startup_queued{false};

#if defined(WB_ENABLE_TERRAIN_MATERIAL_REPAIR) && defined(_WIN32) && !defined(_WIN64)

DWORD WINAPI TerrainMaterialRepairWorker(void*) noexcept {
    HMODULE pinned_module = nullptr;
    if (!GetModuleHandleExW(
            GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                GET_MODULE_HANDLE_EX_FLAG_PIN,
            reinterpret_cast<LPCWSTR>(&TerrainMaterialRepairWorker),
            &pinned_module)) {
        return 1U;
    }

    // Do not race the loader's process-attach path. The worker cannot execute
    // extension code until the loader lock is released, but yielding once keeps
    // that ordering explicit and avoids doing file hashing from DllMain.
    Sleep(0U);
    return InitializeTerrainMaterialRepair() ? 0U : 2U;
}

#endif

}  // namespace

bool QueueTerrainMaterialRepairStartup(HMODULE extension_module) noexcept {
#if !defined(WB_ENABLE_TERRAIN_MATERIAL_REPAIR) || !defined(_WIN32) || defined(_WIN64)
    (void)extension_module;
    return false;
#else
    if (extension_module == nullptr) {
        return false;
    }
    bool expected = false;
    if (!g_startup_queued.compare_exchange_strong(
            expected, true, std::memory_order_acq_rel)) {
        return true;
    }

    const HANDLE thread = CreateThread(
        nullptr,
        0U,
        &TerrainMaterialRepairWorker,
        nullptr,
        0U,
        nullptr);
    if (thread == nullptr) {
        g_startup_queued.store(false, std::memory_order_release);
        return false;
    }
    CloseHandle(thread);
    return true;
#endif
}

}  // namespace wonderbane::extension::terrain_material
