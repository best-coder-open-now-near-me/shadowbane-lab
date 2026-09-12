#include "targeted_action_trace.h"
#include "graphics_status.h"
#include "import_hook.h"
#include "movement_native_image.h"
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
constexpr std::uintptr_t message_vtable_rva = 0x1158878;
struct alignas(8) Record {
    volatile LONG64 committed_sequence;
    std::uint64_t tick_ms;
    std::uint32_t thread_id;
    std::uint32_t caller_rva;
    // Original message +0x80..+0xaf (last four words reserved), without pointers or interpreted hostility.
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
void Observe(void* message, void* stream, std::uintptr_t caller) noexcept {
    // Call-through owns message and stream through this synchronous observation.
    // Serialize with closure BEFORE touching publication storage. No borrowed
    // message/stream/character pointer survives the callback.
    AcquireSRWLockExclusive(&lock);
    if (storage) {
        std::uint32_t stream_table = 0, message_table = 0;
        Record record{};
        if (caller == image_base + decoder_return_rva
            && Copy(&stream_table, stream, sizeof(stream_table))
            && stream_table == image_base + socket_vtable_rva
            && Copy(&message_table, message, sizeof(message_table))
            && message_table == image_base + message_vtable_rva
            && Copy(record.fields.data(), static_cast<unsigned char*>(message) + 0x80, 48)) {
            // Native decoding leaves conditional payloads untouched when absent.
            // Never export stale/uninitialized values from those absent fields.
            if (!record.fields[4]) { record.fields[5] = record.fields[6] = record.fields[7] = 0; }
            if (!record.fields[8]) { record.fields[9] = record.fields[10] = record.fields[11] = 0; }
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
    // record. Later stream validation may still fail: records are diagnostic only.
    const auto caller = reinterpret_cast<std::uintptr_t>(_ReturnAddress());
    original(message, stream);
    Observe(message, stream, caller);
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
    if (FAILED(StringCchPrintfW(name, 160, L"Local\\ShadowbaneLab.Extension.TargetedAction.v1.%lu.%llu",
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
        std::memcpy(storage->magic, "WBTACT1", 8);
        storage->schema = 1; storage->record_size = sizeof(Record); storage->capacity = 256;
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
    if (!GraphicsExecutableSha256Matches("bb63469eb35917e6b3f58be75d29f94855c9868024271222465b4db62f0e3a87")
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
