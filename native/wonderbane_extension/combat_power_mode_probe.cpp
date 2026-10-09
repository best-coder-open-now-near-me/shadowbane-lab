// Execute the reviewed PreparePower stance and movement/auxiliary predicates
// in private arenas. State locks are instrumented: this qualifies the exact
// predicates and ECX ABI, not synchronization, full Use, or server application.
#include <Windows.h>
#include <bcrypt.h>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
unsigned failures{}, acquired{}, released{};
void* expected_state{};
void Check(bool ok, const char* label) {
    if (!ok) { ++failures; std::fprintf(stderr, "%s\n", label); }
}
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
void __fastcall Acquire(void* state,void*) {
    Check(state==expected_state,"native predicate acquires the exact actor state"); ++acquired;
}
void __fastcall Release(void* state,void*) {
    Check(state==expected_state,"native predicate releases the exact actor state"); ++released;
}
void Jump(unsigned char* at,std::uintptr_t target) {
    at[0]=0xe9;
    const auto relative=static_cast<std::uint32_t>(target-reinterpret_cast<std::uintptr_t>(at)-5);
    std::memcpy(at+1,&relative,4);
}
// Native slice expects EDI=definition, ESI=actor and writable [EBP+14].
// Supply a private frame rather than permitting it to modify caller arguments.
__declspec(naked) bool __cdecl Predicate(void*,void*,void*) {
    __asm {
        push ebp
        mov ebp,esp
        push ebx
        push esi
        push edi
        sub esp,40h
        mov edx,dword ptr [ebp+8]
        mov esi,dword ptr [ebp+0ch]
        mov edi,dword ptr [ebp+10h]
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
    unsigned char* bytes=static_cast<unsigned char*>(VirtualAlloc(nullptr,0x4e400,
        MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    ~Arena(){if(bytes){VirtualFree(bytes,0,MEM_RELEASE);}}
};
}
int main(int argc,char** argv) {
    try {
        if(argc!=2){throw std::runtime_error("usage: combat_power_mode_probe <reviewed original/prepared client13>");}
        std::ifstream stream(std::filesystem::path(argv[1]),std::ios::binary|std::ios::ate);
        const auto size=stream.tellg();
        if(!stream || size<=0 || size>64*1024*1024){throw std::runtime_error("invalid executable");}
        std::vector<unsigned char> bytes(static_cast<std::size_t>(size)); stream.seekg(0);
        if(!stream.read(reinterpret_cast<char*>(bytes.data()),size)){throw std::runtime_error("short executable");}
        const auto sha=Digest(bytes);
        if((sha!="e5bb74e159a9acd8529652eb5b0c07766ced7ffd70c03c960ccdbcefca83c6e8" && (sha!="e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e" && sha!="381e67586b3c36b8ce1dcdb824439010d373d455aa6b460b02cf44f7d58fe9e5"))
            && (sha!="0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d" && (sha!="78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903" && sha!="e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437"))){
            throw std::runtime_error("unreviewed executable");}
        Arena arena;
        if(!arena.bytes){throw std::runtime_error("arena allocation failed");}
        // Raw .text offsets equal RVAs in these two hash-qualified images.
        constexpr std::size_t begin=0x4e0be,end=0x4e133;
        std::memcpy(arena.bytes+begin,bytes.data()+begin,end-begin);
        // Native accept/reject destinations stop here; no diagnostic, resource,
        // network, stance transition or other PreparePower code is executed.
        const unsigned char yes[]{0xb8,1,0,0,0,0xc3},no[]{0x31,0xc0,0xc3};
        std::memcpy(arena.bytes+0x4e1b9,yes,sizeof(yes));
        std::memcpy(arena.bytes+end,no,sizeof(no));
        Jump(arena.bytes+0x7bee,reinterpret_cast<std::uintptr_t>(&Acquire));
        Jump(arena.bytes+0x26eb3,reinterpret_cast<std::uintptr_t>(&Release));
        DWORD old{};
        if(!VirtualProtect(arena.bytes,0x4e400,PAGE_EXECUTE_READ,&old)
            || !FlushInstructionCache(GetCurrentProcess(),arena.bytes,0x4e400)){
            throw std::runtime_error("arena execute protection failed");}
        std::array<std::uint32_t,0xad4/4> actor{};
        std::array<std::uint32_t,0x1f4/4> power{};
        std::array<std::int32_t,8> state{};
        expected_state=state.data();
        actor[0xad0/4]=static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(state.data()));
        unsigned cases{};
        for(const auto requirement:{0U,1U,2U,3U,4U,0xffffffffU}) {
            power[0x1f0/4]=requirement;
            for(const auto mode:{std::numeric_limits<std::int32_t>::min(),-1,0,1,2,3,7,
                                 std::numeric_limits<std::int32_t>::max()}) {
                state[0x18/4]=mode; acquired=released=0;
                const bool expected=(requirement==1&&mode>=2)||(requirement==2&&mode<=1)||requirement==3;
                Check(Predicate(arena.bytes+begin,actor.data(),power.data())==expected,
                    "real native required-mode predicate differs");
                const unsigned locks=(requirement==1||requirement==2)?1U:0U;
                Check(acquired==locks&&released==locks,"native state read guard count differs");
                ++cases;
            }
        }
        // The continuation after accepted mode checks has two independent
        // predicates: non-moving flag +274 rejects state7; auxiliary flag +275
        // rejects aux3. Retained initiation IDs are not read by these predicates.
        Arena continuation;
        if(!continuation.bytes){throw std::runtime_error("continuation allocation failed");}
        constexpr std::size_t moving_begin=0x4e1b9,moving_end=0x4e339;
        std::memcpy(continuation.bytes+moving_begin,bytes.data()+moving_begin,moving_end-moving_begin);
        std::memcpy(continuation.bytes+0x4e1f3,no,sizeof(no));
        std::memcpy(continuation.bytes+0x4e2b3,no,sizeof(no));
        std::memcpy(continuation.bytes+moving_end,yes,sizeof(yes));
        Jump(continuation.bytes+0x7bee,reinterpret_cast<std::uintptr_t>(&Acquire));
        Jump(continuation.bytes+0x26eb3,reinterpret_cast<std::uintptr_t>(&Release));
        if(!VirtualProtect(continuation.bytes,0x4e400,PAGE_EXECUTE_READ,&old)
            || !FlushInstructionCache(GetCurrentProcess(),continuation.bytes,0x4e400)){
            throw std::runtime_error("continuation protection failed");}
        std::array<std::uint32_t,0x278/4> continuation_power{};
        auto* flags=reinterpret_cast<unsigned char*>(continuation_power.data());
        std::array<std::uint32_t,4> retained_ids{123,123,456,0};
        actor[0x65c/4]=static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(retained_ids.data()));
        actor[0x664/4]=actor[0x65c/4]+sizeof(retained_ids);
        for(const auto count:{0U,1U,2U,3U}) {
            actor[0x660/4]=actor[0x65c/4]+count*4;
            for(const auto activity:{1,2,3,4,5,6,7}) {
                for(const auto auxiliary:{0,3}) {
                    for(const auto flag274:{0U,1U}) {
                        for(const auto flag275:{0U,1U}) {
                            flags[0x274]=static_cast<unsigned char>(flag274);
                            flags[0x275]=static_cast<unsigned char>(flag275);
                            state[0x10/4]=activity;state[0x1c/4]=auxiliary;
                            acquired=released=0;
                            const auto before_actor=actor;const auto before_power=continuation_power;
                            const auto before_state=state;const auto before_ids=retained_ids;
                            const bool moving_denied=!flag274&&activity==7;
                            const bool expected=!moving_denied&&(flag275||auxiliary!=3);
                            Check(Predicate(continuation.bytes+moving_begin,actor.data(),continuation_power.data())==expected,
                                "actual movement/auxiliary predicate differs with retained IDs");
                            const unsigned locks=(!flag274?1U:0U)+(!moving_denied&&!flag275?1U:0U);
                            Check(acquired==locks&&released==locks,"movement/auxiliary exact state lock ABI");
                            Check(actor==before_actor&&continuation_power==before_power
                                &&state==before_state&&retained_ids==before_ids,
                                "native eligibility predicates leave state and retained IDs untouched");
                            ++cases;
                        }
                    }
                }
            }
        }
        std::printf("{\"image_sha256\":\"%s\",\"cases\":%u,\"failures\":%u,\"scope\":\"native_mode_movement_aux_predicates_only\"}\n",
            sha.c_str(),cases,failures);
        return failures?1:0;
    } catch(const std::exception& error) {
        std::fprintf(stderr,"%s\n",error.what()); return 2;
    }
}