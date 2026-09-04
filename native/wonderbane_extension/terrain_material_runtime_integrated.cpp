#include "terrain_material_runtime.h"

#include "terrain_append_abi.generated.h"
#include "terrain_append_bridge.h"
#include "terrain_client_profile.generated.h"
#include "terrain_inline_hook.h"
#include "terrain_material_capture.h"
#include "terrain_material_client_adapter.h"
#include "terrain_registration_abi.generated.h"
#include "terrain_registration_bridge.h"

#include <atomic>
#include <chrono>
#include <cstdint>
#include <span>

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
std::atomic<std::uint32_t> g_active_builder_calls{0U};
std::atomic_flag g_lifecycle_lock = ATOMIC_FLAG_INIT;
VtableHook g_builder_hook{};
InlineHook g_registration_hook{};
InlineHook g_append_hook{};

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

class ActiveBuilderCall final {
public:
    ActiveBuilderCall() noexcept {
        g_active_builder_calls.fetch_add(1U, std::memory_order_acq_rel);
    }

    ~ActiveBuilderCall() {
        g_active_builder_calls.fetch_sub(1U, std::memory_order_acq_rel);
    }

    ActiveBuilderCall(const ActiveBuilderCall&) = delete;
    ActiveBuilderCall& operator=(const ActiveBuilderCall&) = delete;
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
    const ActiveBuilderCall active_call;
    const auto original = g_original_builder;
    if (original == nullptr) {
        g_failed_terrains.fetch_add(1U, std::memory_order_relaxed);
        return nullptr;
    }

    if (g_inside_builder_repair) {
        return original(
            builder,
            output_terrain,
            terrain_resource,
            terrain_group);
    }

    g_inside_builder_repair = true;
    const Token key{terrain_resource, terrain_group};
    BeginTerrainBuild(key);
    void* result = original(
        builder,
        output_terrain,
        terrain_resource,
        terrain_group);
    g_builder_calls.fetch_add(1U, std::memory_order_relaxed);

    ClientRepairResult repair_result = ClientRepairResult::unchanged;
    if (output_terrain == nullptr || *output_terrain == nullptr) {
        AbortTerrainBuild();
        repair_result = ClientRepairResult::failed;
    } else {
        __try {
            repair_result = RepairBuiltTerrain(*output_terrain, key);
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            AbortTerrainBuild();
            repair_result = ClientRepairResult::failed;
        }
    }
    g_inside_builder_repair = false;
    CountRepairResult(repair_result);
    return result;
}

void RemoveInstalledHooksForFailedStart() noexcept {
    if (g_builder_hook.installed) {
        RemoveVtableHook(g_builder_hook);
    }
    g_original_builder = nullptr;

    if (g_append_hook.installed) {
        if (RemoveInlineHook(g_append_hook) == InlineHookResult::ok) {
            SetMaterialAppendTrampoline(nullptr);
        }
    }
    if (g_registration_hook.installed) {
        if (RemoveInlineHook(g_registration_hook) == InlineHookResult::ok) {
            SetMaterialRegistrationTrampoline(nullptr);
        }
    }
}

#endif

}  // namespace

bool InitializeTerrainMaterialRepair() noexcept {
    const LifecycleLock lock;

#if !defined(WB_ENABLE_TERRAIN_MATERIAL_REPAIR) || !defined(_WIN32) || defined(_WIN64)
    g_state.store(RuntimeState::profile_disabled, std::memory_order_release);
    return false;
#else
    const auto current_state = g_state.load(std::memory_order_acquire);
    if (current_state == RuntimeState::active) {
        return true;
    }
    if (current_state == RuntimeState::verification_failed ||
        current_state == RuntimeState::hook_install_failed ||
        current_state == RuntimeState::shutdown_conflict) {
        return false;
    }

    const auto verification = VerifyClientProfile(GetModuleHandleW(nullptr));
    g_verification.store(verification.error, std::memory_order_release);
    if (!verification.Verified()) {
        g_state.store(RuntimeState::verification_failed, std::memory_order_release);
        return false;
    }

    const auto registration_replacement = MaterialRegistrationHookAddress();
    const auto append_replacement = MaterialAppendHookAddress();
    if (registration_replacement == nullptr || append_replacement == nullptr) {
        g_state.store(RuntimeState::hook_install_failed, std::memory_order_release);
        return false;
    }

    auto inline_result = InstallInlineHook(
        g_registration_hook,
        reinterpret_cast<void*>(client_profile::kMaterialRegistration),
        registration_replacement,
        std::span<const std::uint8_t>(registration_abi::kPrologue));
    if (inline_result != InlineHookResult::ok) {
        g_state.store(RuntimeState::hook_install_failed, std::memory_order_release);
        return false;
    }
    SetMaterialRegistrationTrampoline(g_registration_hook.trampoline);

    inline_result = InstallInlineHook(
        g_append_hook,
        reinterpret_cast<void*>(client_profile::kMaterialAppend),
        append_replacement,
        std::span<const std::uint8_t>(append_abi::kPrologue));
    if (inline_result != InlineHookResult::ok) {
        RemoveInstalledHooksForFailedStart();
        g_state.store(RuntimeState::hook_install_failed, std::memory_order_release);
        return false;
    }
    SetMaterialAppendTrampoline(g_append_hook.trampoline);

    g_original_builder = reinterpret_cast<BuilderMethod>(
        client_profile::kBuilderThunk);
    const auto builder_result = InstallVtableHook(
        g_builder_hook,
        reinterpret_cast<void**>(client_profile::kBuilderVtableSlot),
        reinterpret_cast<void*>(client_profile::kBuilderThunk),
        reinterpret_cast<void*>(&BuilderHook));
    g_hook_result.store(builder_result, std::memory_order_release);
    if (builder_result != VtableHookResult::ok) {
        RemoveInstalledHooksForFailedStart();
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
    bool conflict = false;
    if (g_builder_hook.installed) {
        const auto result = RemoveVtableHook(g_builder_hook);
        g_hook_result.store(result, std::memory_order_release);
        conflict = result != VtableHookResult::ok;
    }

    const auto deadline = GetTickCount64() + 2000U;
    while (!conflict &&
           g_active_builder_calls.load(std::memory_order_acquire) != 0U &&
           GetTickCount64() < deadline) {
        Sleep(1U);
    }
    if (g_active_builder_calls.load(std::memory_order_acquire) != 0U) {
        conflict = true;
    }

    if (!conflict && g_append_hook.installed) {
        if (RemoveInlineHook(g_append_hook) == InlineHookResult::ok) {
            SetMaterialAppendTrampoline(nullptr);
        } else {
            conflict = true;
        }
    }
    if (!conflict && g_registration_hook.installed) {
        if (RemoveInlineHook(g_registration_hook) == InlineHookResult::ok) {
            SetMaterialRegistrationTrampoline(nullptr);
        } else {
            conflict = true;
        }
    }

    if (conflict) {
        g_state.store(RuntimeState::shutdown_conflict, std::memory_order_release);
        return;
    }

    g_original_builder = nullptr;
    ShutdownClientAdapter();
    g_state.store(RuntimeState::inactive, std::memory_order_release);
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
