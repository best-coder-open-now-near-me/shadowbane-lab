// Offline exact .14 decoder call-through. Synthetic stream supplies decoded scalars;
// only the power-ID dictionary helper is instrumented. No live client/network.
// Full process/destructor bodies are fingerprinted, not executed as gameplay.
#define main SyntheticFixtureMain
#include "item_application_trace_test.cpp"
#undef main
#include <filesystem>
#include <fstream>
#include <iostream>
namespace {
std::string Sha(const unsigned char* bytes,std::size_t size){
    w::Digest digest{};Check(wonderbane::extension::actor::fence::Hash(bytes,size,digest),"SHA256");
    constexpr char hex[]="0123456789abcdef";std::string result;for(auto value:digest){result+=hex[value>>4];result+=hex[value&15];}return result;
}
struct Segment{unsigned rva,size;const char* sha;};
constexpr Segment segments[]{{0x375180,0x60,"844ccda983f47d736ed5566063f37f224b907973291ab0fc2f2e7182feb74dac"},
{0x386380,0x8a,"45f5a6693947fd145237fce1afb406591537068809b8918e1668a3ff3074f86f"},
{0x374fa0,0x17d,"1c1239c9d2196984839ddab651333f1e894cbe85f1d4dfc38eb0d1514966638b"},
{0x382df0,0x2a92,"43f31f774e4ab9c420917bb2bcbd75df811cf794b4a2ea1bdba6f96f40c1b670"},
{0x374da0,0x20,"83bca94f70601235fe4be7665dcdf32674389e675dde4a46df5192b8713020d0"},
{0x382a60,0x20,"6dccfc4768e7df9ad8e80fe8e064be0f19e2a17f53078ebec1997aa951fd5066"},
{0x6cf3,0x5,"0a331a0c69df392b51e4130dcf2f9a4f239fed0857907089566634304835afad"},
{0x293c0,0x5,"06242b7ef22d6bbc3840c84a21552841327b598684aa81bea36b28be37813998"},
{0x7ca2,0x5,"801c6e2de6d79bf86fcab3245bc40f2f451818ade2cc7649f2877e9a799f3894"},
{0xa5bf,0x5,"76528d743097feea1fe288e665e946d3a55b36f5c19c3ba5bef14fcf83e998ad"},
{0x1cc97,0x5,"4ed104d085fb356cd365b156c8ea8e864e9167824e88c67c7052fdddd8ea3876"},
{0x1c5d0,0x5,"060d0431ede1ef73fd7772878b8e2dc7b90c04c7fa94253334cbefbb2400f547"},
{0x12ce2,0x5,"e0c3505c97009c4615e6adcec91d89e1494efbd72531473285aba49246593883"},};
struct Stream {void** table;std::array<std::uint32_t,11> values;unsigned at;};
void __fastcall Scalar(Stream* stream,void*,std::uint32_t* out){*out=stream->values[stream->at++];}
void __fastcall Pair(Stream* stream,void*,std::uint32_t* out){Scalar(stream,nullptr,out);Scalar(stream,nullptr,out+1);}
void __fastcall Triple(Stream* stream,void*,std::uint32_t* out){Pair(stream,nullptr,out);Scalar(stream,nullptr,out+2);}
std::uint32_t __fastcall PowerId(void*,void*,Stream* stream){return stream->values[stream->at++];}
void Jump(unsigned char* at,std::uintptr_t target){at[0]=0xe9;const auto distance=static_cast<std::uint32_t>(target-reinterpret_cast<std::uintptr_t>(at)-5);std::memcpy(at+1,&distance,4);}
}
int main(int argc,char** argv){
    Check(argc==2,"usage item_application_probe exact .14 image");
    std::ifstream file(std::filesystem::path(argv[1]),std::ios::binary|std::ios::ate);const auto size=file.tellg();
    Check(file.good()&&size>0&&size<32*1024*1024,"image size");std::vector<unsigned char> bytes(static_cast<std::size_t>(size));file.seekg(0);
    Check(static_cast<bool>(file.read(reinterpret_cast<char*>(bytes.data()),size)),"image read");
    const auto hash=Sha(bytes.data(),bytes.size());Check((hash=="e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e" || hash=="381e67586b3c36b8ce1dcdb824439010d373d455aa6b460b02cf44f7d58fe9e5")||(hash=="78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903" || hash=="e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437"),"exact original/prepared .14 or .15");
    auto* arena=static_cast<unsigned char*>(VirtualAlloc(nullptr,0x1200000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));Check(arena,"arena");
    const auto base=reinterpret_cast<std::uintptr_t>(arena);std::memset(arena,0xcc,0x1200000);
    for(const auto& span:segments){Check(Sha(bytes.data()+span.rva,span.size)==span.sha,"exact decoder/process/destructor span");std::memcpy(arena+span.rva,bytes.data()+span.rva,span.size);}
    for(unsigned i=0;i<6;++i){std::uint32_t target{};std::memcpy(&target,bytes.data()+t::kTables[i/3]+t::kSlots[i%3],4);Check(target==0x400000+t::kTargets[i],"six original vtable targets");}
    Jump(arena+0x12ce2,reinterpret_cast<std::uintptr_t>(&PowerId));
    DWORD old{};Check(VirtualProtect(arena,0x1200000,PAGE_EXECUTE_READ,&old)&&FlushInstructionCache(GetCurrentProcess(),arena,0x1200000),"executable fixture");
    std::array<void*,40> methods{};methods[0x98/4]=reinterpret_cast<void*>(&Scalar);methods[0x94/4]=reinterpret_cast<void*>(&Scalar);
    methods[0x84/4]=reinterpret_cast<void*>(&Pair);methods[0x7c/4]=reinterpret_cast<void*>(&Triple);
    unsigned cases{};t::image_base=base;
    for(unsigned subtype:{1U,2U}){
        Stream stream{methods.data(),{subtype,1,5802955,30,4050960,53},0};std::array<std::uint32_t,44> message{};message.fill(0xcdcdcdcd);
        message[0]=static_cast<std::uint32_t>(base+t::kTables[0]);
        reinterpret_cast<t::Decode>(base+0x375180)(message.data(),&stream);
        std::array<std::uint32_t,11> actual{};Check(t::Snapshot<0>(message.data(),actual),"actual item decoder snapshots");
        Check(actual[0]==subtype&&actual[1]==1&&actual[2]==5802955&&actual[3]==30,"native item scalar/key layout");
        Check(actual[4]==(subtype==2?4050960U:0)&&actual[5]==(subtype==2?53U:0),"native conditional recipient normalized");
        Check(stream.at==(subtype==2?6U:4U),"native conditional stream consumption");++cases;
    }
    for(unsigned flags:{1U,2U,3U}){for(unsigned status:{0U,7U}){
        Stream stream{methods.data(),{429021400,40,4050960,53,0,0,1,2,3,flags,status},0};std::array<std::uint32_t,44> message{};
        message[0]=static_cast<std::uint32_t>(base+t::kTables[1]);reinterpret_cast<t::Decode>(base+0x386380)(message.data(),&stream);
        std::array<std::uint32_t,11> actual{};Check(t::Snapshot<1>(message.data(),actual)&&actual==stream.values&&stream.at==11,"native power decoder raw fields/status");++cases;
    }}
    VirtualFree(arena,0,MEM_RELEASE);std::printf("item application decoder conformance: %u cases; 13 spans and 6 slots verified; synthetic stream, no live game\n",cases);return 0;
}
