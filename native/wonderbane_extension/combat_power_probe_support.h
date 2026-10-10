#pragma once
#include <bcrypt.h>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>
namespace probe {
std::string Digest(const std::vector<unsigned char>& bytes) {
    BCRYPT_ALG_HANDLE algorithm{}; BCRYPT_HASH_HANDLE hash{};
    std::array<unsigned char,32> digest{};
    const bool ok=BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0
        && BCryptCreateHash(algorithm,&hash,nullptr,0,nullptr,0,0)>=0
        && BCryptHashData(hash,const_cast<unsigned char*>(bytes.data()),static_cast<ULONG>(bytes.size()),0)>=0
        && BCryptFinishHash(hash,digest.data(),static_cast<ULONG>(digest.size()),0)>=0;
    if(hash){BCryptDestroyHash(hash);}if(algorithm){BCryptCloseAlgorithmProvider(algorithm,0);}
    if(!ok){throw std::runtime_error("SHA256 failed");}
    constexpr char hex[]="0123456789abcdef";std::string result;
    for(auto byte:digest){result+=hex[byte>>4];result+=hex[byte&15];}return result;
}
EXCEPTION_DISPOSITION __cdecl NativeFault(EXCEPTION_RECORD*,void*,CONTEXT*,void*) {
    // Foreign native C++ EH metadata is not executable in this isolated arena.
    TerminateProcess(GetCurrentProcess(),3); return ExceptionContinueSearch;
}
void __fastcall Retain(void*,void*,void**) { ++references; }
void* __fastcall Transport(void* holder,void*) { return *static_cast<void**>(holder); }
void __fastcall Network(void*,void*,void* value) {
    ++sends;
    if(unrelated){Check(registered.claim(queue,value,0x2c6eb7).decision==sb::AppendDecision::unrelated,"real nested sender not claimed");pw::Consume(value);return;}
    if(reenter_send){reenter_send=false;Nested();}
    if(!pw::active){pw::Consume(value);return;}
    if(seh_send){RaiseException(0xe0420201,0,0,nullptr);}
    if(fault_send){throw std::runtime_error("native network");}
    const auto claim=registered.claim(queue,value,0x2c6eb7);
    Check(claim.decision!=sb::AppendDecision::unrelated,"real sender exact pointer claimed");
    if(claim.decision==sb::AppendDecision::allow){++appends;registered.complete(claim.owner,sb::AppendResult::queued);}
    else{registered.complete(claim.owner,sb::AppendResult::denied);}
    pw::Consume(value);
}
void Jump(unsigned char* at,std::uintptr_t target) {
    at[0]=0xe9;const auto relative=static_cast<std::uint32_t>(target-reinterpret_cast<std::uintptr_t>(at)-5);
    std::memcpy(at+1,&relative,4);
}
bool Prepare(int argc,char** argv,unsigned char* image) {
    try {
        if(argc!=2){throw std::runtime_error("usage: combat_power_probe <exact reviewed original/prepared client12>");}
        std::ifstream file(std::filesystem::path(argv[1]),std::ios::binary|std::ios::ate);
        const auto size=file.tellg();if(!file || size<=0 || size>64*1024*1024){throw std::runtime_error("invalid executable");}
        std::vector<unsigned char> bytes(static_cast<std::size_t>(size));file.seekg(0);
        if(!file.read(reinterpret_cast<char*>(bytes.data()),size)){throw std::runtime_error("short executable read");}
        const auto digest=Digest(bytes);
        if(digest!="3891fcab09dac06d858ac55911046448e75f3519e2f58e1d7c2ccc954aa410b7"
            && digest!="2dc0e19c3fcf43bc19508939fb9c63982bc370a868f810208394324a12cdc289"
            && (digest!="e5bb74e159a9acd8529652eb5b0c07766ced7ffd70c03c960ccdbcefca83c6e8" && (digest!="e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e" && (digest!="381e67586b3c36b8ce1dcdb824439010d373d455aa6b460b02cf44f7d58fe9e5" && (digest!="a145ef491341e5107ec064de876d97f0e9c6ebbde2520d6509b4a3b47a7d825a" && digest!="051c55ebd0f25ff5fe9bd27b25efbe3cde0190d1dbf1c2a33eb9604996c69698"))))
            && (digest!="0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d" && (digest!="78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903" && (digest!="e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437" && (digest!="1a5a9fd59da8255a3c98e16e1e8ff9a415c0921b4189583158c559ad2594360c" && digest!="baa6c84e5f28aab01d516f12257354b42375d11e8e8e98930cfcf754aeec24e9"))))){
            throw std::runtime_error("unreviewed executable");}
        // In these reviewed files raw text offsets equal RVAs. Copy only the
        // closed, audited primitives; execute no native initialization or imports.
        constexpr std::array<std::array<std::size_t,2>,15> segments{{
            {0x9b400,0x71},{0x9b100,0x71},{0x1db29,5},{0xcba8,5},
            {0xa4520,0x3e},{0x94920,0x3e},{0x1117e0,0x15},{0x1119d0,1},
            {0x7f4da0,0x8e},{0x9d3d4,0x11},{0x9bbf0,3},{0x9c710,3},{0x9bf04,5},{0x1c431,5},{0x9c906,0x1b}}};
        for(const auto& s:segments){std::memcpy(image+s[0],bytes.data()+s[0],s[1]);}
        // Validate every provenance callsite against the supplied reviewed file,
        // rather than accepting only the source fixture's synthetic bytes.
        for(const auto& site:pw::sites) {
            if(std::memcmp(bytes.data()+site.rva,site.bytes.data(),site.bytes.size())) {
                throw std::runtime_error("protocol provenance CALL bytes differ");
            }
            std::memcpy(image+site.rva,bytes.data()+site.rva,site.bytes.size());
        }
        // A separate probe entry executes the exact native target-mode redirect.
        // Its destination returns the derived target; no admission or gameplay runs.
        image[0x9c921]=0x8b; image[0x9c922]=0xc3; image[0x9c923]=0xc3;
        // Keep the real CALL instruction bytes and exact native sender ownership.
        // The fixture terminates at the ordinary call return; no native cast runs.
        // Keep the fixture epilogue after the exact native calls; the real
        // 9d3d9 register argument pushes are included in the copied slice.
        const auto fault=reinterpret_cast<std::uintptr_t>(&NativeFault);std::memcpy(image+0x7f4da6,&fault,4);
        Jump(image+0xb2b7,reinterpret_cast<std::uintptr_t>(&Retain));
        Jump(image+0x7a09,reinterpret_cast<std::uintptr_t>(&Transport));
        Jump(image+0x14128,reinterpret_cast<std::uintptr_t>(&Network));
        return true;
    }catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return false;}
}
__declspec(naked) void* __cdecl Recipient(void*,void*,void*,void*) {
    __asm {
        push ebp
        mov ebp, esp
        push esi
        push edi
        push ebx
        mov esi, dword ptr [ebp+12]
        mov ebx, dword ptr [ebp+16]
        mov edi, dword ptr [ebp+20]
        call dword ptr [ebp+8]
        pop ebx
        pop edi
        pop esi
        pop ebp
        ret
    }
}
void Learned(unsigned char* image) {
    std::array<std::uint32_t,0x208/4> power{};
    int actor_object{}, engagement_object{};
    for(auto mode:{0U,1U,2U,3U,10U}) {
        power[0x1a8/4]=mode;
        Check(Recipient(image+0x9c906,&actor_object,&engagement_object,power.data())
            ==(mode==2||mode==3?static_cast<void*>(&actor_object):static_cast<void*>(&engagement_object)),
            "real native target-mode branch derives actor recipient for self powers");
    }

    using Lookup=int(__thiscall*)(void*,std::uint32_t);
    using Member=void*(__thiscall*)(void*,std::uint32_t);
    using Constructor=void*(__thiscall*)(void*,std::uint32_t);
    using Destructor=void(__thiscall*)(void*);
    auto rank=reinterpret_cast<Lookup>(image+0x9b400);
    auto member=reinterpret_cast<Member>(image+0x9b100);
    struct LearnedRecord{std::uint32_t id,metadata1,metadata2,rank;};
    std::array<LearnedRecord,3> records{{{17,8,9,1},{428918601,8,9,40},{900000000,8,9,9999}}};
    std::array<std::uint32_t,0x678/4> actor{};
    actor[0x670/4]=static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(records.data()));
    actor[0x674/4]=static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(records.data()+records.size()));
    for(const auto& record:records){Check(rank(actor.data(),record.id)==static_cast<int>(record.rank),"real learned-rank exact lookup");Check(member(actor.data(),record.id)==&record.metadata1,"real learned membership pointer ABI");}
    for(auto absent:{0U,16U,18U,428918600U,428918602U,900000001U,0xffffffffU}){
        Check(rank(actor.data(),absent)==0 && member(actor.data(),absent)==nullptr,"real learned exact-ID miss");}
    actor[0x674/4]=actor[0x670/4];Check(rank(actor.data(),428918601)==0,"empty learned vector is unlearned");
    pw::Key key{55,66};Check(reinterpret_cast<Constructor>(image+0x1117e0)(&key,0)==&key && key==pw::Key{},"real zero-key constructor ABI");reinterpret_cast<Destructor>(image+0x1119d0)(&key);
}
}
