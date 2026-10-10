#include "combat_group_chat.cpp"
#include <cstdio>
#include <stdexcept>
namespace g=wonderbane::extension::combat::group_chat;
namespace p=wonderbane::extension::combat::party;
namespace sub=wonderbane::extension::combat::submission;
namespace {
sub::AppendObserver observer{};
p::Snapshot captured{};
std::array<unsigned,0xb0/4> packet{};
std::array<std::uintptr_t,3> table{};
std::array<wchar_t,g::maximum_text> body{};
bool current=true,append_current=true,change_group=false,transport=true,send_fault=false,release_fault=false;
unsigned allocations{},sends{},releases{},text_drops{},mode_now{};
void Check(bool ok){if(!ok){std::fprintf(stderr,"mode=%u sends=%u alloc=%u\n",mode_now,sends,allocations);throw std::runtime_error("group chat regression");}}
bool Current(void*)noexcept{return current;}
bool AppendCurrent(void*)noexcept{return append_current;}
bool Capture(std::uintptr_t,const wonderbane::extension::movement::NativeScene&,p::Snapshot&out)noexcept{out=captured;return true;}
void* __cdecl Allocate(std::size_t n){Check(n==0xb0);++allocations;packet={};return packet.data();}
void* __fastcall Text(void*p,void*,const char*){std::memset(p,0,24);return p;}
void __fastcall TextDrop(void*,void*){++text_drops;}
void __fastcall Release(void*,void*,void**){++releases;if(release_fault)RaiseException(0xe0420201,0,0,nullptr);}
void* __fastcall Ctor(void*value,void*,const void*){
 Check(value==packet.data());packet[0]=static_cast<unsigned>(g::base+0x115dbc4);
 packet[0x84/4]=14;packet[0x10/4]=123;body.fill(0);const char*text="Hunt Foe: Alice";
 for(unsigned i=0;text[i];++i)body[i]=text[i];
 packet[0x70/4]=reinterpret_cast<unsigned>(body.data());packet[0x74/4]=packet[0x70/4]+30;
 if(change_group)captured.count=0;
 return value;
}
void __fastcall Send(void*value,void*){
 ++sends;
 if(transport){
  auto claim=observer.claim(reinterpret_cast<void*>(g::base+0x1602000),value,0x2c6eb7);
  Check(claim.owner!=nullptr);
  observer.complete(claim.owner,claim.decision==sub::AppendDecision::allow?sub::AppendResult::queued:sub::AppendResult::denied);
 }
 if(send_fault)RaiseException(0xe0420201,0,0,nullptr);
}
g::Calls Calls(){return {Allocate,reinterpret_cast<g::TextCtor>(Text),reinterpret_cast<g::TextDtor>(TextDrop),reinterpret_cast<g::MessageCtor>(Ctor),reinterpret_cast<g::Send>(Send),Capture};}
void Put(std::uintptr_t at,std::uintptr_t v){*reinterpret_cast<std::uintptr_t*>(at)=v;}
g::Context Context(){
 current=append_current=transport=true;change_group=send_fault=release_fault=false;
 captured={};captured.valid=true;captured.count=1;captured.manager=123;captured.scene.actor=g::base+0x1600000;
 captured.scene.identity={53,7};captured.scene.epoch=1;
 g::Context c{};c.image=g::base;c.writer=g::base+0x1601000;c.container=g::base+0x1602000;c.group=captured;
 c.current=Current;c.append_current=AppendCurrent;std::memcpy(c.text.data(),"Hunt Foe: Alice",15);return c;
}
}
namespace wonderbane::extension {
bool GraphicsExecutableSha256Matches(const char*)noexcept{return false;}
namespace movement {
bool VerifyNativeMovementImage(std::uintptr_t&)noexcept{return false;}
bool NativeMovementLifetimeCurrent(const NativeScene&)noexcept{return false;}
}
namespace combat::submission {
bool Ready()noexcept{return true;}
bool RegisterAppendObserver(AppendObserverKind k,const AppendObserver&o)noexcept{if(k!=AppendObserverKind::group_chat)return false;observer=o;return true;}
}
}
int main(){try{
 const auto image=reinterpret_cast<std::uintptr_t>(VirtualAlloc(nullptr,0x16c0000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));Check(image!=0);
 Check(g::StartBound(image));Put(image+0x138bdbc,123);Put(image+0x16a2d98,image+0x1600000);Put(image+0x16ab88c,image+0x1601000);
 Put(image+0x1601000,image+0x116036c);Put(image+0x1601044,image+0x1602000);Put(image+0x1602000,image+0x114ce9c);
 Put(image+0x115dbcc,reinterpret_cast<std::uintptr_t>(Release));
 unsigned cases{};
 for(unsigned mode=0;mode<10;++mode){
  mode_now=mode;auto c=Context();g::State s;g::Receipt r;const auto a=allocations,b=sends;
  if(mode==1)current=false;
  if(mode==2)change_group=true;
  if(mode==3)transport=false;
  if(mode==4)append_current=false;
  if(mode==5)send_fault=true;
  if(mode==6){send_fault=true;transport=false;}
  if(mode==7)release_fault=true;
  if(mode==8)c.text[0]='/';
  if(mode==9)c.group.count=0;
  const auto result=g::InvokeBound(c,s,r,Calls());
  if(mode==0)Check(result.result==g::Result::queued&&result.native_entered&&result.append_observed&&!s.message&&!s.text_constructed);
  if(mode==1||mode==4||mode==8||mode==9)Check(result.result==g::Result::denied&&!result.native_entered&&allocations==a);
  if(mode==2)Check(result.result==g::Result::denied&&!result.native_entered&&sends==b&&!s.message&&!s.text_constructed);
  if(mode==3)Check(result.result==g::Result::uncertain&&result.native_entered&&!result.append_observed&&!s.message);
  if(mode==5||mode==6||mode==7)Check(result.ownership_quarantined&&s.quarantined&&result.result==g::Result::uncertain&&result.append_observed==(mode!=6));
  const auto sent=sends;const auto allocated=allocations;
  (void)g::InvokeBound(c,s,r,Calls());Check(sends==sent&&allocations==allocated&&g::active==nullptr);
  ++cases;
 }
 // An unrelated ordinary message is never claimed merely because a scope exists.
 auto c=Context();g::State s;g::Receipt r;auto calls=Calls();g::Scope scope(c,s,r,calls);
 unsigned unrelated{};Check(observer.claim(reinterpret_cast<void*>(c.container),&unrelated,0x2c6eb7).decision==sub::AppendDecision::unrelated);g::active=scope.previous;++cases;
 VirtualFree(reinterpret_cast<void*>(image),0,MEM_RELEASE);std::printf("%u group chat cases passed\n",cases);return 0;
}catch(const std::exception&e){std::fprintf(stderr,"%s\n",e.what());return 1;}}
