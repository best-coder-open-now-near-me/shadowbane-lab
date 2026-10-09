#include "combat_activation_observer.h"
#include "combat_initiation.h"
#include "movement_lifetime.h"
#include <Windows.h>
#include <intrin.h>
#include <cstring>
namespace wonderbane::extension::combat::activation {
static_assert(sizeof(void*)==4);
namespace {
SRWLOCK state_lock=SRWLOCK_INIT,install_lock=SRWLOCK_INIT;
ActivationHistory history;
ActivationIdentity bound;
std::uintptr_t base{};
volatile LONG installed{},serial{};
bool attempted{};
PVOID handler{};
void* trampoline{};
using Process=std::uint32_t(__thiscall*)(void*);
using Setter=void*(__thiscall*)(void*,void**,bool,std::uint32_t,bool);
using Append=void(__thiscall*)(void*,const std::uint32_t*);
using Remove=bool(__thiscall*)(void*,std::uint32_t);
struct Site {std::uint32_t rva;std::array<std::uint8_t,5> bytes;bool owned{},protection_pending{},flush_pending{};DWORD protection{};};
std::array<Site,4> sites{{
 {0x382df0,{0x55,0x8b,0xec,0x6a,0xff}},
 {0x384057,{0xe8,0x77,0x18,0xca,0xff}},
 {0x3849f2,{0xe8,0xdc,0x0e,0xca,0xff}},
 {0x631a3,{0xe8,0x2b,0x27,0xfc,0xff}}
}};
bool Copy(void* out,std::uintptr_t at,std::size_t size) noexcept {
 __try {std::memcpy(out,reinterpret_cast<const void*>(at),size);return true;}
 __except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
template<class T> bool Word(std::uintptr_t at,T& out) noexcept {return Copy(&out,at,sizeof(out));}
ActivationIdentity Bound() noexcept {AcquireSRWLockShared(&state_lock);const auto out=bound;ReleaseSRWLockShared(&state_lock);return out;}
struct Facts {
 movement::NativeScene scene{};
 std::uintptr_t state{},target{};
 std::uint32_t mode{},action{};
 std::array<std::uint32_t,3> header{};
 initiation::Snapshot values{};
};
struct OwnedCall {
 std::uint64_t ticket{},mutation{};Facts armed{},entry{},followup{};
 std::uintptr_t definition{};std::uint32_t power{};std::uint8_t special{};
 bool entered{},following{},followed{},locally_completed{};
};
std::array<OwnedCall,ActivationHistory::capacity> owned_calls{};
bool Capture(const ActivationIdentity& id,Facts& out) noexcept {
 Facts a{};std::array<std::uint32_t,2> key{};std::uintptr_t actor{},state_after{};
 std::array<std::uint32_t,3> after{};
 if(!id.Valid()||!movement::ReadNativeMovementLifetime(a.scene)||a.scene.actor!=id.actor
  ||a.scene.identity!=id.key||a.scene.epoch!=id.scene||!Word(base+0x16a2d98,actor)||actor!=id.actor
  ||!Word(id.actor+0x18,key)||key!=id.key||!Word(id.actor+0xad0,a.state)||a.state<0x10000
  ||!Word(a.state+0x18,a.mode)||!Word(a.state+0x20,a.action)||!Word(id.actor+0xaf8,a.target)
  ||!Word(id.actor+0x65c,a.header)||!initiation::Capture(id.actor,a.state,a.values,[](auto at,auto& v)noexcept{return Word(at,v);})
  ||!Word(id.actor+0x65c,after)||after!=a.header||!Word(id.actor+0xad0,state_after)||state_after!=a.state
  ||!movement::NativeMovementLifetimeCurrent(a.scene)){return false;}
 out=a;return true;
}
bool SameLife(const Facts& a,const Facts& b) noexcept {
 return a.scene.actor==b.scene.actor&&a.scene.identity==b.scene.identity&&a.scene.epoch==b.scene.epoch
  &&a.state==b.state&&movement::NativeMovementLifetimeCurrent(a.scene);
}
bool SameVector(const Facts& a,const Facts& b) noexcept {
 if(a.header!=b.header||a.values.count!=b.values.count){return false;}
 for(std::uint32_t i=0;i<a.values.count;++i){if(a.values.ids[i]!=b.values.ids[i]){return false;}}return true;
}
bool AddedOne(const Facts& a,const Facts& b,std::uint32_t power) noexcept {
 if(!SameLife(a,b)||b.values.count!=a.values.count+1||b.values.ids[a.values.count]!=power){return false;}
 for(std::uint32_t i=0;i<a.values.count;++i){if(a.values.ids[i]!=b.values.ids[i]){return false;}}return true;
}
bool RemovedOne(const Facts& a,const Facts& b,std::uint32_t power,bool returned) noexcept {
 if(!SameLife(a,b)||a.values.state!=b.values.state){return false;}
 std::uint32_t first=a.values.count;
 for(std::uint32_t i=0;i<a.values.count;++i){if(a.values.ids[i]==power){first=i;break;}}
 if(first==a.values.count){return !returned&&SameVector(a,b);}
 if(!returned||a.values.count!=b.values.count+1){return false;}
 for(std::uint32_t i=0;i<b.values.count;++i){if(b.values.ids[i]!=a.values.ids[i+(i>=first?1:0)]){return false;}}return true;
}
struct ProcessFrame {
 ProcessFrame* previous{};std::uintptr_t message{},frame{},definition{},serial{};
 ActivationIdentity identity{};std::array<std::uint32_t,11> body{};
 ActivationHistory::Transition start{},completion{};
 ActivationHistory::ManualTransition manual_start{};
 bool manual_state{};
 bool valid{};
};
thread_local ProcessFrame* process_frame{};
struct Routed {std::uint32_t site{};std::uintptr_t frame{},definition{},original{};};
thread_local Routed routed;
bool Message(std::uintptr_t at,std::array<std::uint32_t,11>& body) noexcept {
 std::uintptr_t table{};return at&&Word(at,table)&&table==base+0x1155fd8&&Copy(body.data(),at+0x80,sizeof(body));
}
bool FrameCurrent(const Routed& call,ProcessFrame*& out,bool start) noexcept {
 auto* p=process_frame;std::uintptr_t msg{},actor{};std::array<std::uint32_t,11> body{};
 if(!p||!p->valid||!call.frame||!Word(call.frame-0x28,msg)||msg!=p->message
  ||!Word(call.frame-0x24,actor)||actor!=p->identity.actor||!Message(msg,body)||body!=p->body){return false;}
 if(p->frame&&p->frame!=call.frame){return false;}
 const auto definition=p->definition?p->definition:call.definition;
 std::uint32_t id{};std::uint8_t special{};
 if(!definition||!Word(definition+0x138,id)||id!=body[0]||!Word(definition+0x274,special)
  ||(start&&(special||(body[9]&1)==0||body[10]!=0))
  ||(!start&&((body[9]&3)!=2||body[10]!=0))){return false;}
 p->frame=call.frame;p->definition=definition;out=p;return true;
}
std::uintptr_t NextSerial() noexcept {
 auto previous=InterlockedCompareExchange(&serial,0,0);
 while(previous>=0&&previous<MAXLONG){const auto found=InterlockedCompareExchange(&serial,previous+1,previous);if(found==previous){return static_cast<std::uintptr_t>(previous+1);}previous=found;}return 0;
}
std::uint32_t __fastcall ProcessHook(void* message,void*) {
 const DWORD error=GetLastError();ProcessFrame frame{};frame.previous=process_frame;
 frame.message=reinterpret_cast<std::uintptr_t>(message);frame.identity=Bound();
 frame.serial=NextSerial();
 Facts facts{};
 frame.valid=frame.serial&&Message(frame.message,frame.body)&&frame.body[2]==frame.identity.key[0]
  &&frame.body[3]==frame.identity.key[1]&&Capture(frame.identity,facts);
 if(frame.previous&&frame.valid){OtherActivity(frame.identity.actor);}
 process_frame=&frame;bool normal=false;std::uint32_t result{};SetLastError(error);
 __try {result=reinterpret_cast<Process>(trampoline)(message);normal=true;}
 __finally {
  const DWORD after=GetLastError();Facts final{};std::array<std::uint32_t,11> body{};
  const bool coherent=normal&&frame.valid&&Capture(frame.identity,final)&&SameLife(facts,final)&&Message(frame.message,body)&&body==frame.body;
  AcquireSRWLockExclusive(&state_lock);
  if(frame.manual_start){history.ManualProcessReturned(frame.manual_start,coherent);}
  if(frame.start){history.StartProcessReturned(frame.start,coherent);}
  if(frame.completion){history.CompletionProcessReturned(frame.completion,coherent);}
  if(!normal&&frame.valid){history.ForeignPowerUse(frame.identity.actor);}
  ReleaseSRWLockExclusive(&state_lock);process_frame=frame.previous;SetLastError(after);
 }
 return result;
}
void* __fastcall StateHook(void* actor,void*,void** output,bool publish,std::uint32_t state,bool no_message) {
 const DWORD error=GetLastError();const auto call=routed;routed={};
 const auto object=reinterpret_cast<std::uintptr_t>(actor);ProcessFrame* p{};
 ActivationIdentity id=Bound();Facts before{},after{};ActivationHistory::Transition token{};ActivationHistory::ManualTransition manual_token{};
 const bool movement=call.site==0x631a3,start=call.site==0x384057;
 const bool exact=(movement?state==7&&publish&&!no_message:(state==(start?6U:5U)&&publish&&!no_message&&FrameCurrent(call,p,start)))
  &&id.actor==object&&Capture(id,before)&&(movement||!p||p->identity==id);
 AcquireSRWLockExclusive(&state_lock);
 if(exact){
  if(start){manual_token=history.BeginManualStart(id,p->body[0],p->serial,p->message,p->definition,GetCurrentThreadId());p->manual_state=static_cast<bool>(manual_token);}
  if(!manual_token){token=movement?history.BeginMovement(id):start?history.BeginStart(id,p->body[0],p->serial,p->message,p->definition,GetCurrentThreadId())
   :history.BeginCompletion(id,p->body[0],p->serial,p->message,p->definition,GetCurrentThreadId());}
 }
 else {history.OtherActivity(object);}
 ReleaseSRWLockExclusive(&state_lock);
 bool normal=false;void* result{};SetLastError(error);
 __try {result=reinterpret_cast<Setter>(call.original)(actor,output,publish,state,no_message);normal=true;}
 __finally {
  const DWORD native_error=GetLastError();
  const bool coherent=normal&&exact&&Capture(id,after)&&SameLife(before,after)&&SameVector(before,after)
   &&after.values.state==state&&(start||before.values.state==6);
  AcquireSRWLockExclusive(&state_lock);
  if(manual_token){history.ManualStateReturned(manual_token,coherent);}
  else if(movement){history.MovementReturned(token,coherent);}
  else if(start){history.StateReturned(token,coherent);}
  else{history.CompletionStateReturned(token,coherent);}
  ReleaseSRWLockExclusive(&state_lock);SetLastError(native_error);
 }
 return result;
}
void __fastcall AppendHook(void* vector,void*,const std::uint32_t* value) {
 const DWORD error=GetLastError();const auto call=routed;routed={};ProcessFrame* p{};
 ActivationIdentity id=Bound();Facts before{},after{};std::uint32_t power{};ActivationHistory::Transition token{};ActivationHistory::ManualTransition manual_token{};
 const bool exact=FrameCurrent(call,p,true)&&reinterpret_cast<std::uintptr_t>(vector)==id.actor+0x65c
  &&Word(reinterpret_cast<std::uintptr_t>(value),power)&&power==p->body[0]&&Capture(id,before);
 AcquireSRWLockExclusive(&state_lock);
 if(exact){if(p->manual_state){manual_token=history.BeginManualAppend(id,power,p->serial,p->message,p->definition,GetCurrentThreadId());}
  else{token=history.BeginAppend(id,power,p->serial,p->message,p->definition,GetCurrentThreadId());}}
 else{history.OtherActivity(reinterpret_cast<std::uintptr_t>(vector)>=0x65c?reinterpret_cast<std::uintptr_t>(vector)-0x65c:0);}
 ReleaseSRWLockExclusive(&state_lock);bool normal=false;SetLastError(error);
 __try {reinterpret_cast<Append>(call.original)(vector,value);normal=true;}
 __finally {const DWORD after_error=GetLastError();const bool coherent=normal&&exact&&Capture(id,after)&&AddedOne(before,after,power)&&before.values.state==6&&after.values.state==6;
  AcquireSRWLockExclusive(&state_lock);const bool candidate=manual_token?history.ManualAppendReturned(manual_token,coherent):history.AppendReturned(token,coherent);ReleaseSRWLockExclusive(&state_lock);
  if(p&&candidate){if(manual_token){p->manual_start=manual_token;}else{p->start=token;}}SetLastError(after_error);}
}
bool __fastcall RemovalHook(void* actor,void*,std::uint32_t power) {
 const DWORD error=GetLastError();const auto call=routed;routed={};ProcessFrame* p{};
 ActivationIdentity id=Bound();Facts before{},after{};ActivationHistory::Transition token{};
 const bool final=call.site==0x385761;
 const bool exact=(call.site==0x384f2b||final)&&FrameCurrent(call,p,false)&&id.actor==reinterpret_cast<std::uintptr_t>(actor)
  &&power==p->body[0]&&Capture(id,before);
 AcquireSRWLockExclusive(&state_lock);
 if(exact){token=history.BeginRemoval(id,power,p->serial,p->message,p->definition,GetCurrentThreadId(),final);}
 else{history.OtherActivity(reinterpret_cast<std::uintptr_t>(actor));}
 ReleaseSRWLockExclusive(&state_lock);bool normal=false,result=false;SetLastError(error);
 __try {result=reinterpret_cast<Remove>(call.original)(actor,power);normal=true;}
 __finally {const DWORD after_error=GetLastError();const bool coherent=normal&&exact&&Capture(id,after)&&RemovedOne(before,after,power,result);
  AcquireSRWLockExclusive(&state_lock);const bool candidate=history.RemovalReturned(token,final,coherent);ReleaseSRWLockExclusive(&state_lock);
  if(p&&final&&candidate){p->completion=token;}SetLastError(after_error);}
 return result;
}
bool SitesCurrent() noexcept {
 for(const auto& site:sites){auto expected=site.bytes;expected[0]=0xcc;std::array<std::uint8_t,5> actual{};
  if(!base||!Copy(actual.data(),base+site.rva,5)||actual!=expected){return false;}}return true;
}
LONG CALLBACK Trap(EXCEPTION_POINTERS* e) noexcept {
 const DWORD error=GetLastError();if(!e||!e->ExceptionRecord||!e->ContextRecord||e->ExceptionRecord->ExceptionCode!=EXCEPTION_BREAKPOINT){SetLastError(error);return EXCEPTION_CONTINUE_SEARCH;}
 auto& c=*e->ContextRecord;
 for(const auto& site:sites){const auto address=base+site.rva;auto expected=site.bytes;expected[0]=0xcc;std::array<std::uint8_t,5> bytes{};
  if(!base||reinterpret_cast<std::uintptr_t>(e->ExceptionRecord->ExceptionAddress)!=address||c.Eip!=address||!Copy(bytes.data(),address,5)||bytes!=expected){continue;}
  if(site.rva==0x382df0){c.Eip=reinterpret_cast<DWORD>(&ProcessHook);}
  else{__try {*reinterpret_cast<DWORD*>(c.Esp-4)=static_cast<DWORD>(address+5);}
   __except(EXCEPTION_EXECUTE_HANDLER){SetLastError(error);return EXCEPTION_CONTINUE_SEARCH;}
   c.Esp-=4;routed={site.rva,c.Ebp,c.Edi,base+0x258d3};c.Eip=reinterpret_cast<DWORD>(&StateHook);}
  SetLastError(error);return EXCEPTION_CONTINUE_EXECUTION;
 }
 SetLastError(error);return EXCEPTION_CONTINUE_SEARCH;
}
bool Install(Site& site) noexcept {
 auto* at=reinterpret_cast<volatile CHAR*>(base+site.rva);DWORD old{};
 if(!VirtualProtect(const_cast<CHAR*>(at),1,PAGE_EXECUTE_READWRITE,&old)){return false;}
 site.protection=old;site.protection_pending=true;
 site.owned=static_cast<unsigned char>(_InterlockedCompareExchange8(at,static_cast<CHAR>(0xcc),static_cast<CHAR>(site.bytes[0])))==site.bytes[0];
 site.flush_pending=!FlushInstructionCache(GetCurrentProcess(),const_cast<CHAR*>(at),1);DWORD ignored{};
 site.protection_pending=!VirtualProtect(const_cast<CHAR*>(at),1,old,&ignored);
 return site.owned&&!site.flush_pending&&!site.protection_pending;
}
bool StartBound(std::uintptr_t image,bool(*install)(Site&)noexcept=Install) noexcept {
 AcquireSRWLockExclusive(&install_lock);
 if(attempted){const bool same=base==image;ReleaseSRWLockExclusive(&install_lock);return same&&Ready();}
 attempted=true;base=image;bool ok=image!=0;
 for(const auto& site:sites){std::array<std::uint8_t,5> actual{};ok=ok&&Copy(actual.data(),base+site.rva,5)&&actual==site.bytes;}
 if(ok){trampoline=VirtualAlloc(nullptr,10,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);ok=trampoline!=nullptr;}
 if(ok){auto* t=static_cast<std::uint8_t*>(trampoline);std::memcpy(t,sites[0].bytes.data(),5);t[5]=0xe9;
  const auto rel=static_cast<std::uint32_t>(base+sites[0].rva+5-reinterpret_cast<std::uintptr_t>(t+10));std::memcpy(t+6,&rel,4);
  DWORD old{};ok=VirtualProtect(t,10,PAGE_EXECUTE_READ,&old)&&FlushInstructionCache(GetCurrentProcess(),t,10);}
 if(ok){handler=AddVectoredExceptionHandler(1,Trap);ok=handler!=nullptr;}
 for(auto& site:sites){if(ok){ok=install(site);}}
 if(ok){InterlockedExchange(&installed,1);}ReleaseSRWLockExclusive(&install_lock);return ok&&Ready();
}
}
Handle Arm(std::size_t slot,const ActivationIdentity& id,std::uint32_t power,ActivationOrigin origin) noexcept {
 const DWORD error=GetLastError();Facts f{};Handle result{};
 if(Ready()&&Capture(id,f)){AcquireSRWLockExclusive(&state_lock);const auto ticket=history.Arm(slot,id,power,origin);if(ticket){bound=id;result={slot,ticket,id};owned_calls[slot]={};owned_calls[slot].ticket=ticket;owned_calls[slot].armed=f;}ReleaseSRWLockExclusive(&state_lock);}
 SetLastError(error);return result;
}
void OwnedUseEntering(const Handle& h,std::uintptr_t definition) noexcept {
 const DWORD error=GetLastError();Facts current{};std::uint32_t power{};std::uint8_t special{};
 const bool captured=h&&definition&&Capture(h.identity,current)&&current.values.state==5
  &&Word(definition+0x138,power)&&Word(definition+0x274,special)&&special;
 AcquireSRWLockExclusive(&state_lock);
 if(captured&&bound==h.identity){auto& call=owned_calls[h.slot];const auto record=history.Read(h.slot);
  if(call.ticket==h.ticket&&record.ticket==h.ticket&&record.origin==ActivationOrigin::self_power
   &&record.power==power&&record.phase==ActivationPhase::awaiting_start&&call.armed.values.state==5
   &&call.armed.state==current.state&&call.armed.scene.epoch==current.scene.epoch){
   call.definition=definition;call.power=power;call.special=special;call.entry=current;call.entered=true;call.mutation=history.Mutation();
  }
 }
 ReleaseSRWLockExclusive(&state_lock);SetLastError(error);
}
void OwnedUseReturned(const Handle& h,bool value) noexcept {
 const DWORD error=GetLastError();OwnedCall call{};
 AcquireSRWLockShared(&state_lock);if(h&&bound==h.identity){call=owned_calls[h.slot];}ReleaseSRWLockShared(&state_lock);
 Facts after{};std::uint32_t power{};std::uint8_t special{};
 const bool coherent=h&&value&&call.ticket==h.ticket&&call.entered&&call.followed&&Capture(h.identity,after)
  &&Word(call.definition+0x138,power)&&power==call.power&&Word(call.definition+0x274,special)&&special==call.special&&special
  &&SameLife(call.entry,after)&&SameLife(call.followup,after)&&SameVector(call.followup,after)
  &&AddedOne(call.entry,after,power)&&after.values.state==5&&call.followup.values.state==5
  &&after.mode==call.entry.mode&&after.action==call.entry.action&&after.target==call.entry.target;
 AcquireSRWLockExclusive(&state_lock);
 if(coherent&&bound==h.identity&&owned_calls[h.slot].ticket==h.ticket&&history.Mutation()==call.mutation){
  const auto record=history.Read(h.slot);if(record.ticket==h.ticket&&record.queued&&record.owned_followup){owned_calls[h.slot].locally_completed=true;}
 }
 ReleaseSRWLockExclusive(&state_lock);SetLastError(error);
}
ActivationHistory::Transition BeginOwnedFollowup(const Handle& h) noexcept {
 const DWORD error=GetLastError();AcquireSRWLockExclusive(&state_lock);ActivationHistory::Transition out{};
 if(h&&bound==h.identity){auto& call=owned_calls[h.slot];
  call.following=call.ticket==h.ticket&&call.entered&&call.mutation==history.Mutation();
  out=history.BeginOwnedFollowup(h.slot,h.ticket);
  call.following=call.following&&static_cast<bool>(out);
 }ReleaseSRWLockExclusive(&state_lock);SetLastError(error);return out;
}
void OwnedFollowupReturned(const Handle& h,const ActivationHistory::Transition& token,bool normal_exact,bool state6) noexcept {
 const DWORD error=GetLastError();Facts after{};const bool captured=h&&Capture(h.identity,after);
 AcquireSRWLockExclusive(&state_lock);if(h&&bound==h.identity){
  const bool accepted=history.OwnedFollowupReturned(token,normal_exact,state6);auto& call=owned_calls[h.slot];
  if(call.ticket==h.ticket&&call.following&&accepted&&captured){call.followed=true;call.followup=after;call.mutation=history.Mutation();}
 }ReleaseSRWLockExclusive(&state_lock);SetLastError(error);
}
namespace {
struct OrdinaryFrame {OrdinaryFrame* previous{};std::uintptr_t actor{};std::uint32_t power{};std::uint64_t send_serial{};bool direct{};Facts direct_after{};};
thread_local OrdinaryFrame* ordinary_frame{};
std::uint64_t Mutation() noexcept {AcquireSRWLockShared(&state_lock);const auto value=history.Mutation();ReleaseSRWLockShared(&state_lock);return value;}
}
void RecordManualPowerSend(std::uintptr_t actor,std::uint32_t power) noexcept {
 const DWORD error=GetLastError();
 if(actor&&power&&ordinary_frame&&ordinary_frame->actor==actor&&ordinary_frame->power==power){ordinary_frame->send_serial=Mutation();}
 SetLastError(error);
}
void ObserveManualFollowup(std::uintptr_t original,void* actor,void* target,void* definition,int rank) {
 const DWORD error=GetLastError();auto* f=ordinary_frame;const auto id=Bound();Facts before{},after{};std::uint32_t power{};
 const bool exact=f&&f->actor==reinterpret_cast<std::uintptr_t>(actor)&&id.actor==f->actor&&f->send_serial
  &&f->send_serial==Mutation()
  &&Word(reinterpret_cast<std::uintptr_t>(definition)+0x138,power)&&power==f->power&&Capture(id,before);
 ForeignPowerUse(reinterpret_cast<std::uintptr_t>(actor));if(f&&exact){f->send_serial=Mutation();}
 bool normal=false;using Call=void(__cdecl*)(void*,void*,void*,int);SetLastError(error);
 __try {reinterpret_cast<Call>(original)(actor,target,definition,rank);normal=true;}
 __finally {const DWORD native_error=GetLastError();
  if(f&&exact&&normal&&ordinary_frame==f&&Capture(id,after)&&AddedOne(before,after,power)&&after.values.state==6
   &&f->send_serial==Mutation()){f->direct=true;f->direct_after=after;}
  else if(f){f->direct=false;}
  SetLastError(native_error);
 }
}
bool ObserveOrdinaryPower(std::uintptr_t original,std::uint32_t power,int rank,void* actor,void* target,const float* position,std::array<std::uint32_t,2> key) {
 const DWORD error=GetLastError();const auto id=Bound();Facts before{},after{};const auto object=reinterpret_cast<std::uintptr_t>(actor);
 const bool observed=object==id.actor, captured=observed&&Capture(id,before);bool normal=false,result=false;
 OrdinaryFrame frame{ordinary_frame,object,power,0};ordinary_frame=&frame;SetLastError(error);
 using Call=bool(__cdecl*)(std::uint32_t,int,void*,void*,const float*,std::array<std::uint32_t,2>);
 __try {result=reinterpret_cast<Call>(original)(power,rank,actor,target,position,key);normal=true;}
 __finally {const DWORD native_error=GetLastError();
  const bool same=normal&&captured&&Capture(id,after)&&SameLife(before,after);
  if(observed&&same&&frame.send_serial&&frame.send_serial==Mutation()){
   const bool direct=frame.direct&&after.values.state==6&&SameLife(frame.direct_after,after)&&SameVector(frame.direct_after,after);
   AcquireSRWLockExclusive(&state_lock);if(bound==id&&history.Mutation()==frame.send_serial){history.ManualSend(object,power);history.ManualDirectReturned(id,power,direct);}ReleaseSRWLockExclusive(&state_lock);
  }else if(observed&&(!same||result||!SameVector(before,after)||before.values.state!=after.values.state||before.mode!=after.mode||before.action!=after.action||before.target!=after.target)){ForeignPowerUse(object);}
  ordinary_frame=frame.previous;SetLastError(native_error);}
 return result;
}
void RecordReturn(const Handle& h,bool queued,bool owned_followup) noexcept {
 const DWORD error=GetLastError();AcquireSRWLockExclusive(&state_lock);
 if(h&&bound==h.identity){history.QueueResult(h.slot,h.ticket,queued);history.OwnedFollowup(h.slot,h.ticket,owned_followup);}
 ReleaseSRWLockExclusive(&state_lock);SetLastError(error);
}
Result Read(const Handle& h) noexcept {
 const DWORD error=GetLastError();Result result=Result::unknown;Facts f{};
 if(Ready()&&h&&Capture(h.identity,f)){AcquireSRWLockShared(&state_lock);const auto r=history.Read(h.slot);
  if(r.ticket==h.ticket&&r.identity==h.identity&&r.queued){
   if(r.phase==ActivationPhase::interrupted||r.phase==ActivationPhase::completed){if(r.origin!=ActivationOrigin::self_power||r.owned_followup){result=r.phase==ActivationPhase::interrupted?Result::interrupted:Result::completed;}}
   else if(owned_calls[h.slot].ticket==h.ticket&&owned_calls[h.slot].locally_completed){result=Result::locally_completed;}
   else if(r.local_relinquished&&r.origin==ActivationOrigin::self_power&&r.owned_followup){result=Result::relinquished;}
   else if(r.phase==ActivationPhase::active){result=Result::active;}
   else if(r.phase!=ActivationPhase::unknown){result=Result::awaiting;}}
  ReleaseSRWLockShared(&state_lock);}
 SetLastError(error);return result;
}
bool ResetExactLifetime(const ActivationIdentity& old) noexcept {const DWORD error=GetLastError();AcquireSRWLockExclusive(&state_lock);const bool ok=history.ResetExactLifetime(old);if(ok){bound={};owned_calls={};}ReleaseSRWLockExclusive(&state_lock);SetLastError(error);return ok;}
void ForeignItemSend(std::uintptr_t actor) noexcept {const DWORD error=GetLastError();AcquireSRWLockExclusive(&state_lock);history.ForeignItemSend(actor?actor:bound.actor);ReleaseSRWLockExclusive(&state_lock);SetLastError(error);}
void ForeignPowerUse(std::uintptr_t actor) noexcept {const DWORD error=GetLastError();AcquireSRWLockExclusive(&state_lock);history.ForeignPowerUse(actor?actor:bound.actor);ReleaseSRWLockExclusive(&state_lock);SetLastError(error);}
void OtherActivity(std::uintptr_t actor) noexcept {const DWORD error=GetLastError();AcquireSRWLockExclusive(&state_lock);history.OtherActivity(actor?actor:bound.actor);ReleaseSRWLockExclusive(&state_lock);SetLastError(error);}
std::uintptr_t Route(std::uint32_t site,std::uintptr_t frame,std::uintptr_t original) noexcept {
 if(site!=0x384451&&site!=0x384f2b&&site!=0x385761&&site!=0x384617&&site!=0x37e8ca){return original;}
 routed={site,frame,0,original};return site==0x384451?reinterpret_cast<std::uintptr_t>(&AppendHook):reinterpret_cast<std::uintptr_t>(&RemovalHook);
}
bool Ready() noexcept {return InterlockedCompareExchange(&installed,0,0)!=0&&SitesCurrent();}
bool Start(std::uintptr_t image) noexcept {const DWORD error=GetLastError();const bool ok=StartBound(image);SetLastError(error);return ok;}
bool NormalizeOwnedCode(std::uintptr_t image,std::uint32_t rva,std::span<std::uint8_t> code,std::span<const std::uint8_t> disk) noexcept {
 AcquireSRWLockShared(&install_lock);bool ok=code.size()==disk.size();
 for(const auto& site:sites){if(!site.owned){continue;}if(!ok||image!=base||site.protection_pending||site.flush_pending||site.rva<rva||code.size()<5||site.rva-rva>code.size()-5){ok=false;break;}
  const auto at=site.rva-rva;auto patched=site.bytes;patched[0]=0xcc;
  if(std::memcmp(disk.data()+at,site.bytes.data(),5)||std::memcmp(code.data()+at,patched.data(),5)){ok=false;break;}code[at]=site.bytes[0];}
 ReleaseSRWLockShared(&install_lock);return ok;
}
}
