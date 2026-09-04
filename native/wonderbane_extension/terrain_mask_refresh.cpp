#include "terrain_mask_refresh.h"
#include "reviewed_terrain_mask_refresh.h"

#include <atomic>
#include <intrin.h>

namespace wonderbane::extension {
namespace {

enum class RepairState { stock, active, unreviewed, failed, restore_failed, disabled };
#if defined(WONDERBANE_EXTENSION_DIAGNOSTICS_ONLY)
std::atomic<RepairState> g_repair_state{RepairState::disabled};
#else
std::atomic<RepairState> g_repair_state{RepairState::stock};
SRWLOCK g_repair_lock = SRWLOCK_INIT;

struct OwnedByte {
    std::uint8_t* address = nullptr;
    std::uint8_t original = 0U, replacement = 0U;
    bool owned = false;
    bool protection_pending = false;
    bool flush_pending = false;
    DWORD protection = 0U;
};
std::array<OwnedByte, 4U> g_owned{};

struct RepairLock {
    RepairLock() noexcept { AcquireSRWLockExclusive(&g_repair_lock); }
    ~RepairLock() { ReleaseSRWLockExclusive(&g_repair_lock); }
};

// Each old/new instruction differs by exactly one byte. No torn multi-byte
// instruction or allocated code trampoline is possible, even during restoration.
bool ChangeByte(OwnedByte& site, const bool install) noexcept {
    if (site.address == nullptr) { return false; }
    DWORD old_protection = 0U;
    if (!VirtualProtect(site.address, 1U, PAGE_EXECUTE_READWRITE, &old_protection)) {
        return false;
    }
    if (!site.protection_pending) { site.protection = old_protection; }
    site.protection_pending = true;
    const auto expected = install ? site.original : site.replacement;
    const auto desired = install ? site.replacement : site.original;
    const auto previous = static_cast<std::uint8_t>(_InterlockedCompareExchange8(
        reinterpret_cast<volatile CHAR*>(site.address),
        static_cast<CHAR>(desired), static_cast<CHAR>(expected)));
    const bool exchanged = previous == expected;
    if (exchanged) { site.owned = install; }
    // Already restored is safe; an unrelated byte is not ours to overwrite.
    if (!install && previous == site.original) { site.owned = false; }
    const bool flushed = FlushInstructionCache(GetCurrentProcess(), site.address, 1U) != FALSE;
    site.flush_pending = !flushed;
    DWORD ignored = 0U;
    const bool protected_again = VirtualProtect(
        site.address, 1U, site.protection, &ignored) != FALSE;
    site.protection_pending = !protected_again;
    return (exchanged || (!install && previous == site.original))
        && flushed && protected_again;
}

template<typename Writer>
bool RestoreOwned(std::array<OwnedByte, 4U>& sites, Writer writer) noexcept {
    bool restored = true;
    for (std::size_t index = sites.size(); index > 0U; --index) {
        auto& site = sites[index - 1U];
        if ((site.owned || site.protection_pending || site.flush_pending) && !writer(site, false)) {
            restored = false;
        }
    }
    return restored;
}

template<typename Writer>
bool InstallOwned(std::array<OwnedByte, 4U>& sites, Writer writer) noexcept {
    for (auto& site : sites) {
        if (!writer(site, true)) {
            const bool restored = RestoreOwned(sites, writer);
            g_repair_state.store(restored ? RepairState::failed : RepairState::restore_failed);
            return false;
        }
    }
    g_repair_state.store(RepairState::active);
    return true;
}
#endif

}  // namespace

void StartTerrainMaskRefresh(std::uint8_t* image, const std::size_t image_size,
    const char* verified_executable_sha256) noexcept {
#if defined(WONDERBANE_EXTENSION_DIAGNOSTICS_ONLY)
    (void)image; (void)image_size; (void)verified_executable_sha256;
#else
    RepairLock lock;
    const auto state = g_repair_state.load();
    if (state == RepairState::active || state == RepairState::restore_failed) { return; }
    if (!terrain_mask_review::VerifyImage(image, image_size, verified_executable_sha256)) {
        g_repair_state.store(RepairState::unreviewed);
        return;
    }
    for (std::size_t index = 0U; index < g_owned.size(); ++index) {
        const auto& patch = terrain_mask_review::kPatches[index];
        g_owned[index] = {image + patch.rva, patch.original, patch.replacement,
            false, false, false, 0U};
    }
    InstallOwned(g_owned, ChangeByte);
#endif
}

void StopTerrainMaskRefresh() noexcept {
#if !defined(WONDERBANE_EXTENSION_DIAGNOSTICS_ONLY)
    RepairLock lock;
    if (!RestoreOwned(g_owned, ChangeByte)) {
        g_repair_state.store(RepairState::restore_failed);
        return;
    }
    g_owned = {};
    g_repair_state.store(RepairState::stock);
#endif
}

const char* TerrainMaskRefreshStatusJson() noexcept {
    switch (g_repair_state.load()) {
    case RepairState::active:
        return "{\"state\":\"active\",\"reason\":\"matched-edge-dirty-flag\","
            "\"patched_sites\":4,\"disk_writes\":false,\"per_frame_queries\":0}";
    case RepairState::unreviewed:
        return "{\"state\":\"stock\",\"reason\":\"unreviewed-terrain-code\",\"patched_sites\":0}";
    case RepairState::failed:
        return "{\"state\":\"stock\",\"reason\":\"install-failed-restored\",\"patched_sites\":0}";
    case RepairState::restore_failed:
        return "{\"state\":\"failed\",\"reason\":\"restore-incomplete\",\"patched_sites\":null}";
    case RepairState::disabled:
        return "{\"state\":\"disabled\",\"reason\":\"diagnostics-only\",\"patched_sites\":0}";
    default:
        return "{\"state\":\"stock\",\"reason\":\"not-installed\",\"patched_sites\":0}";
    }
}

}  // namespace wonderbane::extension
