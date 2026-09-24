#include "furniture_responses.h"
#include "graphics_status.h"
#include "import_hook.h"
#include "movement_native_image.h"
#include "movement_lifetime.h"
#include <intrin.h>
#include <strsafe.h>
#include <cstring>
#include <cmath>
#include <limits>
namespace wonderbane::extension::furniture {
namespace {
using Decode = void(__thiscall*)(void*, void*);
using Serialize = void(__thiscall*)(void*, void*);
using Process = std::uint32_t(__thiscall*)(void*);
using Destroy = void*(__thiscall*)(void*, unsigned);
constexpr std::uintptr_t kTable = 0x115be38, kDecoderReturn = 0x3625bc, kSerializerReturn = 0x362919;
constexpr std::uintptr_t kFurnitureInfo = 0x117b364;
constexpr std::array<std::uintptr_t, 4> kSlots{4, 0x14, 0x1c, 0x20};
constexpr std::array<std::uintptr_t, 4> kTargets{0x1fcb7, 0xeb4c, 0x27791, 0x1942a};
constexpr unsigned kPayload = 1, kScene = 2, kLineage = 4;
SRWLOCK lock = SRWLOCK_INIT;
Decode decode_original = nullptr;
Serialize serialize_original = nullptr;
Process process_original = nullptr;
Destroy destroy_original = nullptr;
std::array<std::uint32_t*, 4> installed_slots{};
std::array<std::uint32_t, 4> original_slots{};
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
enum class Capture { ignored, invalid, valid };
bool Byte(std::uintptr_t address, std::uint32_t& out) noexcept {
    unsigned char value = 0;
    if (address < 0x10000 || address >= 0x80000000
        || !Copy(&value, reinterpret_cast<void*>(address), 1)) { return false; }
    out = value; return true;
}
bool Vector(std::uintptr_t address, std::uint32_t stride,
    std::uint32_t& begin, std::uint32_t& count) noexcept {
    std::array<std::uint32_t, 3> bounds{};
    if (!Read(address, bounds.data(), sizeof(bounds))) { return false; }
    begin = bounds[0]; count = 0;
    if (!begin) { return !bounds[1] && !bounds[2]; }
    if (begin < 0x10000 || begin % 4 || bounds[1] < begin || bounds[2] < bounds[1]
        || bounds[2] >= 0x80000000 || (bounds[1] - begin) % stride
        || (bounds[2] - begin) % stride) { return false; }
    count = (bounds[1] - begin) / stride;
    return true;
}
bool Furniture(std::uint32_t object, Row& out) noexcept {
    std::uint32_t table = 0;
    return Word(object, table) && table == image_base + kFurnitureInfo
        && Read(object + 8, out.asset.data(), 8)
        && Read(object + 0x10, out.instance.data(), 8)
        && Read(object + 0x18, out.auxiliary.data(), 8)
        && Read(object + 0x20, out.position.data(), 12)
        && Read(object + 0x2c, &out.rotation, 4)
        && Read(object + 0x30, &out.floor, 4)
        && Word(object + 0x34, out.word34_raw) && Byte(object + 0x38, out.flag38_raw)
        && std::isfinite(out.position[0]) && std::isfinite(out.position[1])
        && std::isfinite(out.position[2]) && std::isfinite(out.rotation);
}
bool Rows(std::uintptr_t address, std::uint32_t& reported, std::uint32_t& count,
    std::array<Row, kRows>& rows) noexcept {
    std::uint32_t begin = 0;
    if (!Vector(address, 4, begin, reported)) { return false; }
    count = reported > kRows ? static_cast<std::uint32_t>(kRows) : reported;
    for (std::uint32_t i = 0; i < count; ++i) {
        std::uint32_t object = 0;
        if (!Word(begin + i * 4, object) || !Furniture(object, rows[i])) { return false; }
    }
    return true;
}
Capture SnapshotFields(void* message, Payload& out) noexcept {
    const auto address = reinterpret_cast<std::uintptr_t>(message);
    std::uint32_t table = 0;
    if (!Word(address, table) || table != image_base + kTable
        || !Word(address + 0x60, out.operation)) { return Capture::invalid; }
    // Other native operations are deliberately outside this diagnostic scope.
    // They must retain normal forwarding without manufacturing capture errors.
    if (out.operation != 2 && out.operation != 3) { return Capture::ignored; }
    if (!Read(address + 0x68, out.building.data(), 8)
        || !Read(address + 0x70, out.structure.data(), 8)) { return Capture::invalid; }
    out.fields = out.operation == 2 ? 3 : 5;
    if (out.operation == 2) {
        std::uint32_t begin = 0;
        if (!Byte(address + 0x94, out.refresh)
            || !Vector(address + 0xb0, 8, begin, out.reported_consumed)) { return Capture::invalid; }
        out.consumed_count = out.reported_consumed > kRows
            ? static_cast<std::uint32_t>(kRows) : out.reported_consumed;
        for (std::uint32_t i = 0; i < out.consumed_count; ++i) {
            if (!Read(begin + i * 8, out.consumed[i].data(), 8)) { return Capture::invalid; }
        }
        if (out.reported_consumed > kRows) { out.status |= 2; }
    } else {
        if (!Read(address + 0x78, out.deed.data(), 8)
            || !Read(address + 0x80, out.position.data(), 12)
            || !Read(address + 0x8c, &out.rotation, 4)
            || !Read(address + 0x90, &out.floor, 4)
            || !std::isfinite(out.position[0]) || !std::isfinite(out.position[1])
            || !std::isfinite(out.position[2]) || !std::isfinite(out.rotation)) { return Capture::invalid; }
    }
    if (!Rows(address + 0x98, out.reported_scene, out.scene_count, out.scene)
        || !Rows(address + 0xa4, out.reported_secondary, out.secondary_count, out.secondary)) {
        return Capture::invalid;
    }
    if (out.reported_scene > kRows) { out.status |= 1; }
    if (out.reported_secondary > kRows) { out.status |= 4; }
    return Capture::valid;
}
Capture Snapshot(void* message, Payload& out) noexcept {
    out = {};
    const auto result = SnapshotFields(message, out);
    if (result != Capture::valid) { out = {}; }
    return result;
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
    const auto captured = Snapshot(message, record.payload);
    if (captured == Capture::ignored) { SetLastError(native_error); return; }
    const bool valid = captured == Capture::valid;
    if (valid) { record.flags |= kPayload; } else { record.payload = {}; }
    Stamp(record, scene);
    AcquireSRWLockExclusive(&lock);
    if (storage) {
        if (!valid) { InterlockedIncrement(&storage->rejected); }
        const auto sequence = PublishLocked(record);
        if (valid && !record.payload.status && sequence && (record.flags & kScene)) {
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
    const auto captured = Snapshot(message, record.payload);
    const bool valid = captured == Capture::valid;
    if (valid) { record.flags |= kPayload; }
    Stamp(record, scene);
    AcquireSRWLockExclusive(&lock);
    for (auto& ticket : tickets) {
        if (ticket.message != message) { continue; }
        ticket.message = nullptr;
        if (valid && !record.payload.status && (record.flags & kScene)
            && ticket.scene.epoch == scene.epoch
            && movement::NativeMovementLifetimeCurrent(ticket.scene)
            && !std::memcmp(&ticket.payload, &record.payload, sizeof(Payload))) {
            record.flags |= kLineage; record.decode_sequence = ticket.sequence;
        }
    }
    if (captured != Capture::ignored) {
        if (!valid && storage) { InterlockedIncrement(&storage->rejected); }
        (void)PublishLocked(record);
    }
    ReleaseSRWLockExclusive(&lock);
    SetLastError(incoming_error);
    const auto result = process_original(message);
    const DWORD native_error = GetLastError();
    if (captured == Capture::ignored) { SetLastError(native_error); return result; }
    record.stage = 3;
    if (!movement::NativeMovementLifetimeCurrent(scene)) {
        record.flags &= ~(kScene | kLineage); record.scene_epoch = 0; record.local = {};
        record.decode_sequence = 0;
    }
    // The handler transfers/deletes furniture objects and clears the scene vector.
    // Retain the BEFORE-handler copy. Return never proves placement or acceptance.
    AcquireSRWLockExclusive(&lock); (void)PublishLocked(record); ReleaseSRWLockExclusive(&lock);
    SetLastError(native_error);
    return result;
}
void __fastcall SerializeHook(void* message, void*, void* stream) {
    const DWORD incoming_error = GetLastError();
    const auto caller = reinterpret_cast<std::uintptr_t>(_ReturnAddress());
    if (caller == image_base + kSerializerReturn) {
        Record record{}; record.stage = 4;
        record.caller_rva = static_cast<std::uint32_t>(kSerializerReturn);
        movement::NativeScene scene{};
        (void)movement::ReadNativeMovementLifetime(scene);
        const auto captured = Snapshot(message, record.payload);
        if (captured != Capture::ignored) {
            if (captured == Capture::valid) { record.flags |= kPayload; }
            Stamp(record, scene);
            AcquireSRWLockExclusive(&lock);
            ForgetLocked(message);
            if (captured == Capture::invalid && storage) { InterlockedIncrement(&storage->rejected); }
            (void)PublishLocked(record);
            ReleaseSRWLockExclusive(&lock);
        } else { Forget(message); }
    }
    SetLastError(incoming_error);
    serialize_original(message, stream); // Preserve ABI, native exceptions and last error.
}
void* __fastcall DestroyHook(void* message, void*, unsigned flags) {
    const DWORD incoming_error = GetLastError();
    Forget(message);
    SetLastError(incoming_error);
    return destroy_original(message, flags);
}
std::array<std::uint32_t, 4> Hooks() noexcept {
    return {reinterpret_cast<std::uint32_t>(&DestroyHook), reinterpret_cast<std::uint32_t>(&ProcessHook),
        reinterpret_cast<std::uint32_t>(&DecodeHook), reinterpret_cast<std::uint32_t>(&SerializeHook)};
}
bool CursorLocked(Cursor& out) noexcept {
    if (!storage || storage->stopped || storage->sequence < 0 || storage->rejected < 0
        || storage->ticket_drops < 0 || !storage->process_id || !storage->creation
        || storage->schema != 1 || storage->record_size != sizeof(Record)
        || storage->capacity != kCapacity || std::memcmp(storage->magic, "WBFURN1\0", 8)
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
    const std::array<std::uint32_t*, 4>& slots, const std::array<std::uint32_t, 4>& targets) noexcept {
    AcquireSRWLockExclusive(&lock);
    if (attempted) { ReleaseSRWLockExclusive(&lock); return ERROR_ALREADY_INITIALIZED; }
    attempted = true;
    DWORD result = ERROR_SUCCESS;
    wchar_t name[160]{};
    if (FAILED(StringCchPrintfW(name, 160, L"Local\\ShadowbaneLab.Extension.Furniture.v1.%lu.%llu",
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
        std::memcpy(storage->magic, "WBFURN1\0", 8);
        storage->schema = 1; storage->record_size = sizeof(Record); storage->capacity = kCapacity;
        storage->process_id = identity.process_id; storage->creation = identity.creation_filetime_utc;
        image_base = base; installed_slots = slots; original_slots = targets;
        destroy_original = reinterpret_cast<Destroy>(targets[0]);
        process_original = reinterpret_cast<Process>(targets[1]);
        decode_original = reinterpret_cast<Decode>(targets[2]);
        serialize_original = reinterpret_cast<Serialize>(targets[3]);
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
    if (!GraphicsExecutableSha256Matches("7f283cdbeb691d65ef3073d32e4ea7bc0cfcb31e1bb205e460573f23d0a7758f")
        || !movement::VerifyNativeMovementImage(base)) { return ERROR_NOT_SUPPORTED; }
    std::array<std::uint32_t*, 4> slots{};
    std::array<std::uint32_t, 4> targets{};
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
