#include "terrain_mask_refresh.cpp"

#include <cstdio>
#include <filesystem>
#include <fstream>
#include <vector>

using namespace wonderbane::extension;
using namespace wonderbane::extension::terrain_mask_review;

int Fail(const char* reason) { std::printf("FAIL: %s\n", reason); return 1; }

bool ReadOnlyIntegration(const wchar_t* path) {
    std::ifstream stream(std::filesystem::path(path), std::ios::binary);
    if (!stream) { return false; }
    std::array<std::vector<std::uint8_t>, 7U> bodies{};
    for (std::size_t index = 0U; index < kFunctions.size(); ++index) {
        const auto& function = kFunctions[index];
        std::vector<std::uint8_t> original(function.size);
        // The exact reviewed .text has raw offset == RVA. Never load the client.
        stream.seekg(function.rva);
        stream.read(reinterpret_cast<char*>(original.data()), function.size);
        if (!stream || !VerifyFunction(function, original.data(), original.size(),
                kScenePreferredBase)) { return false; }
        bodies[index] = original;
        if (index < kPatches.size()) {
            const auto& patch = kPatches[index];
            const std::size_t displacement = patch.rva - function.rva;
            auto corrected = original;
            if (corrected[displacement] != patch.original) { return false; }
            corrected[displacement] = patch.replacement;
            const std::size_t start = displacement - 1U;
            const auto target = [start](const std::vector<std::uint8_t>& bytes) {
                if (bytes[start] == 0xEBU) {
                    return static_cast<std::size_t>(static_cast<std::int64_t>(start) + 2
                        + static_cast<std::int8_t>(bytes[start + 1U]));
                }
                if (bytes[start] != 0xE9U) { return std::size_t{0U}; }
                std::int32_t relative = 0;
                std::memcpy(&relative, bytes.data() + start + 1U, sizeof(relative));
                return static_cast<std::size_t>(
                    static_cast<std::int64_t>(start) + 5 + relative);
            };
            const std::size_t dirty = target(corrected);
            constexpr std::array<std::uint8_t, 7U> store{0xC6U,0x83U,0xADU,1U,0U,0U,1U};
            if (dirty + store.size() > corrected.size()
                || target(original) != dirty + store.size()
                || std::memcmp(corrected.data() + dirty, store.data(), store.size()) != 0) {
                return false;
            }
            // The new path executes only this register/flag-preserving dirty
            // store before the original continuation. Direction bits are skipped.
        }
        for (const std::uint32_t base : {0x100000U, 0x10000000U}) {
            auto relocated = original;
            for (std::size_t n = 0U; n < function.relocation_count; ++n) {
                const std::size_t at = function.relocations[n];
                std::uint32_t word = 0U;
                std::memcpy(&word, relocated.data() + at, sizeof(word));
                word += base - kScenePreferredBase;
                std::memcpy(relocated.data() + at, &word, sizeof(word));
            }
            if (!VerifyFunction(function, relocated.data(), relocated.size(), base)
                || VerifyFunction(function, relocated.data(), relocated.size(), kScenePreferredBase)) {
                return false;
            }
            for (auto& byte : relocated) {
                byte ^= 1U;
                const bool accepted = VerifyFunction(
                    function, relocated.data(), relocated.size(), base);
                byte ^= 1U;
                if (accepted) { return false; }
            }
        }
    }
    // Exercise the real public startup/stop path against a relocated, local
    // copy of the reviewed bytes. No game code is executed or process attached.
    constexpr std::size_t image_size = 0x4B0000U;
    auto* image = static_cast<std::uint8_t*>(VirtualAlloc(
        nullptr, image_size, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE));
    if (image == nullptr) { return false; }
    const auto base = static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(image));
    for (std::size_t index = 0U; index < kFunctions.size(); ++index) {
        const auto& function = kFunctions[index];
        auto body = bodies[index];
        for (std::size_t n = 0U; n < function.relocation_count; ++n) {
            const auto at = function.relocations[n];
            std::uint32_t value = 0U;
            std::memcpy(&value, body.data() + at, sizeof(value));
            value += base - kScenePreferredBase;
            std::memcpy(body.data() + at, &value, sizeof(value));
        }
        std::memcpy(image + function.rva, body.data(), body.size());
    }
    StopTerrainMaskRefresh();
    for (const char* digest : {
            "55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc",
            "a9a59004b36f9331bb85f85e7853a02a5d5f07bda9acb9ea4a8affbf169a54b8"}) {
        if (!VerifyImage(image, image_size, digest)) { return false; }
        StartTerrainMaskRefresh(image, image_size, digest);
        StartTerrainMaskRefresh(image, image_size, digest);
        for (const auto& patch : kPatches) {
#if defined(WONDERBANE_EXTENSION_DIAGNOSTICS_ONLY)
            if (image[patch.rva] != patch.original) { return false; }
#else
            if (image[patch.rva] != patch.replacement) { return false; }
#endif
        }
        StopTerrainMaskRefresh();
        for (const auto& patch : kPatches) {
            if (image[patch.rva] != patch.original) { return false; }
        }
    }
    // Drift in the last guard must prevent every earlier patch.
    image[kFunctions.back().rva + kFunctions.back().size - 1U] ^= 1U;
    StartTerrainMaskRefresh(image, image_size,
        "a9a59004b36f9331bb85f85e7853a02a5d5f07bda9acb9ea4a8affbf169a54b8");
    for (const auto& patch : kPatches) {
        if (image[patch.rva] != patch.original) { return false; }
    }
    StopTerrainMaskRefresh();
    VirtualFree(image, 0U, MEM_RELEASE);
    std::puts("All seven actual code fingerprints, both ASLR directions, every-byte drift,"
        " and all four dirty-only branch targets passed.");
    return true;
}

