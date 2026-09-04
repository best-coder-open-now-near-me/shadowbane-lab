#include "terrain_client_verification.h"

#include "terrain_client_profile.generated.h"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>

#if defined(_WIN32) && !defined(_WIN64)
#include <bcrypt.h>
#include <windows.h>

#pragma comment(lib, "bcrypt.lib")
#endif

namespace wonderbane::extension::terrain_material {
namespace {

#if defined(_WIN32) && !defined(_WIN64)

[[nodiscard]] bool NtSucceeded(const NTSTATUS status) noexcept {
    return status >= 0;
}

[[nodiscard]] bool ReadableRange(
    const void* address,
    const std::size_t size) noexcept {
    if (address == nullptr || size == 0U) {
        return false;
    }

    auto cursor = reinterpret_cast<std::uintptr_t>(address);
    const auto end = cursor + size;
    if (end < cursor) {
        return false;
    }

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
        const auto region_start = reinterpret_cast<std::uintptr_t>(
            information.BaseAddress);
        const auto region_end = region_start + information.RegionSize;
        if (region_end <= cursor) {
            return false;
        }
        cursor = region_end;
    }
    return true;
}

template <std::size_t Size>
[[nodiscard]] bool VerifyBytes(
    const std::uintptr_t preferred_address,
    const std::array<std::uint8_t, Size>& expected) noexcept {
    const auto* actual = reinterpret_cast<const void*>(preferred_address);
    return ReadableRange(actual, expected.size()) &&
           std::memcmp(actual, expected.data(), expected.size()) == 0;
}

[[nodiscard]] bool HashLoadedExecutable(
    const wchar_t* path,
    std::array<std::uint8_t, 32>& digest,
    ClientVerificationError& error) noexcept {
    const HANDLE file = CreateFileW(
        path,
        GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        nullptr,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL | FILE_FLAG_SEQUENTIAL_SCAN,
        nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        error = ClientVerificationError::executable_open_failed;
        return false;
    }

    LARGE_INTEGER size{};
    if (!GetFileSizeEx(file, &size) || size.QuadPart < 0 ||
        static_cast<std::uint64_t>(size.QuadPart) !=
            client_profile::kExpectedFileSize) {
        CloseHandle(file);
        error = ClientVerificationError::executable_size_mismatch;
        return false;
    }

    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    PUCHAR hash_object = nullptr;
    bool success = false;

    do {
        if (!NtSucceeded(BCryptOpenAlgorithmProvider(
                &algorithm,
                BCRYPT_SHA256_ALGORITHM,
                nullptr,
                0U))) {
            break;
        }

        DWORD object_size = 0U;
        DWORD result_size = 0U;
        if (!NtSucceeded(BCryptGetProperty(
                algorithm,
                BCRYPT_OBJECT_LENGTH,
                reinterpret_cast<PUCHAR>(&object_size),
                sizeof(object_size),
                &result_size,
                0U)) ||
            object_size == 0U) {
            break;
        }

        DWORD hash_size = 0U;
        if (!NtSucceeded(BCryptGetProperty(
                algorithm,
                BCRYPT_HASH_LENGTH,
                reinterpret_cast<PUCHAR>(&hash_size),
                sizeof(hash_size),
                &result_size,
                0U)) ||
            hash_size != digest.size()) {
            break;
        }

        hash_object = static_cast<PUCHAR>(HeapAlloc(
            GetProcessHeap(), HEAP_ZERO_MEMORY, object_size));
        if (hash_object == nullptr) {
            break;
        }
        if (!NtSucceeded(BCryptCreateHash(
                algorithm,
                &hash,
                hash_object,
                object_size,
                nullptr,
                0U,
                0U))) {
            break;
        }

        std::array<std::uint8_t, 64U * 1024U> buffer{};
        for (;;) {
            DWORD read = 0U;
            if (!ReadFile(
                    file,
                    buffer.data(),
                    static_cast<DWORD>(buffer.size()),
                    &read,
                    nullptr)) {
                break;
            }
            if (read == 0U) {
                success = NtSucceeded(BCryptFinishHash(
                    hash,
                    digest.data(),
                    static_cast<ULONG>(digest.size()),
                    0U));
                break;
            }
            if (!NtSucceeded(BCryptHashData(
                    hash,
                    buffer.data(),
                    read,
                    0U))) {
                break;
            }
        }
    } while (false);

    if (hash != nullptr) {
        BCryptDestroyHash(hash);
    }
    if (hash_object != nullptr) {
        HeapFree(GetProcessHeap(), 0U, hash_object);
    }
    if (algorithm != nullptr) {
        BCryptCloseAlgorithmProvider(algorithm, 0U);
    }
    CloseHandle(file);

    if (!success) {
        error = ClientVerificationError::executable_hash_failed;
    }
    return success;
}

#endif

}  // namespace

