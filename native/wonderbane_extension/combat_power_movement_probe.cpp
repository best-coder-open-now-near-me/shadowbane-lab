// Offline exact-image probe. No process is opened; no client initialization runs.
// Actual movement CALL, state setter, CharacterActivityEvent constructor, and
// synchronous listener traversal execute in a private RX arena. Reference/lock,
// event-base/destructor, and animation services are named substitutes below.
#include <Windows.h>
#include <bcrypt.h>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>
static_assert(sizeof(void*)==4);
namespace {
unsigned failures{},cases{},callbacks{},animation{},depth{};
unsigned char* image{};
enum class Fault { none,key,scene,vector_clear,vector_replace,state_pointer,reenter,exception } fault;
std::array<std::uint32_t,0xae0/4> actor{};
std::array<std::uint32_t,8> state{},alternate{},ids{},primary{},secondary{};
std::array<std::uint32_t,5> header{},node{},listener{},listener_table{};
std::uint64_t scene=3;
bool nested{},callback_before_write{};
std::uint32_t Address(const void* p){return static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(p));}
void Check(bool ok,const char* why){if(!ok){++failures;std::fprintf(stderr,"%s\n",why);}}
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
void Jump(std::size_t at,const void* fn){image[at]=0xe9;auto rel=Address(fn)-Address(image+at)-5;std::memcpy(image+at+1,&rel,4);}
void* __fastcall Guard(void** self,void*,void* value){*self=value;return self;}
void __fastcall Unlock(void*,void*){}
void __fastcall Lock(void*,void*){}
void* __fastcall Reference(void** self,void*,void* value){*self=value;return self;}
void __fastcall Retain(void*,void*,void**){}
void __fastcall Release(void*,void*,void** holder){*holder=nullptr;}
void* __fastcall EventBase(std::uint32_t* self,void*,void* value){self[1]=Address(value);return self;}
void __fastcall EventDestroy(void*,void*){}
void __fastcall Animate(void*,void*){++animation;}
EXCEPTION_DISPOSITION __cdecl UnwindPass(EXCEPTION_RECORD*,void*,CONTEXT*,void*){return ExceptionContinueSearch;}
// The exact movement slice supplies its original arguments/register ABI. Only
// its continuation is replaced with RET, so no later network/movement code runs.
__declspec(naked) void __cdecl MoveCall(void*,void*){
 __asm {
  push ebp
  mov ebp,esp
  push ebx
  push esi
  push edi
  sub esp,40h
  mov edx,dword ptr [ebp+8]
  mov esi,dword ptr [ebp+0ch]
  xor ebx,ebx
  lea eax,[esp+10h]
  push ebp
  mov ebp,eax
  call edx
  pop ebp
  add esp,40h
  pop edi
  pop esi
  pop ebx
  pop ebp
  ret
 }
}
void __fastcall Listener(void*,void*,const std::uint32_t* event){
 ++callbacks;
 Check(event[1]==Address(actor.data())&&event[2]==7,"native event actor/new-state arguments");
 if(!depth)callback_before_write=state[4]!=7;
 if(depth)return;
 switch(fault){
 case Fault::key:++actor[0x18/4];break;
 case Fault::scene:++scene;break;
 case Fault::vector_clear:actor[0x660/4]=actor[0x65c/4];break;
 case Fault::vector_replace:ids[0]=123;break;
 case Fault::state_pointer:actor[0xad0/4]=Address(alternate.data());break;
 case Fault::reenter:++depth;nested=true;MoveCall(image+0x63198,actor.data());--depth;break;
 case Fault::exception:RaiseException(0xe0420201,0,0,nullptr);break;
 default:break;
 }
}
bool Call() noexcept {
 __try{MoveCall(image+0x63198,actor.data());return true;}
 __except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
struct Facts{
 std::uint32_t actor_address,key0,key1,state_address,state_value,begin,end,capacity,id;
 std::uint64_t scene_epoch;
};
Facts Capture(){
 const auto p=actor[0xad0/4];
 return {Address(actor.data()),actor[6],actor[7],p,*reinterpret_cast<std::uint32_t*>(p+0x10),
 actor[0x65c/4],actor[0x660/4],actor[0x664/4],ids[0],scene};
}
// Testable observer contract, not production authorization or server outcome.
bool Interrupted(const Facts& a,const Facts& b,bool returned){
 return returned&&!nested&&a.actor_address==b.actor_address&&a.key0==b.key0&&a.key1==b.key1
 &&a.scene_epoch==b.scene_epoch&&a.state_address==b.state_address&&a.state_value==6&&b.state_value==7
 &&a.begin==b.begin&&a.end==b.end&&a.capacity==b.capacity&&a.end==a.begin+4&&a.id==b.id;
}
void Reset(unsigned initial,unsigned count,Fault mode){
 actor.fill(0);state.fill(0);alternate.fill(0);ids.fill(0);primary.fill(0);secondary.fill(0);
 header.fill(0);node.fill(0);listener.fill(0);listener_table.fill(0);
 primary[2]=Address(reinterpret_cast<void*>(&Release));secondary[1]=static_cast<std::uint32_t>(-8);
 actor[0]=Address(primary.data());actor[2]=Address(secondary.data());actor[6]=4050960;actor[7]=53;
 actor[0xad0/4]=Address(state.data());state[4]=initial;alternate[4]=6;
 ids[0]=ids[1]=429021400;actor[0x65c/4]=Address(ids.data());actor[0x660/4]=Address(ids.data()+count);actor[0x664/4]=Address(ids.data()+ids.size());
 // Native event dispatcher's exact one-node ordered listener container.
 header[1]=header[2]=header[3]=Address(node.data());node[1]=Address(header.data());node[4]=Address(listener.data());
 listener[0]=Address(listener_table.data());listener_table[1]=Address(reinterpret_cast<void*>(&Listener));
 actor[(0x48+0x14)/4]=Address(header.data());
 fault=mode;scene=3;callbacks=animation=depth=0;nested=callback_before_write=false;
}
}
int main(int argc,char** argv){try{
 AddVectoredExceptionHandler(1,[](EXCEPTION_POINTERS* p)->LONG{std::fprintf(stderr,"exception %08lx at %08lx relative %08lx\n",p->ExceptionRecord->ExceptionCode,p->ContextRecord->Eip,p->ContextRecord->Eip-Address(image));std::fflush(stderr);return EXCEPTION_CONTINUE_SEARCH;});
 if(argc!=2)throw std::runtime_error("usage: movement_transition_probe <exact original/prepared .15>");
 std::ifstream f(std::filesystem::path(argv[1]),std::ios::binary|std::ios::ate);auto n=f.tellg();
 if(!f||n<=0||n>64*1024*1024)throw std::runtime_error("invalid image");
 std::vector<unsigned char>b(static_cast<std::size_t>(n));f.seekg(0);if(!f.read(reinterpret_cast<char*>(b.data()),n))throw std::runtime_error("short image");
 const auto sha=Digest(b);if((sha!="381e67586b3c36b8ce1dcdb824439010d373d455aa6b460b02cf44f7d58fe9e5" && sha!="a145ef491341e5107ec064de876d97f0e9c6ebbde2520d6509b4a3b47a7d825a")&&(sha!="e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437" && sha!="1a5a9fd59da8255a3c98e16e1e8ff9a415c0921b4189583158c559ad2594360c"))throw std::runtime_error("unreviewed image");
 constexpr std::size_t size=0x453000;
 image=static_cast<unsigned char*>(VirtualAlloc(nullptr,size,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));if(!image)throw std::runtime_error("arena allocation");
 std::memset(image,0xcc,size);
 for(auto span:{std::array<std::size_t,2>{0x63198,16},{0x258d3,5},{0x5f8c0,506},{0xd3b4,5},{0x44f840,159},{0x28065,5},{0x4520c0,184}})std::memcpy(image+span[0],b.data()+span[0],span[1]);
 image[0x631a8]=0xc3;
 // Foreign C++ SEH handlers/metadata cannot unwind in this process; use a
 // transparent SEH search substitute and catch faults outside the call-through.
 for(auto at:{0x5f8c6U,0x44f846U,0x4520c6U}){const auto p=Address(reinterpret_cast<void*>(&UnwindPass));std::memcpy(image+at,&p,4);}
 Jump(0x1e8c1,reinterpret_cast<void*>(&Guard));Jump(0x26eb3,reinterpret_cast<void*>(&Unlock));Jump(0x7bee,reinterpret_cast<void*>(&Lock));
 Jump(0x6703,reinterpret_cast<void*>(&Reference));Jump(0xb2b7,reinterpret_cast<void*>(&Retain));Jump(0x1a64a,reinterpret_cast<void*>(&EventBase));Jump(0x119f0,reinterpret_cast<void*>(&EventDestroy));Jump(0x1c7b,reinterpret_cast<void*>(&Animate));
 DWORD old{};if(!VirtualProtect(image,size,PAGE_EXECUTE_READ,&old)||!FlushInstructionCache(GetCurrentProcess(),image,size))throw std::runtime_error("RX protection");
 for(unsigned prior:{4U,5U,6U,7U,8U})for(unsigned count:{0U,1U,2U}){
  Reset(prior,count,Fault::none);const auto before=Capture();bool ok=Call();const auto after=Capture();
  Check(ok&&after.state_value==7&&callbacks==1,"native movement setter state/event completion");
  Check(callback_before_write==(prior!=7),"synchronous event precedes native state write");
  Check(Interrupted(before,after,ok)==(prior==6&&count==1),"exact single active initiation transition contract");
  Check(before.begin==after.begin&&before.end==after.end&&before.id==after.id,"ordinary movement does not itself remove protocol ID");++cases;
 }
 for(auto mode:{Fault::key,Fault::scene,Fault::vector_clear,Fault::vector_replace,Fault::state_pointer,Fault::reenter,Fault::exception}){
  Reset(6,1,mode);auto before=Capture();bool ok=Call();auto after=Capture();
  Check(!Interrupted(before,after,ok),"changed/reentered/faulted transition must remain unknown");
  if(mode==Fault::exception)Check(!ok&&after.state_value==6,"listener exception cannot count as completed movement");
  ++cases;
 }
 std::printf("{\"image_sha256\":\"%s\",\"cases\":%u,\"failures\":%u,\"scope\":\"actual_movement_call_state_setter_and_event_dispatch\",\"native_protocol_removal_proven\":false,\"server_failure_proven\":false}\n",sha.c_str(),cases,failures);
 VirtualFree(image,0,MEM_RELEASE);return failures?1:0;
 }catch(const std::exception& e){std::fprintf(stderr,"%s\n",e.what());return 2;}}
