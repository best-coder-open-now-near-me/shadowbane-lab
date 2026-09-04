#pragma once

#include <cstdint>

#if defined(_WIN32)
#include <windows.h>
#else
using HMODULE = void*;
#endif

namespace wonderbane::extension::terrain_material {

enum class ClientVerificationError : std::uint8_t {
    ok,
    unsupported_platform,
    null_module,
    unexpected_image_base,
    invalid_pe_image,
    image_size_mismatch,
    module_path_unavailable,
    executable_open_failed,
    executable_size_mismatch,
    executable_hash_failed,
    executable_hash_mismatch,
    code_signature_mismatch,
    vtable_mismatch,
};

struct ClientVerificationReport {
    ClientVerificationError error = ClientVerificationError::unsupported_platform;
    std::uintptr_t failing_address = 0U;

    [[nodiscard]] bool Verified() const noexcept {
        return error == ClientVerificationError::ok;
    }
};

// Verifies the loaded main executable, not the extension DLL. The profile is
// accepted only at the reviewed preferred base, with the exact file SHA-256,
// exact in-memory code signatures, and exact pre-hook vtable targets.
[[nodiscard]] ClientVerificationReport VerifyClientProfile(
    HMODULE executable_module) noexcept;

}  // namespace wonderbane::extension::terrain_material
