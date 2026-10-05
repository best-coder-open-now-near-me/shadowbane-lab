// Execute reviewed INITTIME getter and protocol vector operations in a private
// arena. No client startup, allocator, network, action or game process is invoked.
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
namespace {
unsigned failures{};
void Check(bool ok,const char* label) { if(!ok) { ++failures; std::fprintf(stderr,"%s\n",label); } }
std::string Digest(const std::vector<unsigned char>& bytes) {
    BCRYPT_ALG_HANDLE algorithm{}; BCRYPT_HASH_HANDLE hash{};
    std::array<unsigned char,32> result{};
    const bool ok=BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0
        && BCryptCreateHash(algorithm,&hash,nullptr,0,nullptr,0,0)>=0
        && BCryptHashData(hash,const_cast<unsigned char*>(bytes.data()),static_cast<ULONG>(bytes.size()),0)>=0
        && BCryptFinishHash(hash,result.data(),static_cast<ULONG>(result.size()),0)>=0;
    if(hash){BCryptDestroyHash(hash);} if(algorithm){BCryptCloseAlgorithmProvider(algorithm,0);}
    if(!ok){throw std::runtime_error("SHA256 failed");}
    constexpr char hex[]="0123456789abcdef"; std::string text;
    for(auto byte:result){text+=hex[byte>>4];text+=hex[byte&15];} return text;
}

void Pointer(unsigned char* at,const void* value) { const auto n=reinterpret_cast<std::uintptr_t>(value); std::memcpy(at,&n,4); }
// Native append slice uses EBX actor, EDI definition and [EBP+10] scratch.
__declspec(naked) void __cdecl Append(void*,void*,void*) {
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
struct Arena {
    static constexpr std::size_t size=0x12d3000;
    unsigned char* bytes=static_cast<unsigned char*>(VirtualAlloc(nullptr,size,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    ~Arena(){if(bytes){VirtualFree(bytes,0,MEM_RELEASE);}}
};
}
int main(int argc,char** argv) {
    try {
        if(argc!=2) { throw std::runtime_error("usage: combat_power_initiation_probe <reviewed client13>"); }
        std::ifstream stream(std::filesystem::path(argv[1]),std::ios::binary|std::ios::ate);
        const auto size=stream.tellg();
        if(!stream || size<=0 || size>64*1024*1024) { throw std::runtime_error("invalid image"); }
        std::vector<unsigned char> bytes(static_cast<std::size_t>(size));stream.seekg(0);
        if(!stream.read(reinterpret_cast<char*>(bytes.data()),size)){throw std::runtime_error("short image");}
        const auto sha=Digest(bytes);
        if((sha!="e5bb74e159a9acd8529652eb5b0c07766ced7ffd70c03c960ccdbcefca83c6e8" && sha!="e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e")
            &&(sha!="0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d" && sha!="78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903")){
            throw std::runtime_error("unreviewed image");}
        Arena arena;if(!arena.bytes){throw std::runtime_error("allocation failed");}
        // Hash-qualified .text RVAs equal file offsets in both images.
        const auto copy=[&](std::size_t start,std::size_t length){std::memcpy(arena.bytes+start,bytes.data()+start,length);};
        copy(0x1725b0,0x1e);copy(0xaae2,5);copy(0x2df5f0,0x25);copy(0x121fc,5);copy(0x2bc1b0,0x63);
        copy(0x2bc320,10);copy(0x2bc560,16);copy(0x2bc750,19);
        copy(0x12d2c08,24);copy(0x9a140,0x5c);copy(0x9e014,0x2b);
        // Relocate absolute operands, leaving native relative calls unchanged.
        Pointer(arena.bytes+0x1725bf,arena.bytes+0x12d2c08);
        const float zero=0;std::memcpy(arena.bytes+0x100,&zero,4);
        Pointer(arena.bytes+0x2bc20a,arena.bytes+0x100);
        void* (__cdecl* move)(void*,const void*,std::size_t)=&std::memmove;
        Pointer(arena.bytes+0x108,reinterpret_cast<void*>(move));
        Pointer(arena.bytes+0x9a17f,arena.bytes+0x108);
        arena.bytes[0x9e105]=0xc3;
        // A full vector would take the allocator branch, intentionally excluded.
        arena.bytes[0x9e03f]=0xcc;
        DWORD old{};if(!VirtualProtect(arena.bytes,Arena::size,PAGE_EXECUTE_READ,&old)
            ||!FlushInstructionCache(GetCurrentProcess(),arena.bytes,Arena::size)) { throw std::runtime_error("protect failed"); }
        using Curve=double(__thiscall*)(void*,std::uint32_t,std::uint32_t);
        auto curve=reinterpret_cast<Curve>(arena.bytes+0x1725b0);
        std::array<std::uint32_t,0x300/4> definition{};
        unsigned cases{};
        for(auto rank:{1U,40U,9999U}) {
            for(float duration:{0.0f,0.25f,8.0f}) {
                std::memcpy(&definition[0x1d8/4],&duration,4);definition[0x1dc/4]=0;
                Check(curve(definition.data(),3,rank)==duration,"actual INITTIME constant getter");++cases;
            }
        }
        // Execute all three reviewed concrete segment classes, including the
        // ranked virtual ABI; every segment is native x87 arithmetic with no calls.
        std::array<std::uintptr_t,2> table{};
        struct Segment { void* table; float coefficient; } segment{table.data(),0.5f};
        struct Point { float threshold; void* segment; } point{10000.0f,&segment};
        std::array<std::uintptr_t,3> rank_curve{0,reinterpret_cast<std::uintptr_t>(&point),reinterpret_cast<std::uintptr_t>(&point+1)};
        float base=2;std::memcpy(&definition[0x1d8/4],&base,4);
        definition[0x1dc/4]=static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(rank_curve.data()));
        for(auto method:{0x2bc320U,0x2bc560U,0x2bc750U}) {
            table[1]=reinterpret_cast<std::uintptr_t>(arena.bytes+method);
            for(auto rank:{1U,40U,9999U}) {
                const double expected=method==0x2bc320?2.0:method==0x2bc560?rank*0.5+2.0:rank+2.0;
                Check(curve(definition.data(),3,rank)==expected,"actual ranked INITTIME segment dispatch");++cases;
            }
        }
        std::array<std::uint32_t,0x668/4> actor{};std::array<std::uint32_t,8> ids{};
        actor[0x65c/4]=static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(ids.data()));
        actor[0x660/4]=actor[0x65c/4];actor[0x664/4]=actor[0x65c/4]+sizeof(ids);
        definition[0x138/4]=7;
        Append(arena.bytes+0x9e014,actor.data(),definition.data());
        Append(arena.bytes+0x9e014,actor.data(),definition.data());
        Check(actor[0x660/4]==actor[0x65c/4]+8&&ids[0]==7&&ids[1]==7,"real followup preserves duplicate IDs");++cases;
        definition[0x138/4]=9;Append(arena.bytes+0x9e014,actor.data(),definition.data());
        using Remove=bool(__thiscall*)(void*,std::uint32_t);
        auto remove=reinterpret_cast<Remove>(arena.bytes+0x9a140);
        Check(!remove(actor.data(),99)&&actor[0x660/4]==actor[0x65c/4]+12,"missing protocol ID unchanged");++cases;
        Check(remove(actor.data(),7)&&ids[0]==7&&ids[1]==9&&actor[0x660/4]==actor[0x65c/4]+8,"remove first duplicate only");++cases;
        Check(remove(actor.data(),7)&&ids[0]==9&&actor[0x660/4]==actor[0x65c/4]+4,"second acknowledgement removes second duplicate");++cases;
        Check(remove(actor.data(),9)&&!remove(actor.data(),9)&&actor[0x660/4]==actor[0x65c/4],"empty protocol reached without effect claims");++cases;
        std::printf("{\"image_sha256\":\"%s\",\"cases\":%u,\"failures\":%u,\"scope\":\"ranked_inittime_and_protocol_operations\"}\n",sha.c_str(),cases,failures);
        return failures?1:0;
    }catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return 2;}
}
