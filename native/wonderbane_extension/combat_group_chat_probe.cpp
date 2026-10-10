// Exact-image GroupChannelMessage constructor/queue probe.
// No game process or network. Core.dll strings, clock, transport and final
// destructor are named substitutes; real constructors/refcounts/queue execute.
#include <Windows.h>
#include <bcrypt.h>
#include <array>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>
struct Segment{unsigned rva,size;const char* hash;};
constexpr Segment segments[]{
{0x427e00,0x85,"fe6f5931f48b80eefed495e72328e43a2c3ae131b6dd87c0f87eaf2a54c5002b"},
{0x414100,0x7a,"020a479c8cb06e1a18ae8cfda6f28894df67a528fad4e47f80cf0c720721b982"},
{0x362060,0x97,"d82e83951c7b055da2b978d105c94b0a33040d8050b4da48e514a2e6e7953206"},
{0x111790,0x10,"9d20fb9737545d0eeb198c79dc5d325beabd6d570a4058d3f1e7f4a887df0403"},
{0x145000,0x15,"ffe1e81f55a49ab4bf41d36c87c6c8354c3e0cbf15aa0a6238551fa8d194a673"},
{0x145860,0x2d,"b9fc3b3861e98deb7d3ddad4bf53a69a1b4e4b21f3d8440f2018de20c0f12db4"},
{0x131190,0xd,"0d3ed09b1b254a1431ad870bad1528cc3fcde07a728f6cf621d6529201f91de5"},
{0x1311b0,0x24,"96e124d1f3bf74ce703626356fba6e0cf6b97535fb57b9ca2e8c985aa30ca63b"},
{0x414520,0x51,"8b8aed48516064b9af909cccbe4e90dd7fefb70d8171f15d9ee7cb6102e6bdaf"},
{0x7f4490,0x33,"a9b5138d3ed220c464eb586de242863e18bdf29935df0e97ee870cdc56dad534"},
{0x7f4da0,0x8e,"a85832da1fbfd197812fcd02e2728ce81bd425e5eb959e9221dfe1bc86dc57c1"},
{0xc540,0x5,"615c5fd38772c7054f00b0d79347670b313b7a4e698cca959341f6fdbc6ccc6c"},
{0x1e19b,0x5,"fb20738ae4d915146c7e48917d080aa94a419792d054b0cbef95eb6bd1f9c5b6"},
{0x22e30,0x5,"c4bfbf6e340d9f9a826f6e9007c24db10b73e714035b168d65ec8dec0b028603"},
{0x1cf76,0x5,"4773e698a3b0365d1c58ce3e16d3a13cb08521f982deee398ac25afe6d2154cd"},
{0x9674,0x5,"430e6f533f35f4ab216d1ae073b6f2c402f067616e0d896dd5c6274cf6f9f12f"},
{0xb2b7,0x5,"64c03dded86ce9f2b6b89075b5954e449701ee2bb83ac77f4fecf8c2195bf50f"},
{0x7dab,0x5,"0fde90202b6768789010f75c36699706d8e5cc8937a07090de2d5aca9f683c04"},
{0x5a65,0x5,"8d3809109e40eff446b1693d197bbd846a1d74aa6aed03ce9f02e93cbb24a4e9"},
{0x1b8e2,0x5,"62fffacfe55e1b6b932ba1d581a98c42f80d02db3b75b8881a7234c551c484c6"},
{0x23cb3,0x5,"51437f515e988923edf0497a63088d6a5bb422b277d8b8321a07560ba177575f"},
};
constexpr unsigned relocations[]{0x145005,0x145882,0x362066,0x36208a,0x3620e2,0x414106,0x41415d,0x414526,0x427e06,0x427e1c,0x427e69,0x7f4492,0x7f449f,0x7f44a7,0x7f44b1,0x7f44be,0x7f4da6};
namespace {
std::uintptr_t arena{}; unsigned forwarded{}, finalized{}, copies{};
std::array<unsigned, 0xb0/4> message{};
std::unordered_map<void*,std::wstring> strings;
void Require(bool v,const char* what){if(!v)throw std::runtime_error(what);}
std::string Hash(const unsigned char* p,std::size_t n){
 BCRYPT_ALG_HANDLE a{};BCRYPT_HASH_HANDLE h{};std::array<unsigned char,32>d{};
 Require(BCryptOpenAlgorithmProvider(&a,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0,"hash provider");
 Require(BCryptCreateHash(a,&h,nullptr,0,nullptr,0,0)>=0,"hash create");
 Require(BCryptHashData(h,const_cast<unsigned char*>(p),static_cast<ULONG>(n),0)>=0,"hash data");
 Require(BCryptFinishHash(h,d.data(),32,0)>=0,"hash finish");BCryptDestroyHash(h);BCryptCloseAlgorithmProvider(a,0);
 std::string out;for(auto b:d){out+="0123456789abcdef"[b>>4];out+="0123456789abcdef"[b&15];}return out;
}
void Put(unsigned r,std::uintptr_t v){*reinterpret_cast<unsigned*>(arena+r)=static_cast<unsigned>(v);}
void Jump(unsigned r,std::uintptr_t v){auto*p=reinterpret_cast<unsigned char*>(arena+r);*p=0xe9;auto x=static_cast<unsigned>(v-arena-r-5);std::memcpy(p+1,&x,4);}
EXCEPTION_DISPOSITION __cdecl Fault(EXCEPTION_RECORD*,void*,CONTEXT*,void*){std::fprintf(stderr,"foreign native exception\n");TerminateProcess(GetCurrentProcess(),3);return ExceptionContinueSearch;}
LONG CALLBACK Diagnostic(EXCEPTION_POINTERS* e){std::fprintf(stderr,"fault %08lx rva %08lx\n",e->ExceptionRecord->ExceptionCode,e->ContextRecord->Eip-static_cast<DWORD>(arena));return EXCEPTION_CONTINUE_SEARCH;}
void* __fastcall StringDefault(void*p,void*){std::memset(p,0,16);strings[p]=L"";return p;}
void* __fastcall StringAssign(void*p,void*,const void*other){Require(strings.contains(const_cast<void*>(other)),"unknown imported source string");strings[p]=strings.at(const_cast<void*>(other));++copies;return p;}
double __cdecl Clock(){return 123.0;}
LONG __cdecl Increment(volatile LONG*p){return InterlockedIncrement(p);}
LONG __cdecl Decrement(volatile LONG*p){return InterlockedDecrement(p);}
void __fastcall Finalize(void*p,void*,unsigned flags){Require(p==message.data()&&flags==1&&message[1]==0,"finalizer identity");++finalized;}
void* __fastcall Transport(void*p,void*){return *static_cast<void**>(p);}
void Release(void*p){using F=void(__thiscall*)(void*,void*);reinterpret_cast<F>(arena+0x1311b0)(p,&p);}
void __fastcall Network(void*writer,void*,void*p){
 Require(writer==reinterpret_cast<void*>(arena+0x1600000)&&p==message.data(),"transport identity");
 Require(message[1]==3,"caller/sender/transport refs");
 Require(message[0]==arena+0x115dbc4&&message[0x84/4]==14,"group type and channel");
 ++forwarded;Release(p);
}
}
int main(int argc,char**argv){try{
 Require(argc==2,"usage: group_message_probe exact-image");
 std::ifstream f(std::filesystem::path(argv[1]),std::ios::binary|std::ios::ate);auto n=f.tellg();Require(n>0&&n<64*1024*1024,"image size");
 std::vector<unsigned char>b(static_cast<std::size_t>(n));f.seekg(0);Require(static_cast<bool>(f.read(reinterpret_cast<char*>(b.data()),n)),"image read");
 const auto hash=Hash(b.data(),b.size());Require(hash=="a145ef491341e5107ec064de876d97f0e9c6ebbde2520d6509b4a3b47a7d825a"||hash=="1a5a9fd59da8255a3c98e16e1e8ff9a415c0921b4189583158c559ad2594360c","exact .16 required");
 arena=reinterpret_cast<std::uintptr_t>(VirtualAlloc(nullptr,0x16c0000,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));Require(arena!=0,"arena");
 std::memset(reinterpret_cast<void*>(arena),0xcc,0x1000000);AddVectoredExceptionHandler(0,Diagnostic);
 for(const auto&s:segments){Require(Hash(b.data()+s.rva,s.size)==s.hash,"primitive digest");std::memcpy(reinterpret_cast<void*>(arena+s.rva),b.data()+s.rva,s.size);}
 for(auto r:relocations){auto&v=*reinterpret_cast<unsigned*>(arena+r);v+=static_cast<unsigned>(arena)-0x400000;}
 for(auto r:{0x362066U,0x414106U,0x414526U,0x427e06U,0x7f4da6U})Put(r,reinterpret_cast<std::uintptr_t>(&Fault));
 Put(0x16b005c,reinterpret_cast<std::uintptr_t>(&StringDefault));Put(0x16b0070,reinterpret_cast<std::uintptr_t>(&StringAssign));
 Jump(0x46b0,reinterpret_cast<std::uintptr_t>(&Clock));Jump(0x1795e,reinterpret_cast<std::uintptr_t>(&Increment));Jump(0xbdc5,reinterpret_cast<std::uintptr_t>(&Decrement));
 Jump(0x7a09,reinterpret_cast<std::uintptr_t>(&Transport));Jump(0x14128,reinterpret_cast<std::uintptr_t>(&Network));
 Put(0x115dbc8,reinterpret_cast<std::uintptr_t>(&Finalize));Put(0x115dbcc,arena+0x1311b0);
 *reinterpret_cast<unsigned char*>(arena+0x16ab894)=1;
 DWORD old{};Require(VirtualProtect(reinterpret_cast<void*>(arena),0x1000000,PAGE_EXECUTE_READ,&old)!=FALSE,"protect");FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(arena),0x1000000);
 unsigned cases{};
 for(unsigned token:{1U,0x12345678U})for(bool available:{false,true})for(const auto&body:{std::wstring(),std::wstring(L"Hunt Foe: Alice, Bob"),std::wstring(120,L'A'),std::wstring(L"\u00c9owyn")}){
  message.fill(0xa5a5a5a5);strings.clear();std::array<unsigned,6>input{};strings[input.data()]=body;
  Put(0x138bdbc,token);Put(0x16ab88c,available?arena+0x1600000:0);
  const auto before=forwarded,before_final=finalized,before_copy=copies;
  using Ctor=void*(__thiscall*)(void*,const void*);auto*p=reinterpret_cast<Ctor>(arena+0x427e00)(message.data(),input.data());
  Require(p==message.data()&&message[1]==1&&message[0x10/4]==token,"real constructor ownership/token");
  Require(message[0x84/4]==14&&message[0]==arena+0x115dbc4,"real group constructor channel/vtable");
  Require(message[0x60/4]==0&&message[0x64/4]==0&&message[0x68/4]==0,"base response defaults");
  Require(strings.at(reinterpret_cast<unsigned char*>(p)+0x6c)==body&&copies==before_copy+1,"body passed through real ArcString wrapper");
  Require(message[0xa8/4]==0xa5a5a5a5,"constructor does not invent subtype field semantics");
  using Send=void(__thiscall*)(void*);reinterpret_cast<Send>(arena+0x414520)(p);
  Require(message[1]==1&&forwarded==before+(available?1:0),"normal send can silently drop without transport");
  Release(p);Require(message[1]==0&&finalized==before_final+1,"caller+queue references balance");++cases;
 }
 std::printf("{\"image_sha256\":\"%s\",\"cases\":%u,\"failures\":0,\"scope\":\"group_constructor_queue\",\"core_strings_substituted\":true,\"server_delivery_proven\":false}\n",hash.c_str(),cases);
 VirtualFree(reinterpret_cast<void*>(arena),0,MEM_RELEASE);return 0;
}catch(const std::exception&e){std::fprintf(stderr,"%s\n",e.what());return 1;}}
