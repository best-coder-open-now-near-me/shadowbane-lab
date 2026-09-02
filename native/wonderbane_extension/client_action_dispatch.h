#pragma once

#include <Windows.h>

#include <cstddef>
#include <cstdint>

namespace wonderbane::extension {

enum class ClientActionKind : std::uint32_t {
    native_action = 1U,
    learned_power = 2U,
};

enum class ClientActionResultStage : std::uint32_t {
    received = 1U,
    resolved = 2U,
    submitted_to_client = 3U,
    rejected_by_client = 4U,
    action_queue_observed = 5U,
    effect_observed = 6U,
    failed = 7U,
};

constexpr std::uint32_t kClientActionTransportCapability = 1U << 0U;
constexpr std::uint32_t kNativeActionDispatchCapability = 1U << 1U;
constexpr std::uint32_t kLearnedPowerDispatchCapability = 1U << 2U;
constexpr std::uint32_t kKnownClientActionCapabilities =
    kClientActionTransportCapability
    | kNativeActionDispatchCapability
    | kLearnedPowerDispatchCapability;

struct ClientActionRequest {
    std::uint64_t command_id;
    ClientActionKind kind;
    std::int32_t action_code;
    std::int32_t parameter_one;
    std::int32_t parameter_two;
    const char* argument;
    std::uint32_t argument_length;
    const char* power_identifier;
    std::uint32_t power_identifier_length;
};

struct ClientActionDispatchResult {
    ClientActionResultStage stage;
    DWORD error;
    const char* detail;
    std::size_t detail_length;
    DWORD execution_thread_id;
};

[[nodiscard]] constexpr bool IsTerminalClientActionStage(
    const ClientActionResultStage stage
) noexcept {
    return (
        stage == ClientActionResultStage::rejected_by_client
        || stage == ClientActionResultStage::effect_observed
        || stage == ClientActionResultStage::failed
    );
}

[[nodiscard]] constexpr std::uint32_t ReviewedClientActionCapabilities() noexcept {
    // The IPC transport is reviewed, but no native Shadowbane receiver/calling convention or
    // learned-power executor has been pinned for this build yet. Advertising either dispatch
    // capability before calibration would turn transport success into a false action claim.
    return kClientActionTransportCapability;
}

[[nodiscard]] inline ClientActionDispatchResult DispatchClientAction(
    const ClientActionRequest& request
) noexcept {
    static constexpr char kDispatcherUnavailable[] =
        "reviewed_client_dispatcher_unavailable";
    (void)request;
    return ClientActionDispatchResult{
        ClientActionResultStage::failed,
        ERROR_NOT_SUPPORTED,
        kDispatcherUnavailable,
        sizeof(kDispatcherUnavailable) - 1U,
        GetCurrentThreadId(),
    };
}

}  // namespace wonderbane::extension
