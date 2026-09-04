#include "terrain_material_client_adapter.h"

#include "terrain_append_bridge.h"
#include "terrain_material_capture.h"
#include "terrain_registration_bridge.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <span>

#if defined(_WIN32) && !defined(_WIN64)
#include <windows.h>
#endif

namespace wonderbane::extension::terrain_material {
namespace {

#if defined(WB_ENABLE_TERRAIN_MATERIAL_REPAIR) && defined(_WIN32) && !defined(_WIN64)

constexpr std::uintptr_t kRegionColorsOffset = 0x4CU;
constexpr std::uintptr_t kRegionMaterialMapOffset = 0x64U;
constexpr std::uintptr_t kMapHeadOffset = 0x00U;
constexpr std::uintptr_t kMapSizeOffset = 0x04U;
constexpr std::uintptr_t kNodeLeftOffset = 0x00U;
constexpr std::uintptr_t kNodeParentOffset = 0x04U;
constexpr std::uintptr_t kNodeRightOffset = 0x08U;
constexpr std::uintptr_t kNodeKeyOffset = 0x10U;
constexpr std::uintptr_t kNodeMasksOffset = 0x18U;
constexpr std::uintptr_t kTerrainRenderSourceOffset = 0xC0U;
constexpr std::size_t kMaximumMapNodes = 4096U;
constexpr std::size_t kMaximumCapturedArguments = 16U;
constexpr std::size_t kMaximumRepairedTerrains = 256U;

struct RawVector {
    std::uintptr_t begin = 0U;
    std::uintptr_t end = 0U;
    std::uintptr_t capacity = 0U;
};

enum class CoverageState : std::uint8_t {
    invalid,
    absent,
    present,
};

struct Coverage {
    CoverageState state = CoverageState::invalid;
    std::array<Layer, kMaximumLayers> layers{};
    std::size_t count = 0U;
};

struct RawSlot {
    bool is_this = false;
    std::size_t argument_index = 0U;
    std::uintptr_t value = 0U;
};

struct RepairedTerrain {
    std::uintptr_t terrain = 0U;
    std::uintptr_t source = 0U;
    Token key{};
    std::uintptr_t material_region = 0U;
    std::array<Layer, kMaximumLayers> additions{};
    std::size_t addition_count = 0U;
};

struct BuildContext {
    bool active = false;
    bool rejected = false;
    bool substitution_pending = false;
    bool substitution_completed = false;
    Token key{};
    std::uintptr_t current_region = 0U;
    std::uintptr_t selected_region = 0U;
    std::array<Layer, kMaximumLayers> existing{};
    std::size_t existing_count = 0U;
    std::array<Layer, kMaximumLayers> pending{};
    std::size_t pending_count = 0U;
    std::array<Layer, kMaximumLayers> additions{};
    std::size_t addition_count = 0U;
};

std::atomic_flag g_registry_lock = ATOMIC_FLAG_INIT;
std::array<std::uintptr_t, kMaximumRegions> g_regions{};
std::size_t g_region_count = 0U;
std::array<RepairedTerrain, kMaximumRepairedTerrains> g_repaired{};
std::size_t g_repaired_count = 0U;
thread_local BuildContext g_build{};
thread_local std::array<std::uintptr_t, kMaximumMapNodes> g_tree_stack{};
thread_local std::array<std::uintptr_t, kMaximumMapNodes> g_tree_seen{};

class RegistryLock final {
public:
    RegistryLock() noexcept {
        while (g_registry_lock.test_and_set(std::memory_order_acquire)) {
            YieldProcessor();
        }
    }

    ~RegistryLock() {
        g_registry_lock.clear(std::memory_order_release);
    }

