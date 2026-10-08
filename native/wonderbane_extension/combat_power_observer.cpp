#include "combat_power_observer.h"
#include "graphics_status.h"
#include "movement_native_image.h"
#include <Windows.h>
#include <intrin.h>
#include <cstring>
namespace wonderbane::extension::combat::power {
static_assert(sizeof(void*) == 4, "Reviewed power ABI is x86");
namespace {
using Send = void(__thiscall*)(void*, void*);
using Followup = void(__cdecl*)(void*, void*, void*, int);
std::uintptr_t base{};
Send original_send{};
Followup original_followup{};
thread_local Scope* active{};
thread_local bool native_use_in_flight{};
using OrdinaryUse = bool(__cdecl*)(std::uint32_t,int,void*,void*,const float*,Key);
bool __cdecl OrdinaryUseHook(std::uint32_t id,int rank,void* actor,void* target,const float* position,Key key) {
    const bool previous=native_use_in_flight;
    native_use_in_flight=true;
    bool result=false;
    // No synthetic native return address: this remains foreign, unscoped entry.
    // Preserve the original return/LastError and restore nesting even on SEH.
    __try { result=reinterpret_cast<OrdinaryUse>(base+0x1082a)(id,rank,actor,target,position,key); }
    __finally { native_use_in_flight=previous; }
    return result;
}
SRWLOCK install_lock = SRWLOCK_INIT;
volatile LONG installed{};
bool attempted{};
PVOID handler{};
struct Site {
    std::uint32_t rva;
    std::array<std::uint8_t, 5> bytes;
    bool owned = false, protection_pending = false, flush_pending = false;
    DWORD protection{};
};
// Original .13 native caller census: all ordinary Use callers, both followup
// callers, incoming init append and all four first-match remover calls. The
// epoch deliberately invalidates on unrelated actors too; it is not a response ID.
std::array<Site, 12> sites{{
    {0x9d3d4,{0xe8,0x8c,0x86,0xf6,0xff}},
    {0x9d3e0,{0xe8,0x74,0x92,0xf6,0xff}},
    {0x48191d,{0xe8,0x08,0xef,0xb8,0xff}},
    {0x4bcbc4,{0xe8,0x61,0x3c,0xb5,0xff}},
    {0x7d2708,{0xe8,0x1d,0xe1,0x83,0xff}},
    {0x7d286a,{0xe8,0xbb,0xdf,0x83,0xff}},
    {0x9c25d,{0xe8,0xf7,0xa3,0xf6,0xff}},
    {0x384451,{0xe8,0xf6,0x10,0xc8,0xff}},
    {0x37e8ca,{0xe8,0xe8,0xe7,0xc8,0xff}},
    {0x384617,{0xe8,0x9b,0x8a,0xc8,0xff}},
    {0x384f2b,{0xe8,0x87,0x81,0xc8,0xff}},
    {0x385761,{0xe8,0x51,0x79,0xc8,0xff}}
}};
alignas(8) volatile LONG64 initiation_epoch = 1;
std::uint64_t Epoch() noexcept {
    const auto value=InterlockedCompareExchange64(&initiation_epoch,0,0);
    return value>0 && value<MAXLONGLONG ? static_cast<std::uint64_t>(value) : 0;
}
void AdvanceEpoch() noexcept {
    auto prior=InterlockedCompareExchange64(&initiation_epoch,0,0);
    while(prior>0 && prior<MAXLONGLONG) {
        const auto observed=InterlockedCompareExchange64(&initiation_epoch,prior+1,prior);
        if(observed==prior) { return; }
        prior=observed;
    }
}

bool Copy(void* out, std::uintptr_t at, std::size_t size) noexcept {
    __try { std::memcpy(out, reinterpret_cast<const void*>(at), size); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
bool Word(std::uintptr_t at, std::uintptr_t expected) noexcept {
    std::uintptr_t value{}; return Copy(&value, at, sizeof(value)) && value == expected;
}
bool KeyAt(std::uintptr_t at, const Key& key) noexcept {
    Key value{}; return Copy(value.data(), at, sizeof(value)) && value == key;
}
bool AuthorityValid(const Context& c) noexcept {
    if (c.authority == Authority::actor) {
        return c.target_mode == TargetMode::self && !c.target && c.target_key == Key{}
            && c.actor_key[0] && c.actor_key[1] == 53;
    }
    return c.authority == Authority::engagement && c.target && c.target != c.actor
        && c.target_key[0] && (c.target_key[1] == 37 || c.target_key[1] == 53)
        && c.target_key != c.actor_key;
}
bool MatchesBinding(const Context& c) noexcept {
    return AuthorityValid(c) && c.image == base && Word(base + 0x16a2d98, c.actor)
        && Word(c.actor, base + 0x114165c) && KeyAt(c.actor + 0x18, c.actor_key)
        && (c.authority == Authority::actor || KeyAt(c.target + 0x18, c.target_key))
        && Word(base + 0x16ab88c, c.writer) && Word(c.writer, base + 0x116036c)
        && Word(c.writer + 0x44, c.container) && Word(c.container, base + 0x114ce9c);
}
void Consume(void* message) {
    if (!message || message == reinterpret_cast<void*>(static_cast<std::uintptr_t>(-1))) { return; }
    void* empty{};
    using Release = void(__thiscall*)(void*, void**);
    const auto table = *static_cast<std::uintptr_t*>(message);
    reinterpret_cast<Release>(*reinterpret_cast<std::uintptr_t*>(table + 8))(message, &empty);
}
bool SitesCurrent() noexcept {
    for (const auto& site : sites) {
        std::array<std::uint8_t,5> actual{};
        auto expected = site.bytes; expected[0] = 0xcc;
        if (!base || !Copy(actual.data(), base + site.rva, actual.size()) || actual != expected) { return false; }
    }
    return true;
}
}
namespace detail {
struct Observer {
    static bool OwnsFrame(std::uintptr_t frame) noexcept {
        auto* s = active;
        std::uintptr_t parent{}, caller{};
        return s && s->active_ && s->native_frame_ && s->native_return_
            && Copy(&parent, frame, sizeof(parent)) && parent == s->native_frame_
            && Copy(&caller, frame + 4, sizeof(caller)) && caller == base + 0x9bf09
            && Word(parent + 4, s->native_return_);
    }
    static void Publish(Scope& s) noexcept { if (s.context_.receipt) { *s.context_.receipt = s.receipt_; } }
    static void Block(Scope& s) noexcept {
        s.blocked_ = true;
        s.receipt_.result = s.receipt_.native_entered ? Result::uncertain : Result::denied;
        Publish(s);
    }
    static bool Ticket(const Scope& s, void* message) noexcept {
        const auto p = reinterpret_cast<std::uintptr_t>(message);
        return p && Word(p, base + 0x1155fd8) && Word(p + 0x80, s.context_.power_id)
            && Word(p + 0x84, s.rank_) && KeyAt(p + 0x88, s.context_.actor_key)
            && KeyAt(p + 0x90, s.context_.RecipientKey())
            && Word(p + 0x98, 0) && Word(p + 0x9c, 0) && Word(p + 0xa0, 0)
            && Word(p + 0xa4, 1);
    }
    static void __fastcall SendHook(void* sender, void*, void* message) {
        const DWORD error = GetLastError();
        auto* s = active;
        if (!s) { SetLastError(error); original_send(sender, message); return; }
        const bool allowed = s->active_ && !s->blocked_ && s->receipt_.native_entered
            && !s->send_seen_ && Ready() && sender == reinterpret_cast<void*>(base + 0x16ab888)
            && MatchesBinding(s->context_) && Ticket(*s, message) && s->context_.current(s->context_.owner);
        s->send_seen_ = true;
        s->receipt_.send_observed = true;
        s->ticket_ = reinterpret_cast<std::uintptr_t>(message);
        if (!allowed) { Block(*s); SetLastError(error); Consume(message); return; }
        s->receipt_.result = Result::uncertain; Publish(*s);
        SetLastError(error);
        try { original_send(sender, message); }
        catch (...) { Block(*s); throw; }
        const DWORD after = GetLastError();
        if (!s->receipt_.append_observed) { Block(*s); }
        SetLastError(after);
    }
    static void __cdecl FollowupHook(void* actor, void* target, void* definition, int rank) {
        const DWORD error = GetLastError();
        auto* s = active;
        if (!s) { SetLastError(error); original_followup(actor, target, definition, rank); return; }
        const bool allowed = s->active_ && !s->blocked_ && s->receipt_.append_observed
            && !s->receipt_.followup_entered && Ready()
            && actor == reinterpret_cast<void*>(s->context_.actor)
            && target == reinterpret_cast<void*>(s->context_.Recipient())
            && definition == reinterpret_cast<void*>(s->definition_)
            && rank > 0 && static_cast<std::uint32_t>(rank) == s->rank_
            && MatchesBinding(s->context_) && s->context_.current(s->context_.owner);
        if (!allowed) { Block(*s); SetLastError(error); return; }
        s->receipt_.followup_entered = true; s->receipt_.result = Result::uncertain; Publish(*s);
        const auto epoch=Epoch();
        SetLastError(error);
        try { original_followup(actor, target, definition, rank); }
        catch (...) { Block(*s); throw; }
        const DWORD after = GetLastError();
        if (!Ready() || !MatchesBinding(s->context_) || !s->context_.current(s->context_.owner)) { Block(*s); }
        else {
            s->receipt_.result = Result::queued;
            s->receipt_.initiation_epoch=epoch && s->preparation_epoch_
                && epoch==s->preparation_epoch_+1 && Epoch()==epoch ? epoch : 0;
            Publish(*s);
        }
        SetLastError(after);
    }
    static submission::AppendClaim Claim(void* container, void* message, std::uintptr_t caller) noexcept {
        // Search live ancestors so reentrant native work cannot hide a captured
        // ticket behind a nested scope. Completion receives this exact owner.
        for (auto* s = active; s; s = s->previous_) {
            if (!s->ticket_ || s->ticket_ != reinterpret_cast<std::uintptr_t>(message)) { continue; }
            const bool allowed = s == active && s->active_ && !s->blocked_ && !s->append_seen_
                && caller == 0x2c6eb7 && container == reinterpret_cast<void*>(s->context_.container)
                && Ready() && MatchesBinding(s->context_) && Ticket(*s, message)
                && s->context_.append_current(s->context_.owner);
            s->append_seen_ = true;
            if (!allowed) { Block(*s); }
            else { s->receipt_.result = Result::uncertain; Publish(*s); }
            return {allowed ? submission::AppendDecision::allow : submission::AppendDecision::deny, s};
        }
        return {};
    }
    static void Complete(void* owner, submission::AppendResult result) noexcept {
        auto& s = *static_cast<Scope*>(owner);
        if (result != submission::AppendResult::queued) { Block(s); return; }
        s.receipt_.append_observed = true; Publish(s);
        if (!s.blocked_ && Ready() && MatchesBinding(s.context_) && s.context_.append_current(s.context_.owner)) {
            s.receipt_.result = Result::queued; Publish(s);
        } else { Block(s); }
    }
};
}
namespace {
LONG CALLBACK Trap(EXCEPTION_POINTERS* exception) noexcept {
    const DWORD error = GetLastError();
    if (!exception || !exception->ExceptionRecord || !exception->ContextRecord
        || exception->ExceptionRecord->ExceptionCode != EXCEPTION_BREAKPOINT) {
        SetLastError(error); return EXCEPTION_CONTINUE_SEARCH;
    }
    auto& context = *exception->ContextRecord;
    for (std::size_t i = 0; i < sites.size(); ++i) {
        const auto& site = sites[i];
        const auto address = base + site.rva;
        std::array<std::uint8_t,5> actual{};
        auto expected = site.bytes; expected[0] = 0xcc;
        if (!base || reinterpret_cast<std::uintptr_t>(exception->ExceptionRecord->ExceptionAddress) != address
            || context.Eip != address || !Copy(actual.data(), address, actual.size()) || actual != expected) { continue; }
        // Emulate only the original near CALL. Preserve every other register and
        // flag. Handler lifetime and native call-throughs are process-pinned.
        __try { *reinterpret_cast<DWORD*>(context.Esp - sizeof(DWORD)) = static_cast<DWORD>(address + 5); }
        __except(EXCEPTION_EXECUTE_HANDLER) { SetLastError(error); return EXCEPTION_CONTINUE_SEARCH; }
        context.Esp -= sizeof(DWORD);
        if(i != 0) { AdvanceEpoch(); }
        if(i >= 2) {
            std::int32_t displacement{}; std::memcpy(&displacement,site.bytes.data()+1,4);
            context.Eip=static_cast<DWORD>(i>=2 && i<=5
                ? reinterpret_cast<std::uintptr_t>(&OrdinaryUseHook) : address+5+displacement);
            SetLastError(error); return EXCEPTION_CONTINUE_EXECUTION;
        }
        if (!detail::Observer::OwnsFrame(context.Ebp)) {
            context.Eip = static_cast<DWORD>(i == 0
                ? reinterpret_cast<std::uintptr_t>(original_send)
                : reinterpret_cast<std::uintptr_t>(original_followup));
            SetLastError(error); return EXCEPTION_CONTINUE_EXECUTION;
        }
        context.Eip = static_cast<DWORD>(i == 0
            ? reinterpret_cast<std::uintptr_t>(&detail::Observer::SendHook)
            : reinterpret_cast<std::uintptr_t>(&detail::Observer::FollowupHook));
        SetLastError(error); return EXCEPTION_CONTINUE_EXECUTION;
    }
    SetLastError(error); return EXCEPTION_CONTINUE_SEARCH;
}
bool InstallByte(Site& site) noexcept {
    auto* at = reinterpret_cast<volatile CHAR*>(base + site.rva);
    DWORD prior{};
    if (!VirtualProtect(const_cast<CHAR*>(at), 1, PAGE_EXECUTE_READWRITE, &prior)) { return false; }
    site.protection = prior; site.protection_pending = true;
    const auto replaced = _InterlockedCompareExchange8(at, static_cast<CHAR>(0xcc), static_cast<CHAR>(0xe8));
    site.owned = static_cast<unsigned char>(replaced) == 0xe8;
    site.flush_pending = FlushInstructionCache(GetCurrentProcess(), const_cast<CHAR*>(at), 1) == FALSE;
    DWORD ignored{};
    site.protection_pending = VirtualProtect(const_cast<CHAR*>(at), 1, prior, &ignored) == FALSE;
    // Never remove the pinned handler on a partial installation: an owned INT3
    // can already be executing on another thread. Readiness remains false.
    return site.owned && !site.flush_pending && !site.protection_pending;
}
bool StartBound(std::uintptr_t image, Send send, Followup followup,
    bool (*install)(Site&) noexcept = InstallByte) noexcept {
    AcquireSRWLockExclusive(&install_lock);
    if (attempted) { const bool same = base == image; ReleaseSRWLockExclusive(&install_lock); return same && Ready(); }
    attempted = true; base = image; original_send = send; original_followup = followup;
    bool ok = image && send && followup;
    for (const auto& site : sites) {
        std::array<std::uint8_t,5> bytes{};
        ok = ok && Copy(bytes.data(), base + site.rva, bytes.size()) && bytes == site.bytes;
    }
    if (ok) { handler = AddVectoredExceptionHandler(1, Trap); ok = handler != nullptr; }
    if (ok) { ok = submission::RegisterAppendObserver(submission::AppendObserverKind::power, {detail::Observer::Claim, detail::Observer::Complete}); }
    for (auto& site : sites) { if (ok) { ok = install(site); } }
    if (ok) { InterlockedExchange(&installed, 1); }
    ReleaseSRWLockExclusive(&install_lock); return ok && Ready();
}
}
Scope::Scope(const Context& c) noexcept : context_(c), previous_(active) {
    const DWORD error = GetLastError(); active = this; active_ = true;
    if (!Ready() || c.image != base || !c.actor || !AuthorityValid(c) || !c.writer || !c.container
        || !c.power_id || !c.current || !c.append_current || !c.receipt
        || (c.target_mode != TargetMode::engagement_object && c.target_mode != TargetMode::self)) { detail::Observer::Block(*this); }
    else { detail::Observer::Publish(*this); }
    SetLastError(error);
}
Scope::~Scope() { (void)Finish(); }
void Scope::PublishObservation() noexcept { detail::Observer::Publish(*this); }
bool Scope::CanEnter() const noexcept {
    return !receipt_.native_entered && Current();
}
bool Scope::Current() const noexcept {
    return active == this && active_ && !blocked_
        && Ready() && MatchesBinding(context_) && context_.current(context_.owner);
}
bool Scope::AdmitAvailability(Availability value, std::uint64_t epoch) noexcept {
    if (!epoch || !CanEnter() || Epoch()!=epoch) { return false; }
    receipt_.availability = value; receipt_.availability_epoch=epoch;
    detail::Observer::Publish(*this);
    return value == Availability::ready;
}
bool Scope::Enter(std::uintptr_t definition, std::uint32_t rank) noexcept {
    if (!definition || !rank || rank > 9999 || !CanEnter()) { detail::Observer::Block(*this); return false; }
    AdvanceEpoch(); // The extension bridge bypasses the four ordinary UI callers.
    preparation_epoch_=Epoch();
    definition_ = definition; rank_ = rank;
    receipt_.native_entered = true; receipt_.result = Result::uncertain;
    detail::Observer::Publish(*this); return true;
}
Receipt Scope::Finish() noexcept {
    if (active_) {
        if(!receipt_.native_entered && (!receipt_.availability_epoch || !Current()
            || Epoch()!=receipt_.availability_epoch)) {
            receipt_.availability=Availability::unknown; receipt_.availability_epoch=0;
        }
        if (active == this) { active = previous_; }
        else {
            for (auto* child = active; child; child = child->previous_) {
                detail::Observer::Block(*child);
                if (child->previous_ == this) { child->previous_ = previous_; break; }
            }
        }
        native_frame_ = 0; native_return_ = 0;
        active_ = false;
        if (receipt_.native_entered && (!Ready() || !receipt_.append_observed || !receipt_.followup_entered)) {
            detail::Observer::Block(*this);
        }
    }
    detail::Observer::Publish(*this); return receipt_;
}
Boundary::Boundary() noexcept : previous_(active) {}
void Boundary::Restore() noexcept { active = previous_; }
bool NativeUseInFlight() noexcept { return native_use_in_flight; }
std::uint64_t InitiationEpoch() noexcept { return Ready() ? Epoch() : 0; }
bool Ready() noexcept { return InterlockedCompareExchange(&installed, 0, 0) != 0 && SitesCurrent(); }
bool Start(std::uintptr_t image) noexcept {
    const DWORD error = GetLastError(); std::uintptr_t verified{};
    const bool ok = image
        && (GraphicsExecutableSha256Matches("0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d") || (GraphicsExecutableSha256Matches("78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903") || GraphicsExecutableSha256Matches("e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437")))
        && movement::VerifyNativeMovementImage(verified) && verified == image
        && StartBound(image, reinterpret_cast<Send>(image + 0x7f4da0),
            reinterpret_cast<Followup>(image + 0x9d7b0));
    SetLastError(error); return ok;
}
bool NormalizeOwnedCode(std::uintptr_t image, std::uint32_t text_rva,
    std::span<std::uint8_t> code, std::span<const std::uint8_t> disk) noexcept {
    AcquireSRWLockShared(&install_lock);
    bool ok = code.size() == disk.size();
    for (const auto& site : sites) {
        if (!site.owned) { continue; }
        if (!ok || image != base || site.protection_pending || site.flush_pending
            || site.rva < text_rva || code.size() < site.bytes.size()
            || site.rva - text_rva > code.size() - site.bytes.size()) { ok = false; break; }
        const auto offset = site.rva - text_rva;
        auto patched = site.bytes; patched[0] = 0xcc;
        if (std::memcmp(disk.data() + offset, site.bytes.data(), 5)
            || std::memcmp(code.data() + offset, patched.data(), 5)) { ok = false; break; }
        code[offset] = site.bytes[0];
    }
    ReleaseSRWLockShared(&install_lock); return ok;
}
}
