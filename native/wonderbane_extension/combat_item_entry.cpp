#include "combat_item_entry.h"
#include "graphics_status.h"
#include "movement_native_image.h"
#include <Windows.h>
#include <intrin.h>
#include <cstring>
namespace wonderbane::extension::combat::item {
static_assert(sizeof(void*) == 4, "Reviewed item ABI is x86");
namespace {
using Lookup = void*(__thiscall*)(void*, void**, const Key*);
using Release = void(__thiscall*)(void**, void*);
using Use = void(__thiscall*)(void*, void*, bool);
using Send = void(__thiscall*)(void*, void*);
struct Calls { Lookup lookup; Release release; Use use; };
std::uintptr_t base{};
Send original_send{};
SRWLOCK install_lock = SRWLOCK_INIT;
volatile LONG installed{};
bool attempted{};
PVOID handler{};
struct Site {
    std::uint32_t rva = 0xaea65;
    std::array<std::uint8_t, 5> bytes{0xe8,0xfb,0x6f,0xf5,0xff};
    bool owned = false, protection_pending = false, flush_pending = false;
    DWORD protection{};
} site;
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
bool Simple(std::uint32_t type, std::uint32_t flags) noexcept {
    // Only the concrete qualified potion family is admitted by this module.
    return type == 8 && flags == 0x0a;
}
bool Binding(const Context& c) noexcept {
    return c.image == base && Word(base + 0x16a2d98, c.actor)
        && Word(c.actor, base + 0x114165c) && KeyAt(c.actor + 0x18, c.actor_key)
        && Word(c.actor + 8, base + 0x11417d4)
        && Word(c.actor + 0xea0, 0) && Word(c.actor + 0xea4, base + 0x1141570)
        && Word(base + 0x16ab88c, c.writer) && Word(c.writer, base + 0x116036c)
        && Word(c.writer + 0x44, c.container) && Word(c.container, base + 0x114ce9c);
}
bool Item(const Context& c, void* owned, std::uintptr_t expected_template) noexcept {
    const auto object = reinterpret_cast<std::uintptr_t>(owned);
    std::uintptr_t definition{};
    return object && object == c.item_address && Word(object, base + 0x1142748) && KeyAt(object + 0x18, c.item_key)
        && KeyAt(object + 0x10, c.template_key)
        && Copy(&definition, object + 0x68c, 4) && definition && definition == c.template_address
        && (!expected_template || definition == expected_template)
        && Word(definition, base + 0x11428f0)
        && Word(definition + 0xf4, c.template_type) && Word(definition + 0x11c, c.template_flags)
        && Simple(c.template_type, c.template_flags);
}
struct Scope;
thread_local Scope* active{};
struct Scope {
    const Context& context;
    State& state;
    Receipt& receipt;
    const Calls& calls;
    Scope* previous = active;
    std::uintptr_t definition{}, frame{}, returned{}, ticket{};
    bool blocked = false, send_seen = false, append_seen = false;
    Scope(const Context& c, State& s, Receipt& r, const Calls& f) : context(c), state(s), receipt(r), calls(f) { active=this; }
    void Block() noexcept { blocked=true; receipt.result=receipt.native_entered ? Result::uncertain : Result::denied; }
    bool Current() const noexcept {
        return active==this && !blocked && !state.quarantined && Ready()
            && Binding(context) && context.current(context.owner)
            && Binding(context);
    }
    void Quarantine() noexcept {
        state.quarantined=true; receipt.ownership_quarantined=true;
        receipt.result=Result::uncertain; blocked=true;
    }
    void Drop(void** slot) {
        if (state.quarantined || !*slot) { return; }
        calls.release(slot, nullptr);
        if (*slot) { Quarantine(); }
    }
    bool Member() {
        if (!Current() || state.membership_item || !Item(context,state.retained_item,definition)) { return false; }
        // The native actor inventory getter retains under its own container lock.
        // Output is caller-owned and persists outside faulting native frames.
        const auto returned_output=calls.lookup(reinterpret_cast<void*>(context.actor+0xea4),
            &state.membership_item,&context.item_key);
        if (returned_output != &state.membership_item) { Quarantine(); return false; }
        const bool same=state.membership_item==state.retained_item
            && Item(context,state.membership_item,definition);
        Drop(&state.membership_item);
        // No full callback after the last native membership lookup: a callback
        // could mutate inventory after the proof. Recheck the captured owner
        // through the queue-safe scalar fence and exact identities instead.
        return same && active==this && !blocked && !state.quarantined && Ready()
            && Binding(context) && Item(context,state.retained_item,definition)
            && context.append_current(context.owner);
    }
};
void Consume(void* message) {
    if (!message || message==reinterpret_cast<void*>(static_cast<std::uintptr_t>(-1))) { return; }
    void* empty{};
    using MessageRelease=void(__thiscall*)(void*,void**);
    const auto table=*static_cast<std::uintptr_t*>(message);
    reinterpret_cast<MessageRelease>(*reinterpret_cast<std::uintptr_t*>(table+8))(message,&empty);
}
bool Ticket(const Scope& s,void* message) noexcept {
    const auto p=reinterpret_cast<std::uintptr_t>(message);
    return p && Word(p,base+0x1155680) && Word(p+0x70,2) && Word(p+0x74,1)
        && KeyAt(p+0x78,s.context.item_key) && KeyAt(p+0x80,Key{});
}
bool OwnsFrame(std::uintptr_t frame) noexcept {
    const auto* s=active;
    return s && s->frame && frame==s->frame && s->returned
        && Word(frame+4,s->returned) && Word(frame+8,s->context.actor) && Word(frame+12,0);
}
thread_local std::uintptr_t foreign_actor{};
void __fastcall ForeignSendHook(void* sender,void*,void* message) {
    const DWORD error=GetLastError();const auto actor=foreign_actor;foreign_actor=0;
    activation::ForeignItemSend(actor);SetLastError(error);original_send(sender,message);
}
void __fastcall SendHook(void* sender,void*,void* message) {
    const DWORD error=GetLastError();
    auto* s=active;
    if (!s) { SetLastError(error); original_send(sender,message); return; }
    // Latch the exact sender argument before any full check can reenter.
    const bool first=!s->send_seen;
    s->send_seen=true; s->receipt.send_observed=true;
    if (!s->ticket) { s->ticket=reinterpret_cast<std::uintptr_t>(message); }
    const bool allowed=first && !s->blocked && s->receipt.native_entered
        && sender==reinterpret_cast<void*>(base+0x16ab888) && Ticket(*s,message) && s->Member();
    if (!allowed) { s->Block(); SetLastError(error); Consume(message); return; }
    s->receipt.result=Result::uncertain;
    SetLastError(error);
    original_send(sender,message);
    const DWORD after=GetLastError();
    if (!s->receipt.append_observed) { s->Block(); }
    activation::RecordReturn(s->context.activation,!s->blocked&&s->receipt.append_observed);
    SetLastError(after);
}
submission::AppendClaim Claim(void* container,void* message,std::uintptr_t caller) noexcept {
    for (auto* s=active;s;s=s->previous) {
        if (!s->ticket || s->ticket!=reinterpret_cast<std::uintptr_t>(message)) { continue; }
        const bool allowed=s==active && !s->blocked && !s->state.quarantined && !s->append_seen
            && caller==0x2c6eb7 && container==reinterpret_cast<void*>(s->context.container)
            && Ready() && Binding(s->context) && Item(s->context,s->state.retained_item,s->definition)
            && Ticket(*s,message) && s->context.append_current(s->context.owner);
        s->append_seen=true;
        if (!allowed) { s->Block(); }
        else { s->receipt.result=Result::uncertain; }
        return {allowed ? submission::AppendDecision::allow : submission::AppendDecision::deny,s};
    }
    return {};
}
void Complete(void* owner,submission::AppendResult result) noexcept {
    auto& s=*static_cast<Scope*>(owner);
    if (result!=submission::AppendResult::queued) { s.Block(); return; }
    s.receipt.append_observed=true;
    if (!s.blocked && Ready() && Binding(s.context)
        && s.context.append_current(s.context.owner)) { s.receipt.result=Result::queued; }
    else { s.Block(); }
}
LONG CALLBACK Trap(EXCEPTION_POINTERS* exception) noexcept {
    const DWORD error=GetLastError();
    if (!exception || !exception->ExceptionRecord || !exception->ContextRecord
        || exception->ExceptionRecord->ExceptionCode!=EXCEPTION_BREAKPOINT) {
        SetLastError(error); return EXCEPTION_CONTINUE_SEARCH;
    }
    auto& c=*exception->ContextRecord;
    const auto address=base+site.rva;
    std::array<std::uint8_t,5> actual{}; auto expected=site.bytes; expected[0]=0xcc;
    if (!base || reinterpret_cast<std::uintptr_t>(exception->ExceptionRecord->ExceptionAddress)!=address
        || c.Eip!=address || !Copy(actual.data(),address,actual.size()) || actual!=expected) {
        SetLastError(error); return EXCEPTION_CONTINUE_SEARCH;
    }
    __try { *reinterpret_cast<DWORD*>(c.Esp-4)=static_cast<DWORD>(address+5); }
    __except(EXCEPTION_EXECUTE_HANDLER) { SetLastError(error); return EXCEPTION_CONTINUE_SEARCH; }
    c.Esp-=4;
    const bool owned=OwnsFrame(c.Ebp);
    if(!owned){foreign_actor=0;(void)Copy(&foreign_actor,c.Ebp+8,sizeof(foreign_actor));}
    c.Eip=static_cast<DWORD>(owned ? reinterpret_cast<std::uintptr_t>(&SendHook)
        : reinterpret_cast<std::uintptr_t>(&ForeignSendHook));
    SetLastError(error); return EXCEPTION_CONTINUE_EXECUTION;
}
bool InstallByte() noexcept {
    auto* at=reinterpret_cast<volatile CHAR*>(base+site.rva);
    DWORD prior{};
    if (!VirtualProtect(const_cast<CHAR*>(at),1,PAGE_EXECUTE_READWRITE,&prior)) { return false; }
    site.protection=prior;site.protection_pending=true;
    const auto replaced=_InterlockedCompareExchange8(at,static_cast<CHAR>(0xcc),static_cast<CHAR>(0xe8));
    site.owned=static_cast<unsigned char>(replaced)==0xe8;
    site.flush_pending=FlushInstructionCache(GetCurrentProcess(),const_cast<CHAR*>(at),1)==FALSE;
    DWORD ignored{};
    site.protection_pending=VirtualProtect(const_cast<CHAR*>(at),1,prior,&ignored)==FALSE;
    return site.owned && !site.flush_pending && !site.protection_pending;
}
bool StartBound(std::uintptr_t image,Send send,bool (*install)() noexcept=InstallByte) noexcept {
    AcquireSRWLockExclusive(&install_lock);
    if (attempted) { const bool same=base==image;ReleaseSRWLockExclusive(&install_lock);return same && Ready(); }
    attempted=true;base=image;original_send=send;
    std::array<std::uint8_t,5> actual{};
    bool ok=image && send && Copy(actual.data(),image+site.rva,5) && actual==site.bytes;
    if (ok) { handler=AddVectoredExceptionHandler(1,Trap);ok=handler!=nullptr; }
    if (ok) { ok=submission::RegisterAppendObserver(submission::AppendObserverKind::item,{Claim,Complete}); }
    if (ok) { ok=install(); }
    if (ok) { InterlockedExchange(&installed,1); }
    // Handler/original remain pinned even after partial publication.
    ReleaseSRWLockExclusive(&install_lock);return ok && Ready();
}
struct Invocation { Use use;void* item;void* actor;std::uintptr_t* frame;std::uintptr_t* returned; };
static_assert(sizeof(Invocation)==20);
__declspec(naked) void __cdecl Bridge(const Invocation*) {
    __asm {
        push ebp
        mov ebp,esp
        push esi
        mov esi,dword ptr [ebp+8]
        lea eax,[ebp-20]
        mov edx,dword ptr [esi+12]
        mov dword ptr [edx],eax
        mov eax,offset NativeReturned
        mov edx,dword ptr [esi+16]
        mov dword ptr [edx],eax
        push 0
        push dword ptr [esi+8]
        mov ecx,dword ptr [esi+4]
        call dword ptr [esi]
    NativeReturned:
        mov edx,dword ptr [esi+12]
        mov dword ptr [edx],0
        mov edx,dword ptr [esi+16]
        mov dword ptr [edx],0
        pop esi
        mov esp,ebp
        pop ebp
        ret
    }
}
void Run(const Context& c,State& state,Receipt& receipt,const Calls& calls) {
    Scope scope(c,state,receipt,calls);
    if (!scope.Current()) { return; }
    const auto result=calls.lookup(reinterpret_cast<void*>(c.actor+0xea4),&state.retained_item,&c.item_key);
    if (result!=&state.retained_item) { scope.Quarantine();return; }
    if (!state.retained_item || !Item(c,state.retained_item,0)) {
        scope.Drop(&state.retained_item);return;
    }
    if (!Copy(&scope.definition,reinterpret_cast<std::uintptr_t>(state.retained_item)+0x68c,4)
        || !scope.Member()) { scope.Drop(&state.retained_item);return; }
    receipt.native_entered=true;receipt.result=Result::uncertain;
    const Invocation invocation{calls.use,state.retained_item,reinterpret_cast<void*>(c.actor),&scope.frame,&scope.returned};
    // The original caller can release its message before returning. Once it
    // returns, a recycled message address must not inherit this scope ticket.
    Bridge(&invocation);
    scope.ticket=0;
    if (!scope.Current() || !receipt.append_observed) { scope.Block(); }
    scope.Drop(&state.retained_item);
}
void RunCxx(const Context& c,State& state,Receipt& receipt,const Calls& calls) noexcept {
    try { Run(c,state,receipt,calls); }
    catch (...) { state.quarantined=true;receipt.ownership_quarantined=true;receipt.result=Result::uncertain; }
}
Receipt InvokeBound(const Context& c,State& state,Receipt& receipt,const Calls& calls) noexcept {
    if (state.attempted || state.retained_item || state.membership_item || state.quarantined) { return receipt; }
    state.attempted=true;
    receipt={};
    if (!Ready() || c.image!=base || !c.actor || !c.writer || !c.container
        || !c.item_address || !c.template_address
        || !c.actor_key[0] || c.actor_key[1]!=53 || !c.item_key[0] || !c.item_key[1]
        || !c.template_key[0] || c.template_key[1]!=0 || !Simple(c.template_type,c.template_flags)
        || !c.current || !c.append_current || !calls.lookup || !calls.release || !calls.use) { return receipt; }
    Scope* const previous=active;
    __try {
        __try { RunCxx(c,state,receipt,calls); }
        __finally { active=previous; }
    } __except(EXCEPTION_EXECUTE_HANDLER) {
        state.quarantined=true;receipt.ownership_quarantined=true;receipt.result=Result::uncertain;
    }
    activation::RecordReturn(c.activation,receipt.result==Result::queued&&receipt.append_observed&&!receipt.ownership_quarantined);
    return receipt;
}
}
Receipt Invoke(const Context& c,State& state,Receipt& receipt) noexcept {
    // Final actor inventory interface vslot4 has the qualified vtordisp adjustor.
    // The actor/vtable is validated before this pointer is called.
    return InvokeBound(c,state,receipt,{reinterpret_cast<Lookup>(c.image+0x4b6f),
        reinterpret_cast<Release>(c.image+0x89bd0),reinterpret_cast<Use>(c.image+0xae810)});
}
bool Ready() noexcept {
    std::array<std::uint8_t,5> actual{};auto expected=site.bytes;expected[0]=0xcc;
    return InterlockedCompareExchange(&installed,0,0)!=0 && base
        && Copy(actual.data(),base+site.rva,5) && actual==expected;
}
bool Start(std::uintptr_t image) noexcept {
    const DWORD error=GetLastError();std::uintptr_t verified{};
    const bool ok=image
        && (GraphicsExecutableSha256Matches("0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d") || (GraphicsExecutableSha256Matches("78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903") || (GraphicsExecutableSha256Matches("e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437") || (GraphicsExecutableSha256Matches("1a5a9fd59da8255a3c98e16e1e8ff9a415c0921b4189583158c559ad2594360c") || GraphicsExecutableSha256Matches("baa6c84e5f28aab01d516f12257354b42375d11e8e8e98930cfcf754aeec24e9")))))
        && movement::VerifyNativeMovementImage(verified) && verified==image
        && StartBound(image,reinterpret_cast<Send>(image+0x7f4da0));
    SetLastError(error);return ok;
}
bool NormalizeOwnedCode(std::uintptr_t image,std::uint32_t text_rva,
    std::span<std::uint8_t> code,std::span<const std::uint8_t> disk) noexcept {
    AcquireSRWLockShared(&install_lock);
    bool ok=code.size()==disk.size();
    if (site.owned) {
        ok=ok && image==base && !site.protection_pending && !site.flush_pending
            && site.rva>=text_rva && code.size()>=5 && site.rva-text_rva<=code.size()-5;
        if (ok) {
            const auto offset=site.rva-text_rva;auto patched=site.bytes;patched[0]=0xcc;
            ok=std::memcmp(disk.data()+offset,site.bytes.data(),5)==0
                && std::memcmp(code.data()+offset,patched.data(),5)==0;
            if (ok) { code[offset]=site.bytes[0]; }
        }
    }
    ReleaseSRWLockShared(&install_lock);return ok;
}
}
