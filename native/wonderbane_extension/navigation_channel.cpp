#include "navigation_channel.h"
#include <strsafe.h>
#include <cstring>

namespace wonderbane::extension {
namespace {
SRWLOCK g_lock = SRWLOCK_INIT;
HANDLE g_mapping = nullptr;
void* g_address = nullptr;
ProcessIdentity g_identity{};
}

DWORD StartNavigationChannel(const ProcessIdentity& identity) noexcept {
    AcquireSRWLockExclusive(&g_lock);
    if (g_mapping != nullptr) {
        ReleaseSRWLockExclusive(&g_lock);
        return ERROR_ALREADY_INITIALIZED;
    }
    wchar_t name[160]{};
    if (identity.process_id != GetCurrentProcessId() || identity.creation_filetime_utc == 0U
        || FAILED(StringCchPrintfW(name, 160U, L"Local\\WonderBaneNavigation-%lu-%llu",
                                  identity.process_id, identity.creation_filetime_utc))) {
        ReleaseSRWLockExclusive(&g_lock);
        return ERROR_INVALID_PARAMETER;
    }
    HANDLE mapping = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE,
        0U, static_cast<DWORD>(navigation::kMappingBytes), name);
    DWORD error = GetLastError();
    if (mapping == nullptr || error == ERROR_ALREADY_EXISTS) {
        if (mapping != nullptr) CloseHandle(mapping);
        ReleaseSRWLockExclusive(&g_lock);
        return error;
    }
    void* address = MapViewOfFile(mapping, FILE_MAP_READ | FILE_MAP_WRITE,
                                 0U, 0U, navigation::kMappingBytes);
    if (address == nullptr) {
        error = GetLastError();
        CloseHandle(mapping);
        ReleaseSRWLockExclusive(&g_lock);
        return error;
    }
    navigation::FrameHeader initial{};
    initial.magic = navigation::kMagic;
    initial.version = navigation::kVersion;
    initial.size = sizeof(initial);
    initial.process_id = identity.process_id;
    initial.process_creation = identity.creation_filetime_utc;
    std::memcpy(address, &initial, sizeof(initial));
    g_identity = identity;
    g_mapping = mapping;
    g_address = address;
    ReleaseSRWLockExclusive(&g_lock);
    return ERROR_SUCCESS;
}

void StopNavigationChannel() noexcept {
    AcquireSRWLockExclusive(&g_lock);
    if (g_address != nullptr) UnmapViewOfFile(g_address);
    if (g_mapping != nullptr) CloseHandle(g_mapping);
    g_address = nullptr;
    g_mapping = nullptr;
    g_identity = {};
    ReleaseSRWLockExclusive(&g_lock);
}

namespace {
bool ReadFrame(NavigationFrameBuffer* const buffer, const bool evidence) noexcept {
    if (buffer == nullptr || !TryAcquireSRWLockShared(&g_lock)) return false;
    bool accepted = false;
    if (g_address != nullptr) {
        auto* sequence = reinterpret_cast<volatile LONG*>(
            static_cast<unsigned char*>(g_address) + offsetof(navigation::FrameHeader, sequence));
        const auto before = static_cast<std::uint32_t>(InterlockedCompareExchange(sequence, 0, 0));
        if (before != 0U && (before & 1U) == 0U) {
            navigation::FrameHeader header{};
            std::memcpy(&header, g_address, sizeof(header));
            if (before == buffer->accepted_sequence
                && header.checksum == buffer->header.checksum
                && header.session_id == buffer->header.session_id) {
                accepted = buffer->header.process_id == g_identity.process_id
                    && buffer->header.process_creation == g_identity.creation_filetime_utc
                    && (evidence || navigation::FramePlacementValid(buffer->header, GetTickCount64()));
            } else {
                if (header.size >= sizeof(header) && header.size <= buffer->bytes.size()) {
                    std::memcpy(buffer->bytes.data(), g_address, header.size);
                    MemoryBarrier();
                    const auto after = static_cast<std::uint32_t>(InterlockedCompareExchange(sequence, 0, 0));
                    const auto validate = evidence ? navigation::ValidateEvidenceFrame : navigation::ValidateFrame;
                    if (before == after && validate(buffer->bytes.data(), header.size,
                        after, g_identity.process_id, g_identity.creation_filetime_utc,
                        GetTickCount64()) == navigation::FrameError::none) {
                        std::memcpy(&buffer->header, buffer->bytes.data(), sizeof(header));
                        buffer->accepted_sequence = after;
                        accepted = true;
                    }
                }
            }
            // Also close the cached-frame race with a writer that began during this read.
            MemoryBarrier();
            accepted = accepted && before == static_cast<std::uint32_t>(
                InterlockedCompareExchange(sequence, 0, 0));
        }
    }
    buffer->live_placement = accepted
        && navigation::FramePlacementValid(buffer->header, GetTickCount64());
    buffer->presentation = buffer->header;
    if (accepted && evidence) {
        auto* controls_address = static_cast<unsigned char*>(g_address) + navigation::kMaximumFrameBytes;
        auto* marker = reinterpret_cast<volatile LONG*>(controls_address + 12U);
        const auto before = static_cast<std::uint32_t>(InterlockedCompareExchange(marker, 0, 0));
        if (before == 0U) {
            // A forced producer can draw live without a panel. Persistent evidence
            // requires a panel so the owner always has an immediate hide control.
            if (!buffer->live_placement) buffer->presentation.flags &= ~navigation::kEnabled;
        } else {
            navigation::ControlFrame controls{};
            std::memcpy(&controls, controls_address, sizeof(controls));
            MemoryBarrier();
            const auto after = static_cast<std::uint32_t>(InterlockedCompareExchange(marker, 0, 0));
            if (before != after || !navigation::ValidateControls(controls, after, buffer->header)) {
                buffer->presentation.flags &= ~navigation::kEnabled;
            } else {
                buffer->presentation.flags &= ~(navigation::kEnabled | navigation::kXray);
                if ((controls.flags & 1U) != 0U) buffer->presentation.flags |= navigation::kEnabled;
                if ((controls.flags & 2U) != 0U) buffer->presentation.flags |= navigation::kXray;
                buffer->presentation.layer_mask = controls.layer_mask;
            }
        }
    }
    if (!accepted) buffer->accepted_sequence = 0U;
    ReleaseSRWLockShared(&g_lock);
    return accepted;
}
}  // namespace
bool ReadNavigationFrame(NavigationFrameBuffer* const buffer) noexcept {
    return ReadFrame(buffer, false);
}
bool ReadNavigationEvidence(NavigationFrameBuffer* const buffer) noexcept {
    return ReadFrame(buffer, true);
}
}  // namespace wonderbane::extension
