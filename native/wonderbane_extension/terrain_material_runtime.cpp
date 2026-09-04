#include "terrain_material_runtime.h"

#include "terrain_client_profile.generated.h"
#include "terrain_material_client_adapter.h"

#include <atomic>
#include <cstdint>

#if defined(_WIN32)
#include <windows.h>
#endif

namespace wonderbane::extension::terrain_material {
namespace {

std::atomic<RuntimeState> g_state{RuntimeState::inactive};
std::atomic<ClientVerificationError> g_verification{
    ClientVerificationError::unsupported_platform};
std::atomic<VtableHookResult> g_hook_result{
    VtableHookResult::invalid_argument};
std::atomic<std::uint64_t> g_builder_calls{0U};
std::atomic<std::uint64_t> g_repaired_terrains{0U};
std::atomic<std::uint64_t> g_rejected_terrains{0U};
std::atomic<std::uint64_t> g_failed_terrains{0U};
std::atomic_flag g_lifecycle_lock = ATOMIC_FLAG_INIT;
VtableHook g_builder_hook{};

class LifecycleLock final {
public:
    LifecycleLock() noexcept {
        while (g_lifecycle_lock.test_and_set(std::memory_order_acquire)) {
#if defined(_WIN32)
            YieldProcessor();
#endif
        }
    }
    ~LifecycleLock() {
        g_lifecycle_lock.clear(std::memory_order_release);
    }

    LifecycleLock(const LifecycleLock&) = delete;
    LifecycleLock& operator=(const LifecycleLock&) = delete;
};

#if defined(WB_ENABLE_TERRAIN_MATERIAL_REPAIR) && defined(_WIN32) && !defined(_WIN64)

using BuilderMethod = void* (__thiscall*)(
    void* builder,
    void** output_terrain,
    std::uint32_t terrain_resource,
    std::uint32_t terrain_group);

BuilderMethod g_original_builder = nullptr;
thread_local bool g_inside_builder_repair = false;

void CountRepairResult(const ClientRepairResult result) noexcept {
    switch (result) {
        case ClientRepairResult::repaired:
            g_repaired_terrains.fetch_add(1U, std::memory_order_relaxed);
            break;
        case ClientRepairResult::rejected:
        case ClientRepairResult::unavailable:
            g_rejected_terrains.fetch_add(1U, std::memory_order_relaxed);
            break;
        case ClientRepairResult::failed:
            g_failed_terrains.fetch_add(1U, std::memory_order_relaxed);
            break;
        case ClientRepairResult::unchanged:
            break;
    }
}

void* __fastcall BuilderHook(
    void* builder,
    void*,
    void** output_terrain,
    const std::uint32_t terrain_resource,
    const std::uint32_t terrain_group) noexcept {
    const auto original = g_original_builder;
    if (original == nullptr) {
        g_failed_terrains.fetch_add(1U, std::memory_order_relaxed);
        return nullptr;
    }

    void* result = original(
        builder,
        output_terrain,
        terrain_resource,
        terrain_group);
    g_builder_calls.fetch_add(1U, std::memory_order_relaxed);

    if (output_terrain == nullptr || *output_terrain == nullptr ||
        g_inside_builder_repair) {
        return result;
    }

    g_inside_builder_repair = true;
    ClientRepairResult repair_result = ClientRepairResult::failed;
    __try {
        repair_result = RepairBuiltTerrain(
            *output_terrain,
            Token{terrain_resource, terrain_group});
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        repair_result = ClientRepairResult::failed;
    }
    g_inside_builder_repair = false;
    CountRepairResult(repair_result);
    return result;
}

#endif

}  // namespace

bool InitializeTerrainMaterialRepair() noexcept {
    const LifecycleLock lock;

#if !defined(WB_ENABLE_TERRAIN_MATERIAL_REPAIR) || !defined(_WIN32) || defined(_WIN64)
    g_state.store(RuntimeState::profile_disabled, std::memory_order_release);
    return false;
#else
    if (g_state.load(std::memory_order_acquire) == RuntimeState::active) {
        return true;
    }

    HMODULE executable = GetModuleHandleW(nullptr);
    const auto verification = VerifyClientProfile(executable);
    g_verification.store(verification.error, std::memory_order_release);
    if (!verification.Verified()) {
        g_state.store(RuntimeState::verification_failed, std::memory_order_release);
        return false;
    }

    g_original_builder = reinterpret_cast<BuilderMethod>(
        client_profile::kBuilderThunk);
    const auto hook_result = InstallVtableHook(
        g_builder_hook,
        reinterpret_cast<void**>(client_profile::kBuilderVtableSlot),
        reinterpret_cast<void*>(client_profile::kBuilderThunk),
        reinterpret_cast<void*>(&BuilderHook));
    g_hook_result.store(hook_result, std::memory_order_release);
    if (hook_result != VtableHookResult::ok) {
        g_original_builder = nullptr;
        g_state.store(RuntimeState::hook_install_failed, std::memory_order_release);
        return false;
    }

    g_state.store(RuntimeState::active, std::memory_order_release);
    return true;
#endif
}

void ShutdownTerrainMaterialRepair() noexcept {
    const LifecycleLock lock;

#if defined(WB_ENABLE_TERRAIN_MATERIAL_REPAIR) && defined(_WIN32) && !defined(_WIN64)
    if (g_builder_hook.installed) {
        const auto result = RemoveVtableHook(g_builder_hook);
        g_hook_result.store(result, std::memory_order_release);
        if (result == VtableHookResult::restore_conflict) {
            g_state.store(RuntimeState::shutdown_conflict, std::memory_order_release);
        } else {
            g_state.store(RuntimeState::inactive, std::memory_order_release);
        }
    } else {
        g_state.store(RuntimeState::inactive, std::memory_order_release);
    }
    g_original_builder = nullptr;
    ShutdownClientAdapter();
#else
    g_state.store(RuntimeState::inactive, std::memory_order_release);
#endif
}

RuntimeStatus ReadTerrainMaterialRuntimeStatus() noexcept {
    RuntimeStatus status;
    status.state = g_state.load(std::memory_order_acquire);
    status.verification = g_verification.load(std::memory_order_acquire);
    status.hook = g_hook_result.load(std::memory_order_acquire);
    status.builder_calls = g_builder_calls.load(std::memory_order_relaxed);
    status.repaired_terrains = g_repaired_terrains.load(std::memory_order_relaxed);
    status.rejected_terrains = g_rejected_terrains.load(std::memory_order_relaxed);
    status.failed_terrains = g_failed_terrains.load(std::memory_order_relaxed);
    return status;
}

}  // namespace wonderbane::extension::terrain_material
