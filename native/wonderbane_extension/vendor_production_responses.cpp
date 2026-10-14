#include "vendor_production_responses.h"
#include "graphics_status.h"
#include "import_hook.h"
#include "movement_native_image.h"
#include "movement_lifetime.h"
#include <intrin.h>
#include <strsafe.h>
#include <cstring>
#include <limits>
namespace wonderbane::extension::vendor_production {
namespace {
using Decode = void(__thiscall*)(void*, void*);
using Process = std::uint32_t(__thiscall*)(void*);
using Destroy = void*(__thiscall*)(void*, unsigned);
constexpr std::uintptr_t kTable = 0x115bfd8, kDecoderReturn = 0x3625bc;
constexpr std::array<std::uintptr_t, 3> kSlots{4, 0x14, 0x1c};
constexpr std::array<std::uintptr_t, 3> kTargets{0x20e55, 0x27dbd, 0x1f523};
constexpr unsigned kPayload = 1, kScene = 2, kLineage = 4;
SRWLOCK lock = SRWLOCK_INIT;
Decode decode_original = nullptr;
Process process_original = nullptr;
Destroy destroy_original = nullptr;
std::array<std::uint32_t*, 3> installed_slots{};
std::array<std::uint32_t, 3> original_slots{};
std::uintptr_t image_base = 0;
HANDLE mapping = nullptr;
Storage* storage = nullptr;
bool attempted = false;
struct Ticket {
    void* message = nullptr; // Lookup only; never dereferenced after callback.
    std::uint64_t sequence = 0;
    movement::NativeScene scene{};
    Payload payload{};
};
std::array<Ticket, 64> tickets{};
std::size_t next_ticket = 0;
bool Copy(void* out, const void* input, std::size_t size) noexcept {
    __try { std::memcpy(out, input, size); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
bool Read(std::uintptr_t address, void* out, std::size_t size) noexcept {
    return address >= 0x10000 && address % 4 == 0 && size && size <= 8192
        && address < 0x80000000 && size <= 0x80000000 - address
        && Copy(out, reinterpret_cast<void*>(address), size);
}
bool Word(std::uintptr_t address, std::uint32_t& out) noexcept { return Read(address, &out, 4); }
bool Snapshot(void* message, Payload& out) noexcept {
    out = {};
    const auto p = reinterpret_cast<std::uintptr_t>(message);
    std::uint32_t table = 0;
    if (!Word(p, table) || table != image_base + kTable
        || !Word(p + 0x70, out.action) || out.action > 11
        || !Word(p + 0xa0, out.error)
        || !Read(p + 0x78, out.building.data(), 8)
        || !Read(p + 0x80, out.vendor.data(), 8)
        || !Read(p + 0x88, out.reference.data(), 8)
        || !Word(p + 0x90, out.quantity) || !Word(p + 0x94, out.marker)
        || !Word(p + 0x98, out.prefix) || !Word(p + 0x9c, out.suffix)) { return false; }
    std::uint32_t flags = 0;
    if (!Word(p + 0x11c, flags) || (flags & 255) > 1) { return false; }
    if (flags & 255) {
        if (!Word(p + 0x10c, out.strongbox_gold)) { return false; }
        out.fields |= 4;
    }
    if (out.action == 1) {
        out.multiple = (flags >> 8) & 255;
        if (out.multiple > 1) { return false; }
        out.fields |= 8;
    }
    if (out.action == 8 && !out.error) {
        if (!Read(p + 0xc0, out.item.data(), 8) || !out.item[0] || out.item[1] != 40
            || !Word(p + 0xc8, out.item_template) || !out.item_template
            || !Word(p + 0xcc, flags) || flags != 0 || !Word(p + 0xd0, out.value)
            || !Word(p + 0xd4, out.seconds) || !Word(p + 0xd8, out.duration)
            || !Word(p + 0xdc, out.remaining) || !out.remaining || out.remaining > 255
            || !Word(p + 0xe0, flags)) { return false; }
        // +0xc8/+0xcc is the typed template key, not an item count.
        // The native receive handler passes +0xdc as the displayed count and
        // the two low bytes at +0xe0 as active/completed flags.
        out.in_progress = flags & 255;
        out.complete = (flags >> 8) & 255;
        if (out.in_progress > 1 || out.complete > 1 || out.in_progress == out.complete
            || (out.complete && out.seconds)) { return false; }
        out.fields |= 1;
    }
    if (out.action == 10 && !out.error) {
        std::uint32_t instance = 0;
        if (!Word(p + 0x100, instance)) { return false; }
        if (instance) {
            if (!Word(instance, table) || table != image_base + 0x114bb68
                || !Read(instance + 0x10, out.deposited_template.data(), 8)
                || !Read(instance + 0x18, out.deposited_item.data(), 8)
                || !out.deposited_template[0] || out.deposited_template[1]
                || !out.deposited_item[0] || out.deposited_item[1] != 40) { return false; }
            out.fields |= 2;
        }
    }
    return true;
}
bool ActiveSocket(void* socket) noexcept {
    std::uint32_t table = 0, flags = 0;
    const auto address = reinterpret_cast<std::uintptr_t>(socket);
    return Word(address, table) && table == image_base + 0x116019c
        && Word(address + 0x1c, flags) && (flags & 255) == 0;
}
void ForgetLocked(void* message) noexcept {
    for (auto& ticket : tickets) { if (ticket.message == message) { ticket.message = nullptr; } }
}
void Forget(void* message) noexcept {
    AcquireSRWLockExclusive(&lock); ForgetLocked(message); ReleaseSRWLockExclusive(&lock);
}
std::uint64_t PublishLocked(Record& record) noexcept {
    if (!storage || storage->stopped || storage->sequence == std::numeric_limits<LONG64>::max()) { return 0; }
    const auto sequence = storage->sequence + 1;
    record.tick_ms = GetTickCount64(); record.thread_id = GetCurrentThreadId();
    if (record.stage == 1) { record.decode_sequence = static_cast<std::uint64_t>(sequence); }
    auto& destination = storage->records[(sequence - 1) % kCapacity];
    InterlockedExchange64(&destination.sequence, 0);
    std::memcpy(reinterpret_cast<unsigned char*>(&destination) + 8,
        reinterpret_cast<const unsigned char*>(&record) + 8, sizeof(Record) - 8);
    MemoryBarrier(); InterlockedExchange64(&destination.sequence, sequence);
    if (sequence > static_cast<LONG64>(kCapacity)) { InterlockedIncrement64(&storage->overwritten); }
    InterlockedExchange64(&storage->sequence, sequence);
    return static_cast<std::uint64_t>(sequence);
}
void Stamp(Record& record, const movement::NativeScene& scene) noexcept {
    if (scene.epoch && movement::NativeMovementLifetimeCurrent(scene)) {
        record.flags |= kScene; record.scene_epoch = scene.epoch; record.local = scene.identity;
    }
}
void __fastcall DecodeHook(void* message, void*, void* socket) {
    const DWORD incoming_error = GetLastError();
    const auto caller = reinterpret_cast<std::uintptr_t>(_ReturnAddress());
    Forget(message); // Even a replay or failed decode must invalidate an earlier ticket.
    const bool active = caller == image_base + kDecoderReturn && ActiveSocket(socket);
    movement::NativeScene scene{};
    if (active) { (void)movement::ReadNativeMovementLifetime(scene); }
    SetLastError(incoming_error);
    decode_original(message, socket); // Preserve native exceptions and native call-through.
    const DWORD native_error = GetLastError();
    if (!active || !ActiveSocket(socket)) { SetLastError(native_error); return; }
    Record record{}; record.stage = 1; record.caller_rva = static_cast<std::uint32_t>(kDecoderReturn);
    const bool valid = Snapshot(message, record.payload);
    if (valid) { record.flags |= kPayload; } else { record.payload = {}; }
    Stamp(record, scene);
    AcquireSRWLockExclusive(&lock);
    if (storage) {
        if (!valid) { InterlockedIncrement(&storage->rejected); }
        const auto sequence = PublishLocked(record);
        if (valid && sequence && (record.flags & kScene)) {
            auto& ticket = tickets[next_ticket++ % tickets.size()];
            if (ticket.message) { InterlockedIncrement64(&storage->ticket_drops); }
            ticket.message = message; ticket.sequence = sequence; ticket.scene = scene; ticket.payload = record.payload;
        }
    }
    ReleaseSRWLockExclusive(&lock);
    SetLastError(native_error);
}
std::uint32_t __fastcall ProcessHook(void* message, void*) {
    const DWORD incoming_error = GetLastError();
    const auto caller = reinterpret_cast<std::uintptr_t>(_ReturnAddress());
    Record record{}; record.stage = 2;
    record.caller_rva = caller >= image_base && caller - image_base < 0x16b0000
        ? static_cast<std::uint32_t>(caller - image_base) : 0;
    movement::NativeScene scene{};
    (void)movement::ReadNativeMovementLifetime(scene);
    const bool valid = Snapshot(message, record.payload);
    if (valid) { record.flags |= kPayload; } else { record.payload = {}; }
    Stamp(record, scene);
    AcquireSRWLockExclusive(&lock);
    for (auto& ticket : tickets) {
        if (ticket.message != message) { continue; }
        ticket.message = nullptr;
        if (valid && (record.flags & kScene) && ticket.scene.epoch == scene.epoch
            && movement::NativeMovementLifetimeCurrent(ticket.scene)
            && !std::memcmp(&ticket.payload, &record.payload, sizeof(Payload))) {
            record.flags |= kLineage; record.decode_sequence = ticket.sequence;
        }
    }
    (void)PublishLocked(record);
    ReleaseSRWLockExclusive(&lock);
    SetLastError(incoming_error);
    const auto result = process_original(message);
    const DWORD native_error = GetLastError();
    record.stage = 3;
    if (!movement::NativeMovementLifetimeCurrent(scene)) {
        record.flags &= ~(kScene | kLineage); record.scene_epoch = 0; record.local = {};
        record.decode_sequence = 0;
    }
    // Keep the copied response body, not native fields mutated by UI processing.
    // Returning from the handler does not establish acceptance or gameplay effect.
    AcquireSRWLockExclusive(&lock); (void)PublishLocked(record); ReleaseSRWLockExclusive(&lock);
    SetLastError(native_error);
    return result;
}
void* __fastcall DestroyHook(void* message, void*, unsigned flags) {
    const DWORD incoming_error = GetLastError();
    Forget(message);
    SetLastError(incoming_error);
    return destroy_original(message, flags);
}
std::array<std::uint32_t, 3> Hooks() noexcept {
    return {reinterpret_cast<std::uint32_t>(&DestroyHook), reinterpret_cast<std::uint32_t>(&ProcessHook),
        reinterpret_cast<std::uint32_t>(&DecodeHook)};
}
bool CursorLocked(Cursor& out) noexcept {
    if (!storage || storage->stopped || storage->sequence < 0 || storage->rejected < 0
        || storage->ticket_drops < 0 || !storage->process_id || !storage->creation
        || storage->schema != 2 || storage->record_size != sizeof(Record)
        || storage->capacity != kCapacity || std::memcmp(storage->magic, "WBPRD2\0", 8)
        || storage->overwritten != (storage->sequence > static_cast<LONG64>(kCapacity)
            ? storage->sequence - static_cast<LONG64>(kCapacity) : 0)) { return false; }
    out = {storage->process_id, storage->creation, static_cast<std::uint64_t>(storage->sequence),
        static_cast<std::uint64_t>(storage->rejected), static_cast<std::uint64_t>(storage->ticket_drops)};
    return true;
}
void CloseLocked() noexcept {
    for (auto& ticket : tickets) { ticket.message = nullptr; }
    if (storage) { InterlockedExchange(&storage->stopped, 1); UnmapViewOfFile(storage); storage = nullptr; }
    if (mapping) { CloseHandle(mapping); mapping = nullptr; }
}
DWORD StartBound(const ProcessIdentity& identity, std::uintptr_t base,
    const std::array<std::uint32_t*, 3>& slots, const std::array<std::uint32_t, 3>& targets) noexcept {
    AcquireSRWLockExclusive(&lock);
    if (attempted) { ReleaseSRWLockExclusive(&lock); return ERROR_ALREADY_INITIALIZED; }
    attempted = true;
    DWORD result = ERROR_SUCCESS;
    wchar_t name[160]{};
    if (FAILED(StringCchPrintfW(name, 160, L"Local\\ShadowbaneLab.Extension.VendorProduction.v2.%lu.%llu",
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
        std::memcpy(storage->magic, "WBPRD2\0", 8);
        storage->schema = 2; storage->record_size = sizeof(Record); storage->capacity = kCapacity;
        storage->process_id = identity.process_id; storage->creation = identity.creation_filetime_utc;
        image_base = base; installed_slots = slots; original_slots = targets;
        destroy_original = reinterpret_cast<Destroy>(targets[0]);
        process_original = reinterpret_cast<Process>(targets[1]);
        decode_original = reinterpret_cast<Decode>(targets[2]);
        const auto hooks = Hooks();
        for (std::size_t i = 0; i < slots.size(); ++i) {
            result = ReplaceImportAddressSlot(slots[i], targets[i], hooks[i]);
            if (result) { break; }
        }
        if (result) {
            for (std::size_t i = 0; i < slots.size(); ++i) {
                (void)ReplaceImportAddressSlot(slots[i], hooks[i], targets[i]);
            }
        }
    }
    if (result) { CloseLocked(); }
    ReleaseSRWLockExclusive(&lock);
    return result;
}
}
DWORD Start(const ProcessIdentity& identity) noexcept {
    FILETIME creation{}, exit{}, kernel{}, user{};
    if (identity.process_id != GetCurrentProcessId()
        || !GetProcessTimes(GetCurrentProcess(), &creation, &exit, &kernel, &user)
        || identity.creation_filetime_utc != ((static_cast<std::uint64_t>(creation.dwHighDateTime) << 32)
            | creation.dwLowDateTime)) { return ERROR_INVALID_DATA; }
    std::uintptr_t base = 0;
    if (!(GraphicsExecutableSha256Matches("366ea471a47bf6f6cdc1da91ea415f5b202d307e4ec6e8272b349f39e63d142a") || GraphicsExecutableSha256Matches("6bd0e391edc1c773b4c96d8a9801db45f96db9e34202afcfc8d383d4971fe5ad"))
        || !movement::VerifyNativeMovementImage(base)) { return ERROR_NOT_SUPPORTED; }
    std::array<std::uint32_t*, 3> slots{};
    std::array<std::uint32_t, 3> targets{};
    for (std::size_t i = 0; i < slots.size(); ++i) {
        slots[i] = reinterpret_cast<std::uint32_t*>(base + kTable + kSlots[i]);
        targets[i] = static_cast<std::uint32_t>(base + kTargets[i]);
    }
    return StartBound(identity, base, slots, targets);
}
bool ReadCursor(Cursor& out) noexcept {
    out = {};
    AcquireSRWLockShared(&lock);
    const bool valid = CursorLocked(out);
    ReleaseSRWLockShared(&lock);
    return valid;
}
bool ReadAfter(const Cursor& before, Batch& out) noexcept {
    out.after = {}; out.count = 0;
    AcquireSRWLockShared(&lock);
    Cursor after{};
    bool valid = CursorLocked(after) && before.process_id == after.process_id
        && before.creation == after.creation && before.sequence <= after.sequence
        && after.sequence - before.sequence <= kCapacity
        && before.rejected == after.rejected && before.ticket_drops == after.ticket_drops;
    if (valid) {
        for (auto sequence = before.sequence + 1; sequence <= after.sequence; ++sequence) {
            const auto& source = storage->records[(sequence - 1) % kCapacity];
            if (source.sequence != static_cast<LONG64>(sequence)) { valid = false; break; }
            std::memcpy(&out.records[out.count++], &source, sizeof(Record));
        }
    }
    if (valid) { out.after = after; }
    else { out.after = {}; out.count = 0; }
    ReleaseSRWLockShared(&lock);
    return valid;
}
void Stop() noexcept {
    AcquireSRWLockExclusive(&lock);
    const auto hooks = Hooks();
    for (std::size_t i = 0; i < installed_slots.size(); ++i) {
        if (installed_slots[i]) { (void)ReplaceImportAddressSlot(installed_slots[i], hooks[i], original_slots[i]); }
    }
    CloseLocked();
    // Immutable call-through and code remain pinned for callbacks already in flight.
    ReleaseSRWLockExclusive(&lock);
}
}
