// Exact-image readiness predicates and native list/property/recycle primitives.
// Private synthetic objects only; allocator release and notification tail are
// instrumented. No client startup, action, network or live process is invoked.
#include "combat_power_readiness.h"
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
unsigned failures{}, freed{};
std::array<void*,4> owned_nodes{};
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

void Pointer(unsigned char* at,const void* value) {
    const auto address=reinterpret_cast<std::uintptr_t>(value); std::memcpy(at,&address,4);
}
void Jump(unsigned char* at,std::uintptr_t target) {
    at[0]=0xe9;const auto delta=static_cast<std::uint32_t>(target-reinterpret_cast<std::uintptr_t>(at)-5);
    std::memcpy(at+1,&delta,4);
}
void __cdecl ReleaseNode(void* node,std::size_t size) {
    bool owned=false;for(auto value:owned_nodes){owned|=value==node;}
    Check(owned&&size==16,"native unlink releases only a fixture-owned 16-byte node");++freed;
}
// Exact gate slice: ESI actor, EDI definition, private EBP scratch. Stop before
// diagnostics/PreparePower side effects; result 0=ready,1=recovery,2=reuse.
__declspec(naked) unsigned __cdecl Predicate(void*,void*,void*) {
    __asm {
        push ebp
        mov ebp,esp
        push ebx
        push esi
        push edi
        sub esp,0a0h
        mov edx,[ebp+8]
        mov esi,[ebp+0ch]
        mov edi,[ebp+10h]
        lea eax,[esp+60h]
        push ebp
        mov ebp,eax
        call edx
        pop ebp
        add esp,0a0h
        pop edi
        pop esi
        pop ebx
        pop ebp
        ret
    }
}
struct Arena {
    static constexpr std::size_t size=0x1142000;
    unsigned char* bytes=static_cast<unsigned char*>(VirtualAlloc(nullptr,size,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    ~Arena(){if(bytes){VirtualFree(bytes,0,MEM_RELEASE);}}
};
struct Node { Node* next;Node* previous;std::uint32_t id;float predicted_time; };
static_assert(sizeof(Node)==16);
}
int main(int argc,char** argv) {
    try {
        if(argc!=2){throw std::runtime_error("usage: combat_power_readiness_probe <reviewed original/prepared client13>");}
        std::ifstream stream(std::filesystem::path(argv[1]),std::ios::binary|std::ios::ate);
        const auto size=stream.tellg();
        if(!stream||size<=0||size>64*1024*1024){throw std::runtime_error("invalid image");}
        std::vector<unsigned char> bytes(static_cast<std::size_t>(size));stream.seekg(0);
        if(!stream.read(reinterpret_cast<char*>(bytes.data()),size)){throw std::runtime_error("short image");}
        const auto sha=Digest(bytes);
        if((sha!="e5bb74e159a9acd8529652eb5b0c07766ced7ffd70c03c960ccdbcefca83c6e8" && (sha!="e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e" && (sha!="381e67586b3c36b8ce1dcdb824439010d373d455aa6b460b02cf44f7d58fe9e5" && sha!="a145ef491341e5107ec064de876d97f0e9c6ebbde2520d6509b4a3b47a7d825a")))
            &&(sha!="0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d" && (sha!="78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903" && (sha!="e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437" && sha!="1a5a9fd59da8255a3c98e16e1e8ff9a415c0921b4189583158c559ad2594360c")))){
            throw std::runtime_error("unreviewed image");}
        Arena arena;if(!arena.bytes){throw std::runtime_error("allocation failed");}
        const auto copy=[&](std::size_t begin,std::size_t length){std::memcpy(arena.bytes+begin,bytes.data()+begin,length);};
        // These hash-qualified images have .text raw offsets equal to RVAs.
        copy(0x4e339,0x1a);copy(0x4e3d9,0x30);
        for(auto thunk:{0x13b42U,0x9e76U,0x3cbaU,0x1f992U,0x10960U,0x2742bU,
            0x23d71U,0x7464U,0x21acbU,0x2947eU,0x70eaU,0x1393U,0x24d4dU,0x10ca3U}){copy(thunk,5);}
        copy(0x9a770,0x5b);copy(0xa0870,0xe);copy(0xa0850,0x10);copy(0xa3840,0x3e);
        copy(0xa3890,0x10);copy(0xa4370,0x24);copy(0x9a6a0,0x9f);copy(0xa1860,0x2a);
        copy(0x13fae0,0xb9);copy(0x86da0,0x167);copy(0x83920,0x4e);copy(0x883f0,0x1a);
        copy(0x86f70,0x1a);copy(0x83990,0x1c);copy(0x7dfb0,0x18);copy(0x114133c,128);
        copy(0x38e2d0,0x19);copy(0x38e2fa,6);
        const auto result=[&](std::size_t rva,unsigned value){
            const unsigned char code[]{0xb8,static_cast<unsigned char>(value),0,0,0,0xc3};
            std::memcpy(arena.bytes+rva,code,sizeof(code));
        };
        result(0x4e353,1);result(0x4e409,2);result(0x4e48f,0);
        // Recycle handler's notification tail is excluded after its actual removal.
        const unsigned char recycled[]{0x31,0xc0,0x5e,0xc3};
        std::memcpy(arena.bytes+0x38e2e9,recycled,sizeof(recycled));
        Jump(arena.bytes+0x1ea6,reinterpret_cast<std::uintptr_t>(&ReleaseNode));
        // The null-container remover's logging branch is excluded; tests invoke
        // remove only with allocated lists. The read-only membership null case is native.
        arena.bytes[0x9a6b3]=0xcc;
        std::array<std::uint32_t,0x680/4> actor{};
        std::array<std::uint32_t,0x13c/4> definition{};
        std::array<std::uintptr_t,7> descriptor_table{};
        std::array<std::uint32_t,5> descriptor{};
        descriptor_table[6]=reinterpret_cast<std::uintptr_t>(arena.bytes+0x7dfb0);
        descriptor[0]=static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(descriptor_table.data()));
        descriptor[1]=7; // A synthetic registered property key; native hashing is exercised.
        descriptor[4]=0; // Reviewed ADMIN_ISADMIN constructor's default low byte.
        double clock=100;void* current_actor=actor.data();
        Pointer(arena.bytes+0x4e33b,&clock);
        Pointer(arena.bytes+0x4e3f3,descriptor.data());
        Pointer(arena.bytes+0x86e5c,arena.bytes+0x114133c);
        Pointer(arena.bytes+0x38e2d4,&current_actor);
        DWORD old{};
        if(!VirtualProtect(arena.bytes,Arena::size,PAGE_EXECUTE_READ,&old)
            ||!FlushInstructionCache(GetCurrentProcess(),arena.bytes,Arena::size)){throw std::runtime_error("protect failed");}
        unsigned cases{};
        using Member=bool(__thiscall*)(void*,std::uint32_t);
        using Property=std::uint32_t*(__thiscall*)(void*,std::uint32_t*,void*);
        using Recycle=unsigned(__thiscall*)(void*);
        const auto member=reinterpret_cast<Member>(arena.bytes+0x9a770);
        const auto property=reinterpret_cast<Property>(arena.bytes+0x13fae0);
        const auto recycle=reinterpret_cast<Recycle>(arena.bytes+0x38e2d0);
        auto gate=[&](){return Predicate(arena.bytes+0x4e339,actor.data(),definition.data());};
        auto recovery=[&](float value){std::memcpy(&actor[0x67c/4],&value,4);};
        Node sentinel{};Node* head=&sentinel;
        std::array<Node,3> nodes{};
        std::array<std::array<std::uint32_t,2>,4> map{};
        const auto image=reinterpret_cast<std::uintptr_t>(arena.bytes);
        // Translate the relocated fixture globals into the module-relative view
        // consumed by production. Object/list/map bytes are read unchanged.
        const auto read=[&](std::uintptr_t at,auto& out) noexcept {
            const auto assign=[&](const auto& value) noexcept {
                if constexpr(sizeof(out)!=sizeof(value)){return false;}
                else {std::memcpy(&out,&value,sizeof(out));return true;}
            };
            if(at==image+0x16a2d70){return assign(clock);}
            if(at==image+0x1389560){return assign(static_cast<std::uint32_t>(image+0x1141a24));}
            if(at==image+0x1389564){return assign(descriptor[1]);}
            if(at==image+0x1389568){return assign(static_cast<std::uint32_t>(image+0x12e86b4));}
            if(at==image+0x1389570){return assign(static_cast<std::uint8_t>(descriptor[4]));}
            const auto inside=[&](const void* data,std::size_t length) noexcept {
                const auto begin=reinterpret_cast<std::uintptr_t>(data);
                return at>=begin&&sizeof(out)<=length&&at-begin<=length-sizeof(out);
            };
            if(!inside(actor.data(),sizeof(actor))&&!inside(&head,sizeof(head))
                &&!inside(&sentinel,sizeof(sentinel))&&!inside(nodes.data(),sizeof(nodes))
                &&!inside(map.data(),sizeof(map))&&!inside(arena.bytes+0x114133c,128)){return false;}
            std::memcpy(&out,reinterpret_cast<const void*>(at),sizeof(out));return true;
        };
        auto check=[&](bool value,const char* name){
            Check(value,name);
            const auto actual=gate();
            const auto observed=wonderbane::extension::combat::power::readiness::Observe(
                image,reinterpret_cast<std::uintptr_t>(actor.data()),definition[0x138/4],read);
            using A=wonderbane::extension::combat::power::Availability;
            const auto expected=actual==0?A::ready:actual==1?A::global_recovery:A::reuse_blocked;
            Check(observed==expected,"production capture differs from actual native readiness predicate");
            ++cases;
        };
        definition[0x138/4]=19;
        for(float deadline:{0.0f,99.0f,100.0f,100.25f}){
            recovery(deadline);check(gate()==(clock<deadline?1U:0U),"real recovery predicate boundary");
        }
        recovery(0);check(!member(actor.data(),19),"native null reuse list is absent");
        actor[0x5c8/4]=static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(&head));
        sentinel.next=sentinel.previous=&sentinel;
        check(!member(actor.data(),19)&&gate()==0,"native allocated empty list is ready");
        const auto reset=[&](){
            sentinel.next=&nodes[0];sentinel.previous=&nodes[2];
            nodes[0]={&nodes[1],&sentinel,19,1.0f};
            nodes[1]={&nodes[2],&nodes[0],23,200.0f};
            nodes[2]={&sentinel,&nodes[1],19,200.0f};
            for(std::size_t n=0;n<nodes.size();++n){owned_nodes[n]=&nodes[n];}
        };
        reset();
        check(member(actor.data(),19)&&member(actor.data(),23)&&!member(actor.data(),99),"native reuse membership IDs");
        check(gate()==2,"elapsed predicted deadline does not remove reuse membership");
        recovery(101);check(gate()==1,"global recovery precedes per-power reuse");recovery(0);
        std::uint32_t value=0xcccccccc;
        auto get=[&](){value=0xcccccccc;auto* out=property(actor.data()+0x34/4,&value,descriptor.data());
            Check(out==&value,"native property returns exact output pointer");return value&255;};
        check(get()==0,"native absent admin property uses reviewed false default");
        actor[0x34/4]=static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(map.data()));actor[0x38/4]=2;
        check(get()==0&&gate()==2,"native empty sparse bucket default does not bypass");
        map[0]={7,0};check(get()==0&&gate()==2,"native explicit false admin property");
        map[0]={7,1};check(get()==1&&gate()==0,"native explicit true admin bypass");
        map[0]={7,0x100};check(get()==0&&gate()==2,"native bypass tests low byte only");
        map[0]={0xffffffffU,0};check(get()==0&&gate()==2,"native tombstone is not a property");
        map[3]={7,1};check(get()==1&&gate()==0,"native lookup follows tombstone collision");
        map[0]={11,1};check(get()==1&&gate()==0,"native lookup follows occupied collision");
        map={};
        std::array<std::uint32_t,0x64/4> message{};
        message[0x60/4]=19;freed=0;
        check(recycle(message.data())==0&&freed==2&&!member(actor.data(),19)&&member(actor.data(),23),
            "actual recycle message removes all matching duplicate reuse nodes");
        check(sentinel.next==&nodes[1]&&sentinel.previous==&nodes[1]
            &&nodes[1].next==&sentinel&&nodes[1].previous==&sentinel&&gate()==0,"native unlink preserves unrelated list and readiness");
        message[0x60/4]=99;check(recycle(message.data())==0&&freed==2,"missing recycle ID leaves list unchanged");
        message[0x60/4]=23;check(recycle(message.data())==0&&freed==3&&sentinel.next==&sentinel
            &&sentinel.previous==&sentinel,"last native recycle restores empty sentinel");
        current_actor=nullptr;check(recycle(message.data())==1&&freed==3,"native recycle without actor does not remove");
        std::printf("{\"image_sha256\":\"%s\",\"cases\":%u,\"failures\":%u,\"scope\":\"native_power_recovery_reuse_and_admin_bypass\"}\n",sha.c_str(),cases,failures);
        return failures?1:0;
    }catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return 2;}
}
