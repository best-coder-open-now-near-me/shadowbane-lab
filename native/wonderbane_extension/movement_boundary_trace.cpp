#include "movement_boundary_trace.h"
#include "graphics_status.h"
#include "import_hook.h"
#include <bcrypt.h>
#include <intrin.h>
#include <strsafe.h>
#include <array>
#include <cstring>

namespace wonderbane::extension {
namespace {
constexpr std::uintptr_t preferred_base = 0x400000;
constexpr std::uintptr_t update_rva = 0x79AB40;
constexpr std::uintptr_t thunk_rva = 0x1354D;
constexpr std::uintptr_t slot_rva = 0x11748F0;
constexpr std::size_t update_size = 2350;
constexpr std::array<std::size_t, 63> relocations{
    0x6,0x23,0x4e,0x90,0xa1,0xaf,0xba,0x122,0x128,0x134,0x155,0x15b,0x160,
    0x175,0x1a2,0x1ae,0x1cb,0x216,0x280,0x286,0x28c,0x292,0x2a3,0x2a9,
    0x2b6,0x2d1,0x2e1,0x3ab,0x3b1,0x44e,0x464,0x478,0x489,0x4a6,0x4bc,
    0x4e3,0x526,0x531,0x56d,0x58f,0x594,0x604,0x639,0x65b,0x660,0x6fd,
    0x706,0x723,0x72f,0x734,0x751,0x760,0x76f,0x77a,0x867,0x880,0x899,
    0x8a7,0x8cc,0x8e0,0x8ec,0x908,0x90f};
constexpr std::array<unsigned char,32> expected_digest{
    0xf7,0x68,0xa9,0xed,0xb8,0x84,0x24,0x03,0x9a,0xe7,0x59,0xb4,0x4e,0xc4,0xd4,0x4d,
    0xe6,0xa0,0x17,0x41,0xb6,0x65,0x24,0xc0,0xbb,0xf2,0x4e,0x80,0x92,0x11,0x1a,0x8e};
using Update = std::uint32_t(__thiscall*)(void*, double);
std::uintptr_t image_base = 0;
Update original = nullptr;
MovementBoundaryTrace* trace = nullptr;
HANDLE mapping = nullptr;
std::uint32_t* installed_slot = nullptr;
NativeMovementUpdate movement_update = nullptr;
volatile LONG movement_enabled = 0;
bool movement_registered = false;
bool hook_ready = false, hook_retired = false;
SRWLOCK publication_lock = SRWLOCK_INIT;
SRWLOCK lifecycle_lock = SRWLOCK_INIT;
struct LifecycleGuard {
    LifecycleGuard() noexcept { AcquireSRWLockExclusive(&lifecycle_lock); }
    ~LifecycleGuard() { ReleaseSRWLockExclusive(&lifecycle_lock); }
    LifecycleGuard(const LifecycleGuard&) = delete;
    LifecycleGuard& operator=(const LifecycleGuard&) = delete;
};
bool ExactIdentity(const ProcessIdentity& identity) noexcept {
    FILETIME creation{}, exit{}, kernel{}, user{};
    if (identity.process_id != GetCurrentProcessId()
        || !GetProcessTimes(GetCurrentProcess(), &creation, &exit, &kernel, &user)) { return false; }
    const auto actual = (static_cast<std::uint64_t>(creation.dwHighDateTime) << 32)
        | creation.dwLowDateTime;
    return identity.creation_filetime_utc == actual;
}
volatile LONG enabled = 0;
LONG64 sequence = 0;

bool CopyRead(void* output, std::uintptr_t address, std::size_t size) noexcept {
    if (address < 0x10000 || size > 0x7FFF0000 || address > 0x7FFF0000 - size) { return false; }
    MEMORY_BASIC_INFORMATION region{};
    if (!VirtualQuery(reinterpret_cast<const void*>(address), &region, sizeof(region))
        || region.State != MEM_COMMIT || (region.Protect & (PAGE_GUARD | PAGE_NOACCESS))
        || !(region.Protect & (PAGE_READONLY | PAGE_READWRITE | PAGE_WRITECOPY
                              | PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY))
        || address - reinterpret_cast<std::uintptr_t>(region.BaseAddress) > region.RegionSize
        || size > region.RegionSize - (address - reinterpret_cast<std::uintptr_t>(region.BaseAddress))) {
        return false;
    }
    __try { std::memcpy(output, reinterpret_cast<const void*>(address), size); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
bool Read32(std::uintptr_t address, std::uint32_t& output) noexcept {
    return CopyRead(&output, address, sizeof(output));
}
bool VerifyUpdate() noexcept {
    std::array<unsigned char, update_size> code{};
    if (!CopyRead(code.data(), image_base + update_rva, code.size())) { return false; }
    const auto delta = static_cast<std::uint32_t>(image_base - preferred_base);
    for (const auto offset : relocations) {
        std::uint32_t value = 0;
        std::memcpy(&value, code.data() + offset, 4);
        value -= delta;
        std::memcpy(code.data() + offset, &value, 4);
    }
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    std::array<unsigned char,32> digest{};
    const bool ok = BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) >= 0
        && BCryptCreateHash(algorithm, &hash, nullptr, 0, nullptr, 0, 0) >= 0
        && BCryptHashData(hash, code.data(), static_cast<ULONG>(code.size()), 0) >= 0
        && BCryptFinishHash(hash, digest.data(), static_cast<ULONG>(digest.size()), 0) >= 0;
    if (hash) { BCryptDestroyHash(hash); }
    if (algorithm) { BCryptCloseAlgorithmProvider(algorithm,0); }
    std::array<unsigned char,5> thunk{};
    if (!CopyRead(thunk.data(), image_base + thunk_rva, thunk.size()) || thunk[0] != 0xE9) { return false; }
    std::int32_t displacement = 0;
    std::memcpy(&displacement, thunk.data()+1, 4);
    return ok && digest == expected_digest
        && image_base + thunk_rva + 5 + displacement == image_base + update_rva;
}
void Observe(void* receiver, double delta, std::uintptr_t caller) noexcept {
    if (!InterlockedCompareExchange(&enabled,0,0)) { return; }
    if (!TryAcquireSRWLockExclusive(&publication_lock)) {
        InterlockedIncrement(&trace->dropped); return;
    }
    if (!InterlockedCompareExchange(&enabled,0,0)) { ReleaseSRWLockExclusive(&publication_lock); return; }
    MovementBoundaryRecord record{};
    record.tick_ms = GetTickCount64(); record.native_delta = delta;
    record.thread_id = GetCurrentThreadId();
    DWORD pid = 0;
    record.foreground_thread = GetWindowThreadProcessId(GetForegroundWindow(), &pid);
    record.foreground_pid = pid;
    record.receiver = reinterpret_cast<std::uint32_t>(receiver);
    record.caller_rva = caller >= image_base && caller - image_base < 0x1766000
        ? static_cast<std::uint32_t>(caller - image_base) : 0;
    std::uint32_t window = 0, begin = 0, end = 0, state = 0;
    bool valid = Read32(image_base + 0x16A7BFC, window) && window == record.receiver
        && Read32(image_base + 0x16A2D98, record.actor)
        && Read32(window + 0x64, record.game_mode)
        && Read32(window + 0x28, record.ui_candidate)
        && Read32(image_base + 0x16A9EE8, record.modal_candidate);
    if (valid && record.actor) {
        valid = Read32(record.actor + 0xC10, begin) && Read32(record.actor + 0xC14, end)
            && end >= begin && (end - begin) % 16 == 0 && end - begin <= 1048576
            && Read32(record.actor + 0xAD0, state) && state && Read32(state + 0x10, record.movement_state);
        if (valid) { record.path_count = (end - begin) / 16; }
    }
    record.read_valid = valid ? 1U : 0U;
    ++sequence;
    auto& target = trace->records[(sequence - 1) % 256];
    InterlockedExchange64(&target.committed_sequence, 0);
    std::memcpy(reinterpret_cast<unsigned char*>(&target) + 8,
                reinterpret_cast<const unsigned char*>(&record) + 8, sizeof(record)-8);
    MemoryBarrier();
    InterlockedExchange64(&target.committed_sequence, sequence);
    InterlockedExchange64(&trace->write_sequence, sequence);
    ReleaseSRWLockExclusive(&publication_lock);
}
std::uint32_t __fastcall TracedUpdate(void* receiver, void*, double delta) {
    Observe(receiver, delta, reinterpret_cast<std::uintptr_t>(_ReturnAddress()));
    // Callback identity is immutable after publication and remains process-pinned.
    // A consumer admitted before retirement may finish; retirement never destroys
    // its state or the original call-through. The runtime handles native shutdown
    // on this thread before requesting its own retirement.
    if (InterlockedCompareExchange(&movement_enabled, 0, 0)) { movement_update(receiver, delta); }
    return original(receiver, delta);
}
DWORD InstallUpdate(std::uint32_t* slot, Update target) noexcept {
    if (installed_slot) {
        if (!hook_ready || hook_retired || installed_slot != slot || original != target) { return ERROR_ALREADY_INITIALIZED; }
        std::uint32_t current = 0;
        return Read32(reinterpret_cast<std::uintptr_t>(slot), current)
            && current == reinterpret_cast<std::uint32_t>(&TracedUpdate) ? ERROR_SUCCESS : ERROR_INVALID_DATA;
    }
    original = target; installed_slot = slot;
    const auto result = ReplaceImportAddressSlot(slot, reinterpret_cast<std::uint32_t>(target),
        reinterpret_cast<std::uint32_t>(&TracedUpdate));
    hook_ready = result == ERROR_SUCCESS;
    // A failed protection restoration may still have made the callback visible.
    // Preserve original/state even on failure; do not admit another installation.
    return result;
}
void RetireUnusedUpdate() noexcept {
    if (!installed_slot || InterlockedCompareExchange(&movement_enabled, 0, 0)
        || InterlockedCompareExchange(&enabled, 0, 0)) { return; }
    hook_retired = true;
    (void)ReplaceImportAddressSlot(installed_slot,
        reinterpret_cast<std::uint32_t>(&TracedUpdate), reinterpret_cast<std::uint32_t>(original));
}
DWORD InstallMovement(const ProcessIdentity& identity, NativeMovementUpdate callback,
    std::uint32_t* slot, Update target) noexcept {
    if (!ExactIdentity(identity) || !callback) { return ERROR_INVALID_DATA; }
    if (movement_registered) { return ERROR_ALREADY_INITIALIZED; }
    // Publish immutable callback identity before making its admission flag visible.
    movement_update = callback; movement_registered = true;
    const auto result = InstallUpdate(slot, target);
    if (result == ERROR_SUCCESS) { InterlockedExchange(&movement_enabled, 1); }
    return result;
}
DWORD VerifyBinding(const ProcessIdentity& identity) noexcept {
    if (!GraphicsExecutableSha256Matches("feb351f0fae87d47549fa43c37836405a753d76fbcd0b02232fc1c0733550dff")) {
        return ERROR_NOT_SUPPORTED;
    }
    if (!ExactIdentity(identity)) { return ERROR_INVALID_DATA; }
    const auto base = reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr));
    if (!base || (image_base && image_base != base)) { return ERROR_INVALID_DATA; }
    if (!image_base) { image_base = base; }
    return VerifyUpdate() ? ERROR_SUCCESS : ERROR_INVALID_DATA;
}
DWORD InstallTrace(const ProcessIdentity& identity, std::uint32_t* slot, Update target) noexcept {
    if (!ExactIdentity(identity)) { return ERROR_INVALID_DATA; }
    if (mapping) { return ERROR_ALREADY_INITIALIZED; }
    wchar_t name[160]{};
    if (FAILED(StringCchPrintfW(name,160,L"Local\\ShadowbaneLab.Extension.MovementBoundary.%lu.%llu",
        identity.process_id,identity.creation_filetime_utc))) { return ERROR_INVALID_DATA; }
    mapping = CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,sizeof(MovementBoundaryTrace),name);
    if (!mapping) { return GetLastError(); }
    if (GetLastError() == ERROR_ALREADY_EXISTS) { CloseHandle(mapping); mapping = nullptr; return ERROR_ALREADY_EXISTS; }
    trace = static_cast<MovementBoundaryTrace*>(MapViewOfFile(mapping,FILE_MAP_WRITE,0,0,sizeof(MovementBoundaryTrace)));
    if (!trace) { const auto error=GetLastError(); CloseHandle(mapping); mapping=nullptr; return error; }
    std::memcpy(trace->magic,"WBMVTR1",8);
    trace->schema=1; trace->record_size=sizeof(MovementBoundaryRecord); trace->capacity=256;
    trace->process_id=identity.process_id; trace->creation_filetime=identity.creation_filetime_utc;
    const auto result = InstallUpdate(slot, target);
    if (result == ERROR_SUCCESS) {
        InterlockedExchange(&trace->enabled,1); InterlockedExchange(&enabled,1);
    }
    // Retain mapping even on failed installation: an in-flight callback can still hold it.
    return result;
}
}

