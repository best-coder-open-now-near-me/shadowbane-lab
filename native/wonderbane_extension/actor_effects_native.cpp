#include "actor_effects_native.h"
#include "graphics_status.h"
#include "movement_bootstrap_patches.h"
#include "movement_native_image.h"
#include <Windows.h>
#include <intrin.h>
#include <cstring>
#include <limits>

namespace wonderbane::extension::actor_effects {
static_assert(sizeof(void*) == 4, "Reviewed effect ABI is x86");
namespace {
std::uintptr_t base{};
SRWLOCK installation = SRWLOCK_INIT;
volatile LONG installed{}, poisoned{}, depth{};
alignas(8) volatile LONG64 epoch = 1;
bool attempted{};
PVOID handler{};
using NoArgs = std::uint32_t(__thiscall*)(void*);
using OneArg = std::uint32_t(__thiscall*)(void*, std::uint32_t);
using TwoArgs = std::uint32_t(__thiscall*)(void*, std::uint32_t, std::uint32_t);
NoArgs original_incoming{}, original_rebuild{};
OneArg original_add{}, original_equipment{};
TwoArgs original_remove{};

bool Copy(void* out, std::uintptr_t at, std::size_t size) noexcept {
    if (!at || size > 65536 || at > UINTPTR_MAX - size) { return false; }
    __try { std::memcpy(out, reinterpret_cast<const void*>(at), size); return true; }
    __except (EXCEPTION_EXECUTE_HANDLER) { return false; }
}
template<class T> bool Read(std::uintptr_t at, T& out) noexcept { return Copy(&out, at, sizeof(out)); }
bool Word(std::uintptr_t at, std::uint32_t expected) noexcept {
    std::uint32_t actual{}; return Read(at, actual) && actual == expected;
}
void Poison() noexcept { InterlockedExchange(&poisoned, 1); }
std::uint64_t Epoch() noexcept {
    const auto value = InterlockedCompareExchange64(&epoch, 0, 0);
    return value > 0 && value < MAXLONGLONG ? static_cast<std::uint64_t>(value) : 0;
}
void Advance() noexcept {
    auto prior = InterlockedCompareExchange64(&epoch, 0, 0);
    while (prior > 0 && prior < MAXLONGLONG) {
        const auto seen = InterlockedCompareExchange64(&epoch, prior + 1, prior);
        if (seen == prior) { if (prior + 1 == MAXLONGLONG) { Poison(); } return; }
        prior = seen;
    }
    Poison();
}
bool EnterMutation() noexcept {
    auto prior = InterlockedCompareExchange(&depth, 0, 0);
    while (prior >= 0 && prior < MAXLONG) {
        const auto seen = InterlockedCompareExchange(&depth, prior + 1, prior);
        if (seen == prior) { Advance(); return true; }
        prior = seen;
    }
    Poison(); return false;
}
void LeaveMutation(bool counted, bool abnormal) noexcept {
    const DWORD error = GetLastError();
    if (abnormal) { Poison(); }
    Advance();
    if (counted && InterlockedDecrement(&depth) < 0) { Poison(); }
    SetLastError(error);
}
// The exact native signatures return EAX and pop 0/4/8 stack bytes. These
// wrappers preserve that result and original exception; no native call is made
// by the observer itself except the intercepted original, exactly once.
std::uint32_t __fastcall AddHook(void* self, void*, std::uint32_t value) {
    const DWORD error = GetLastError(); const bool counted = EnterMutation();
    std::uint32_t result{}; SetLastError(error);
    __try { result = original_add(self, value); }
    __finally { LeaveMutation(counted, AbnormalTermination() != FALSE); }
    return result;
}
std::uint32_t __fastcall RemoveHook(void* self, void*, std::uint32_t a, std::uint32_t b) {
    const DWORD error = GetLastError(); const bool counted = EnterMutation();
    std::uint32_t result{}; SetLastError(error);
    __try { result = original_remove(self, a, b); }
    __finally { LeaveMutation(counted, AbnormalTermination() != FALSE); }
    return result;
}
std::uint32_t __fastcall IncomingHook(void* self, void*) {
    const DWORD error = GetLastError(); const bool counted = EnterMutation();
    std::uint32_t result{}; SetLastError(error);
    __try { result = original_incoming(self); }
    __finally { LeaveMutation(counted, AbnormalTermination() != FALSE); }
    return result;
}
std::uint32_t __fastcall RebuildHook(void* self, void*) {
    const DWORD error = GetLastError(); const bool counted = EnterMutation();
    std::uint32_t result{}; SetLastError(error);
    __try { result = original_rebuild(self); }
    __finally { LeaveMutation(counted, AbnormalTermination() != FALSE); }
    return result;
}
std::uint32_t __fastcall EquipmentHook(void* self, void*, std::uint32_t value) {
    const DWORD error = GetLastError(); const bool counted = EnterMutation();
    std::uint32_t result{}; SetLastError(error);
    __try { result = original_equipment(self, value); }
    __finally { LeaveMutation(counted, AbnormalTermination() != FALSE); }
    return result;
}
struct Site {
    std::uint32_t rva;
    std::array<std::uint8_t, 5> bytes;
    bool rebuild;
    bool owned = false, protection_pending = false, flush_pending = false;
};
std::array<Site, 9> sites{{
    {0x339674,{0xe8,0x80,0x47,0xce,0xff},true},
    {0x37c3c6,{0xe8,0x2e,0x1a,0xca,0xff},true},
    {0x49fbb2,{0xe8,0x42,0xe2,0xb7,0xff},true},
    {0x560ef,{0xe8,0xfc,0x12,0xfc,0xff},false},
    {0x570d3,{0xe8,0x18,0x03,0xfc,0xff},false},
    {0x6fe6f,{0xe8,0x7c,0x75,0xfa,0xff},false},
    {0x70898,{0xe8,0x53,0x6b,0xfa,0xff},false},
    {0xbaab5,{0xe8,0x36,0xc9,0xf5,0xff},false},
    {0x33972e,{0xe8,0xbd,0xdc,0xcd,0xff},false}
}};
struct Slot {
    std::uint32_t rva, original_rva;
    std::uintptr_t replacement;
    bool owned = false, protection_pending = false;
};
std::array<Slot, 3> slots{{
    {0x1141600,0x9d1d,reinterpret_cast<std::uintptr_t>(&AddHook)},
    {0x1141604,0x25b94,reinterpret_cast<std::uintptr_t>(&RemoveHook)},
    {0x11598b8,0x72ca,reinterpret_cast<std::uintptr_t>(&IncomingHook)}
}};
bool HooksCurrent() noexcept {
    if (!base) { return false; }
    for (const auto& site : sites) {
        auto expected = site.bytes; expected[0] = 0xcc;
        std::array<std::uint8_t, 5> actual{};
        if (!site.owned || site.protection_pending || site.flush_pending
            || !Read(base + site.rva, actual) || actual != expected) { return false; }
    }
    for (const auto& slot : slots) {
        if (!slot.owned || slot.protection_pending
            || !Word(base + slot.rva, static_cast<std::uint32_t>(slot.replacement))) { return false; }
    }
    return true;
}
LONG CALLBACK Trap(EXCEPTION_POINTERS* exception) noexcept {
    const DWORD error = GetLastError();
    if (!exception || !exception->ExceptionRecord || !exception->ContextRecord
        || exception->ExceptionRecord->ExceptionCode != EXCEPTION_BREAKPOINT) {
        SetLastError(error); return EXCEPTION_CONTINUE_SEARCH;
    }
    auto& context = *exception->ContextRecord;
    for (const auto& site : sites) {
        const auto address = base + site.rva;
        auto expected = site.bytes; expected[0] = 0xcc;
        std::array<std::uint8_t, 5> actual{};
        if (!base || !site.owned || reinterpret_cast<std::uintptr_t>(exception->ExceptionRecord->ExceptionAddress) != address
            || context.Eip != address || !Read(address, actual) || actual != expected) { continue; }
        __try { *reinterpret_cast<DWORD*>(context.Esp - sizeof(DWORD)) = static_cast<DWORD>(address + 5); }
        __except (EXCEPTION_EXECUTE_HANDLER) { Poison(); SetLastError(error); return EXCEPTION_CONTINUE_SEARCH; }
        context.Esp -= sizeof(DWORD);
        context.Eip = static_cast<DWORD>(site.rebuild
            ? reinterpret_cast<std::uintptr_t>(&RebuildHook) : reinterpret_cast<std::uintptr_t>(&EquipmentHook));
        SetLastError(error); return EXCEPTION_CONTINUE_EXECUTION;
    }
    SetLastError(error); return EXCEPTION_CONTINUE_SEARCH;
}
bool InstallSite(Site& site) noexcept {
    auto* at = reinterpret_cast<volatile CHAR*>(base + site.rva); DWORD prior{}, ignored{};
    if (!VirtualProtect(const_cast<CHAR*>(at), 1, PAGE_EXECUTE_READWRITE, &prior)) { return false; }
    site.protection_pending = true;
    site.owned = static_cast<unsigned char>(_InterlockedCompareExchange8(at, static_cast<CHAR>(0xcc), static_cast<CHAR>(0xe8))) == 0xe8;
    site.flush_pending = FlushInstructionCache(GetCurrentProcess(), const_cast<CHAR*>(at), 1) == FALSE;
    site.protection_pending = VirtualProtect(const_cast<CHAR*>(at), 1, prior, &ignored) == FALSE;
    return site.owned && !site.flush_pending && !site.protection_pending;
}
bool InstallSlot(Slot& slot) noexcept {
    auto* at = reinterpret_cast<void* volatile*>(base + slot.rva); DWORD prior{}, ignored{};
    if (!VirtualProtect(const_cast<void**>(at), sizeof(void*), PAGE_READWRITE, &prior)) { return false; }
    slot.protection_pending = true;
    slot.owned = InterlockedCompareExchangePointer(at, reinterpret_cast<void*>(slot.replacement),
        reinterpret_cast<void*>(base + slot.original_rva)) == reinterpret_cast<void*>(base + slot.original_rva);
    slot.protection_pending = VirtualProtect(const_cast<void**>(at), sizeof(void*), prior, &ignored) == FALSE;
    return slot.owned && !slot.protection_pending;
}
bool StartupCurrent(std::uintptr_t image, std::uintptr_t caller) noexcept {
    IMAGE_DOS_HEADER dos{}; IMAGE_NT_HEADERS32 nt{};
    std::array<unsigned char, 113> stub{};
    return image && image <= UINTPTR_MAX - 0x16c0000 && caller == image + 0x1140e9e
        && Read(image, dos) && dos.e_magic == IMAGE_DOS_SIGNATURE && dos.e_lfanew > 0 && dos.e_lfanew < 0x1000
        && Read(image + static_cast<std::uintptr_t>(dos.e_lfanew), nt) && nt.Signature == IMAGE_NT_SIGNATURE
        && nt.FileHeader.Machine == IMAGE_FILE_MACHINE_I386 && nt.OptionalHeader.Magic == IMAGE_NT_OPTIONAL_HDR32_MAGIC
        && nt.OptionalHeader.AddressOfEntryPoint == 0x8d8c4a
        && nt.OptionalHeader.NumberOfRvaAndSizes > IMAGE_DIRECTORY_ENTRY_TLS
        && nt.OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_TLS].VirtualAddress == 0
        && nt.OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_TLS].Size == 0
        && Read(image + 0x1140e70, stub) && stub == movement::bootstrap_replacement_6;
}
bool StartBound(std::uintptr_t image,
    bool (*install_site)(Site&) noexcept = InstallSite,
    bool (*install_slot)(Slot&) noexcept = InstallSlot) noexcept {
    AcquireSRWLockExclusive(&installation);
    if (attempted) { const bool same = base == image; ReleaseSRWLockExclusive(&installation); return same && Ready(); }
    attempted = true; base = image;
    original_add = reinterpret_cast<OneArg>(image + 0x9d1d);
    original_remove = reinterpret_cast<TwoArgs>(image + 0x25b94);
    original_incoming = reinterpret_cast<NoArgs>(image + 0x72ca);
    original_rebuild = reinterpret_cast<NoArgs>(image + 0x1ddf9);
    original_equipment = reinterpret_cast<OneArg>(image + 0x173f0);
    bool ok = image != 0;
    for (const auto& site : sites) {
        std::array<std::uint8_t, 5> actual{};
        ok = ok && Read(image + site.rva, actual) && actual == site.bytes;
    }
    for (const auto& slot : slots) { ok = ok && Word(image + slot.rva, static_cast<std::uint32_t>(image + slot.original_rva)); }
    if (ok) { handler = AddVectoredExceptionHandler(1, Trap); ok = handler != nullptr; }
    for (auto& site : sites) { if (ok) { ok = install_site(site); } }
    for (auto& slot : slots) { if (ok) { ok = install_slot(slot); } }
    if (ok) { InterlockedExchange(&installed, 1); }
    else { Poison(); }
    // Even a failed installation retains every published wrapper and handler.
    // There is no unload/unhook operation while native code may call through.
    ReleaseSRWLockExclusive(&installation); return ok && Ready();
}
bool Identity(const Context& c) noexcept {
    Key key{};
    return c.image == base && c.actor && c.scene && c.actor_key[0] && c.actor_key[1] && c.current
        && c.current(c.owner) && Word(base + 0x16a2d98, static_cast<std::uint32_t>(c.actor))
        && Word(c.actor, static_cast<std::uint32_t>(base + 0x114165c))
        && Word(c.actor + 0x588, static_cast<std::uint32_t>(base + 0x11415fc))
        && Read(c.actor + 0x18, key) && key == c.actor_key;
}
std::uint32_t U32(const auto& bytes, std::size_t offset) noexcept {
    std::uint32_t value{}; std::memcpy(&value, bytes.data() + offset, sizeof(value)); return value;
}
bool Classify(std::uint32_t table, ActionClass& kind) noexcept {
    constexpr std::array<std::uint32_t, 7> tables{0x1148b48,0x1148b84,0x114853c,0x1148bc0,0x1148c38,0x1148cb0,0x114dfa0};
    for (std::size_t i = 0; i < tables.size(); ++i) {
        if (table == base + tables[i]) { kind = static_cast<ActionClass>(i); return true; }
    }
    return false;
}
struct Vector { std::uint32_t begin{}, end{}, capacity{}; bool operator==(const Vector&) const = default; };
using Pair = std::array<std::uint32_t, 2>;
Unknown CopyEffects(const Context& c, Snapshot& result) noexcept {
    Vector vector{};
    if (!Read(c.actor + 0x58c, vector)) { return Unknown::read_fault; }
    if (vector.begin > vector.end || vector.end > vector.capacity || (vector.begin & 3)
        || (vector.end - vector.begin) % 8 || (vector.capacity - vector.begin) % 8
        || (vector.capacity - vector.begin) / 8 > kMaxEffects
        || (!vector.begin && (vector.end || vector.capacity))) { return Unknown::geometry; }
    const auto count = (vector.end - vector.begin) / 8;
    std::array<Pair, kMaxEffects> pairs{}, again{};
    if (count && !Copy(pairs.data(), vector.begin, count * sizeof(Pair))) { return Unknown::read_fault; }
    for (std::uint32_t i = 0; i < count; ++i) {
        const auto [id, address] = pairs[i];
        if (!id || !address || (address & 3)) { return Unknown::geometry; }
        for (std::uint32_t j = 0; j < i; ++j) { if (pairs[j][1] == address) { return Unknown::geometry; } }
        std::array<std::uint8_t, 0x78> record{}, record_again{};
        std::array<std::uint8_t, 0x60> descriptor{}, descriptor_again{};
        std::array<std::uint8_t, 0x20> action{}, action_again{};
        if (!Read(address, record)) { return Unknown::read_fault; }
        const auto definition = U32(record, 0), action_address = U32(record, 0x68);
        if (!Read(definition, descriptor) || !Read(action_address, action)) { return Unknown::read_fault; }
        auto& out = result.effects[i];
        if (U32(descriptor, 0) != base + 0x1147930 || U32(descriptor, 0x14) != id
            || U32(record, 0x14) != definition + 0x5c || !Classify(U32(action, 0), out.action_class)
            || U32(record, 0x24) > 2 || record[0x28] > 1) { return Unknown::unsupported; }
        out.descriptor_id = id; out.action_id = U32(action, 0x1c);
        out.rank = U32(record, 0x10); out.native_class = U32(record, 0x24); out.source_tag = record[0x28];
        out.source_words = {U32(record, 0x30), U32(record, 0x34), U32(record, 0x38)};
        out.local_add_suppression = descriptor[0x4c];
        if (!out.action_id || !Read(address, record_again) || !Read(definition, descriptor_again)
            || !Read(action_address, action_again)) { return Unknown::read_fault; }
        if (record != record_again || descriptor != descriptor_again || action != action_again) { return Unknown::changed; }
    }
    Vector final_vector{};
    if (!Read(c.actor + 0x58c, final_vector)
        || (count && !Copy(again.data(), vector.begin, count * sizeof(Pair)))) { return Unknown::read_fault; }
    if (vector != final_vector || pairs != again) { return Unknown::changed; }
    result.count = count; return Unknown::none;
}
}
bool Ready() noexcept {
    return InterlockedCompareExchange(&installed, 0, 0) != 0
        && InterlockedCompareExchange(&poisoned, 0, 0) == 0 && Epoch() != 0 && HooksCurrent();
}
bool StartAtBootstrap(std::uintptr_t image, std::uintptr_t caller) noexcept {
    const DWORD error = GetLastError(); std::uintptr_t verified{}; HMODULE pinned{};
    const bool ok = StartupCurrent(image, caller)
        && (GraphicsExecutableSha256Matches("0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d") || (GraphicsExecutableSha256Matches("78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903") || GraphicsExecutableSha256Matches("e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437")))
        && movement::VerifyNativeMovementImage(verified) && verified == image
        && GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
            reinterpret_cast<LPCWSTR>(&StartAtBootstrap), &pinned)
        && StartBound(image);
    SetLastError(error); return ok;
}
Unknown Capture(const Context& c, Snapshot& out) noexcept {
    const DWORD error = GetLastError(); out = {};
    const auto before = Epoch();
    Unknown reason = !Ready() ? Unknown::unavailable
        : !before ? Unknown::exhausted
        : InterlockedCompareExchange(&depth, 0, 0) != 0 ? Unknown::mutation_active
        : !Identity(c) ? Unknown::identity : Unknown::none;
    if (reason == Unknown::none) { reason = CopyEffects(c, out); }
    if (reason == Unknown::none && !Identity(c)) { reason = Unknown::identity; }
    if (reason == Unknown::none && (!Ready() || Epoch() != before
        || InterlockedCompareExchange(&depth, 0, 0) != 0)) { reason = Unknown::changed; }
    if (reason != Unknown::none) { out = {}; }
    else {
        out.actor_key = c.actor_key; out.scene = c.scene; out.epoch = before;
        out.image_identity_ = c.image; out.actor_identity_ = c.actor;
        out.owner_identity_ = c.owner; out.current_identity_ = c.current;
    }
    out.unknown = reason; SetLastError(error); return reason;
}
bool Revalidate(const Context& c, const Snapshot& snapshot) noexcept {
    const DWORD error = GetLastError();
    const bool ok = snapshot.Complete() && snapshot.count <= kMaxEffects && snapshot.scene == c.scene
        && snapshot.image_identity_ == c.image && snapshot.actor_identity_ == c.actor
        && snapshot.owner_identity_ == c.owner && snapshot.current_identity_ == c.current
        && snapshot.actor_key == c.actor_key && Ready() && Epoch() == snapshot.epoch
        && InterlockedCompareExchange(&depth, 0, 0) == 0 && Identity(c)
        && Ready() && Epoch() == snapshot.epoch && InterlockedCompareExchange(&depth, 0, 0) == 0;
    SetLastError(error); return ok;
}
bool NormalizeOwnedCode(std::uintptr_t image, std::uint32_t rva,
    std::span<std::uint8_t> code, std::span<const std::uint8_t> disk) noexcept {
    AcquireSRWLockShared(&installation);
    bool ok = code.size() == disk.size();
    for (const auto& site : sites) {
        if (!site.owned) { continue; }
        if (!ok || image != base || site.protection_pending || site.flush_pending || site.rva < rva
            || code.size() < site.bytes.size() || site.rva - rva > code.size() - site.bytes.size()) { ok = false; break; }
        const auto offset = site.rva - rva;
        auto expected = site.bytes; expected[0] = 0xcc;
        if (std::memcmp(disk.data() + offset, site.bytes.data(), 5)
            || std::memcmp(code.data() + offset, expected.data(), 5)) { ok = false; break; }
        code[offset] = site.bytes[0];
    }
    ReleaseSRWLockShared(&installation); return ok;
}
}
