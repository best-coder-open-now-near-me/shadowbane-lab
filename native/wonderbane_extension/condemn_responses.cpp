#include "condemn_responses.h"
#include "graphics_status.h"
#include "import_hook.h"
#include "movement_native_image.h"
#include "movement_lifetime.h"
#include <intrin.h>
#include <strsafe.h>
#include <cstring>
#include <limits>
namespace wonderbane::extension::condemn {
namespace {
using Decode = void(__thiscall*)(void*, void*);
using Process = std::uint32_t(__thiscall*)(void*);
using Destroy = void*(__thiscall*)(void*, unsigned);
constexpr std::uintptr_t kTable = 0x114f198, kDecoderReturn = 0x3625bc;
constexpr std::array<std::uintptr_t, 3> kSlots{4, 0x14, 0x1c};
constexpr std::array<std::uintptr_t, 3> kTargets{0xa1aa, 0x23d49, 0x7ce3};
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
    const auto address = reinterpret_cast<std::uintptr_t>(message);
    std::uint32_t table = 0;
    if (!Word(address, table) || table != image_base + kTable
        || !Word(address + 0x80, out.operation) || out.operation < 11 || out.operation > 22
        || !Word(address + 0x60, out.status)
        || !Read(address + 0x88, out.entry.data(), 8)
        || !Read(address + 0xc0, out.building.data(), 8)) { return false; }
    out.fields = 1; // Context and state are serialized for operations 11..22.
    std::uint32_t state = 0;
    if (!Word(address + 0xc8, state) || !Word(address + 0xcc, out.reported_count)) { return false; }
    out.state = state & 255; out.inverted = (state >> 8) & 255;
    if (out.state > 1 || out.inverted > 1) { return false; }
    if (out.operation == 14 || out.operation == 16) {
        out.fields |= 2;
        if (!Word(address + 0x84, out.scope)
            || !Read(address + 0x90, out.character.data(), 8)
            || !Read(address + 0x98, out.nation.data(), 8)
            || !Read(address + 0xa0, out.guild.data(), 8)) { return false; }
    } else if (out.operation == 15) {
        out.fields |= 4;
        if (!Read(address + 0x90, out.character.data(), 8)
            || !Read(address + 0x98, out.nation.data(), 8)
            || !Read(address + 0xa0, out.guild.data(), 8)) { return false; }
    }
    std::uint32_t head = 0;
    std::array<std::uint32_t, 2> ends{};
    if (!Word(address + 0xd0, head) || !Read(head, ends.data(), 8)) { return false; }
    auto node = ends[0], previous = head;
    std::array<std::uint32_t, kRows> nodes{}, entries{}, objects{};
    while (node != head) {
        const auto i = out.row_count;
        if (i >= kRows) { return false; }
        std::array<std::uint32_t, 3> link{};
        std::uint32_t object = 0;
        if (!Read(node, link.data(), 12) || link[1] != previous || !Word(link[2], object)) { return false; }
        for (std::size_t j = 0; j < i; ++j) {
            if (nodes[j] == node || entries[j] == link[2] || (object && objects[j] == object)) { return false; }
        }
        nodes[i] = node; entries[i] = link[2]; objects[i] = object;
        auto& row = out.rows[i];
        // A row without a CoupEntry is a valid native no-op; preserve its empty row.
        if (object) {
            std::uint32_t flags = 0;
            if (!Word(object, row.kind) || !Read(object + 8, row.entry.data(), 8)
                || !Read(object + 0x30, row.character.data(), 8)
                || !Read(object + 0x38, row.guild.data(), 8)
                || !Read(object + 0x40, row.nation.data(), 8)
                || !Word(object + 0x48, flags)) { return false; }
            row.flags = flags & 0xffffff; // Exclude padding, which native code does not initialize.
        }
        ++out.row_count; previous = node; node = link[0];
    }
    return previous == ends[1];
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
        || storage->schema != 1 || storage->record_size != sizeof(Record)
        || storage->capacity != kCapacity || std::memcmp(storage->magic, "WBKOS1\0", 8)
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
    if (FAILED(StringCchPrintfW(name, 160, L"Local\\ShadowbaneLab.Extension.Condemn.v1.%lu.%llu",
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
        std::memcpy(storage->magic, "WBKOS1\0", 8);
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
    if (!GraphicsExecutableSha256Matches("e277e5a4e1e4e1df048a32c07bdbac6fec0591c7d01588b984577251cf475891")
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
