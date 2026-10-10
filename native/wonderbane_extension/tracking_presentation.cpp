#include "tracking_presentation.h"
#include <algorithm>
#include <atomic>
#include <cstring>
#include <limits>
namespace wonderbane::extension::tracking::presentation {
namespace {
constexpr std::uintptr_t kRoot = 0x16a7bfc, kRootTable = 0x1174884;
constexpr std::uintptr_t kHudTable = 0x116fb58, kClose = 0x5f4e70;
constexpr std::uint32_t kHuntFoe = 429578587;
struct Hud { std::uintptr_t address = 0; std::uint32_t selector = 0; };
struct State {
    movement::NativeScene scene{};
    Owner owner{};
    std::uint64_t serial = 1;
    DWORD thread = 0;
    unsigned processing = 0;
    bool active = false, adopt = false, adoption_consumed = false;
    bool manual = false, manual_pending = false, manual_seen = false;
    std::uintptr_t last_hud = 0;
};
SRWLOCK mutex = SRWLOCK_INIT;
State state;
std::atomic<std::uintptr_t> base{0};
bool Copy(std::uintptr_t address, void* out, std::size_t size) noexcept {
    if(address < 0x10000 || address >= 0x80000000 || size > 0x80000000-address){return false;}
    __try { std::memcpy(out,reinterpret_cast<void*>(address),size);return true; }
    __except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
bool Word(std::uintptr_t at,std::uint32_t& out) noexcept {return at%4==0&&Copy(at,&out,4);}
bool Same(const movement::NativeScene& a,const movement::NativeScene& b) noexcept {
    return a.epoch&&a.epoch==b.epoch&&a.actor==b.actor&&a.parent==b.parent&&a.world==b.world
        &&a.window==b.window&&a.identity==b.identity;
}
void Advance() noexcept {
    if(state.serial != std::numeric_limits<std::uint64_t>::max()){++state.serial;}
    else {state.active=false;}
}
bool Capture(const movement::NativeScene& scene,Hud& out) noexcept {
    out={};std::uint32_t root{},table{},mode{},head{},node{},previous{};
    if(!base||!movement::NativeMovementLifetimeCurrent(scene)||!Word(base+kRoot,root)||root!=scene.window
        ||!Word(root,table)||table!=base+kRootTable||!Word(root+0x64,mode)||mode!=2
        ||!Word(root+0x20,head)||!Word(head,node)){return false;}
    previous=head;
    for(unsigned count=0;node!=head;++count){
        std::array<std::uint32_t,3> entry{};std::uint32_t hud_table{},kind{},selector{};unsigned char closed{};
        if(count==512||node%4||!Copy(node,entry.data(),sizeof(entry))||entry[1]!=previous
            ||!Word(entry[2],hud_table)){return false;}
        if(hud_table==base+kHudTable){
            if(!Word(entry[2]+0xdc,kind)||kind!=0x34||!Copy(entry[2]+0x271,&closed,1)
                ||closed>1||!Word(entry[2]+0x3b8,selector)){return false;}
            if(!closed){if(out.address){return false;}out={entry[2],selector};}
        }
        previous=node;node=entry[0];
    }
    std::uint32_t tail{},again{};
    return Word(head+4,tail)&&tail==previous&&Word(base+kRoot,again)&&again==root
        &&movement::NativeMovementLifetimeCurrent(scene);
}
bool Close(const movement::NativeScene& scene,const Hud& hud) noexcept {
    Hud current{};std::uint32_t target{};
    if(!hud.address||hud.selector!=kHuntFoe||!Capture(scene,current)||current.address!=hud.address
        ||current.selector!=hud.selector||!Word(base+kHudTable+0x10c,target)||target!=base+kClose){return false;}
    using Function=void(__thiscall*)(void*,bool);
    // This is the same lifecycle used by ListMsg::Process. Never write flags,
    // unlink nodes or invoke a destructor ourselves.
    __try {reinterpret_cast<Function>(target)(reinterpret_cast<void*>(hud.address),true);return true;}
    __except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
using CaptureFn=bool(*)(const movement::NativeScene&,Hud&) noexcept;
using CloseFn=bool(*)(const movement::NativeScene&,const Hud&) noexcept;
CaptureFn capture=Capture;CloseFn close_hud=Close;
void ResetScene(const movement::NativeScene& scene) noexcept {
    const auto serial=state.serial;state={};state.serial=serial;state.scene=scene;Advance();
}
void ObserveOutside(const Hud& hud) noexcept {
    if(state.manual){
        if(hud.address){state.manual_seen=true;}
        else if(state.manual_seen&&!state.manual_pending){state.manual=false;state.manual_seen=false;Advance();}
    }else if(hud.address&&!state.adopt&&hud.address!=state.last_hud){
        // A window opened outside a response is user presentation, even without
        // a new outbound query (for example reopening an existing native HUD).
        state.manual=true;state.manual_seen=true;Advance();
    }
    state.last_hud=hud.address;
}
void TryClose(const movement::NativeScene& scene,std::uint64_t serial,const Hud& hud) noexcept {
    AcquireSRWLockShared(&mutex);
    const bool allowed=state.active&&!state.manual&&state.serial==serial&&Same(state.scene,scene)
        &&state.thread==GetCurrentThreadId();
    ReleaseSRWLockShared(&mutex);
    if(!allowed||!hud.address||hud.selector!=kHuntFoe){return;}
    const bool closed=close_hud(scene,hud);
    AcquireSRWLockExclusive(&mutex);
    if(state.serial==serial&&Same(state.scene,scene)){
        if(closed){state.last_hud=0;state.adopt=false;}
        else {state.active=false;Advance();}
    }
    ReleaseSRWLockExclusive(&mutex);
}
}
bool Bind(std::uintptr_t image) noexcept {
    // Full relocated .text and exact executable hash have already been checked
    // by tracking::Start. Also bind the newly used close slot/prologue explicitly.
    constexpr unsigned char expected[]{0x55,0x8b,0xec,0x81,0xec,0x04,0x02,0x00,0x00};
    unsigned char bytes[sizeof(expected)]{};std::uint32_t target{};
    if(!image||!Copy(image+kClose,bytes,sizeof(bytes))||std::memcmp(bytes,expected,sizeof(bytes))
        ||!Word(image+kHudTable+0x10c,target)||target!=image+kClose){return false;}
    AcquireSRWLockExclusive(&mutex);base=image;state={};ReleaseSRWLockExclusive(&mutex);return true;
}
void Unbind() noexcept {
    AcquireSRWLockExclusive(&mutex);state.active=false;Advance();base=0;ReleaseSRWLockExclusive(&mutex);
}
void Arm(const movement::NativeScene& scene,const Owner& owner) noexcept {
    if(!base||!std::any_of(owner.begin(),owner.end(),[](auto byte){return byte!=0;})
        ||!movement::NativeMovementLifetimeCurrent(scene)){return;}
    AcquireSRWLockExclusive(&mutex);
    if(!Same(state.scene,scene)){ResetScene(scene);}
    if(!state.active||state.owner!=owner){
        state.owner=owner;state.active=true;
        state.adopt=!state.adoption_consumed&&!state.manual;state.adoption_consumed=true;
        state.thread=GetCurrentThreadId();Advance();
    }
    ReleaseSRWLockExclusive(&mutex);
    Maintain(scene,owner);
}
void Maintain(const movement::NativeScene& scene,const Owner& owner) noexcept {
    AcquireSRWLockShared(&mutex);
    const bool eligible=state.active&&state.owner==owner&&Same(state.scene,scene)
        &&state.thread==GetCurrentThreadId()&&!state.processing;
    ReleaseSRWLockShared(&mutex);
    if(!eligible){return;}
    Hud hud{};if(!capture(scene,hud)){Retire(owner);return;}
    AcquireSRWLockExclusive(&mutex);
    const bool valid=state.active&&state.owner==owner&&Same(state.scene,scene)
        &&state.thread==GetCurrentThreadId()&&!state.processing;
    if(valid){ObserveOutside(hud);}
    const auto serial=state.serial;const bool adopt=valid&&state.adopt&&!state.manual;
    if(valid&&!hud.address){state.adopt=false;}
    ReleaseSRWLockExclusive(&mutex);
    if(adopt){TryClose(scene,serial,hud);}
}
void Retire(const Owner& owner) noexcept {
    AcquireSRWLockExclusive(&mutex);
    if(state.owner==owner){state.active=false;state.adopt=false;Advance();}
    // Manual reservation is scene-bound, not an automation owner's property.
    ReleaseSRWLockExclusive(&mutex);
}
void ManualQuery() noexcept {
    movement::NativeScene scene{};
    if(!base||!movement::ReadNativeMovementLifetime(scene)||!movement::NativeMovementLifetimeCurrent(scene)){return;}
    AcquireSRWLockExclusive(&mutex);
    if(!Same(state.scene,scene)){ResetScene(scene);}
    state.manual=state.manual_pending=true;state.manual_seen=false;state.adopt=false;Advance();
    ReleaseSRWLockExclusive(&mutex);
}
Processing Begin(const movement::NativeScene& scene) noexcept {
    AcquireSRWLockExclusive(&mutex);Processing result{};
    if(Same(state.scene,scene)){
        ++state.processing;result={state.serial,true};
    }
    ReleaseSRWLockExclusive(&mutex);return result;
}
void End(const movement::NativeScene& scene,Processing processing,bool complete_hunt_foe,bool native_returned) noexcept {
    if(!processing.entered){return;}
    Hud hud{};const bool observed=capture(scene,hud);
    AcquireSRWLockExclusive(&mutex);
    const bool same=Same(state.scene,scene);
    if(same&&state.processing){--state.processing;}
    if(same&&observed){
        // Native Process closes the previous HUD and creates another. That
        // internal close is NOT manual dismissal, including nested callbacks.
        state.last_hud=hud.address;
        if(state.manual&&hud.address){state.manual_seen=true;if(native_returned){state.manual_pending=false;}}
    }
    const bool close= same&&observed&&complete_hunt_foe&&!state.processing;
    ReleaseSRWLockExclusive(&mutex);
    if(close){TryClose(scene,processing.policy,hud);}
}
}
