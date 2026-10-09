#include "tracking_responses.h"
#include "graphics_status.h"
#include "import_hook.h"
#include "movement_native_image.h"
#include "movement_lifetime.h"
#include <intrin.h>
#include <strsafe.h>
#include <cstring>
#include <limits>
namespace wonderbane::extension::tracking {
namespace {
using Decode = void(__thiscall*)(void*, void*);
using Process = std::uint32_t(__thiscall*)(void*);
using Destroy = void*(__thiscall*)(void*, unsigned);
constexpr std::uintptr_t kTable = 0x1158bf8, kDecoderReturn = 0x3625bc;
constexpr std::array<std::uintptr_t, 3> kSlots{4, 0x14, 0x1c};
constexpr std::array<std::uintptr_t, 3> kTargets{0x21d64, 0x11c52, 0x7cd9};
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
std::array<Ticket, 16> tickets{};
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
    const auto address = reinterpret_cast<std::uintptr_t>(message);
    std::array<std::uint32_t, 4> header{}, again{};
    std::uint32_t table = 0;
    if (!Word(address, table) || table != image_base + kTable
        || !Read(address + 0x60, header.data(), sizeof(header)) || !header[0]) { return false; }
    const auto begin = header[1], end = header[2], capacity = header[3];
    if (begin || end || capacity) {
        if (begin < 0x10000 || begin % 4 || end < begin || capacity < end
            || capacity >= 0x80000000 || (end - begin) % 0x40
            || (capacity - begin) % 0x40 || (end - begin) / 0x40 > kRows) { return false; }
    }
    out.power_id = header[0]; out.row_count = (end - begin) / 0x40;
    for (std::uint32_t i = 0; i < out.row_count; ++i) {
        std::array<std::uint32_t, 16> source{}, check{};
        auto& row = out.rows[i];
        const auto at = begin + i * 0x40;
        if (!Read(at, source.data(), sizeof(source))) { return false; }
        row.object = {source[0], source[1]};
        if (!row.object[0] && !row.object[1]) { return false; }
        const auto text_begin = source[3], text_end = source[4], text_capacity = source[5];
        if (text_begin < 0x10000 || text_begin % 4 || text_end <= text_begin
            || text_capacity < text_end || text_capacity >= 0x80000000
            || text_end % 2 || text_capacity % 2 || text_end - text_begin > kNameUnits * 2) { return false; }
        row.name_units = (text_end - text_begin) / 2;
        row.flags = source[15] & 255;
        if (!Read(text_begin, row.name.data(), row.name_units * 2)) { return false; }
        for (std::uint32_t n = 0; n < row.name_units; ++n) {
            const auto unit = row.name[n];
            if (unit < 32 || (unit >= 0xdc00 && unit <= 0xdfff)) { return false; }
            if (unit >= 0xd800 && unit <= 0xdbff) {
                if (++n >= row.name_units || row.name[n] < 0xdc00 || row.name[n] > 0xdfff) { return false; }
            }
        }
        for (std::uint32_t j = 0; j < i; ++j) {
            if (out.rows[j].object == row.object) { return false; }
        }
        std::array<std::uint16_t, kNameUnits> name_check{};
        if (!Read(at, check.data(), sizeof(check)) || source != check
            || !Read(text_begin, name_check.data(), row.name_units * 2) || name_check != row.name) { return false; }
    }
    return Read(address + 0x60, again.data(), sizeof(again)) && again == header;
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
    if (record.stage == 2) { record.processing_generation = static_cast<std::uint64_t>(sequence); }
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
    if (!valid && storage) { InterlockedIncrement(&storage->rejected); }
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
        || storage->schema != 1 || storage->record_size != sizeof(Record)
        || storage->capacity != kCapacity || std::memcmp(storage->magic, "WBTRK1\0", 8)
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
    if (FAILED(StringCchPrintfW(name, 160, L"Local\\ShadowbaneLab.Extension.Tracking.v1.%lu.%llu",
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
        std::memcpy(storage->magic, "WBTRK1\0", 8);
        storage->schema = 1; storage->record_size = sizeof(Record); storage->capacity = kCapacity;
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
    if ((!GraphicsExecutableSha256Matches("a145ef491341e5107ec064de876d97f0e9c6ebbde2520d6509b4a3b47a7d825a")
        && !GraphicsExecutableSha256Matches("1a5a9fd59da8255a3c98e16e1e8ff9a415c0921b4189583158c559ad2594360c"))
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
