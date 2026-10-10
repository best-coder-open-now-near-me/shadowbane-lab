#include "combat_group_chat.h"
#include "combat_submission.h"
#include "graphics_status.h"
#include "movement_native_image.h"
#include <cstring>
namespace wonderbane::extension::combat::group_chat {
static_assert(sizeof(void*)==4);
namespace {
using Allocate=void*(__cdecl*)(std::size_t);
using TextCtor=void*(__thiscall*)(void*,const char*);
using TextDtor=void(__thiscall*)(void*);
using MessageCtor=void*(__thiscall*)(void*,const void*);
using Send=void(__thiscall*)(void*);
using Release=void(__thiscall*)(void*,void**);
struct Calls {Allocate allocate;TextCtor text_ctor;TextDtor text_dtor;MessageCtor ctor;Send send;
    bool (*capture)(std::uintptr_t,const movement::NativeScene&,party::Snapshot&) noexcept;};
std::uintptr_t base{};
volatile LONG installed{};
SRWLOCK installation=SRWLOCK_INIT;
bool Copy(void*out,std::uintptr_t at,std::size_t n) noexcept {
    __try{std::memcpy(out,reinterpret_cast<void*>(at),n);return true;}
    __except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
bool Word(std::uintptr_t at,std::uintptr_t expected) noexcept {
    std::uintptr_t value{};return Copy(&value,at,4)&&value==expected;
}
std::size_t TextLength(const Context& c) noexcept {
    std::size_t n=0;
    while(n<c.text.size()&&c.text[n]){
        const auto ch=static_cast<unsigned char>(c.text[n]);
        if(ch<32||ch>126||ch=='/'||ch=='\\'||ch=='^'||ch=='<'||ch=='>'){return 0;}
        ++n;
    }
    if(!n||n>maximum_text){return 0;}
    for(auto i=n+1;i<c.text.size();++i){if(c.text[i])return 0;}
    return n;
}
bool Binding(const Context& c) noexcept {
    return c.image==base&&c.group.valid&&c.group.count&&c.group.count<=party::kMaximumMembers
        &&Word(base+0x16a2d98,c.group.scene.actor)
        &&Word(base+0x16ab88c,c.writer)&&Word(c.writer,base+0x116036c)
        &&Word(c.writer+0x44,c.container)&&Word(c.container,base+0x114ce9c);
}
struct Scope;
thread_local Scope* active{};
struct Scope {
    const Context& c;State& state;Receipt& receipt;const Calls& calls;
    Scope* previous=active;bool append_seen=false,blocked=false;
    Scope(const Context& a,State& b,Receipt& d,const Calls& e):c(a),state(b),receipt(d),calls(e){active=this;}
    bool Current() const noexcept {
        party::Snapshot group{};
        return active==this&&!blocked&&!state.quarantined&&Ready()&&Binding(c)
            &&c.current(c.owner)&&calls.capture(base,c.group.scene,group)
            &&party::Equal(c.group,group)&&Binding(c)&&c.append_current(c.owner);
    }
    void Block() noexcept {blocked=true;receipt.result=receipt.native_entered?Result::uncertain:Result::denied;}
    void Drop() {
        if(state.message&&state.message_constructed){
            auto*p=state.message;void*empty{};
            const auto table=*static_cast<std::uintptr_t*>(p);
            reinterpret_cast<Release>(*reinterpret_cast<std::uintptr_t*>(table+8))(p,&empty);
            state.message=nullptr;state.message_constructed=false;
        }
        if(state.text_constructed){calls.text_dtor(state.text.data());state.text_constructed=false;}
    }
};
bool Message(const Scope& s) noexcept {
    const auto p=reinterpret_cast<std::uintptr_t>(s.state.message);
    std::uintptr_t begin{},end{},token{};
    const auto n=TextLength(s.c);
    if(!p||!n||!Copy(&token,base+0x138bdbc,4)||!token||!Word(p+0x10,token)
        ||!Word(p,base+0x115dbc4)||!Word(p+0x84,14)||!Word(p+0x68,0)
        ||!Copy(&begin,p+0x70,4)||!Copy(&end,p+0x74,4)||begin<0x10000||end<begin||end-begin!=n*2){return false;}
    std::array<wchar_t,maximum_text> text{};
    if(!Copy(text.data(),begin,n*2)){return false;}
    for(std::size_t i=0;i<n;++i){if(text[i]!=static_cast<unsigned char>(s.c.text[i]))return false;}
    return true;
}
submission::AppendClaim Claim(void* container,void*message,std::uintptr_t caller) noexcept {
    for(auto*s=active;s;s=s->previous){
        if(!s->state.message_constructed||s->state.message!=message){continue;}
        const bool allowed=s==active&&!s->blocked&&!s->state.quarantined&&!s->append_seen
            &&s->receipt.native_entered&&caller==0x2c6eb7
            &&container==reinterpret_cast<void*>(s->c.container)&&Ready()&&Binding(s->c)
            &&s->c.append_current(s->c.owner);
        s->append_seen=true;s->receipt.result=Result::uncertain;
        if(!allowed)s->blocked=true;
        return {allowed?submission::AppendDecision::allow:submission::AppendDecision::deny,s};
    }
    return {};
}
void Complete(void*value,submission::AppendResult result) noexcept {
    auto&s=*static_cast<Scope*>(value);
    if(result!=submission::AppendResult::queued){s.Block();return;}
    s.receipt.append_observed=true;
    if(!s.blocked&&Ready()&&Binding(s.c)&&s.c.append_current(s.c.owner))s.receipt.result=Result::queued;
    else s.Block();
}
void Run(const Context&c,State&state,Receipt&receipt,const Calls&calls){
    Scope s(c,state,receipt,calls);
    if(!s.Current())return;
    if(calls.text_ctor(state.text.data(),c.text.data())!=state.text.data())throw 1;
    state.text_constructed=true;
    state.message=calls.allocate(0xb0);
    if(!state.message){s.Drop();return;}
    if(calls.ctor(state.message,state.text.data())!=state.message)throw 1;
    state.message_constructed=true;
    // Native constructors may call services. Revalidate the complete same group
    // immediately before the ordinary sender; queue callback is scalar-only.
    if(!s.Current()||!Message(s)){s.Drop();return;}
    receipt.native_entered=true;receipt.result=Result::uncertain;
    calls.send(state.message);
    if(!receipt.append_observed||!s.Current())s.Block();
    s.Drop();
}
void Quarantine(State&s,Receipt&r) noexcept {s.quarantined=true;r.ownership_quarantined=true;r.result=Result::uncertain;}
void RunCxx(const Context&c,State&s,Receipt&r,const Calls&calls) noexcept {
    try{Run(c,s,r,calls);}catch(...){Quarantine(s,r);}
}
Receipt InvokeBound(const Context&c,State&s,Receipt&r,const Calls&calls) noexcept {
    if(s.attempted||s.message||s.text_constructed||s.quarantined)return r;
    s.attempted=true;r={};
    if(!Ready()||!TextLength(c)||!c.current||!c.append_current||!calls.allocate||!calls.text_ctor
        ||!calls.text_dtor||!calls.ctor||!calls.send||!calls.capture)return r;
    auto*previous=active;
    __try{__try{RunCxx(c,s,r,calls);}__finally{active=previous;}}
    __except(EXCEPTION_EXECUTE_HANDLER){Quarantine(s,r);}
    return r;
}
bool StartBound(std::uintptr_t image) noexcept {
    AcquireSRWLockExclusive(&installation);
    bool ok=!base||base==image;
    if(ok){base=image;ok=image&&submission::RegisterAppendObserver(
        submission::AppendObserverKind::group_chat,{Claim,Complete});}
    if(ok)InterlockedExchange(&installed,1);
    ReleaseSRWLockExclusive(&installation);return ok;
}
}
Receipt Invoke(const Context&c,State&s,Receipt&r) noexcept {
    return InvokeBound(c,s,r,{reinterpret_cast<Allocate>(c.image+0x8d88e6),
        reinterpret_cast<TextCtor>(c.image+0x145030),reinterpret_cast<TextDtor>(c.image+0x145310),
        reinterpret_cast<MessageCtor>(c.image+0x427e00),reinterpret_cast<Send>(c.image+0x414520),party::Capture});
}
bool Ready() noexcept{return InterlockedCompareExchange(&installed,0,0)!=0&&submission::Ready();}
bool Start(std::uintptr_t image) noexcept {
    const auto error=GetLastError();std::uintptr_t verified{};
    const bool ok=image&&GraphicsExecutableSha256Matches(
        "1a5a9fd59da8255a3c98e16e1e8ff9a415c0921b4189583158c559ad2594360c")
        &&movement::VerifyNativeMovementImage(verified)&&verified==image&&StartBound(image);
    SetLastError(error);return ok;
}
}
