#include "item_application_trace.h"
#include <sddl.h>
#include <vector>
#include <string>
#include "graphics_status.h"
#include "import_hook.h"
#include "movement_native_image.h"
#include "movement_lifetime.h"
#include <intrin.h>
#include <strsafe.h>
#include <cstring>
#include <limits>
namespace wonderbane::extension::item_trace {
namespace {
using Decode = void(__thiscall*)(void*, void*);
using Process = std::uint32_t(__thiscall*)(void*);
using Destroy = void*(__thiscall*)(void*, unsigned);
constexpr std::array<std::uintptr_t,2> kTables{0x1155680,0x1155fd8};
constexpr std::uintptr_t kDecoderReturn=0x3625bc;
constexpr std::array<std::uintptr_t, 3> kSlots{4, 0x14, 0x1c};
constexpr std::array<std::uintptr_t,6> kTargets{0x6cf3,0x293c0,0x7ca2,0xa5bf,0x1cc97,0x1c5d0};
constexpr unsigned kPayload = 1, kScene = 2, kLineage = 4;
SRWLOCK lock = SRWLOCK_INIT;
std::array<Decode,2> decode_original{};
std::array<Process,2> process_original{};
std::array<Destroy,2> destroy_original{};
std::array<std::uint32_t*, 6> installed_slots{};
std::array<std::uint32_t, 6> original_slots{};
std::uintptr_t image_base = 0;
HANDLE mapping = nullptr;
Storage* storage = nullptr;
bool attempted = false;
struct Ticket {
    void* message = nullptr; // Lookup only; never dereferenced after callback.
    std::uint64_t sequence = 0;
    movement::NativeScene scene{};
    std::array<std::uint32_t,11> payload{};
    unsigned kind{};
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
template<unsigned Kind> bool Snapshot(void* message,std::array<std::uint32_t,11>& out) noexcept {
    out={};const auto address=reinterpret_cast<std::uintptr_t>(message);std::uint32_t table{};
    if(!Word(address,table)||table!=image_base+kTables[Kind]){return false;}
    if constexpr(Kind==0){
        if(!Read(address+0x70,out.data(),16)){return false;}
        // Recipient key is serialized only for subtype 2. Other bytes are stale.
        return out[0]!=2 || Read(address+0x80,out.data()+4,8);
    }else{return Read(address+0x80,out.data(),44);}
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
template<unsigned Kind> void __fastcall DecodeHook(void* message, void*, void* socket) {
    const DWORD incoming_error = GetLastError();
    const auto caller = reinterpret_cast<std::uintptr_t>(_ReturnAddress());
    Forget(message); // Even a replay or failed decode must invalidate an earlier ticket.
    const bool active = caller == image_base + kDecoderReturn && ActiveSocket(socket);
    movement::NativeScene scene{};
    if (active) { (void)movement::ReadNativeMovementLifetime(scene); }
    SetLastError(incoming_error);
    decode_original[Kind](message, socket); // Preserve native exceptions and native call-through.
    const DWORD native_error = GetLastError();
    if (!active || !ActiveSocket(socket)) { SetLastError(native_error); return; }
    Record record{}; record.kind=Kind+1; record.stage = 1; record.caller_rva = static_cast<std::uint32_t>(kDecoderReturn);
    const bool valid = Snapshot<Kind>(message, record.payload);
    if (valid) { record.flags |= kPayload; } else { record.payload = {}; }
    Stamp(record, scene);
    AcquireSRWLockExclusive(&lock);
    if (storage) {
        if (!valid) { InterlockedIncrement(&storage->rejected); }
        const auto sequence = PublishLocked(record);
        if (valid && sequence && (record.flags & kScene)) {
            auto& ticket = tickets[next_ticket++ % tickets.size()];
            if (ticket.message) { InterlockedIncrement64(&storage->ticket_drops); }
            ticket.message = message; ticket.sequence = sequence; ticket.scene = scene; ticket.payload = record.payload; ticket.kind=Kind;
        }
    }
    ReleaseSRWLockExclusive(&lock);
    SetLastError(native_error);
}
template<unsigned Kind> std::uint32_t __fastcall ProcessHook(void* message, void*) {
    const DWORD incoming_error = GetLastError();
    const auto caller = reinterpret_cast<std::uintptr_t>(_ReturnAddress());
    Record record{}; record.kind=Kind+1; record.stage = 2;
    record.caller_rva = caller >= image_base && caller - image_base < 0x16b0000
        ? static_cast<std::uint32_t>(caller - image_base) : 0;
    movement::NativeScene scene{};
    (void)movement::ReadNativeMovementLifetime(scene);
    const bool valid = Snapshot<Kind>(message, record.payload);
    if (valid) { record.flags |= kPayload; } else { record.payload = {}; }
    Stamp(record, scene);
    AcquireSRWLockExclusive(&lock);
    for (auto& ticket : tickets) {
        if (ticket.message != message) { continue; }
        ticket.message = nullptr;
        if (valid && ticket.kind==Kind && (record.flags & kScene) && ticket.scene.epoch == scene.epoch
            && movement::NativeMovementLifetimeCurrent(ticket.scene)
            && !std::memcmp(&ticket.payload, &record.payload, sizeof(record.payload))) {
            record.flags |= kLineage; record.decode_sequence = ticket.sequence;
        }
    }
    (void)PublishLocked(record);
    ReleaseSRWLockExclusive(&lock);
    SetLastError(incoming_error);
    const auto result = process_original[Kind](message);
    const DWORD native_error = GetLastError();
    record.stage = 3; record.native_return=result;
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
template<unsigned Kind> void* __fastcall DestroyHook(void* message, void*, unsigned flags) {
    const DWORD incoming_error = GetLastError();
    Forget(message);
    SetLastError(incoming_error);
    return destroy_original[Kind](message, flags);
}
std::array<std::uint32_t,6> Hooks() noexcept {
    return {reinterpret_cast<std::uint32_t>(&DestroyHook<0>),reinterpret_cast<std::uint32_t>(&ProcessHook<0>),
        reinterpret_cast<std::uint32_t>(&DecodeHook<0>),reinterpret_cast<std::uint32_t>(&DestroyHook<1>),
        reinterpret_cast<std::uint32_t>(&ProcessHook<1>),reinterpret_cast<std::uint32_t>(&DecodeHook<1>)};
}
bool Security(PSECURITY_DESCRIPTOR& result){
    HANDLE token{};if(!OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token)){return false;}
    DWORD size{};GetTokenInformation(token,TokenUser,nullptr,0,&size);
    std::vector<std::uint8_t> bytes(size);const bool obtained=size&&GetTokenInformation(token,TokenUser,bytes.data(),size,&size);
    CloseHandle(token);if(!obtained){return false;}
    LPWSTR sid{};if(!ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER*>(bytes.data())->User.Sid,&sid)){return false;}
    const std::wstring sddl=L"D:P(A;;GR;;;"+std::wstring(sid)+L")";LocalFree(sid);
    return ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl.c_str(),SDDL_REVISION_1,&result,nullptr)!=FALSE;
}
void CloseLocked() noexcept {
    for (auto& ticket : tickets) { ticket.message = nullptr; }
    if (storage) { InterlockedExchange(&storage->stopped, 1); UnmapViewOfFile(storage); storage = nullptr; }
    if (mapping) { CloseHandle(mapping); mapping = nullptr; }
}
DWORD StartBound(const ProcessIdentity& identity, std::uintptr_t base,
    const std::array<std::uint32_t*, 6>& slots, const std::array<std::uint32_t, 6>& targets) noexcept {
    AcquireSRWLockExclusive(&lock);
    if (attempted) { ReleaseSRWLockExclusive(&lock); return ERROR_ALREADY_INITIALIZED; }
    attempted = true;
    DWORD result = ERROR_SUCCESS;
    wchar_t name[160]{};
    if (FAILED(StringCchPrintfW(name, 160, L"Local\\ShadowbaneLab.Extension.ItemApplication.v1.%lu.%llu",
        identity.process_id, identity.creation_filetime_utc))) { result = ERROR_INVALID_DATA; }
    if (!result) {
        PSECURITY_DESCRIPTOR descriptor{};
        try { if(!Security(descriptor)){result=ERROR_ACCESS_DENIED;} } catch(...){result=ERROR_NOT_ENOUGH_MEMORY;}
        SECURITY_ATTRIBUTES attributes{sizeof(SECURITY_ATTRIBUTES),descriptor,FALSE};
        if(!result){mapping = CreateFileMappingW(INVALID_HANDLE_VALUE, &attributes, PAGE_READWRITE, 0, sizeof(Storage), name);}
        const auto mapping_error=GetLastError();if(descriptor){LocalFree(descriptor);}SetLastError(mapping_error);
        if (!mapping && !result) { result = GetLastError(); }
        else if (GetLastError() == ERROR_ALREADY_EXISTS) { result = ERROR_ALREADY_EXISTS; }
    }
    if (!result) {
        storage = static_cast<Storage*>(MapViewOfFile(mapping, FILE_MAP_WRITE, 0, 0, sizeof(Storage)));
        if (!storage) { result = GetLastError(); }
    }
    if (!result) {
        std::memcpy(storage->magic, "WBITEM1\0", 8);
        storage->schema = 1; storage->record_size = sizeof(Record); storage->capacity = kCapacity;
        storage->process_id = identity.process_id; storage->creation = identity.creation_filetime_utc;
        image_base = base; installed_slots = slots; original_slots = targets;
        for(unsigned i=0;i<2;++i){
            destroy_original[i]=reinterpret_cast<Destroy>(targets[i*3]);
            process_original[i]=reinterpret_cast<Process>(targets[i*3+1]);
            decode_original[i]=reinterpret_cast<Decode>(targets[i*3+2]);
        }
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
    if(!GraphicsExecutableSha256Matches("78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903")
        || !movement::VerifyNativeMovementImage(base)){return ERROR_NOT_SUPPORTED;}
    std::array<std::uint32_t*, 6> slots{};
    std::array<std::uint32_t, 6> targets{};
    for (std::size_t i = 0; i < slots.size(); ++i) {
        slots[i] = reinterpret_cast<std::uint32_t*>(base + kTables[i/3] + kSlots[i%3]);
        targets[i] = static_cast<std::uint32_t>(base + kTargets[i]);
    }
    return StartBound(identity, base, slots, targets);
}
void OwnedReturn(const actor::wire::Command& command,const movement::NativeScene& scene,
    actor::wire::Outcome outcome,actor::wire::Entry entry,actor::wire::LocalSettlement settled,std::uint32_t history) noexcept {
    const auto error=GetLastError();
    if(command.action==actor::wire::Action::use_item){
        Record record{};record.stage=4;record.kind=1;
        if(actor::wire::HashCommand(command,record.command)){
            record.request=command.request;record.outcome=static_cast<std::uint32_t>(outcome);
            record.entry=static_cast<std::uint32_t>(entry);record.local_settlement=static_cast<std::uint32_t>(settled);
            record.history=history;record.payload[0]=2;record.payload[1]=1;
            record.payload[2]=command.item_key[0];record.payload[3]=command.item_key[1];
            record.flags=kPayload;Stamp(record,scene);
            AcquireSRWLockExclusive(&lock);(void)PublishLocked(record);ReleaseSRWLockExclusive(&lock);
        }
    }
    SetLastError(error);
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
