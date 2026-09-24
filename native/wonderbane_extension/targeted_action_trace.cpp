#include "targeted_action_trace.h"
#include "graphics_status.h"
#include "import_hook.h"
#include "movement_native_image.h"
#include "movement_lifetime.h"
#include <intrin.h>
#include <strsafe.h>
#include <array>
#include <cstring>

namespace wonderbane::extension {
namespace {
using Deserialize = void(__thiscall*)(void*, void*);
// The image seal covers executable code; slot identity is checked separately.
constexpr std::uintptr_t slot_rva = 0x1158894;
constexpr std::uintptr_t target_rva = 0x1C9DB;
constexpr std::uintptr_t decoder_return_rva = 0x3625BC;
constexpr std::uintptr_t socket_vtable_rva = 0x116019C;
// ArcServerLink retirement marks ArcLinkedSocket +0x1c before releasing it.
constexpr std::size_t socket_retired_offset = 0x1c;
constexpr std::uintptr_t message_vtable_rva = 0x1158878;
struct alignas(8) Record {
    volatile LONG64 committed_sequence;
    std::uint64_t tick_ms;
    std::uint32_t thread_id;
    std::uint32_t caller_rva;
    // Original message +0x80..+0xaf, then decode-spanning epoch (two words) and local key.
    std::array<std::uint32_t, 16> fields;
};
struct alignas(8) Storage {
    char magic[8];
    std::uint32_t schema, record_size, capacity, process_id;
    std::uint64_t creation_filetime;
    volatile LONG64 write_sequence;
    volatile LONG64 overwritten;
    volatile LONG stopped;
    std::uint32_t reserved;
    Record records[256];
};
static_assert(sizeof(Record) == 88 && offsetof(Storage, records) == 56);
SRWLOCK lock = SRWLOCK_INIT;
Deserialize original = nullptr;
std::uint32_t* installed_slot = nullptr;
std::uintptr_t image_base = 0;
HANDLE mapping = nullptr;
Storage* storage = nullptr;
bool attempted = false;

bool Copy(void* output, const void* source, std::size_t size) noexcept {
    __try { std::memcpy(output, source, size); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
bool ActiveSocket(void* stream) noexcept {
    std::uint32_t table = 0;
    unsigned char retired = 1;
    return Copy(&table, stream, sizeof(table)) && table == image_base + socket_vtable_rva
        && Copy(&retired, static_cast<unsigned char*>(stream) + socket_retired_offset, sizeof(retired))
        && retired == 0;
}
void Observe(void* message, void* stream, std::uintptr_t caller, const movement::NativeScene& scene = {}) noexcept {
    // Call-through owns message and stream through this synchronous observation.
    // Serialize with closure BEFORE touching publication storage. No borrowed
    // message/stream/character pointer survives the callback.
    AcquireSRWLockExclusive(&lock);
    if (storage) {
        std::uint32_t message_table = 0;
        Record record{};
        if (caller == image_base + decoder_return_rva
            && ActiveSocket(stream)
            && Copy(&message_table, message, sizeof(message_table))
            && message_table == image_base + message_vtable_rva
            && Copy(record.fields.data(), static_cast<unsigned char*>(message) + 0x80, 48)) {
            // Native decoding leaves conditional payloads untouched when absent.
            // Never export stale/uninitialized values from those absent fields.
            if (!record.fields[4]) { record.fields[5] = record.fields[6] = record.fields[7] = 0; }
            if (!record.fields[8]) { record.fields[9] = record.fields[10] = record.fields[11] = 0; }
            // No native pointers leave the callback. Only a watch present before
            // decode and still current afterward may label this observation.
            // This does not prove network queue age or authorize combat.
            if (scene.epoch && movement::NativeMovementLifetimeCurrent(scene)) {
                record.fields[12] = static_cast<std::uint32_t>(scene.epoch);
                record.fields[13] = static_cast<std::uint32_t>(scene.epoch >> 32);
                record.fields[14] = scene.identity[0]; record.fields[15] = scene.identity[1];
            }
            // Extra fields +0xb0/+0xb8 remain excluded pending semantic review.
            record.tick_ms = GetTickCount64(); record.thread_id = GetCurrentThreadId();
            record.caller_rva = static_cast<std::uint32_t>(decoder_return_rva);
            const auto sequence = storage->write_sequence + 1;
            auto& destination = storage->records[(sequence - 1) % 256];
            InterlockedExchange64(&destination.committed_sequence, 0);
            std::memcpy(reinterpret_cast<unsigned char*>(&destination) + 8,
                reinterpret_cast<const unsigned char*>(&record) + 8, sizeof(Record) - 8);
            MemoryBarrier();
            InterlockedExchange64(&destination.committed_sequence, sequence);
            if (sequence > 256) { InterlockedIncrement64(&storage->overwritten); }
            InterlockedExchange64(&storage->write_sequence, sequence);
        }
    }
    ReleaseSRWLockExclusive(&lock);
}
void __fastcall TracedDeserialize(void* message, void*, void* stream) {
    // Preserve native exceptions and call-through. A thrown decode produces no
    // record. Native bookkeeping/queue publication follows: diagnostics only.
    const auto caller = reinterpret_cast<std::uintptr_t>(_ReturnAddress());
    const bool active_socket = ActiveSocket(stream);
    movement::NativeScene scene{};
    (void)movement::ReadNativeMovementLifetime(scene);
    original(message, stream);
    if (active_socket) { Observe(message, stream, caller, scene); }
}
void CloseLocked() noexcept {
    if (storage) {
        InterlockedExchange(&storage->stopped, 1);
        UnmapViewOfFile(storage); storage = nullptr;
    }
    if (mapping) { CloseHandle(mapping); mapping = nullptr; }
}
DWORD StartBound(const ProcessIdentity& identity, std::uintptr_t base,
    std::uint32_t* slot, Deserialize target) noexcept {
    AcquireSRWLockExclusive(&lock);
    if (attempted) { ReleaseSRWLockExclusive(&lock); return ERROR_ALREADY_INITIALIZED; }
    attempted = true;
    wchar_t name[160]{};
    DWORD result = ERROR_SUCCESS;
    if (FAILED(StringCchPrintfW(name, 160, L"Local\\ShadowbaneLab.Extension.TargetedAction.v2.%lu.%llu",
        identity.process_id, identity.creation_filetime_utc))) { result = ERROR_INVALID_DATA; }
    if (!result) {
        mapping = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0, sizeof(Storage), name);
        if (!mapping) { result = GetLastError(); }
        else if (GetLastError() == ERROR_ALREADY_EXISTS) { result = ERROR_ALREADY_EXISTS; }
    }
    if (!result) {
        storage = static_cast<Storage*>(MapViewOfFile(mapping, FILE_MAP_WRITE, 0, 0, sizeof(Storage)));
        if (!storage) { result = GetLastError(); }
    }
    if (!result) {
        std::memcpy(storage->magic, "WBTACT2", 8);
        storage->schema = 2; storage->record_size = sizeof(Record); storage->capacity = 256;
        storage->process_id = identity.process_id; storage->creation_filetime = identity.creation_filetime_utc;
        // Immutable forever after possible publication, including failed restore.
        original = target; installed_slot = slot; image_base = base;
        result = ReplaceImportAddressSlot(slot, reinterpret_cast<std::uint32_t>(target),
            reinterpret_cast<std::uint32_t>(&TracedDeserialize));
        if (result) {
            (void)ReplaceImportAddressSlot(slot, reinterpret_cast<std::uint32_t>(&TracedDeserialize),
                reinterpret_cast<std::uint32_t>(target));
        }
    }
    if (result) { CloseLocked(); }
    ReleaseSRWLockExclusive(&lock);
    return result;
}
}  // namespace
DWORD StartTargetedActionTrace(const ProcessIdentity& identity) noexcept {
    wchar_t enabled[2]{};
    if (GetEnvironmentVariableW(L"WONDERBANE_TARGETED_ACTION_TRACE", enabled, 2) != 1 || enabled[0] != L'1') {
        return ERROR_NOT_SUPPORTED;
    }
    FILETIME creation{}, exit{}, kernel{}, user{};
    if (identity.process_id != GetCurrentProcessId()
        || !GetProcessTimes(GetCurrentProcess(), &creation, &exit, &kernel, &user)
        || identity.creation_filetime_utc != ((static_cast<std::uint64_t>(creation.dwHighDateTime) << 32)
            | creation.dwLowDateTime)) { return ERROR_INVALID_DATA; }
    std::uintptr_t base = 0;
    if ((!GraphicsExecutableSha256Matches("bb63469eb35917e6b3f58be75d29f94855c9868024271222465b4db62f0e3a87")
        && !GraphicsExecutableSha256Matches("b646ae32ebc44be45a7a65da3c764e1cd67f63f45fca91262b75f21fd11002f3")
        && !GraphicsExecutableSha256Matches("e277e5a4e1e4e1df048a32c07bdbac6fec0591c7d01588b984577251cf475891")
        && !GraphicsExecutableSha256Matches("761f375e422332cac2512398bb935af38b30267b9b3a7a5cede9f87e98982442")
        && !GraphicsExecutableSha256Matches("7f283cdbeb691d65ef3073d32e4ea7bc0cfcb31e1bb205e460573f23d0a7758f"))
        || !movement::VerifyNativeMovementImage(base)) { return ERROR_NOT_SUPPORTED; }
    return StartBound(identity, base, reinterpret_cast<std::uint32_t*>(base + slot_rva),
        reinterpret_cast<Deserialize>(base + target_rva));
}
void StopTargetedActionTrace() noexcept {
    AcquireSRWLockExclusive(&lock);
    if (installed_slot) {
        (void)ReplaceImportAddressSlot(installed_slot, reinterpret_cast<std::uint32_t>(&TracedDeserialize),
            reinterpret_cast<std::uint32_t>(original));
    }
    CloseLocked();
    // No restart/replacement generation and no unload. A callback that loaded
    // the old slot retains valid original call-through and observes closed state.
    ReleaseSRWLockExclusive(&lock);
}
}  // namespace wonderbane::extension