ClientVerificationReport VerifyClientProfile(
    HMODULE executable_module) noexcept {
#if !defined(_WIN32) || defined(_WIN64)
    (void)executable_module;
    return ClientVerificationReport{
        ClientVerificationError::unsupported_platform,
        0U};
#else
    if (executable_module == nullptr) {
        return ClientVerificationReport{
            ClientVerificationError::null_module,
            0U};
    }

    const auto module_base = reinterpret_cast<std::uintptr_t>(
        executable_module);
    if (module_base != client_profile::kPreferredImageBase) {
        return ClientVerificationReport{
            ClientVerificationError::unexpected_image_base,
            module_base};
    }

    const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(module_base);
    if (!ReadableRange(dos, sizeof(*dos)) || dos->e_magic != IMAGE_DOS_SIGNATURE ||
        dos->e_lfanew <= 0) {
        return ClientVerificationReport{
            ClientVerificationError::invalid_pe_image,
            module_base};
    }
    const auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS32*>(
        module_base + static_cast<std::uintptr_t>(dos->e_lfanew));
    if (!ReadableRange(nt, sizeof(*nt)) ||
        nt->Signature != IMAGE_NT_SIGNATURE ||
        nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR32_MAGIC) {
        return ClientVerificationReport{
            ClientVerificationError::invalid_pe_image,
            reinterpret_cast<std::uintptr_t>(nt)};
    }
    if (nt->OptionalHeader.SizeOfImage != client_profile::kExpectedImageSize) {
        return ClientVerificationReport{
            ClientVerificationError::image_size_mismatch,
            module_base};
    }

    std::array<wchar_t, 32768U> path{};
    const DWORD path_length = GetModuleFileNameW(
        executable_module,
        path.data(),
        static_cast<DWORD>(path.size()));
    if (path_length == 0U || path_length >= path.size()) {
        return ClientVerificationReport{
            ClientVerificationError::module_path_unavailable,
            module_base};
    }

    std::array<std::uint8_t, 32> digest{};
    ClientVerificationError hash_error =
        ClientVerificationError::executable_hash_failed;
    if (!HashLoadedExecutable(path.data(), digest, hash_error)) {
        return ClientVerificationReport{hash_error, module_base};
    }
    if (digest != client_profile::kExpectedSha256) {
        return ClientVerificationReport{
            ClientVerificationError::executable_hash_mismatch,
            module_base};
    }

#define WB_VERIFY_TERRAIN_SIGNATURE(Name)                                      \
    do {                                                                        \
        if (!VerifyBytes(                                                       \
                client_profile::k##Name##SignatureAddress,                     \
                client_profile::k##Name##Signature)) {                         \
            return ClientVerificationReport{                                    \
                ClientVerificationError::code_signature_mismatch,              \
                client_profile::k##Name##SignatureAddress};                    \
        }                                                                       \
    } while (false)

    WB_VERIFY_TERRAIN_SIGNATURE(ImageFactory);
    WB_VERIFY_TERRAIN_SIGNATURE(ImageSetter);
    WB_VERIFY_TERRAIN_SIGNATURE(TextureAssignment);
    WB_VERIFY_TERRAIN_SIGNATURE(TextureClone);
    WB_VERIFY_TERRAIN_SIGNATURE(MaterialRegistration);
    WB_VERIFY_TERRAIN_SIGNATURE(TerrainFinalizer);
    WB_VERIFY_TERRAIN_SIGNATURE(TerrainBuilder);
    WB_VERIFY_TERRAIN_SIGNATURE(MaterialAppend);
    WB_VERIFY_TERRAIN_SIGNATURE(LookupInserting);
    WB_VERIFY_TERRAIN_SIGNATURE(LookupLowerBound);
    WB_VERIFY_TERRAIN_SIGNATURE(BuilderThunk);
    WB_VERIFY_TERRAIN_SIGNATURE(FinalizerThunk);

#undef WB_VERIFY_TERRAIN_SIGNATURE

    const auto* builder_slot = reinterpret_cast<const std::uint32_t*>(
        client_profile::kBuilderVtableSlot);
    const auto* finalizer_slot = reinterpret_cast<const std::uint32_t*>(
        client_profile::kFinalizerVtableSlot);
    if (!ReadableRange(builder_slot, sizeof(*builder_slot)) ||
        *builder_slot != client_profile::kBuilderThunk) {
        return ClientVerificationReport{
            ClientVerificationError::vtable_mismatch,
            client_profile::kBuilderVtableSlot};
    }
    if (!ReadableRange(finalizer_slot, sizeof(*finalizer_slot)) ||
        *finalizer_slot != client_profile::kFinalizerThunk) {
        return ClientVerificationReport{
            ClientVerificationError::vtable_mismatch,
            client_profile::kFinalizerVtableSlot};
    }

    return ClientVerificationReport{ClientVerificationError::ok, 0U};
#endif
}

}  // namespace wonderbane::extension::terrain_material
