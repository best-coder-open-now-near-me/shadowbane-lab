#include "group_updates.h"
#include "graphics_status.h"
#include "import_hook.h"
#include "movement_native_image.h"
#include "movement_lifetime.h"
#include "combat_party.h"
#include <intrin.h>
#include <strsafe.h>
#include <cstring>
#include <limits>
#include <cmath>
namespace wonderbane::extension::group_updates {
namespace {
using Decode = void(__thiscall*)(void*, void*);
using Process = std::uint32_t(__thiscall*)(void*);
using Destroy = void*(__thiscall*)(void*, unsigned);
constexpr std::uintptr_t kTable = 0x115130c, kDecoderReturn = 0x3625bc;
constexpr std::array<std::uintptr_t, 3> kSlots{4, 0x14, 0x1c};
constexpr std::array<std::uintptr_t, 3> kTargets{0x195f6, 0x15dde, 0xd63e};
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
bool Snapshot(void* message,Payload& out) noexcept {
    out={};const auto at=reinterpret_cast<std::uintptr_t>(message);
    std::uint32_t table=0,count=0,keys=0,positions=0,error=0,has_rows=0;
    if(!Word(at,table)||table!=image_base+kTable||!Word(at+0x68,out.kind)
       ||out.kind<1||out.kind>8||!Word(at+0xa8,error)||error) return false;
    // Only these native Process branches copy per-key XYZ into the roster.
    // Other group updates invalidate cached position provenance without inventing coordinates.
    if(out.kind!=1&&out.kind!=2&&out.kind!=5) return true;
    if(!Word(at+0x70,count)||count>kRows||!Word(at+0x74,has_rows)||(count&&!has_rows)||!Word(at+0x90,keys)||!Word(at+0x8c,positions))return false;
    out.row_count=count;
    for(std::uint32_t i=0;i<count;++i){auto& row=out.rows[i];
        if(!Read(keys+i*8,row.object.data(),8)||!row.object[0]||!row.object[1]
           ||!Read(positions+i*12,row.xyz.data(),12))return false;
        for(auto v:row.xyz)if(!std::isfinite(v))return false;
        for(std::uint32_t j=0;j<i;++j)if(out.rows[j].object==row.object)return false;
    }
    std::uint32_t check=0;
    if(!Word(at+0x70,check)||check!=count||!Word(at+0x90,check)||check!=keys||!Word(at+0x8c,check)||check!=positions)return false;
    for(std::uint32_t i=0;i<count;++i){Row checkrow{};
        if(!Read(keys+i*8,checkrow.object.data(),8)||!Read(positions+i*12,checkrow.xyz.data(),12)
           ||std::memcmp(&checkrow,&out.rows[i],sizeof(Row)))return false;
    }
    return Word(at+0x68,check)&&check==out.kind&&Word(at+0xa8,check)&&check==0;
}
bool Relevant(void*) noexcept {return true;}
bool GroupWords(const combat::party::Snapshot& group,std::array<std::uint32_t,55>& words) noexcept {
    if(!group.valid||!group.count)return false;
    words={0x315047U,static_cast<std::uint32_t>(group.scene.window),static_cast<std::uint32_t>(group.manager),static_cast<std::uint32_t>(group.sentinel),static_cast<std::uint32_t>(group.count)};
    for(std::size_t i=0;i<group.count;++i){const auto& m=group.members[i];const auto at=5+5*i;
        words[at]=static_cast<std::uint32_t>(m.node);words[at+1]=static_cast<std::uint32_t>(m.entry);
        words[at+2]=m.key[0];words[at+3]=m.key[1];words[at+4]=m.role;
    }
    return true;
}
bool Qualify(Record& record,const movement::NativeScene& scene) noexcept {
    combat::party::Snapshot group{},again{};
    if(!combat::party::Capture(image_base,scene,group))return false;
    for(std::uint32_t i=0;i<record.payload.row_count;++i){const auto& row=record.payload.rows[i];bool matched=false;
        for(std::size_t j=0;j<group.count;++j){if(group.members[j].key!=row.object)continue;
            std::array<float,3> actual{};
            if(!Read(group.members[j].entry+0x68,actual.data(),12)||actual!=row.xyz)return false;
            matched=true;break;
        }
        if(!matched)return false;
    }
    return combat::party::Capture(image_base,scene,again)&&combat::party::Equal(group,again)&&GroupWords(group,record.payload.group);
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
    if (!active || !ActiveSocket(socket) || !Relevant(message)) { SetLastError(native_error); return; }
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
    if (!Relevant(message)) { SetLastError(incoming_error); return process_original(message); }
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
    // ArcGroupUpdateMsg::Process checks this mode before applying its rows.
    // A watched scene can outlive that transition until the next owner update.
    std::uint32_t entry_mode = 0;
    const bool entered_world = Word(scene.window + 0x64, entry_mode) && entry_mode == 2;
    const auto result = process_original(message);
    const DWORD native_error = GetLastError();
    record.stage = 3;
    std::uint32_t returned_mode = 0;
    if ((record.flags & 7) == 7 && entered_world
        && Word(scene.window + 0x64, returned_mode) && returned_mode == 2
        && Qualify(record, scene)) { record.flags |= 8; }
    if (!movement::NativeMovementLifetimeCurrent(scene)) {
        record.flags &= ~(kScene | kLineage | 8U);
        record.payload.group = {}; record.scene_epoch = 0; record.local = {};
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
    if (FAILED(StringCchPrintfW(name, 160, L"Local\\ShadowbaneLab.Extension.GroupUpdates.v1.%lu.%llu",
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
        std::memcpy(storage->magic, "WBGUP1\0", 8);
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
    if ((!(GraphicsExecutableSha256Matches("a145ef491341e5107ec064de876d97f0e9c6ebbde2520d6509b4a3b47a7d825a") || GraphicsExecutableSha256Matches("051c55ebd0f25ff5fe9bd27b25efbe3cde0190d1dbf1c2a33eb9604996c69698"))
        && !(GraphicsExecutableSha256Matches("1a5a9fd59da8255a3c98e16e1e8ff9a415c0921b4189583158c559ad2594360c") || GraphicsExecutableSha256Matches("baa6c84e5f28aab01d516f12257354b42375d11e8e8e98930cfcf754aeec24e9")))
        || !movement::VerifyNativeMovementImage(base)) { return ERROR_NOT_SUPPORTED; }
    std::array<std::uint32_t*, 3> slots{};
    std::array<std::uint32_t, 3> targets{};
    for (std::size_t i = 0; i < slots.size(); ++i) {
        slots[i] = reinterpret_cast<std::uint32_t*>(base + kTable + kSlots[i]);
        targets[i] = static_cast<std::uint32_t>(base + kTargets[i]);
    }
    return StartBound(identity, base, slots, targets);
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
