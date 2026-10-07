// Offline .14 native field-transfer and health-update conformance only.
// No runtime hook, network lifetime, hostile-event authority, or retaliation.
#include <Windows.h>
#include <bcrypt.h>
#include <array>
#include <cmath>
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
unsigned failures{}, cases{}, setters{}, notifications{}, formats{}, retains{}, releases{};
bool character_type=true, negative_health_type=false;
void* expected_victim{};
std::uintptr_t arena_base{};
std::uintptr_t handler_end{};
unsigned frame_distance{};
__declspec(naked) void Endpoint() {
    __asm {
        mov eax,ebp
        sub eax,esp
        mov frame_distance,eax
        jmp dword ptr [handler_end]
    }
}
LONG CALLBACK Fault(EXCEPTION_POINTERS* exception) {
    std::fprintf(stderr,"unqualified native fault code=%08lx rva=%08lx address=%08lx\n",
        exception->ExceptionRecord->ExceptionCode,
        static_cast<unsigned long>(exception->ContextRecord->Eip-arena_base),
        static_cast<unsigned long>(exception->ExceptionRecord->ExceptionInformation[1]));
    std::fprintf(stderr,"frame distance=%x\n",frame_distance);
    TerminateProcess(GetCurrentProcess(),3);return EXCEPTION_CONTINUE_SEARCH;
}
using SetHealth=void(__thiscall*)(void*,float);
SetHealth native_set{};
void Check(bool ok,const char* label) {
    if(!ok){++failures;std::fprintf(stderr,"%s\n",label);}
}
template<class T> T Read(const void* object,std::size_t offset) {
    T value{};std::memcpy(&value,static_cast<const unsigned char*>(object)+offset,sizeof(value));return value;
}
template<class T> void Write(void* object,std::size_t offset,T value) {
    std::memcpy(static_cast<unsigned char*>(object)+offset,&value,sizeof(value));
}
std::uint32_t Ptr(const void* pointer){return static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(pointer));}
std::string Digest(const unsigned char* bytes,std::size_t length) {
    BCRYPT_ALG_HANDLE algorithm{};BCRYPT_HASH_HANDLE hash{};std::array<unsigned char,32> result{};
    const bool ok=BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0
        && BCryptCreateHash(algorithm,&hash,nullptr,0,nullptr,0,0)>=0
        && BCryptHashData(hash,const_cast<unsigned char*>(bytes),static_cast<ULONG>(length),0)>=0
        && BCryptFinishHash(hash,result.data(),static_cast<ULONG>(result.size()),0)>=0;
    if(hash){BCryptDestroyHash(hash);}if(algorithm){BCryptCloseAlgorithmProvider(algorithm,0);}
    if(!ok){throw std::runtime_error("SHA256 failed");}
    constexpr char hex[]="0123456789abcdef";std::string value;
    for(auto byte:result){value+=hex[byte>>4];value+=hex[byte&15];}return value;
}
// Substitutes below are deliberately NOT native type, reference, equipment,
// notification, formatting, or unwind qualification. Unknown requests fail.
bool __fastcall TypeMask(void* object,void*,unsigned mask) {
    Check(object==static_cast<unsigned char*>(expected_victim)+8,"type query must address exact victim subobject");
    if(mask==0x2000){return character_type;}
    if(mask==0x10){return false;} // exclude equipment/UI character branch
    if(mask==0x10000){return negative_health_type;}
    Check(false,"unexpected type-mask dependency");return false;
}
void __fastcall Retain(void* object,void*,void** reference) {
    Check(object==static_cast<unsigned char*>(expected_victim)+8&&*reference==expected_victim,"reference retain identity");++retains;
}
void* __fastcall CopyReference(void* output,void*,void** input) {
    Write(output,0,*input);return output;
}
void __fastcall Release(void* object,void*,void** reference) {
    Check(object==static_cast<unsigned char*>(expected_victim)+8&&*reference==nullptr,"reference release identity after native clear");++releases;
}
void __cdecl Notify(void* reference,unsigned zero,unsigned kind,void* equipment) {
    Check(reference==expected_victim&&zero==0&&kind==6&&equipment==nullptr,"notification dependency arguments");++notifications;
}
void __fastcall Setter(void* victim,void*,float value) {
    Check(victim==expected_victim,"setter exact victim");++setters;native_set(victim,value);
}
void __fastcall BindAttacker(void* action,void*,void* actor){Write(action,0x38,actor);}
void __fastcall BindVictim(void* action,void*,void* victim){Write(action,0x4c,victim);}
void __fastcall Format(void*,void*){++formats;}
LONG __cdecl UnwindNotQualified(void*,void*,void*,void*) {
    // No fault is an accepted case. Do not execute a client unwind handler in
    // the private arena; let the probe fail rather than infer recovery behavior.
    Check(false,"native exception outside qualified normal execution");return 1;
}
void Jump(unsigned char* at,std::uintptr_t target) {
    at[0]=0xe9;Write(at,1,static_cast<std::uint32_t>(target-reinterpret_cast<std::uintptr_t>(at)-5));
}
struct Arena {
    static constexpr std::size_t size=0x16b0000;
    unsigned char* bytes=static_cast<unsigned char*>(VirtualAlloc(nullptr,size,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    ~Arena(){if(bytes){VirtualFree(bytes,0,MEM_RELEASE);}}
    void Copy(const std::vector<unsigned char>& file,std::size_t offset,std::size_t length,const char* hash=nullptr) {
        if(offset+length>file.size()||offset+length>size){throw std::runtime_error("span bounds");}
        if(hash&&Digest(file.data()+offset,length)!=hash){throw std::runtime_error("native span differs");}
        std::memcpy(bytes+offset,file.data()+offset,length);
    }
    void Absolute(std::size_t offset,std::uint32_t original,std::uint32_t replacement) {
        if(Read<std::uint32_t>(bytes,offset)!=original){throw std::runtime_error("absolute operand differs");}
        Write(bytes,offset,replacement);
    }
    void Redirect(std::size_t offset,void* target){Jump(bytes+offset,reinterpret_cast<std::uintptr_t>(target));}
};
// Original message argument-transfer slices expect ESI=message, EDI=victim key,
// EAX=temporary key, and specific EBP locals. No allocator/lookup/queue executes.
__declspec(naked) void* __cdecl Transfer(void*,void*,void*,void*,unsigned) {
    __asm {
        push ebp
        mov ebp,esp
        sub esp,60h
        push ebx
        push esi
        push edi
        mov esi,[ebp+0ch]
        lea edi,[esi+88h]
        lea eax,[esi+80h]
        mov [ebp-1ch],eax
        mov eax,[ebp+10h]
        mov [ebp-24h],eax
        mov [ebp-2ch],eax
        cmp dword ptr [ebp+18h],0
        je secondary
        mov dword ptr [ebp-24h],0
    secondary:
        mov eax,[ebp+14h]
        mov ebx,2
        call dword ptr [ebp+8]
        pop edi
        pop esi
        pop ebx
        mov esp,ebp
        pop ebp
        ret
    }
}
__declspec(naked) void* __cdecl Fallback(void*,void*,void*) {
    __asm {
        push ebp
        mov ebp,esp
        sub esp,30h
        push edi
        mov edi,[ebp+0ch]
        lea eax,[edi+80h]
        mov [ebp-1ch],eax
        add edi,88h
        mov ecx,[ebp+10h]
        call dword ptr [ebp+8]
        pop edi
        mov esp,ebp
        pop ebp
        ret
    }
}
__declspec(naked) void __cdecl FormatterRoute(void*,void*,void*,void*) {
    __asm {
        push ebp
        mov ebp,esp
        sub esp,30h
        push esi
        mov esi,[ebp+0ch]
        mov eax,[ebp+10h]
        mov [ebp-18h],eax
        mov eax,[ebp+14h]
        mov [ebp-10h],eax
        call dword ptr [ebp+8]
        pop esi
        mov esp,ebp
        pop ebp
        ret
    }
}
}
int main(int argc,char** argv) {
    try {
        if(argc!=2){throw std::runtime_error("usage: hostile_health_consumer_probe <exact original/prepared .14 image>");}
        std::ifstream input(std::filesystem::path(argv[1]),std::ios::binary|std::ios::ate);
        const auto length=input.tellg();
        if(!input||length<=0||length>64*1024*1024){throw std::runtime_error("invalid executable");}
        std::vector<unsigned char> file(static_cast<std::size_t>(length));input.seekg(0);
        if(!input.read(reinterpret_cast<char*>(file.data()),length)){throw std::runtime_error("short executable");}
        const auto hash=Digest(file.data(),file.size());
        if(hash!="e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e"
            &&hash!="78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903"){
            throw std::runtime_error("unreviewed image");}
        Arena arena;if(!arena.bytes){throw std::runtime_error("arena allocation failed");}
        arena_base=reinterpret_cast<std::uintptr_t>(arena.bytes);
        if(!AddVectoredExceptionHandler(1,&Fault)){throw std::runtime_error("fault reporting unavailable");}
        arena.Copy(file,0x455ea0,0xa9,"17d1859be1747c4dd6dde5e10b5d1e6a9151f518690cb58c03ffac441828fcec");
        arena.Copy(file,0x45cd90,0x21c,"0c150915bfdede40de973df717e68e4b83333407c7464023b28a54cfc18b5774");
        arena.Copy(file,0x45dd99,0x16,"4b6ffdf27236bac4d7a596af0ce2d4e218b68a0eae5690f56346ad39be3e301a");
        arena.Copy(file,0x1117b0,0x16,"66b42201ae2adac5438161fdb2a8dc60eb4bf84b6a9462a2564677c9a809cdd4");
        arena.Copy(file,0x111b60,0x29,"28fd5a72534a4ad916ff3c4d24a366264f4f26850deb28f9a859e59ad940aa0f");
        arena.Copy(file,0x9e9f0,0x30,"2d9973faf1244ac24ecec8e94ec1fb5b71b5350533f78171fd8dc7ed598d3540");
        arena.Copy(file,0x3ae261,0x33,"3dfc51cd24e0b871e53dd14d6727aece44127c54565c629c3975d416fec10f15");
        arena.Copy(file,0x3ae2d5,0x36,"b94e46a5fe6811a833af3a393ec3c85529895149bcc022e716b0a398bfa81b5f");
        arena.Copy(file,0x3ae454,9,"571affb3fa9ecd24af304a7210158a6f64a0ca4962b364d14f3648f8e0683ef7");
        arena.Copy(file,0x3ae189,0x1d,"3741ff2dfecd39c2839b0962cf30cafba86ce1e3ec7fc106825fa25c8ba9e40d");
        for(auto rva:{0x25581,0x21aa3,0x1e11e}){arena.Copy(file,rva,5);}
        arena.Copy(file,0x115f9d4,4);arena.Copy(file,0x1141320,4);
        for(auto end:{0x3ae294,0x3ae30b,0x3ae45d,0x3ae1a6}){arena.bytes[end]=0xc3;}
        handler_end=reinterpret_cast<std::uintptr_t>(arena.bytes+0x45dd99);
        Jump(arena.bytes+0x45cfac,reinterpret_cast<std::uintptr_t>(&Endpoint));
        arena.Absolute(0x45cf54,0x155f9d4,Ptr(arena.bytes+0x115f9d4));
        arena.Absolute(0x45cf6b,0x155f9d4,Ptr(arena.bytes+0x115f9d4));
        arena.Absolute(0x45cf8c,0x1541320,Ptr(arena.bytes+0x1141320));
        arena.Absolute(0x45cef4,0x1aa2da4,Ptr(arena.bytes+0x16a2da4));
        arena.Absolute(0x45cf01,0x1aa2d98,Ptr(arena.bytes+0x16a2d98));
        Write(arena.bytes,0x16a2da4,1U); // skip unqualified local-attacker notification19e66
        arena.Absolute(0x455ea6,0xd7fb96,Ptr(reinterpret_cast<void*>(&UnwindNotQualified)));
        arena.Absolute(0x45cd96,0xd81218,Ptr(reinterpret_cast<void*>(&UnwindNotQualified)));
        arena.Redirect(0x5e61,reinterpret_cast<void*>(&TypeMask));
        arena.Redirect(0xb2b7,reinterpret_cast<void*>(&Retain));
        arena.Redirect(0x25a8b,reinterpret_cast<void*>(&CopyReference));
        arena.Redirect(0x27395,reinterpret_cast<void*>(&Notify));
        arena.Redirect(0x19105,reinterpret_cast<void*>(&Setter));
        arena.Redirect(0x79f0,reinterpret_cast<void*>(&BindAttacker));
        arena.Redirect(0x1ca4e,reinterpret_cast<void*>(&BindVictim));
        arena.Redirect(0x21995,reinterpret_cast<void*>(&Format));
        native_set=reinterpret_cast<SetHealth>(arena.bytes+0x9e9f0);
        DWORD old{};if(!VirtualProtect(arena.bytes,Arena::size,PAGE_EXECUTE_READ,&old)
            ||!FlushInstructionCache(GetCurrentProcess(),arena.bytes,Arena::size)){
            throw std::runtime_error("arena protection failed");}
        std::array<unsigned char,0xb0> message{};
        Write(message.data(),0x80,11U);Write(message.data(),0x84,37U);
        Write(message.data(),0x88,22U);Write(message.data(),0x8c,53U);
        Write(message.data(),0x90,21U);Write(message.data(),0x94,123U);
        Write(message.data(),0x98,60.0F);Write(message.data(),0x9c,17U);
        Write(message.data(),0xa0,8U);Write(message.data(),0xa4,456U);
        Write(message.data(),0xa8,40.0F);Write(message.data(),0xac,19U);
        std::array<unsigned char,0x58> action{};
        std::array<unsigned,2> empty_key{};
        for(unsigned primary:{0U,1U}) {
            action.fill(0);
            Check(Transfer(arena.bytes+(primary?0x3ae2d5:0x3ae261),message.data(),action.data(),empty_key.data(),primary)==action.data(),"native constructor return");
            Check(Read<unsigned>(action.data(),8)==11&&Read<unsigned>(action.data(),12)==37
                &&Read<unsigned>(action.data(),0x28)==22&&Read<unsigned>(action.data(),0x2c)==53,"native key field transfer");
            Check(Read<unsigned>(action.data(),0x10)==(primary?21U:8U)
                &&Read<unsigned>(action.data(),0x14)==(primary?123U:456U)
                &&Read<float>(action.data(),0x18)==(primary?60.0F:40.0F)
                &&Read<unsigned>(action.data(),0x1c)==(primary?17U:19U),"native scalar field transfer");
            Check(Read<unsigned>(action.data(),0x4c)==0&&Read<unsigned>(action.data(),0x38)==0,"constructor does not invent participant references");++cases;
        }
        std::array<unsigned char,0x600> victim{};expected_victim=victim.data();
        std::array<std::uintptr_t,4> table{};table[2]=reinterpret_cast<std::uintptr_t>(&Release);
        Write(victim.data(),8,table.data());
        using Handler=unsigned(__thiscall*)(void*);
        const auto consume=reinterpret_cast<Handler>(arena.bytes+0x45cd90);
        struct Case {float old_health,value,max_health,expected;bool special;unsigned calls;};
        const Case values[]{
            {100,60,200,60,false,1},{100,100,200,100,false,0},
            {100,100.0005F,200,100,false,0},{100,140,200,140,false,1},
            {100,250,200,200,false,1},{100,-1,200,-1,false,1},
            {100,-1,200,100,true,0},{100,0,200,0,true,1},
            {100,std::numeric_limits<float>::quiet_NaN(),200,100,false,0},
            {100,std::numeric_limits<float>::infinity(),200,200,false,1},
            {100,-std::numeric_limits<float>::infinity(),200,-std::numeric_limits<float>::infinity(),false,1},
        };
        for(const auto& value:values) {
            Transfer(arena.bytes+0x3ae2d5,message.data(),action.data(),empty_key.data(),1);
            Write(action.data(),0x4c,victim.data());Write(action.data(),0x18,value.value);
            Write(victim.data(),0x5cc,value.old_health);Write(victim.data(),0x5d0,value.max_health);
            character_type=true;negative_health_type=value.special;setters=notifications=retains=releases=frame_distance=0;
            Check(consume(action.data())==1,"native handler return remains nondiscriminating");
            Check(Read<float>(victim.data(),0x5cc)==value.expected&&setters==value.calls,"native health predicate/setter result");
            Check(notifications==1&&retains==1&&releases==1,"instrumented reference/notification path");++cases;
            Check(frame_distance==0x688,"native prefix and substitutes preserve stack ABI");
        }
        // Secondary message kind8 is remapped to21 by the actual handler. Kind7
        // also reaches this health write but maps to20: a write is not itself a
        // discriminator for the supported kind21 case.
        for(unsigned kind:{7U,8U}) {
            Write(message.data(),0xa0,kind);
            Transfer(arena.bytes+0x3ae261,message.data(),action.data(),empty_key.data(),0);
            Write(action.data(),0x4c,victim.data());Write(victim.data(),0x5cc,100.0F);
            character_type=true;negative_health_type=false;setters=0;
            Check(consume(action.data())==1&&setters==1&&Read<float>(victim.data(),0x5cc)==40.0F
                &&Read<unsigned>(action.data(),0x10)==kind+13,"native secondary kind remap and scalar transfer");++cases;
        }
        for(bool missing:{false,true}) {
            Write(victim.data(),0x5cc,100.0F);Write(action.data(),0x18,50.0F);
            Write(action.data(),0x4c,missing?nullptr:victim.data());character_type=false;setters=notifications=0;
            Check(consume(action.data())==1&&setters==0&&notifications==0&&Read<float>(victim.data(),0x5cc)==100,"early rejection return1 is not application");++cases;
        }
        Check(Fallback(arena.bytes+0x3ae454,message.data(),victim.data())==message.data()+0x80,"present attacker retains original key");++cases;
        Check(Fallback(arena.bytes+0x3ae454,message.data(),nullptr)==message.data()+0x88,"missing attacker substitutes victim key; cannot attribute hostility");++cases;
        setters=formats=0;FormatterRoute(arena.bytes+0x3ae189,action.data(),victim.data(),victim.data());
        Check(formats==1&&setters==0,"formatter route does not invoke qualified health consumer; formatter body is substituted");++cases;
        std::printf("{\"image_sha256\":\"%s\",\"cases\":%u,\"failures\":%u,\"scope\":\"native_constructor_and_conditional_health_prefix_only\",\"authority\":false}\n",hash.c_str(),cases,failures);
        return failures?1:0;
    }catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return 2;}
}