    RegistryLock(const RegistryLock&) = delete;
    RegistryLock& operator=(const RegistryLock&) = delete;
};

[[nodiscard]] bool ReadableRange(
    const std::uintptr_t address,
    const std::size_t size) noexcept {
    if (address == 0U || size == 0U) {
        return false;
    }
    const auto end = address + size;
    if (end < address) {
        return false;
    }

    auto cursor = address;
    while (cursor < end) {
        MEMORY_BASIC_INFORMATION information{};
        if (VirtualQuery(
                reinterpret_cast<const void*>(cursor),
                &information,
                sizeof(information)) != sizeof(information)) {
            return false;
        }
        if (information.State != MEM_COMMIT ||
            (information.Protect & PAGE_GUARD) != 0U ||
            (information.Protect & PAGE_NOACCESS) != 0U) {
            return false;
        }
        const auto region_begin = reinterpret_cast<std::uintptr_t>(
            information.BaseAddress);
        const auto region_end = region_begin + information.RegionSize;
        if (region_end <= cursor) {
            return false;
        }
        cursor = region_end;
    }
    return true;
}

template <typename Value>
[[nodiscard]] bool SafeRead(
    const std::uintptr_t address,
    Value& value) noexcept {
    if (!ReadableRange(address, sizeof(Value))) {
        return false;
    }
    __try {
        std::memcpy(&value, reinterpret_cast<const void*>(address), sizeof(Value));
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

[[nodiscard]] bool ReadVector(
    const std::uintptr_t address,
    const std::size_t element_size,
    const std::size_t maximum_count,
    RawVector& vector,
    std::size_t& count) noexcept {
    if (!SafeRead(address, vector)) {
        return false;
    }
    if (vector.begin == 0U && vector.end == 0U && vector.capacity == 0U) {
        count = 0U;
        return true;
    }
    if (vector.begin == 0U || vector.begin > vector.end ||
        vector.end > vector.capacity || element_size == 0U) {
        return false;
    }
    const auto byte_count = vector.end - vector.begin;
    const auto capacity_bytes = vector.capacity - vector.begin;
    if (byte_count % element_size != 0U ||
        capacity_bytes % element_size != 0U) {
        return false;
    }
    count = byte_count / element_size;
    if (count > maximum_count ||
        capacity_bytes / element_size > kMaximumMapNodes) {
        return false;
    }
    return count == 0U || ReadableRange(vector.begin, byte_count);
}

[[nodiscard]] bool ReadTokens(
    const RawVector& vector,
    const std::size_t count,
    std::span<Token> output) noexcept {
    if (count > output.size()) {
        return false;
    }
    for (std::size_t index = 0U; index < count; ++index) {
        if (!SafeRead(
                vector.begin + index * sizeof(Token),
                output[index])) {
            return false;
        }
    }
    return true;
}

[[nodiscard]] bool ValidRegisteredTokens(
    const std::span<const Token> colors,
    const std::span<const Token> masks) noexcept {
    if (colors.empty() || colors.size() != masks.size() ||
        colors.size() > kMaximumLayers) {
        return false;
    }
    for (std::size_t index = 0U; index < colors.size(); ++index) {
        if (colors[index].Empty() || masks[index].Empty()) {
            return false;
        }
        for (std::size_t previous = 0U; previous < index; ++previous) {
            if (masks[previous] == masks[index]) {
                return false;
            }
        }
    }
    return true;
}

[[nodiscard]] bool ReadMapHeader(
    const std::uintptr_t region,
    std::uintptr_t& head,
    std::size_t& size,
    std::uintptr_t& root) noexcept {
    const auto map = region + kRegionMaterialMapOffset;
    std::uint32_t raw_size = 0U;
    if (!SafeRead(map + kMapHeadOffset, head) ||
        !SafeRead(map + kMapSizeOffset, raw_size) ||
        head == 0U || raw_size > kMaximumMapNodes) {
        return false;
    }
    size = raw_size;
    if (!SafeRead(head + kNodeParentOffset, root)) {
        return false;
    }
    if (size == 0U) {
        return root == head;
    }
    return root != 0U && root != head;
}

[[nodiscard]] Coverage LookupCoverage(
    const std::uintptr_t region,
    const Token key) noexcept {
    Coverage result;
    if (region == 0U || key.Empty()) {
        return result;
    }

    RawVector color_vector{};
    std::size_t color_count = 0U;
    if (!ReadVector(
            region + kRegionColorsOffset,
            sizeof(Token),
            kMaximumLayers,
            color_vector,
            color_count)) {
        return result;
    }

    std::array<Token, kMaximumLayers> colors{};
    if (color_count != 0U &&
        !ReadTokens(color_vector, color_count, colors)) {
        return result;
    }

    std::uintptr_t head = 0U;
    std::uintptr_t root = 0U;
    std::size_t map_size = 0U;
    if (!ReadMapHeader(region, head, map_size, root)) {
        return result;
    }
    if (map_size == 0U) {
        result.state = CoverageState::absent;
        return result;
    }

    std::size_t stack_count = 0U;
    std::size_t seen_count = 0U;
    g_tree_stack[stack_count++] = root;
    std::uintptr_t matching_node = 0U;

    while (stack_count != 0U) {
        const auto node = g_tree_stack[--stack_count];
        if (node == 0U || node == head) {
            continue;
        }
        if (seen_count >= map_size || seen_count >= g_tree_seen.size()) {
            return result;
        }
        for (std::size_t previous = 0U; previous < seen_count; ++previous) {
            if (g_tree_seen[previous] == node) {
                return result;
            }
        }
        g_tree_seen[seen_count++] = node;

        std::uintptr_t left = 0U;
        std::uintptr_t right = 0U;
        Token node_key{};
        if (!SafeRead(node + kNodeLeftOffset, left) ||
            !SafeRead(node + kNodeRightOffset, right) ||
            !SafeRead(node + kNodeKeyOffset, node_key)) {
            return result;
        }
        if (node_key == key) {
            if (matching_node != 0U) {
                return result;
            }
            matching_node = node;
        }
        if (left != 0U && left != head) {
            if (stack_count >= g_tree_stack.size()) {
                return result;
            }
            g_tree_stack[stack_count++] = left;
        }
        if (right != 0U && right != head) {
            if (stack_count >= g_tree_stack.size()) {
                return result;
            }
            g_tree_stack[stack_count++] = right;
        }
    }

    if (seen_count != map_size) {
        return result;
    }
    if (matching_node == 0U) {
        result.state = CoverageState::absent;
        return result;
    }

    RawVector mask_vector{};
    std::size_t mask_count = 0U;
    if (!ReadVector(
            matching_node + kNodeMasksOffset,
            sizeof(Token),
            kMaximumLayers,
            mask_vector,
            mask_count)) {
        return result;
    }
    std::array<Token, kMaximumLayers> masks{};
    if (!ReadTokens(mask_vector, mask_count, masks) ||
        !ValidRegisteredTokens(
            std::span<const Token>(colors.data(), color_count),
            std::span<const Token>(masks.data(), mask_count))) {
        return result;
    }

    result.state = CoverageState::present;
    result.count = color_count;
    for (std::size_t index = 0U; index < color_count; ++index) {
        result.layers[index] = Layer{colors[index], masks[index]};
    }
    return result;
}

[[nodiscard]] bool PlausibleRegion(const std::uintptr_t region) noexcept {
    if (region == 0U || (region & (alignof(void*) - 1U)) != 0U) {
        return false;
    }
    RawVector colors{};
    std::size_t color_count = 0U;
    if (!ReadVector(
            region + kRegionColorsOffset,
            sizeof(Token),
            kMaximumLayers,
            colors,
            color_count) ||
        color_count == 0U) {
        return false;
    }
    std::uintptr_t head = 0U;
    std::uintptr_t root = 0U;
    std::size_t map_size = 0U;
    return ReadMapHeader(region, head, map_size, root) && map_size != 0U;
}

void RegisterRegion(const std::uintptr_t region) noexcept {
    if (!PlausibleRegion(region)) {
        return;
    }
    const RegistryLock lock;
    for (std::size_t index = 0U; index < g_region_count; ++index) {
        if (g_regions[index] == region) {
            return;
        }
    }
    if (g_region_count < g_regions.size()) {
        g_regions[g_region_count++] = region;
    }
}

[[nodiscard]] bool IsRegisteredRegion(const std::uintptr_t region) noexcept {
    const RegistryLock lock;
    return std::find(
               g_regions.begin(),
               g_regions.begin() + static_cast<std::ptrdiff_t>(g_region_count),
               region) !=
           g_regions.begin() + static_cast<std::ptrdiff_t>(g_region_count);
}

[[nodiscard]] std::size_t SnapshotRegions(
    std::span<std::uintptr_t> output) noexcept {
    const RegistryLock lock;
    const auto count = std::min(g_region_count, output.size());
    std::copy_n(g_regions.begin(), count, output.begin());
    return count;
}

[[nodiscard]] bool AppendBuildLayers(
    const std::span<const Layer> layers,
    const bool additions) noexcept {
    auto& count = additions ? g_build.addition_count : g_build.existing_count;
    auto& destination = additions ? g_build.additions : g_build.existing;
    if (layers.size() > destination.size() - count) {
        return false;
    }
    std::copy(layers.begin(), layers.end(), destination.begin() + count);
    count += layers.size();
    return true;
}

[[nodiscard]] bool SelectRegionSlot(
    void* this_pointer,
    const std::span<const std::uint32_t> arguments,
    RawSlot& selected) noexcept {
    std::array<RawSlot, kMaximumCapturedArguments + 1U> slots{};
    std::size_t slot_count = 0U;
    slots[slot_count++] = RawSlot{
        true, 0U, reinterpret_cast<std::uintptr_t>(this_pointer)};
    for (std::size_t index = 0U;
         index < arguments.size() && index < kMaximumCapturedArguments;
         ++index) {
        slots[slot_count++] = RawSlot{false, index, arguments[index]};
    }

    std::size_t registered_matches = 0U;
    for (std::size_t index = 0U; index < slot_count; ++index) {
        if (IsRegisteredRegion(slots[index].value)) {
            selected = slots[index];
            ++registered_matches;
        }
    }
    if (registered_matches == 1U) {
        return true;
    }
    if (registered_matches > 1U) {
        return false;
    }

    std::size_t structural_matches = 0U;
    for (std::size_t index = 0U; index < slot_count; ++index) {
        if (PlausibleRegion(slots[index].value)) {
            selected = slots[index];
            ++structural_matches;
        }
    }
    return structural_matches == 1U;
}

void ReplaceRegionSlot(
    const RawSlot& slot,
    const std::uintptr_t replacement,
    void*& this_pointer,
    const std::span<std::uint32_t> arguments) noexcept {
    if (slot.is_this) {
        this_pointer = reinterpret_cast<void*>(replacement);
    } else if (slot.argument_index < arguments.size()) {
        arguments[slot.argument_index] =
            static_cast<std::uint32_t>(replacement);
    }
}

void SaveRepairedTerrain(
    const std::uintptr_t terrain,
    const std::uintptr_t source) noexcept {
    const RegistryLock lock;
    if (g_repaired_count == g_repaired.size()) {
        // Bounded FIFO eviction is safe: losing metadata can only disable later
        // ownership validation for the oldest repaired terrain.
        std::move(
            g_repaired.begin() + 1,
            g_repaired.end(),
            g_repaired.begin());
        --g_repaired_count;
    }
    auto& record = g_repaired[g_repaired_count++];
    record = {};
    record.terrain = terrain;
    record.source = source;
    record.key = g_build.key;
    record.material_region = g_build.selected_region;
    record.addition_count = g_build.addition_count;
    std::copy_n(
        g_build.additions.begin(),
        record.addition_count,
        record.additions.begin());
}

#endif

}  // namespace

void BeginTerrainBuild(const Token terrain_key) noexcept {
#if defined(WB_ENABLE_TERRAIN_MATERIAL_REPAIR) && defined(_WIN32) && !defined(_WIN64)
    g_build = {};
    g_build.active = !terrain_key.Empty();
    g_build.key = terrain_key;
#else
    (void)terrain_key;
#endif
}

void AbortTerrainBuild() noexcept {
#if defined(WB_ENABLE_TERRAIN_MATERIAL_REPAIR) && defined(_WIN32) && !defined(_WIN64)
    g_build = {};
#endif
}

void RecordMaterialRegistration(
    void* this_pointer,
    const std::span<const std::uint32_t> arguments,
    const std::uintptr_t result) noexcept {
#if defined(WB_ENABLE_TERRAIN_MATERIAL_REPAIR) && defined(_WIN32) && !defined(_WIN64)
    RegisterRegion(reinterpret_cast<std::uintptr_t>(this_pointer));
    for (const auto argument : arguments.first(
             std::min(arguments.size(), kMaximumCapturedArguments))) {
        RegisterRegion(argument);
    }
    RegisterRegion(result);
#else
    (void)this_pointer;
    (void)arguments;
    (void)result;
#endif
}

void RewriteMaterialAppendInvocation(
    void*& this_pointer,
    const std::span<std::uint32_t> arguments) noexcept {
#if defined(WB_ENABLE_TERRAIN_MATERIAL_REPAIR) && defined(_WIN32) && !defined(_WIN64)
    if (!g_build.active || g_build.rejected ||
        g_build.substitution_pending) {
        return;
    }

    RawSlot region_slot{};
    if (!SelectRegionSlot(this_pointer, arguments, region_slot)) {
        g_build.rejected = true;
        return;
    }
    g_build.current_region = region_slot.value;
    RegisterRegion(region_slot.value);

    const auto current = LookupCoverage(region_slot.value, g_build.key);
    if (current.state == CoverageState::invalid) {
        g_build.rejected = true;
        return;
    }
    if (current.state == CoverageState::present) {
        g_build.pending_count = current.count;
        std::copy_n(
            current.layers.begin(),
            current.count,
            g_build.pending.begin());
        return;
    }

    std::array<std::uintptr_t, kMaximumRegions> regions{};
    const auto region_count = SnapshotRegions(regions);
    std::uintptr_t candidate_region = 0U;
    Coverage candidate{};
    std::size_t candidate_count = 0U;
    for (std::size_t index = 0U; index < region_count; ++index) {
        const auto region = regions[index];
        if (region == 0U || region == region_slot.value) {
            continue;
        }
        const auto coverage = LookupCoverage(region, g_build.key);
        if (coverage.state == CoverageState::invalid) {
            continue;
        }
        if (coverage.state == CoverageState::present) {
            candidate_region = region;
            candidate = coverage;
            ++candidate_count;
            if (candidate_count > 1U) {
                g_build.rejected = true;
                return;
            }
        }
    }
    if (candidate_count != 1U) {
        return;
    }

    const std::array<Region, 2> synthetic_regions{
        Region{region_slot.value, kNoParent, 0U, true, {}},
        Region{
            candidate_region,
            0U,
            0U,
            true,
            std::span<const Layer>(candidate.layers.data(), candidate.count)},
    };
    const auto plan = PlanCoverage(
        synthetic_regions,
        0U,
        std::span<const Layer>(
            g_build.existing.data(), g_build.existing_count),
        0U);
    if (plan.decision != Decision::append ||
        plan.layer_count != candidate.count ||
        !std::equal(
            candidate.layers.begin(),
            candidate.layers.begin() + static_cast<std::ptrdiff_t>(candidate.count),
            plan.additions.begin())) {
        if (plan.decision != Decision::unchanged) {
            g_build.rejected = true;
        }
        return;
    }

    ReplaceRegionSlot(region_slot, candidate_region, this_pointer, arguments);
    g_build.selected_region = candidate_region;
    g_build.substitution_pending = true;
    g_build.pending_count = candidate.count;
    std::copy_n(
        candidate.layers.begin(),
        candidate.count,
        g_build.pending.begin());
#else
    (void)this_pointer;
    (void)arguments;
#endif
}

void RecordMaterialAppendEnter(
    void*,
    const std::span<const std::uint32_t>) noexcept {
    // The mutable generated bridge has already selected and recorded the exact
    // pending stack. This callback remains as a stable ABI point for diagnostics.
}

void RecordMaterialAppendExit(const std::uintptr_t) noexcept {
#if defined(WB_ENABLE_TERRAIN_MATERIAL_REPAIR) && defined(_WIN32) && !defined(_WIN64)
    if (!g_build.active || g_build.pending_count == 0U) {
        return;
    }
    const auto pending = std::span<const Layer>(
        g_build.pending.data(), g_build.pending_count);
    if (!AppendBuildLayers(pending, false)) {
        g_build.rejected = true;
    }
    if (g_build.substitution_pending) {
        if (!AppendBuildLayers(pending, true)) {
            g_build.rejected = true;
        } else {
            g_build.substitution_completed = true;
        }
    }
    g_build.pending = {};
    g_build.pending_count = 0U;
    g_build.substitution_pending = false;
#endif
}

ClientRepairResult RepairBuiltTerrain(
    void* arc_terrain,
    const Token terrain_key) noexcept {
#if !defined(WB_ENABLE_TERRAIN_MATERIAL_REPAIR) || !defined(_WIN32) || defined(_WIN64)
    (void)arc_terrain;
    (void)terrain_key;
    return ClientRepairResult::unavailable;
#else
    if (!g_build.active || terrain_key != g_build.key) {
        g_build = {};
        return ClientRepairResult::rejected;
    }
    if (g_build.rejected) {
        g_build = {};
        return ClientRepairResult::rejected;
    }
    if (!g_build.substitution_completed) {
        g_build = {};
        return ClientRepairResult::unchanged;
    }
    if (arc_terrain == nullptr) {
        g_build = {};
        return ClientRepairResult::failed;
    }

    std::uintptr_t source = 0U;
    const auto terrain = reinterpret_cast<std::uintptr_t>(arc_terrain);
    if (!SafeRead(terrain + kTerrainRenderSourceOffset, source) || source == 0U) {
        g_build = {};
        return ClientRepairResult::failed;
    }
    SaveRepairedTerrain(terrain, source);
    g_build = {};
    return ClientRepairResult::repaired;
#endif
}

void ShutdownClientAdapter() noexcept {
#if defined(WB_ENABLE_TERRAIN_MATERIAL_REPAIR) && defined(_WIN32) && !defined(_WIN64)
    const RegistryLock lock;
    g_regions = {};
    g_region_count = 0U;
    g_repaired = {};
    g_repaired_count = 0U;
    g_build = {};
#endif
}

}  // namespace wonderbane::extension::terrain_material
