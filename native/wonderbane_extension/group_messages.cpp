#include "group_messages.h"
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
namespace wonderbane::extension::group_messages {
namespace {
using Decode = void(__thiscall*)(void*, void*);
using Process = std::uint32_t(__thiscall*)(void*);
using Destroy = void*(__thiscall*)(void*, unsigned);
constexpr std::uintptr_t kTable = 0x115dbc4, kDecoderReturn = 0x3625bc;
constexpr std::array<std::uintptr_t, 3> kSlots{4, 0x14, 0x1c};
constexpr std::array<std::uintptr_t, 3> kTargets{0xfcbd, 0x10523, 0xac5e};
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
    Key decoded_sender{};
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
template<std::size_t N> bool Text(std::uintptr_t at, std::array<std::uint16_t,N>& out, std::uint32_t& units) noexcept {
    std::array<std::uint32_t,6> data{},again{};
    if(!Read(at,data.data(),sizeof(data))) return false;
    const auto begin=data[1],end=data[2],capacity=data[3];
    if(begin<0x10000||begin%4||end<begin||capacity<end||capacity>=0x80000000||end%2||capacity%2||end-begin>N*2) return false;
    units=(end-begin)/2;
    if(units&&!Read(begin,out.data(),units*2)) return false;
    for(std::uint32_t i=0;i<units;++i){
        auto c=out[i];if(c<32||(c>=0xdc00&&c<=0xdfff))return false;
        if(c>=0xd800&&c<=0xdbff){if(++i>=units||out[i]<0xdc00||out[i]>0xdfff)return false;}
    }
    std::array<std::uint16_t,N> copy{};
    return Read(at,again.data(),sizeof(again))&&again==data
        &&(!units||Read(begin,copy.data(),units*2))&&copy==out;
}
// GroupChannelMessage: common decoder owns key/status/body; its group decoder
// adds sender name. ArcChannelMessage is a different, legacy message class.
bool Snapshot(void* message,Payload& out,Key* decoded_sender=nullptr) noexcept {
    out={};const auto at=reinterpret_cast<std::uintptr_t>(message);
    std::uint32_t table=0,status=0;Key key{};
    if(!Word(at,table)||table!=image_base+kTable
        ||!Word(at+0x84,out.channel)||out.channel!=14
        ||!Word(at+0x68,status)||status!=0
        ||!Read(at+0x60,key.data(),sizeof(key))||!key[0]||!key[1]
        ||!Text(at+0x90,out.sender,out.sender_units)||!out.sender_units
        ||!Text(at+0x6c,out.text,out.text_units)||!out.text_units)return false;
    if(decoded_sender)*decoded_sender=key;
    return true;
}
bool Relevant(void* message) noexcept {
    const auto at=reinterpret_cast<std::uintptr_t>(message);std::uint32_t table=0,channel=0;
    return Word(at,table)&&table==image_base+kTable&&Word(at+0x84,channel)&&channel==14;
}
bool GroupWords(const combat::party::Snapshot& group,std::array<std::uint32_t,55>& words) noexcept {
    if(!group.valid||!group.count)return false;
    words={0x315047U,static_cast<std::uint32_t>(group.scene.window),static_cast<std::uint32_t>(group.manager),static_cast<std::uint32_t>(group.sentinel),static_cast<std::uint32_t>(group.count)};
    for(std::size_t i=0;i<group.count;++i){const auto& m=group.members[i];const auto at=5+5*i;
        words[at]=static_cast<std::uint32_t>(m.node);words[at+1]=static_cast<std::uint32_t>(m.entry);
        words[at+2]=m.key[0];words[at+3]=m.key[1];words[at+4]=m.role;
    }
    return true;
}
bool Qualify(Record& record,const movement::NativeScene& scene,const Key& decoded_sender) noexcept {
    combat::party::Snapshot group{},again{};
    if(!combat::party::Capture(image_base,scene,group))return false;
    Key key{};unsigned matches=0;
    for(std::size_t i=0;i<group.count;++i){
        std::array<std::uint16_t,kNameUnits> name{};std::uint32_t units=0;
        if(!Text(group.members[i].entry+0x28,name,units))return false;
        if(units&&CompareStringOrdinal(reinterpret_cast<const wchar_t*>(name.data()),static_cast<int>(units),
            reinterpret_cast<const wchar_t*>(record.payload.sender.data()),static_cast<int>(record.payload.sender_units),TRUE)==CSTR_EQUAL){key=group.members[i].key;++matches;}
    }
    if(matches!=1||key!=decoded_sender||!combat::party::Capture(image_base,scene,again)||!combat::party::Equal(group,again))return false;
    record.payload.sender_key=key;return GroupWords(group,record.payload.group);
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
    Key decoded_sender{};
    const bool valid = Snapshot(message, record.payload, &decoded_sender);
    if (valid) { record.flags |= kPayload; } else { record.payload = {}; }
    Stamp(record, scene);
    AcquireSRWLockExclusive(&lock);
    if (storage) {
        if (!valid) { InterlockedIncrement(&storage->rejected); }
        const auto sequence = PublishLocked(record);
        if (valid && sequence && (record.flags & kScene)) {
            auto& ticket = tickets[next_ticket++ % tickets.size()];
            if (ticket.message) { InterlockedIncrement64(&storage->ticket_drops); }
            ticket.message = message; ticket.sequence = sequence; ticket.scene = scene; ticket.payload = record.payload; ticket.decoded_sender = decoded_sender;
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
    Key decoded_sender{};
    const bool valid = Snapshot(message, record.payload, &decoded_sender);
    if (valid) { record.flags |= kPayload; } else { record.payload = {}; }
    Stamp(record, scene);
    AcquireSRWLockExclusive(&lock);
    for (auto& ticket : tickets) {
        if (ticket.message != message) { continue; }
        ticket.message = nullptr;
        if (valid && (record.flags & kScene) && ticket.scene.epoch == scene.epoch
            && movement::NativeMovementLifetimeCurrent(ticket.scene)
            && ticket.decoded_sender == decoded_sender
            && !std::memcmp(&ticket.payload, &record.payload, sizeof(Payload))) {
            record.flags |= kLineage; record.decode_sequence = ticket.sequence;
        }
    }
    if (!valid && storage) { InterlockedIncrement(&storage->rejected); }
    if ((record.flags & 7) == 7 && Qualify(record, scene, decoded_sender)) { record.flags |= 8; }
    (void)PublishLocked(record);
    ReleaseSRWLockExclusive(&lock);
    SetLastError(incoming_error);
    const auto result = process_original(message);
    const DWORD native_error = GetLastError();
    record.stage = 3;
    if(record.flags&8){Record check=record;check.payload.group={};check.payload.sender_key={};
        if(!Qualify(check,scene,decoded_sender)||check.payload.group!=record.payload.group||check.payload.sender_key!=record.payload.sender_key){
            record.flags&=~8U;record.payload.group={};record.payload.sender_key={};
        }
    }
    if (!movement::NativeMovementLifetimeCurrent(scene)) {
        record.flags &= ~(kScene | kLineage | 8U);
        record.payload.group = {}; record.payload.sender_key = {}; record.scene_epoch = 0; record.local = {};
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
    if (FAILED(StringCchPrintfW(name, 160, L"Local\\ShadowbaneLab.Extension.GroupMessages.v1.%lu.%llu",
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
        std::memcpy(storage->magic, "WBGRP1\0", 8);
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