int wmain(int argc, wchar_t** argv) {
    std::array<std::uint8_t, kMaximumFunctionSize> zero{};
    for (const auto& function : kFunctions) {
        if (VerifyFunction(function, nullptr, function.size, kScenePreferredBase)
            || VerifyFunction(function, zero.data(), function.size, kScenePreferredBase)
            || VerifyFunction(function, zero.data(), function.size - 1U, kScenePreferredBase)) {
            return Fail("unreviewed function accepted");
        }
    }
    if (VerifyImage(nullptr, 0U, nullptr)
        || VerifyImage(zero.data(), zero.size(), "unknown")) { return Fail("image gate"); }
    StartTerrainMaskRefresh(zero.data(), zero.size(),
        "55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc");
#if defined(WONDERBANE_EXTENSION_DIAGNOSTICS_ONLY)
    if (g_repair_state.load() != RepairState::disabled) { return Fail("profile isolation"); }
    StopTerrainMaskRefresh();
    if (g_repair_state.load() != RepairState::disabled) { return Fail("disabled stop"); }
#else
    if (g_repair_state.load() != RepairState::unreviewed) { return Fail("unknown code modified"); }
    StopTerrainMaskRefresh();
    auto* memory = static_cast<std::uint8_t*>(VirtualAlloc(
        nullptr, 4096U, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE));
    if (memory == nullptr) { return Fail("fixture allocation"); }
    const auto fresh = [memory]() {
        std::array<OwnedByte, 4U> sites{};
        for (std::size_t index = 0U; index < sites.size(); ++index) {
            memory[index] = kPatches[index].original;
            sites[index] = {memory + index, kPatches[index].original,
                kPatches[index].replacement, false, false, false, 0U};
        }
        return sites;
    };
    auto sites = fresh();
    if (!InstallOwned(sites, ChangeByte) || g_repair_state.load() != RepairState::active
        || !RestoreOwned(sites, ChangeByte)) { return Fail("install/restore"); }
    for (const auto& site : sites) {
        if (*site.address != site.original || site.owned || site.protection_pending
            || site.flush_pending) { return Fail("incomplete normal restore"); }
    }
    for (std::size_t failed = 0U; failed < sites.size(); ++failed) {
        for (const bool after_write : {false, true}) {
            sites = fresh();
            const auto fail_one = [failed, after_write, memory](OwnedByte& site, bool install) {
                if (install && site.address == memory + failed) {
                    if (after_write && !ChangeByte(site, true)) { return false; }
                    return false;
                }
                return ChangeByte(site, install);
            };
            if (InstallOwned(sites, fail_one)
                || g_repair_state.load() != RepairState::failed) { return Fail("rollback state"); }
            for (const auto& site : sites) {
                if (*site.address != site.original || site.owned) { return Fail("partial rollback"); }
            }
        }
    }
    sites = fresh();
    if (!InstallOwned(sites, ChangeByte)) { return Fail("restore fixture"); }
    memory[1] = 0xCCU;
    if (RestoreOwned(sites, ChangeByte) || memory[1] != 0xCCU
        || !sites[1].owned) { return Fail("unrelated patch overwritten"); }
    memory[1] = sites[1].replacement;
    if (!RestoreOwned(sites, ChangeByte)) { return Fail("restoration retry"); }
    sites = fresh();
    const auto blocked_restore = [memory](OwnedByte& site, bool install) {
        if ((install && site.address == memory + 1U)
            || (!install && site.address == memory)) { return false; }
        return ChangeByte(site, install);
    };
    if (InstallOwned(sites, blocked_restore)
        || g_repair_state.load() != RepairState::restore_failed || !sites[0].owned
        || !RestoreOwned(sites, ChangeByte)) { return Fail("failed rollback retry"); }
    sites = fresh();
    DWORD protection = 0U;
    if (!VirtualProtect(memory, 4096U, PAGE_READONLY, &protection)
        || !InstallOwned(sites, ChangeByte) || !RestoreOwned(sites, ChangeByte)) {
        return Fail("read-only page transaction");
    }
    MEMORY_BASIC_INFORMATION page{};
    if (!VirtualQuery(memory, &page, sizeof(page)) || page.Protect != PAGE_READONLY) {
        return Fail("page protection not restored");
    }
    VirtualFree(memory, 0U, MEM_RELEASE);
    OwnedByte invalid{reinterpret_cast<std::uint8_t*>(1U), 0U, 1U};
    if (ChangeByte(invalid, true)) { return Fail("inaccessible page accepted"); }
#endif
    if (argc > 2 || (argc == 2 && !ReadOnlyIntegration(argv[1]))) {
        return Fail("frozen executable integration");
    }
    std::puts("Terrain mask refresh tests passed.");
    return 0;
}
