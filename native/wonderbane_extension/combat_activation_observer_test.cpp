// Required hooks with real entry trampoline/VEH and explicit native-body fixtures.
// This does not execute the full game message handler or create a game process.
#include "combat_activation_observer.cpp"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>
#include <cstdio>
#include <bcrypt.h>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>
namespace a=wonderbane::extension::combat::activation;
namespace m=wonderbane::extension::movement;
namespace {
std::string Digest(const std::vector<unsigned char>& b){
 BCRYPT_ALG_HANDLE a{};BCRYPT_HASH_HANDLE h{};std::array<unsigned char,32>d{};
 bool ok=BCryptOpenAlgorithmProvider(&a,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0
 &&BCryptCreateHash(a,&h,nullptr,0,nullptr,0,0)>=0
 &&BCryptHashData(h,const_cast<unsigned char*>(b.data()),static_cast<ULONG>(b.size()),0)>=0
 &&BCryptFinishHash(h,d.data(),32,0)>=0;
 if(h)BCryptDestroyHash(h);if(a)BCryptCloseAlgorithmProvider(a,0);
 if(!ok)throw std::runtime_error("digest failed");
 const char* hex="0123456789abcdef";std::string s;for(auto c:d){s+=hex[c>>4];s+=hex[c&15];}return s;
}
m::NativeScene scene{};bool live=true;unsigned calls{},callback_depth{},mode{},inner_result{};
std::array<std::uint32_t,0xb00/4> actor{};
std::array<std::uint32_t,12> state{},replacement_state{},ids{};
std::array<std::uint32_t,0x300/4> definition{};
std::array<std::uint32_t,0xb0/4> message{},manual{};
a::Handle owned{};bool recurse{},exception{},native_false{},mutate_use{},replace_tail{},manual_send{},direct_followup{},nested_activity{},direct_fault{};
std::uint32_t Address(const void* p){return static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(p));}
std::uint32_t Enter(void* value){return reinterpret_cast<a::Process>(a::base+0x382df0)(value);}
void* __fastcall Setter(void*,void*,void** out,bool publish,std::uint32_t value,bool no_message){
 assert(publish&&!no_message);*out=nullptr;
 if(recurse&&!callback_depth){++callback_depth;const auto saved=mode;mode=0;
  a::ForeignItemSend(Address(actor.data()));inner_result=Enter(manual.data());mode=saved;--callback_depth;}
 if(exception){RaiseException(0xe0420301,0,0,nullptr);}
 state[4]=value;return out;
}
void __fastcall Append(void* vector,void*,const std::uint32_t* value){auto* v=static_cast<std::uint32_t*>(vector);assert(v[1]<v[2]);*reinterpret_cast<std::uint32_t*>(v[1])=*value;v[1]+=4;}
bool __fastcall Remove(void* value,void*,std::uint32_t id){auto* actor_value=static_cast<std::uint32_t*>(value);auto* first=reinterpret_cast<std::uint32_t*>(actor_value[0x65c/4]);auto* last=reinterpret_cast<std::uint32_t*>(actor_value[0x660/4]);
 for(auto* p=first;p<last;++p){if(*p==id){std::memmove(p,p+1,static_cast<std::size_t>(last-p-1)*4);actor_value[0x660/4]-=4;return true;}}return false;}
std::uint32_t __cdecl NativeBody(void* input){
 ++calls;auto* msg=static_cast<std::uint32_t*>(input);assert(msg==message.data()||msg==manual.data());
 std::array<std::uint32_t,64> frame{};const auto fp=Address(frame.data()+40);frame[30]=Address(msg);frame[31]=Address(actor.data());void* output{};
 a::routed={mode?0x3849f2U:0x384057U,fp,Address(definition.data()),reinterpret_cast<std::uintptr_t>(&Setter)};
 a::StateHook(actor.data(),nullptr,&output,true,mode?5:6,false);
 if(!mode){a::Route(0x384451,fp,reinterpret_cast<std::uintptr_t>(&Append));a::AppendHook(actor.data()+0x65c/4,nullptr,msg+0x80/4);
  assert(a::Read(owned)!=a::Result::active);}
 else {a::Route(0x384f2b,fp,reinterpret_cast<std::uintptr_t>(&Remove));(void)a::RemovalHook(actor.data(),nullptr,msg[0x80/4]);
  a::Route(0x385761,fp,reinterpret_cast<std::uintptr_t>(&Remove));(void)a::RemovalHook(actor.data(),nullptr,msg[0x80/4]);
  assert(a::Read(owned)!=a::Result::completed);if(mode==2){RaiseException(0xe0420302,0,0,nullptr);}}
 if(replace_tail){replacement_state=state;actor[0xad0/4]=Address(replacement_state.data());}
 SetLastError(734);return 0x13579;
}
bool TryEnter() noexcept {__try {(void)Enter(message.data());return true;}__except(EXCEPTION_EXECUTE_HANDLER){return false;}}
void __cdecl ManualFollowup(void*,void*,void*,int){
 const auto n=(actor[0x660/4]-actor[0x65c/4])/4;ids[n]=111;actor[0x660/4]+=4;state[4]=6;
 if(nested_activity){a::OtherActivity(Address(actor.data()));}
 if(direct_fault){RaiseException(0xe0420303,0,0,nullptr);}
 SetLastError(841);
}
bool __cdecl Ordinary(std::uint32_t,int,void*,void*,const float*,std::array<std::uint32_t,2>){if(mutate_use){a::ForeignPowerUse(Address(actor.data()));}if(manual_send){a::ForeignPowerUse(Address(actor.data()));a::RecordManualPowerSend(Address(actor.data()),111);if(direct_followup){a::ObserveManualFollowup(reinterpret_cast<std::uintptr_t>(&ManualFollowup),actor.data(),nullptr,definition.data(),1);}}SetLastError(913);return !native_false;}
bool TryOrdinary() noexcept {__try {(void)a::ObserveOrdinaryPower(reinterpret_cast<std::uintptr_t>(&Ordinary),111,1,actor.data(),nullptr,nullptr,{91,53});return true;}__except(EXCEPTION_EXECUTE_HANDLER){return false;}}
void Reset(unsigned count=0){if(a::bound.Valid()){assert(a::ResetExactLifetime(a::bound));}actor.fill(0);state.fill(0);ids.fill(0);definition.fill(0);message.fill(0);manual.fill(0);
 scene={Address(actor.data()),1,2,3,{91,53},7};actor[6]=91;actor[7]=53;actor[0xad0/4]=Address(state.data());state[4]=5;state[6]=1;
 actor[0x65c/4]=Address(ids.data());actor[0x660/4]=Address(ids.data()+count);actor[0x664/4]=Address(ids.data()+ids.size());for(auto& id:ids){id=111;}
 *reinterpret_cast<std::uintptr_t*>(a::base+0x16a2d98)=Address(actor.data());definition[0x138/4]=111;
 message[0]=static_cast<std::uint32_t>(a::base+0x1155fd8);message[0x80/4]=111;message[0x88/4]=91;message[0x8c/4]=53;message[0xa4/4]=1;manual=message;
 live=true;calls=callback_depth=mode=inner_result=0;recurse=exception=mutate_use=replace_tail=manual_send=direct_followup=nested_activity=direct_fault=false;native_false=true;
 owned=a::Arm(0,{Address(actor.data()),{91,53},7},111,a::ActivationOrigin::self_power);assert(owned);a::RecordReturn(owned,true,true);
}
void Complete(unsigned variant=1){mode=variant;message[0xa4/4]=2;(void)Enter(message.data());}
void Move(){void* output{};a::routed={0x631a3,0,0,reinterpret_cast<std::uintptr_t>(&Setter)};a::StateHook(actor.data(),nullptr,&output,true,7,false);}
}
namespace wonderbane::extension::movement {
bool ReadNativeMovementLifetime(NativeScene& out)noexcept {out=scene;return live;}
bool NativeMovementLifetimeCurrent(const NativeScene& s)noexcept{return live&&s.epoch==scene.epoch&&s.actor==scene.actor&&s.identity==scene.identity;}
}
int main(int argc,char** argv){
 auto* arena=static_cast<unsigned char*>(VirtualAlloc(nullptr,0x1800000,MEM_RESERVE|MEM_COMMIT,PAGE_EXECUTE_READWRITE));assert(arena);
 std::vector<unsigned char> original;
 if(argc==2){
  std::ifstream f(std::filesystem::path(argv[1]),std::ios::binary|std::ios::ate);const auto n=f.tellg();
  if(!f||n<=0||n>64*1024*1024){return 2;}
  original.resize(static_cast<std::size_t>(n));f.seekg(0);if(!f.read(reinterpret_cast<char*>(original.data()),n)){return 2;}
  const auto sha=Digest(original);
  if(sha!="381e67586b3c36b8ce1dcdb824439010d373d455aa6b460b02cf44f7d58fe9e5"&&sha!="e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437"){return 2;}
  for(const auto& site:a::sites){assert(original.size()>site.rva+5);assert(!std::memcmp(original.data()+site.rva,site.bytes.data(),5));}
 }else if(argc!=1){return 2;}
 for(const auto& site:a::sites){std::memcpy(arena+site.rva,original.empty()?site.bytes.data():original.data()+site.rva,5);}
 // Real copied native prologue runs in trampoline. Named synthetic continuation
 // calls NativeBody, then performs matching ordinary epilogue. No foreign SEH table.
 auto* code=arena+0x382df5;code[0]=0x51;code[1]=0xe8;const auto target=reinterpret_cast<std::uintptr_t>(&NativeBody)-reinterpret_cast<std::uintptr_t>(code+6);const auto rel=static_cast<std::uint32_t>(target);std::memcpy(code+2,&rel,4);
 const unsigned char end[]{0x83,0xc4,0x04,0x8b,0xe5,0x5d,0xc3};std::memcpy(code+6,end,sizeof(end));FlushInstructionCache(GetCurrentProcess(),arena,0x1800000);
 assert(a::StartBound(reinterpret_cast<std::uintptr_t>(arena)));unsigned cases{};
 for(unsigned old:{0U,1U,2U}){Reset(old);assert(Enter(message.data())==0x13579&&GetLastError()==734);assert(a::Read(owned)==a::Result::active);Complete();assert(a::Read(owned)==a::Result::completed);++cases;}
 Reset(1);Enter(message.data());Move();assert(a::Read(owned)==a::Result::interrupted);a::ForeignItemSend(Address(actor.data()));assert(a::Read(owned)==a::Result::interrupted);++cases;
 Reset(1);Enter(message.data());mode=2;message[0xa4/4]=2;assert(!TryEnter());assert(a::Read(owned)==a::Result::unknown);++cases;
 // Same process stack/message address after exception cannot resurrect old proof.
 mode=1;assert(TryEnter());assert(a::Read(owned)==a::Result::unknown);++cases;
 Reset(1);Enter(message.data());recurse=true;Complete();assert(inner_result==0x13579&&a::Read(owned)==a::Result::unknown);++cases;
 Reset();exception=true;assert(!TryEnter());assert(a::Read(owned)==a::Result::unknown);++cases;
 Reset();Enter(message.data());assert(!a::ObserveOrdinaryPower(reinterpret_cast<std::uintptr_t>(&Ordinary),111,1,actor.data(),nullptr,nullptr,{91,53}));assert(GetLastError()==913&&a::Read(owned)==a::Result::active);Complete();assert(a::Read(owned)==a::Result::completed);++cases;
 Reset();Enter(message.data());mutate_use=true;assert(!a::ObserveOrdinaryPower(reinterpret_cast<std::uintptr_t>(&Ordinary),111,1,actor.data(),nullptr,nullptr,{91,53}));assert(a::Read(owned)==a::Result::unknown);++cases;
 Reset();const auto first=owned;live=false;assert(a::Read(first)==a::Result::unknown);live=true;scene.epoch=8;assert(a::Read(first)==a::Result::unknown);++cases;
 // Trampoline is below optional vtable wrapper; layering retains identical result.
 Reset();using Optional=std::uint32_t(*)(void*);Optional optional=[](void* msg){const auto out=Enter(msg);assert(GetLastError()==734);return out;};assert(optional(message.data())==0x13579);++cases;
 Reset();owned=a::Arm(0,owned.identity,111,a::ActivationOrigin::self_power);a::RecordReturn(owned,false,false);Enter(message.data());assert(a::Read(owned)==a::Result::unknown);++cases;
 Reset();auto token=a::BeginOwnedFollowup(owned);state[4]=6;a::OwnedFollowupReturned(owned,token,true,true);Move();assert(a::Read(owned)==a::Result::interrupted);++cases;
 Reset();replace_tail=true;Enter(message.data());assert(a::Read(owned)==a::Result::unknown);++cases;
 Reset();Enter(message.data());replace_tail=true;Complete();assert(a::Read(owned)==a::Result::unknown);++cases;
 Reset(1);Enter(message.data());manual_send=true;native_false=false;
 assert(a::ObserveOrdinaryPower(reinterpret_cast<std::uintptr_t>(&Ordinary),111,1,actor.data(),nullptr,nullptr,{91,53}));
 assert(a::Read(owned)==a::Result::unknown);Enter(message.data());assert(a::Read(owned)==a::Result::relinquished);++cases;
 // Later ordinary activity cannot convert local handoff into application terminal.
 assert(a::history.Read(owned.slot).phase==a::ActivationPhase::unknown);++cases;
 Reset();Enter(message.data());manual_send=true;native_false=false;
 a::ObserveOrdinaryPower(reinterpret_cast<std::uintptr_t>(&Ordinary),111,1,actor.data(),nullptr,nullptr,{91,53});
 replace_tail=true;Enter(message.data());assert(a::Read(owned)==a::Result::unknown);++cases;
 Reset();Enter(message.data());manual_send=true;native_false=false;
 a::ObserveOrdinaryPower(reinterpret_cast<std::uintptr_t>(&Ordinary),111,1,actor.data(),nullptr,nullptr,{91,53});
 exception=true;assert(!TryEnter());assert(a::Read(owned)==a::Result::unknown);++cases;
 Reset();Enter(message.data());a::RecordManualPowerSend(Address(actor.data()),111);Enter(message.data());
 assert(a::Read(owned)!=a::Result::relinquished);++cases;
 Reset(1);Enter(message.data());manual_send=direct_followup=true;native_false=false;
 assert(a::ObserveOrdinaryPower(reinterpret_cast<std::uintptr_t>(&Ordinary),111,1,actor.data(),nullptr,nullptr,{91,53}));
 assert(a::Read(owned)==a::Result::relinquished&&a::history.Read(owned.slot).phase==a::ActivationPhase::unknown);++cases;
 Reset(1);Enter(message.data());manual_send=direct_followup=nested_activity=true;native_false=false;
 a::ObserveOrdinaryPower(reinterpret_cast<std::uintptr_t>(&Ordinary),111,1,actor.data(),nullptr,nullptr,{91,53});
 assert(a::Read(owned)==a::Result::unknown);++cases;
 Reset(1);Enter(message.data());manual_send=direct_followup=direct_fault=true;native_false=false;
 assert(!TryOrdinary());assert(a::Read(owned)==a::Result::unknown&&a::ordinary_frame==nullptr);++cases;
 Reset();Enter(message.data());a::ForeignPowerUse(0);Enter(message.data());assert(a::Read(owned)!=a::Result::relinquished);++cases;
 Reset();Enter(message.data());Complete();manual_send=direct_followup=true;native_false=false;
 a::ObserveOrdinaryPower(reinterpret_cast<std::uintptr_t>(&Ordinary),111,1,actor.data(),nullptr,nullptr,{91,53});
 assert(a::Read(owned)==a::Result::completed);++cases;
 for(const auto& site:a::sites){
  DWORD stack[4]{};CONTEXT c{};EXCEPTION_RECORD r{};EXCEPTION_POINTERS e{&r,&c};
  const auto address=a::base+site.rva;r.ExceptionCode=EXCEPTION_BREAKPOINT;r.ExceptionAddress=reinterpret_cast<void*>(address);
  c.Eip=static_cast<DWORD>(address);c.Esp=Address(stack+2);c.Eax=11;c.Ebx=22;c.Ecx=33;c.Edx=44;c.Esi=55;c.Edi=66;c.Ebp=77;c.EFlags=0x246;
  SetLastError(571);assert(a::Trap(&e)==EXCEPTION_CONTINUE_EXECUTION);
  assert(c.Eax==11&&c.Ebx==22&&c.Ecx==33&&c.Edx==44&&c.Esi==55&&c.Edi==66&&c.Ebp==77&&c.EFlags==0x246&&GetLastError()==571);
  if(site.rva==0x382df0){assert(c.Esp==Address(stack+2)&&c.Eip==Address(reinterpret_cast<void*>(&a::ProcessHook)));}
  else {assert(c.Esp==Address(stack+1)&&stack[1]==address+5&&c.Eip==Address(reinterpret_cast<void*>(&a::StateHook)));}
  ++cases;
 }
 assert(a::StartBound(a::base)&&!a::StartBound(a::base+4));++cases;
 std::vector<std::uint8_t> disk(0x3849f7-0x631a3),patched;
 for(const auto& site:a::sites){std::copy(site.bytes.begin(),site.bytes.end(),disk.begin()+site.rva-0x631a3);}
 patched=disk;for(const auto& site:a::sites){patched[site.rva-0x631a3]=0xcc;}
 assert(a::NormalizeOwnedCode(a::base,0x631a3,patched,disk)&&patched==disk);++cases;
 patched=disk;for(const auto& site:a::sites){patched[site.rva-0x631a3]=0xcc;}patched.back()^=1;
 assert(!a::NormalizeOwnedCode(a::base,0x631a3,patched,disk));++cases;
 std::printf("%u activation observer cases passed\n",cases);return 0;
}
