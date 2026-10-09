// Offline exact-image probe: actual incoming branch/state6 setter and append
// callsite slices execute separately with matching synthetic Process frames.
// The intervening Process body and foreign native exception unwind are NOT run.
// No game process, initialization, producer, action, or network is invoked.
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
unsigned failures{},cases{},callbacks{},animation{},depth{},expected_activity=6;
unsigned char* image{};
enum class Fault { none,key,scene,vector_clear,vector_replace,state_pointer,reenter,exception } fault;
std::array<std::uint32_t,0xae0/4> actor{};
std::array<std::uint32_t,8> state{},alternate{},ids{},primary{},secondary{};
std::array<std::uint32_t,5> header{},node{},listener{},listener_table{};
std::array<std::uint32_t,0x300/4> message{},definition{},nested_message{};
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
// Recreates Process register ABI and its frame-local message pointer. The
// intervening Process body is intentionally not executed between these slices.
__declspec(naked) void __cdecl Incoming(void*,void*,void*,void*){
 __asm {
  push ebp
  mov ebp,esp
  push ebx
  push esi
  push edi
  sub esp,100h
  mov edx,[ebp+8]
  mov esi,[ebp+0ch]
  mov ecx,[ebp+10h]
  mov edi,[ebp+14h]
  lea eax,[esp+80h]
  mov [eax-28h],ecx
  mov [eax-24h],esi
  push ebp
  mov ebp,eax
  call edx
  pop ebp
  add esp,100h
  pop edi
  pop esi
  pop ebx
  pop ebp
  ret
 }
}
void Start(std::uint32_t* m){Incoming(image+0x38401b,actor.data(),m,definition.data());}
void Append(std::uint32_t* m){Incoming(image+0x38443b,actor.data(),m,definition.data());}
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
__declspec(naked) void __cdecl OwnedAppend(void*,void*,void*) {
    __asm {
        push ebp
        mov ebp,esp
        push ebx
        push esi
        push edi
        sub esp,40h
        mov edx,[ebp+8]
        mov ebx,[ebp+0ch]
        mov edi,[ebp+10h]
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
 Check(event[1]==Address(actor.data())&&event[2]==expected_activity,"native event actor/new-state arguments");
 if(!depth)callback_before_write=state[4]!=6;
 if(depth)return;
 switch(fault){
 case Fault::key:++actor[0x18/4];break;
 case Fault::scene:++scene;break;
 case Fault::vector_clear:actor[0x660/4]=actor[0x65c/4];break;
 case Fault::vector_replace:ids[0]=123;break;
 case Fault::state_pointer:actor[0xad0/4]=Address(alternate.data());break;
 case Fault::reenter:{++depth;nested=true;auto saved=expected_activity;expected_activity=6;Start(nested_message.data());Append(nested_message.data());expected_activity=saved;--depth;break;}
 case Fault::exception:RaiseException(0xe0420201,0,0,nullptr);break;
 default:break;
 }
}
bool Call() noexcept {
 __try{Start(message.data());return true;}
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
 message.fill(0);definition.fill(0);nested_message.fill(0);
 message[0xa4/4]=1;message[0xa8/4]=0;message[0x80/4]=429021400;nested_message=message;
 fault=mode;scene=3;callbacks=animation=depth=0;nested=callback_before_write=false;
}
}
int main(int argc,char** argv){try{
 AddVectoredExceptionHandler(1,[](EXCEPTION_POINTERS* p)->LONG{std::fprintf(stderr,"exception %08lx at %08lx relative %08lx\n",p->ExceptionRecord->ExceptionCode,p->ContextRecord->Eip,p->ContextRecord->Eip-Address(image));std::fflush(stderr);return EXCEPTION_CONTINUE_SEARCH;});
 if(argc!=2)throw std::runtime_error("usage: owned_power_completion_probe <exact original/prepared .15>");
 std::ifstream f(std::filesystem::path(argv[1]),std::ios::binary|std::ios::ate);auto n=f.tellg();
 if(!f||n<=0||n>64*1024*1024)throw std::runtime_error("invalid image");
 std::vector<unsigned char>b(static_cast<std::size_t>(n));f.seekg(0);if(!f.read(reinterpret_cast<char*>(b.data()),n))throw std::runtime_error("short image");
 const auto sha=Digest(b);if(sha!="381e67586b3c36b8ce1dcdb824439010d373d455aa6b460b02cf44f7d58fe9e5"&&sha!="e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437")throw std::runtime_error("unreviewed image");
 constexpr std::size_t size=0x1790000;
 image=static_cast<unsigned char*>(VirtualAlloc(nullptr,size,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));if(!image)throw std::runtime_error("arena allocation");
 std::memset(image,0xcc,size);
 for(auto span:{std::array<std::size_t,2>{0x3849ab,76},{0x384f1e,18},{0x385754,18},{0xd0b7,5},{0x9a140,92},{0x1eed4,5},{0x611d0,11},{0x176e3,5},{0x4bac0,32},{0x63198,16},{0x9e014,0x2b},{0x38401b,65},{0x38443b,27},{0x554c,5},{0x1bcb30,48},{0x258d3,5},{0x5f8c0,506},{0xd3b4,5},{0x44f840,159},{0x28065,5},{0x4520c0,184}})std::memcpy(image+span[0],b.data()+span[0],span[1]);
 const auto absent=Address(image+0x110);std::memset(image+0x110,0,4);std::memcpy(image+0x3849b9,&absent,4);
 void* (__cdecl* move)(void*,const void*,std::size_t)=&std::memmove;
 const auto copyfn=Address(reinterpret_cast<void*>(move));std::memcpy(image+0x108,&copyfn,4);
 const auto copyptr=Address(image+0x108);std::memcpy(image+0x9a17f,&copyptr,4);
 image[0x3849f7]=image[0x384a13]=image[0x384f30]=0xc3;
 image[0x631a8]=image[0x9e105]=0xc3;
 image[0x38405c]=image[0x384066]=image[0x38489f]=image[0x385766]=image[0x38460d]=image[0x384456]=0xc3;
 // Foreign C++ SEH handlers/metadata cannot unwind in this process; use a
 // transparent SEH search substitute and catch faults outside the call-through.
 for(auto at:{0x5f8c6U,0x44f846U,0x4520c6U}){const auto p=Address(reinterpret_cast<void*>(&UnwindPass));std::memcpy(image+at,&p,4);}
 Jump(0x1e8c1,reinterpret_cast<void*>(&Guard));Jump(0x26eb3,reinterpret_cast<void*>(&Unlock));Jump(0x7bee,reinterpret_cast<void*>(&Lock));
 Jump(0x6703,reinterpret_cast<void*>(&Reference));Jump(0xb2b7,reinterpret_cast<void*>(&Retain));Jump(0x1a64a,reinterpret_cast<void*>(&EventBase));Jump(0x119f0,reinterpret_cast<void*>(&EventDestroy));Jump(0x1c7b,reinterpret_cast<void*>(&Animate));
 DWORD old{};if(!VirtualProtect(image,size,PAGE_EXECUTE_READ,&old)||!FlushInstructionCache(GetCurrentProcess(),image,size))throw std::runtime_error("RX protection");
 for(unsigned prior:{5U,6U,7U})for(unsigned count:{0U,1U,2U,3U}){
  Reset(prior,count,Fault::none);const auto before=Capture();bool ok=Call();
  Check(ok&&state[4]==6&&callbacks==1,"incoming setter normal state/event ABI");
  Check(callback_before_write==(prior!=6),"event runs before state6 write");
  Check(actor[0x660/4]==before.end,"setter does not append");
  Append(message.data());
  Check(actor[0x660/4]==before.end+4&&ids[count]==message[0x80/4],"actual Process frame message ID appended including duplicates");++cases;
 }
 for(unsigned gate=0;gate<3;++gate){
  Reset(5,2,Fault::none);
  if(gate==0)message[0xa4/4]=2;
  if(gate==1)message[0xa8/4]=1;
  if(gate==2)definition[0x274/4]=1;
  Check(Call()&&state[4]==5&&callbacks==0,"flag/status/definition gate skips state6 setter");
  if(gate==2){Append(message.data());Check(ids[2]==message[0x80/4],"definition skip alone does not prohibit later append");}++cases;
 }
 for(bool same:{false,true}){
  Reset(5,1,Fault::reenter);if(!same)nested_message[0x80/4]=123;
  Check(Call()&&nested&&callbacks==2&&state[4]==6,"nested start completes during outer synchronous listener");
  Append(message.data());
  Check(actor[0x660/4]==Address(ids.data()+3)&&ids[1]==nested_message[0x80/4]&&ids[2]==message[0x80/4],"nested append precedes outer append even with same IDs");++cases;
 }
 Reset(5,2,Fault::exception);Check(!Call()&&state[4]==5&&actor[0x660/4]==Address(ids.data()+2),"exception does not prove completed start/append");++cases;
 Reset(5,2,Fault::none);Check(Call(),"normal setter before different append message");message[0x80/4]=123;Append(message.data());Check(ids[2]==123,"append reads message at append time; setter itself has no power ID binding");++cases;
 for(bool later_manual:{false,true}){
  Reset(5,0,Fault::none);expected_activity=6;definition[0x138/4]=429021400;
  OwnedAppend(image+0x9e014,actor.data(),definition.data());
  Check(ids[0]==429021400&&actor[0x660/4]==Address(ids.data()+1),"real owned followup append creates first protocol record");
  Check(Call()&&state[4]==6,"normal incoming state6 after owned followup");Append(message.data());
  Check(ids[1]==429021400&&actor[0x660/4]==Address(ids.data()+2),"same-power incoming start appends another retained ID");
  expected_activity=7;MoveCall(image+0x63198,actor.data());
  Check(state[4]==7&&ids[0]==429021400&&ids[1]==429021400&&actor[0x660/4]==Address(ids.data()+2),"actual movement changes activity while preserving both protocol IDs");
  if(later_manual){expected_activity=6;message[0x80/4]=123;Start(message.data());Append(message.data());
   Check(state[4]==6&&ids[2]==123&&actor[0x660/4]==Address(ids.data()+3),"later manual activation remains independently present; no cleanup invoked");}
  ++cases;
 }
 for(unsigned retained:{0U,1U,2U}){
  Reset(5,retained,Fault::none);expected_activity=6;definition[0x138/4]=429021400;
  OwnedAppend(image+0x9e014,actor.data(),definition.data());Check(Call(),"incoming start");Append(message.data());
  expected_activity=5;Incoming(image+0x3849ab,actor.data(),message.data(),definition.data());
  Check(state[4]==5&&actor[0x660/4]==Address(ids.data()+retained+2),"completion setter6-to5 precedes removals and preserves duplicates");
  Incoming(image+0x384f1e,actor.data(),message.data(),definition.data());
  Check(actor[0x660/4]==Address(ids.data()+retained+1),"first completion remover decrements one");
  Incoming(image+0x385754,actor.data(),message.data(),definition.data());
  Check(actor[0x660/4]==Address(ids.data()+retained),"shared completion tail removes second; historical IDs may remain");++cases;
 }
 Reset(7,2,Fault::none);expected_activity=5;Incoming(image+0x3849ab,actor.data(),message.data(),definition.data());
 Check(state[4]==7&&!callbacks,"completion setter gate does not reset already-moving activity");
 Incoming(image+0x384f1e,actor.data(),message.data(),definition.data());Incoming(image+0x385754,actor.data(),message.data(),definition.data());
 Check(state[4]==7&&actor[0x660/4]==Address(ids.data()),"late completion removers do not prove state5");++cases;
 for(bool same_id:{false,true}){
 Reset(6,2,Fault::reenter);nested_message[0x80/4]=same_id?429021400:123;expected_activity=5;
 Incoming(image+0x3849ab,actor.data(),message.data(),definition.data());
 Check(nested&&callbacks==2&&state[4]==5&&ids[2]==nested_message[0x80/4],"nested newer start can be overwritten by outer state5 write; state alone is insufficient");
 fault=Fault::none;Incoming(image+0x384f1e,actor.data(),message.data(),definition.data());Incoming(image+0x385754,actor.data(),message.data(),definition.data());
 Check(actor[0x660/4]==Address(ids.data()+1)&&ids[0]==nested_message[0x80/4],"native removers leave later manual initiation including identical ID; observer must reject superseded association");++cases;
 }
 std::printf("{\"image_sha256\":\"%s\",\"cases\":%u,\"failures\":%u,\"scope\":\"owned_start_and_normal_completion_slices\",\"full_process_bridge_executed\":false,\"server_failure_proven\":false}\n",sha.c_str(),cases,failures);
 VirtualFree(image,0,MEM_RELEASE);return failures?1:0;
 }catch(const std::exception& e){std::fprintf(stderr,"%s\n",e.what());return 2;}}