DWORD StartMovementBoundaryTrace(const ProcessIdentity& identity) noexcept {
    const LifecycleGuard lifecycle;
    wchar_t option[4]{};
    if (GetEnvironmentVariableW(L"WONDERBANE_MOVEMENT_TRACE", option, 4) != 1 || option[0] != L'1') {
        return ERROR_SUCCESS;
    }
    // Initialized once by the shared process-pinned extension startup.
    if (mapping) { return ERROR_ALREADY_INITIALIZED; }
    const auto verified = VerifyBinding(identity);
    if (verified != ERROR_SUCCESS) { return verified; }
    return InstallTrace(identity, reinterpret_cast<std::uint32_t*>(image_base + slot_rva),
        reinterpret_cast<Update>(image_base + thunk_rva));
}

void StopMovementBoundaryTrace() noexcept {
    const LifecycleGuard lifecycle;
    InterlockedExchange(&enabled,0);
    if (mapping) {
        AcquireSRWLockExclusive(&publication_lock);
        InterlockedExchange(&trace->enabled,0);
        ReleaseSRWLockExclusive(&publication_lock);
    }
    RetireUnusedUpdate();
    // Pinned code and bounded mapping stay alive until process exit. No unload race.
}
DWORD StartNativeMovementUpdates(const ProcessIdentity& identity, NativeMovementUpdate callback) noexcept {
    const LifecycleGuard lifecycle;
    if (movement_registered) { return ERROR_ALREADY_INITIALIZED; }
    const auto verified = VerifyBinding(identity);
    if (verified != ERROR_SUCCESS) { return verified; }
    return InstallMovement(identity, callback, reinterpret_cast<std::uint32_t*>(image_base + slot_rva),
        reinterpret_cast<Update>(image_base + thunk_rva));
}
void StopNativeMovementUpdates() noexcept {
    const LifecycleGuard lifecycle;
    InterlockedExchange(&movement_enabled, 0);
    RetireUnusedUpdate();
}
#if defined(WONDERBANE_MOVEMENT_TRACE_TESTING)
DWORD StartMovementBoundaryTraceForTesting(const ProcessIdentity& identity,
    std::uint32_t* slot, std::uint32_t target) noexcept {
    const LifecycleGuard lifecycle;
    return InstallTrace(identity, slot, reinterpret_cast<Update>(target));
}
DWORD StartNativeMovementUpdatesForTesting(const ProcessIdentity& identity, NativeMovementUpdate callback,
    std::uint32_t* slot, std::uint32_t target) noexcept {
    const LifecycleGuard lifecycle;
    return InstallMovement(identity, callback, slot, reinterpret_cast<Update>(target));
}
const MovementBoundaryTrace* MovementBoundaryTraceForTesting() noexcept { return trace; }
#endif

} // namespace wonderbane::extension
