// Reuse the unit fixture's bounded synthetic actor/maps and production resolver.
// This binary additionally executes actual reviewed native lookup/rank functions
// in a private image arena. It does not execute client entry or native actions.
#define ACTOR_BUFF_OBSERVATION_PROBE
#include "actor_buff_observation_test.cpp"
#include <bcrypt.h>
#include <filesystem>
#include <fstream>
#include <vector>
#include <string>
#include <stdexcept>
namespace {
std::string Digest(const std::vector<unsigned char>& bytes){
    BCRYPT_ALG_HANDLE algorithm{};BCRYPT_HASH_HANDLE hash{};std::array<unsigned char,32> result{};
    const bool ok=BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0
        && BCryptCreateHash(algorithm,&hash,nullptr,0,nullptr,0,0)>=0
        && BCryptHashData(hash,const_cast<unsigned char*>(bytes.data()),static_cast<ULONG>(bytes.size()),0)>=0
        && BCryptFinishHash(hash,result.data(),static_cast<ULONG>(result.size()),0)>=0;
    if(hash){BCryptDestroyHash(hash);}if(algorithm){BCryptCloseAlgorithmProvider(algorithm,0);}if(!ok){throw std::runtime_error("hash");}
    constexpr char digits[]="0123456789abcdef";std::string text;for(auto byte:result){text+=digits[byte>>4];text+=digits[byte&15];}return text;
}
void Load(const std::vector<unsigned char>& bytes){
    const auto* dos=reinterpret_cast<const IMAGE_DOS_HEADER*>(bytes.data());
    if(bytes.size()<0x1000 || dos->e_magic!=IMAGE_DOS_SIGNATURE || dos->e_lfanew<0
        || static_cast<std::size_t>(dos->e_lfanew)>bytes.size()-sizeof(IMAGE_NT_HEADERS32)){throw std::runtime_error("PE");}
    const auto* nt=reinterpret_cast<const IMAGE_NT_HEADERS32*>(bytes.data()+dos->e_lfanew);
    const auto size=nt->OptionalHeader.SizeOfImage;
    if(nt->Signature!=IMAGE_NT_SIGNATURE || nt->FileHeader.Machine!=IMAGE_FILE_MACHINE_I386 || size<0x16b0000 || size>32*1024*1024){throw std::runtime_error("image geometry");}
    image=static_cast<unsigned char*>(VirtualAlloc(nullptr,size,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));if(!image){throw std::runtime_error("arena");}
    std::memcpy(image,bytes.data(),nt->OptionalHeader.SizeOfHeaders);const auto* section=IMAGE_FIRST_SECTION(nt);
    for(unsigned i=0;i<nt->FileHeader.NumberOfSections;++i){const auto& s=section[i];
        if(s.PointerToRawData>bytes.size() || s.SizeOfRawData>bytes.size()-s.PointerToRawData
            || s.VirtualAddress>size || s.SizeOfRawData>size-s.VirtualAddress){throw std::runtime_error("sections");}
        std::memcpy(image+s.VirtualAddress,bytes.data()+s.PointerToRawData,s.SizeOfRawData);
    }
    const auto delta=static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(image)-nt->OptionalHeader.ImageBase);
    const auto directory=nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_BASERELOC];
    if(directory.VirtualAddress>size || directory.Size>size-directory.VirtualAddress){throw std::runtime_error("relocs");}
    for(std::size_t offset=0;offset<directory.Size;){
        const auto* block=reinterpret_cast<const IMAGE_BASE_RELOCATION*>(image+directory.VirtualAddress+offset);
        if(block->SizeOfBlock<8 || block->SizeOfBlock%2 || block->SizeOfBlock>directory.Size-offset){throw std::runtime_error("reloc block");}
        const auto* entries_reloc=reinterpret_cast<const WORD*>(block+1);
        for(unsigned i=0;i<(block->SizeOfBlock-8)/2;++i){const auto kind=entries_reloc[i]>>12;const auto at=block->VirtualAddress+(entries_reloc[i]&0xfff);
            if(!kind){continue;}if(kind!=IMAGE_REL_BASED_HIGHLOW || at>size-4){throw std::runtime_error("reloc kind");}
            *reinterpret_cast<std::uint32_t*>(image+at)+=delta;
        }offset+=block->SizeOfBlock;
    }
    DWORD old{};if(!VirtualProtect(image,size,PAGE_EXECUTE_READWRITE,&old) || !FlushInstructionCache(GetCurrentProcess(),image,size)){throw std::runtime_error("execute protection");}
}
}
int main(int argc,char** argv){
    try{
        if(argc!=2){throw std::runtime_error("usage: actor_buff_observation_probe <exact original/prepared client13>");}
        std::ifstream stream(std::filesystem::path(argv[1]),std::ios::binary|std::ios::ate);const auto length=stream.tellg();
        if(!stream || length<=0 || length>32*1024*1024){throw std::runtime_error("image size");}
        std::vector<unsigned char> bytes(static_cast<std::size_t>(length));stream.seekg(0);if(!stream.read(reinterpret_cast<char*>(bytes.data()),length)){throw std::runtime_error("image read");}
        const auto sha=Digest(bytes);if((sha!="e5bb74e159a9acd8529652eb5b0c07766ced7ffd70c03c960ccdbcefca83c6e8" && (sha!="e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e" && (sha!="381e67586b3c36b8ce1dcdb824439010d373d455aa6b460b02cf44f7d58fe9e5" && (sha!="a145ef491341e5107ec064de876d97f0e9c6ebbde2520d6509b4a3b47a7d825a" && sha!="051c55ebd0f25ff5fe9bd27b25efbe3cde0190d1dbf1c2a33eb9604996c69698"))))
            && (sha!="0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d" && (sha!="78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903" && (sha!="e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437" && (sha!="1a5a9fd59da8255a3c98e16e1e8ff9a415c0921b4189583158c559ad2594360c" && sha!="baa6c84e5f28aab01d516f12257354b42375d11e8e8e98930cfcf754aeec24e9"))))){throw std::runtime_error("unreviewed image");}
        if(RunActorBuffFixtureCases()){return 1;}Load(bytes);Reset();const auto initial_checks=checks;
        using NativeLookup=void*(__cdecl*)(std::uint32_t);
        using NativeRank=int(__thiscall*)(void*,std::uint32_t);
        const auto power_lookup=reinterpret_cast<NativeLookup>(image+0x16d8a0);
        const auto effect_lookup=reinterpret_cast<NativeLookup>(image+0x154b50);
        const auto rank=reinterpret_cast<NativeRank>(image+0x9b400);
        for(auto id:std::array<std::uint32_t,3>{110,111,112}){
            std::uint32_t bounded_rank{};Check(b::Learned(context.actor,id,bounded_rank)==b::Unknown::none,"bounded learned vector readable");
            Check(static_cast<int>(bounded_rank)==rank(actor.data(),id),"actual native learned lower_bound/+C agrees");
            b::MapPath path{};const auto result=b::Lookup(context.image,0x138757c,id,true,path);
            Check((result==b::Unknown::none?reinterpret_cast<void*>(path.matched):nullptr)==power_lookup(id),"actual native power tree lookup agrees");
        }
        for(auto id:std::array<std::uint32_t,3>{221,222,223}){
            b::MapPath path{};const auto result=b::Lookup(context.image,0x1387098,id,false,path);
            Check((result==b::Unknown::none?reinterpret_cast<void*>(path.matched):nullptr)==effect_lookup(id),"actual native descriptor tree lookup agrees");
        }
        for(auto native_rank:std::array<std::uint32_t,4>{0,1,9999,10000}){
            learned[0][3]=native_rank;std::uint32_t bounded_rank{};
            Check(b::Learned(context.actor,111,bounded_rank)==b::Unknown::none
                && bounded_rank==static_cast<std::uint32_t>(std::min(rank(actor.data(),111),9999)),"rank cap matches ordinary native caller");
        }
        b::State owner;b::Publication out;learned[0][3]=40;
        Check(b::Capture(context,Request(),owner,out)==b::Unknown::none
            && out.actions[0].learned_rank==static_cast<std::uint32_t>(rank(actor.data(),111))
            && out.actions[0].descriptors[0].id==*reinterpret_cast<std::uint32_t*>(static_cast<unsigned char*>(effect_lookup(222))+0x14),
            "public resolver derives native matching descriptor/rank without calling entry");b::Release(owner);
        std::printf("{\"sha256\":\"%s\",\"native_checks\":%u,\"failures\":%u,\"scope\":\"native_definition_lookup_and_learned_rank_differential\"}\n",sha.c_str(),checks-initial_checks,failures);
        return failures?1:0;
    }catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return 1;}
}
