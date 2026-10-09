// Execute qualified local effect wrappers, rebuild/prune paths and the actual
// bootstrap in an isolated image arena. Allocation/lookup/notification and UI
// tails are instrumented; this does not execute a client or prove server effects.
#include "actor_effects_native.cpp"
#include <bcrypt.h>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>
#include <stdexcept>
namespace wonderbane::extension {
bool GraphicsExecutableSha256Matches(const char*) noexcept { return false; }
namespace movement { bool VerifyNativeMovementImage(std::uintptr_t&) noexcept { return false; } }
}
namespace e = wonderbane::extension::actor_effects;
namespace {
unsigned failures{}, checks{}, notification_count{}, base_add_count{}, undo_count{}, apply_count{}, releases{};
unsigned char* arena{};
std::size_t arena_size{};
bool initialized{}, entry_reached{};
LONG CALLBACK Fault(EXCEPTION_POINTERS* error){
    if(error && error->ExceptionRecord && error->ExceptionRecord->ExceptionCode!=EXCEPTION_BREAKPOINT){
        std::fprintf(stderr,"probe exception %08lx at %08lx (arena %08lx), address %08lx\n",
            error->ExceptionRecord->ExceptionCode,error->ContextRecord->Eip,reinterpret_cast<DWORD>(arena),
            error->ExceptionRecord->NumberParameters>1?static_cast<DWORD>(error->ExceptionRecord->ExceptionInformation[1]):0);
    }return EXCEPTION_CONTINUE_SEARCH;
}
alignas(4) std::array<unsigned char,0xe00> actor{};
alignas(4) std::array<unsigned char,0x78> record{};
alignas(4) std::array<unsigned char,0x60> descriptor{};
alignas(4) std::array<unsigned char,0x20> action{};
alignas(4) std::array<unsigned char,0x90> message{};
std::array<std::uint32_t,4> virtual_base{}, release_table{};
std::array<e::Pair,2> entries{};
e::Context context{};
void Check(bool ok,const char* label){++checks;if(!ok){++failures;std::fprintf(stderr,"%s\n",label);}}
std::uintptr_t Address(auto& value){return reinterpret_cast<std::uintptr_t>(value.data());}
template<class T>void Put(std::uintptr_t at,const T& value){std::memcpy(reinterpret_cast<void*>(at),&value,sizeof(value));}
void Jump(std::uint32_t rva,std::uintptr_t target){arena[rva]=0xe9;Put(reinterpret_cast<std::uintptr_t>(arena+rva+1),static_cast<std::uint32_t>(target-reinterpret_cast<std::uintptr_t>(arena+rva+5)));}
std::string Digest(const std::vector<unsigned char>& bytes){
    BCRYPT_ALG_HANDLE algorithm{};BCRYPT_HASH_HANDLE hash{};std::array<unsigned char,32> result{};
    const bool ok=BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0
        && BCryptCreateHash(algorithm,&hash,nullptr,0,nullptr,0,0)>=0
        && BCryptHashData(hash,const_cast<unsigned char*>(bytes.data()),static_cast<ULONG>(bytes.size()),0)>=0
        && BCryptFinishHash(hash,result.data(),static_cast<ULONG>(result.size()),0)>=0;
    if(hash){BCryptDestroyHash(hash);}if(algorithm){BCryptCloseAlgorithmProvider(algorithm,0);}if(!ok){throw std::runtime_error("hash failure");}
    constexpr char digits[]="0123456789abcdef";std::string text;for(auto byte:result){text+=digits[byte>>4];text+=digits[byte&15];}return text;
}
void Load(const std::vector<unsigned char>& bytes){
    if(bytes.size()<0x1000){throw std::runtime_error("short PE");}
    const auto* dos=reinterpret_cast<const IMAGE_DOS_HEADER*>(bytes.data());
    if(dos->e_magic!=IMAGE_DOS_SIGNATURE || dos->e_lfanew<0 || static_cast<std::size_t>(dos->e_lfanew)>bytes.size()-sizeof(IMAGE_NT_HEADERS32)){throw std::runtime_error("PE headers");}
    const auto* nt=reinterpret_cast<const IMAGE_NT_HEADERS32*>(bytes.data()+dos->e_lfanew);
    if(nt->Signature!=IMAGE_NT_SIGNATURE || nt->FileHeader.Machine!=IMAGE_FILE_MACHINE_I386
        || nt->OptionalHeader.SizeOfImage>32*1024*1024 || nt->OptionalHeader.SizeOfImage<0x16b0000
        || nt->OptionalHeader.DataDirectory[9].VirtualAddress || nt->OptionalHeader.DataDirectory[9].Size){throw std::runtime_error("PE geometry/TLS");}
    arena_size=nt->OptionalHeader.SizeOfImage;arena=static_cast<unsigned char*>(VirtualAlloc(nullptr,arena_size,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    if(!arena){throw std::runtime_error("arena");}std::memcpy(arena,bytes.data(),nt->OptionalHeader.SizeOfHeaders);
    const auto* section=IMAGE_FIRST_SECTION(nt);
    for(unsigned i=0;i<nt->FileHeader.NumberOfSections;++i){const auto& s=section[i];
        if(s.PointerToRawData>bytes.size() || s.SizeOfRawData>bytes.size()-s.PointerToRawData || s.VirtualAddress>arena_size || s.SizeOfRawData>arena_size-s.VirtualAddress){throw std::runtime_error("section bounds");}
        std::memcpy(arena+s.VirtualAddress,bytes.data()+s.PointerToRawData,s.SizeOfRawData);
    }
    const auto delta=static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(arena)-nt->OptionalHeader.ImageBase);
    const auto reloc=nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_BASERELOC];
    if(reloc.VirtualAddress>arena_size || reloc.Size>arena_size-reloc.VirtualAddress){throw std::runtime_error("relocations");}
    for(std::size_t offset=0;offset<reloc.Size;){
        const auto* block=reinterpret_cast<const IMAGE_BASE_RELOCATION*>(arena+reloc.VirtualAddress+offset);
        if(block->SizeOfBlock<8 || block->SizeOfBlock>reloc.Size-offset || block->SizeOfBlock%2){throw std::runtime_error("relocation block");}
        const auto* words=reinterpret_cast<const WORD*>(block+1);
        for(unsigned j=0;j<(block->SizeOfBlock-8)/2;++j){const auto kind=words[j]>>12;const auto rva=block->VirtualAddress+(words[j]&0xfff);
            if(!kind){continue;}if(kind!=IMAGE_REL_BASED_HIGHLOW || rva>arena_size-4){throw std::runtime_error("relocation kind");}
            *reinterpret_cast<std::uint32_t*>(arena+rva)+=delta;
        }offset+=block->SizeOfBlock;
    }
}
bool Current(void*)noexcept{return initialized;}
void SampleDuring(const char* label){e::Snapshot snapshot;Check(e::Capture(context,snapshot)==e::Unknown::mutation_active,label);}
std::uint32_t __fastcall BaseAdd(void* self,void*,std::uint32_t){
    Check(self==reinterpret_cast<void*>(context.actor+0x588),"native local add forwards interface");++base_add_count;
    SampleDuring("native add callback cannot publish partial record");return 55;
}
std::uint32_t __fastcall BaseRemove(void* self,void*,std::uint32_t a,std::uint32_t b){
    Check(self==reinterpret_cast<void*>(context.actor+0x588) && a==123 && b==9,"native remove forwards exact args");
    SampleDuring("native remove callback cannot publish");return 56;
}
std::uint32_t __fastcall Notify(void*,void*,std::uint32_t){++notification_count;SampleDuring("native notification remains inside mutation");return 57;}
void* __fastcall Lookup(void*,void*,void** output,const e::Key*){*output=actor.data();return output;}
bool __fastcall IsCharacter(void*,void*,std::uint32_t mask){Check(mask==0x10,"incoming tests native character type mask");return true;}
std::uint32_t __fastcall Undo(void* self,void*){
    Check(self==actor.data(),"incoming undo exact actor");++undo_count;
    const auto p=static_cast<std::uint32_t>(Address(entries));Put(context.actor+0x58c,e::Vector{p,p,p+16});
    SampleDuring("paused native rebuild empty vector is unknown");return 0;
}
std::uint32_t __fastcall Apply(void* self,void*,std::uint32_t){
    Check(self==actor.data(),"native apply exact actor");++apply_count;SampleDuring("native rebuild reapply remains unpublishable");
    const auto p=static_cast<std::uint32_t>(Address(entries));Put(context.actor+0x58c,e::Vector{p,p+8,p+16});return 0;
}
std::uint32_t __fastcall Recalculate(void*,void*,std::uint32_t,std::uint32_t){SampleDuring("incoming post-rebuild notification still guarded");return 0;}
void __fastcall Release(void*,void*,void** output){++releases;*output=nullptr;}
// Enter an actual CALL instruction with the original caller's argument stack.
// Calling that instruction as a C++ function would insert an extra return
// address in front of its argument and would not represent the native ABI.
__declspec(naked) void __cdecl InvokeEquipmentSite(void*,void*,std::uint32_t){
    __asm {
        push ebp
        mov ebp,esp
        mov eax,dword ptr [ebp+8]
        mov ecx,dword ptr [ebp+0ch]
        push offset finished
        push dword ptr [ebp+10h]
        jmp eax
    finished:
        mov esp,ebp
        pop ebp
        ret
    }
}
DWORD WINAPI Initialize(){
    const auto caller=reinterpret_cast<std::uintptr_t>(_ReturnAddress());
    Check(!entry_reached && caller==reinterpret_cast<std::uintptr_t>(arena)+0x1140e9e,"actual bootstrap calls initializer before client entry");
    Check(e::StartupCurrent(reinterpret_cast<std::uintptr_t>(arena),caller),"actual reviewed bootstrap return and noTLS qualified");
    initialized=e::StartBound(reinterpret_cast<std::uintptr_t>(arena));Check(initialized,"native hooks install synchronously before entry");return 0;
}
HMODULE WINAPI LoadLibraryFixture(LPCSTR name){Check(std::strcmp(name,"wonderbane-extension.dll")==0,"native bootstrap DLL name");return reinterpret_cast<HMODULE>(1);}
FARPROC WINAPI GetProcFixture(HMODULE,LPCSTR name){Check(std::strcmp(name,"WonderBaneExtensionInitialize")==0,"native bootstrap export name");return reinterpret_cast<FARPROC>(&Initialize);}
int __cdecl ClientEntry(){entry_reached=true;Check(initialized && e::Ready(),"original entry resumes only after complete installation");return 1;}
void Prepare(){
    const auto b=reinterpret_cast<std::uintptr_t>(arena);context={b,Address(actor),{4050960,53},1,Current,nullptr};
    Put(b+0x16a2d98,static_cast<std::uint32_t>(context.actor));Put(context.actor,static_cast<std::uint32_t>(b+0x114165c));
    Put(context.actor+0x588,static_cast<std::uint32_t>(b+0x11415fc));Put(context.actor+0x18,context.actor_key);
    Put(context.actor+8,static_cast<std::uint32_t>(Address(virtual_base)));virtual_base[1]=8;virtual_base[3]=0;
    release_table[2]=reinterpret_cast<std::uint32_t>(&Release);Put(context.actor+16,static_cast<std::uint32_t>(Address(release_table)));
    Put(Address(descriptor),static_cast<std::uint32_t>(b+0x1147930));Put(Address(descriptor)+0x14,std::uint32_t{123});
    Put(Address(action),static_cast<std::uint32_t>(b+0x1148b48));Put(Address(action)+0x1c,std::uint32_t{456});
    Put(Address(record),static_cast<std::uint32_t>(Address(descriptor)));Put(Address(record)+0x14,static_cast<std::uint32_t>(Address(descriptor)+0x5c));
    Put(Address(record)+0x68,static_cast<std::uint32_t>(Address(action)));entries[0]={123,static_cast<std::uint32_t>(Address(record))};
    const auto p=static_cast<std::uint32_t>(Address(entries));Put(context.actor+0x58c,e::Vector{p,p+8,p+16});
    // Restore the authored exact stub for the original-image variant. Original
    // native effect code is unchanged; only the bootstrap is the reviewed patch.
    std::memcpy(arena+0x1140e70,wonderbane::extension::movement::bootstrap_replacement_6.data(),113);
    Put(b+0x1140e78+0x56f44c,reinterpret_cast<std::uint32_t>(&LoadLibraryFixture));
    Put(b+0x1140e78+0x56f4a8,reinterpret_cast<std::uint32_t>(&GetProcFixture));
    // Instrument only the original entry continuation; restore the exact stub's
    // original prologue stack before entering the assertion callback.
    const unsigned char epilogue[]{0x83,0xc4,4,0x5d};std::memcpy(arena+0x8d8c4f,epilogue,4);Jump(0x8d8c53,reinterpret_cast<std::uintptr_t>(&ClientEntry));
    Jump(0xe5de,reinterpret_cast<std::uintptr_t>(&BaseAdd));Jump(0x1c7a1,reinterpret_cast<std::uintptr_t>(&BaseRemove));
    Jump(0x770c,reinterpret_cast<std::uintptr_t>(&Notify));Jump(0x1ab3b,reinterpret_cast<std::uintptr_t>(&Notify));
    Jump(0x1d7e1,reinterpret_cast<std::uintptr_t>(&Lookup));Jump(0x5e61,reinterpret_cast<std::uintptr_t>(&IsCharacter));
    Jump(0x15f96,reinterpret_cast<std::uintptr_t>(&Undo));Jump(0x5e2a,reinterpret_cast<std::uintptr_t>(&Apply));
    Jump(0x2754d,reinterpret_cast<std::uintptr_t>(&Recalculate));
    // The client's inline prune patch embeds an absolute actor-global operand
    // without a PE HIGHLOW entry. Relocate that operand explicitly in the arena;
    // its exact reviewed instruction and algorithm otherwise remain untouched.
    Check(*reinterpret_cast<std::uint32_t*>(arena+0x297c2)==0x1aa2d98
        || *reinterpret_cast<std::uint32_t*>(arena+0x297c2)==b+0x16a2d98,"inline prune reviewed actor operand");
    Put(b+0x297c2,static_cast<std::uint32_t>(b+0x16a2d98));
    // Exclude unrelated UI publication after real native undo/reapply sequence.
    Jump(0x3c4df8,b+0x3c4e96);
    for(const auto& site:e::sites){arena[site.rva+5]=0xc3;}
    DWORD previous{};if(!VirtualProtect(arena,arena_size,PAGE_EXECUTE_READWRITE,&previous)
        || !FlushInstructionCache(GetCurrentProcess(),arena,arena_size)){throw std::runtime_error("execute arena");}
}
}
int main(int argc,char** argv){
    try{
        if(argc!=2){throw std::runtime_error("usage: actor_effects_native_probe <exact original/prepared client13>");}
        std::ifstream stream(std::filesystem::path(argv[1]),std::ios::binary|std::ios::ate);const auto length=stream.tellg();
        if(!stream || length<=0 || length>32*1024*1024){throw std::runtime_error("image size");}
        std::vector<unsigned char> bytes(static_cast<std::size_t>(length));stream.seekg(0);if(!stream.read(reinterpret_cast<char*>(bytes.data()),length)){throw std::runtime_error("image read");}
        const auto sha=Digest(bytes);
        if((sha!="e5bb74e159a9acd8529652eb5b0c07766ced7ffd70c03c960ccdbcefca83c6e8" && (sha!="e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e" && (sha!="381e67586b3c36b8ce1dcdb824439010d373d455aa6b460b02cf44f7d58fe9e5" && sha!="a145ef491341e5107ec064de876d97f0e9c6ebbde2520d6509b4a3b47a7d825a"))) && (sha!="0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d" && (sha!="78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903" && (sha!="e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437" && sha!="1a5a9fd59da8255a3c98e16e1e8ff9a415c0921b4189583158c559ad2594360c")))){throw std::runtime_error("unreviewed image");}
        Load(bytes);Prepare();AddVectoredExceptionHandler(0,Fault);
        Check(reinterpret_cast<int(__cdecl*)()>(arena+0x1140e70)()==1 && entry_reached,"reviewed bootstrap completes");
        Check(!e::StartupCurrent(context.image,reinterpret_cast<std::uintptr_t>(_ReturnAddress())),"ordinary late caller cannot activate");
        e::Snapshot before,after;Check(e::Capture(context,before)==e::Unknown::none && before.count==1,"canonical owner snapshot after startup");
        std::array<std::uint32_t,2> add_context{0,static_cast<std::uint32_t>(Address(descriptor))};
        auto add=reinterpret_cast<e::OneArg>(*reinterpret_cast<std::uintptr_t*>(arena+0x1141600));
        add(reinterpret_cast<void*>(context.actor+0x588),static_cast<std::uint32_t>(Address(add_context)));
        Check(base_add_count==1 && notification_count==1 && !e::Revalidate(context,before),"native add retained descriptor path invalidates snapshot");
        descriptor[0x4c]=1;add(reinterpret_cast<void*>(context.actor+0x588),static_cast<std::uint32_t>(Address(add_context)));
        Check(base_add_count==1 && notification_count==1,"native descriptor+4C suppression bypasses base add");descriptor[0x4c]=0;
        auto remove=reinterpret_cast<e::TwoArgs>(*reinterpret_cast<std::uintptr_t*>(arena+0x1141604));remove(reinterpret_cast<void*>(context.actor+0x588),123,9);
        Check(notification_count==2,"native remove executes guarded notification");
        auto incoming=reinterpret_cast<e::NoArgs>(*reinterpret_cast<std::uintptr_t*>(arena+0x11598b8));incoming(message.data());
        Check(undo_count==1 && apply_count==1 && releases==1 && e::depth==0,"actual incoming undo/reapply/release completes within one outer scope");
        Check(e::Capture(context,after)==e::Unknown::none && after.count==1,"completed native rebuild can publish again");
        for(const auto& site:e::sites){
            const auto prior=e::Epoch();
            if(site.rebuild){reinterpret_cast<e::NoArgs>(arena+site.rva)(actor.data());Check(e::Epoch()==prior+2,"actual rebuild CALL trap holds full native helper");}
            else{
                const auto p=static_cast<std::uint32_t>(Address(entries));Put(context.actor+0x58c,e::Vector{p,p+8,p+16});
                Put(Address(record)+0x30,std::uint32_t{0x100001});
                InvokeEquipmentSite(arena+site.rva,actor.data(),3);
                Check(e::Epoch()==prior+2 && *reinterpret_cast<std::uint32_t*>(context.actor+0x590)==p,"actual equipment function inline prune invalidates and removes record");
            }
        }
        Check(e::Capture(context,after)==e::Unknown::none && after.count==0 && e::Revalidate(context,after),"complete post-prune census reflects real native empty vector");
        std::printf("{\"sha256\":\"%s\",\"checks\":%u,\"failures\":%u,\"scope\":\"bootstrap_local_wrappers_rebuild_inline_prune_instrumented_dependencies\"}\n",sha.c_str(),checks,failures);
        return failures?1:0;
    }catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return 1;}
}
