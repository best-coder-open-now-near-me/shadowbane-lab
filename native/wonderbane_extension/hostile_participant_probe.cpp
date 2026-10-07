// Offline exact-image continuation. The included probe supplies hash/arena and
// already-qualified health-prefix helpers; neither translation unit enters DLLs.
#define main QualifiedHealthPrefixMain
#include "hostile_health_consumer_probe.cpp"
#undef main

namespace {
struct Participant {
    std::array<unsigned char,0xb00> object{};
    std::array<unsigned,6> bases{};
    std::array<std::uintptr_t,3> references{};
    unsigned held{}, acquired{}, released{};
};
std::array<Participant*,4> participants{};
unsigned participant_cases{};
bool context_type{};
Participant* FindReference(void* subobject) {
    for(auto* p:participants){if(p&&subobject==p->object.data()+0x28){return p;}}
    Check(false,"unexpected reference subobject");return nullptr;
}
void __fastcall Held(void* object,void*,void** slot) {
    auto* p=FindReference(object);if(!p){return;}
    Check(*slot==p->object.data(),"native retain points at original object");++p->held;++p->acquired;
}
void __fastcall Dropped(void* object,void*,void** slot) {
    auto* p=FindReference(object);if(!p){return;}
    Check(*slot==nullptr,"native clears owning slot before release callback");
    Check(p->held>0,"no release without retained ownership");if(p->held){--p->held;}++p->released;
}
bool __fastcall ParticipantType(void* subobject,void*,unsigned mask) {
    for(auto* p:participants){if(p&&subobject==p->object.data()+0x48){
        if(mask==0x2000){return p->object.data()==expected_victim&&character_type;}
        if(context_type&&p==participants[3]&&(mask==0x20||mask==0x20000)){return true;}
        if(mask==0x10||mask==0x20||mask==0x20000||mask==0x10000){return false;}
    }}
    Check(false,"unsupported type dependency");return false;
}
void Init(Participant& p,unsigned id,unsigned type) {
    p={};p.bases[1]=0x20;p.bases[2]=0x30;p.bases[3]=0x40;
    p.references[2]=reinterpret_cast<std::uintptr_t>(&Dropped);
    Write(p.object.data(),8,p.bases.data());Write(p.object.data(),0x28,p.references.data());
    Write(p.object.data(),0x18,id);Write(p.object.data(),0x1c,type);
    Write(p.object.data(),0x5cc,100.0F);Write(p.object.data(),0x5d0,200.0F);
}
struct Registry {
    std::array<unsigned char,0xa0> manager{};
    std::array<unsigned,4> map{};
    std::array<void*,8> slots{};
    Registry(){Write(manager.data(),0x94,map.data());map[1]=Ptr(slots.data());map[2]=3;}
    void Put(Participant& p){
        const auto key=Read<unsigned>(p.object.data(),0x18)^Read<unsigned>(p.object.data(),0x1c);
        const auto index=(~key)&7;
        Check(slots[index]==nullptr,"fixture uses distinct initial hash slots");slots[index]=p.object.data();
    }
};
// Executes original caller key getter+manager lookup, returns the owned result.
// The rest of the queue pump is not emulated or claimed by this wrapper.
__declspec(naked) void* __cdecl CallerLookup(void*,void*,void*) {
    __asm {
        push ebp
        mov ebp,esp
        sub esp,60h
        push ebx
        push esi
        push edi
        mov esi,[ebp+0ch]
        mov eax,[ebp+10h]
        mov [ebp-14h],eax
        call dword ptr [ebp+8]
        mov eax,[ebp-28h]
        pop edi
        pop esi
        pop ebx
        mov esp,ebp
        pop ebp
        ret
    }
}
void PrepareParticipants(Arena& a,const std::vector<unsigned char>& file) {
    // Whole-image seal is checked before these copies. Table pointers and all
    // absolute code/data operands below are checked before relocation.
    const std::pair<unsigned,unsigned> spans[]{
        {0x4563e0,0x438},{0x45681c,23*4},{0x456060,0xf3},
        {0x1faacb,0x2b},{0xda130,0x23},{0x1fcc80,0x22},{0x1fb160,0x19e},
        {0x2150c0,0x230},{0x215680,0x1a},{0x2155f0,0x1c},{0x210c10,0x4e},
        {0x2184d0,0x1a},{0x210b00,0x21},{0x1125d0,0x23},{0x112210,0x11},
        {0x111b00,0x4a},{0x111b60,0x29},{0x1117b0,0x16},{0x1119d0,1},
        {0x89bd0,0x47},{0x89ba0,0x1c},{0x8a760,0x47},{0x8a730,0x1c},
        {0x12dda0,3},{0x12dde0,3},{0x227ea0,0x7c},{0x114a868,32*4},
        {0x45cd90,0x21c},{0x45dd99,0x16},{0x9e9f0,0x30},
        {0x115f9d4,4},{0x1141320,4}
    };
    for(const auto& span:spans){a.Copy(file,span.first,span.second);}
    for(auto rva:{0x10dc5,0x1d7e1,0xab5f,0x16149,0x15744,0x1bc66,0xca40,
        0x1a357,0x21aa3,0x1e11e,0x2923,0x4d9a,0xbd25,0x2526b,0x23cb3,0x25581,0xb069,
        0x208fb,0x1331d,0xc2fc,0x1eeed,0x189b2,0x13f7f,0x14a8d,0x22eb2}){a.Copy(file,rva,5);}
    a.bytes[0x1faaf6]=0xc3;
    for(auto offset:{0x4563e6,0x456066,0x1fb166,0x2150c6,0x45cd96}){
        const auto original=Read<unsigned>(file.data(),offset);
        a.Absolute(offset,original,Ptr(reinterpret_cast<void*>(&UnwindNotQualified)));
    }
    a.Absolute(0x45650e,0x1aa7c3c,Ptr(a.bytes+0x16a7c3c));
    a.Absolute(0x4565cd,0x1aa7c3c,Ptr(a.bytes+0x16a7c3c));
    a.Absolute(0x456632,0x85681c,Ptr(a.bytes+0x45681c));
    for(unsigned i=0;i<23;++i){const auto offset=0x45681c+4*i;
        const auto va=Read<unsigned>(file.data(),offset);
        if(va<0x856636||va>0x8567d3){throw std::runtime_error("dispatch table target outside reviewed consumer");}
        a.Absolute(offset,va,Ptr(a.bytes+va-0x400000));
    }
    a.Absolute(0x2151ed,0x154a868,Ptr(a.bytes+0x114a868));
    a.Absolute(0x45cf54,0x155f9d4,Ptr(a.bytes+0x115f9d4));
    a.Absolute(0x45cf6b,0x155f9d4,Ptr(a.bytes+0x115f9d4));
    a.Absolute(0x45cf8c,0x1541320,Ptr(a.bytes+0x1141320));
    a.Absolute(0x45cef4,0x1aa2da4,Ptr(a.bytes+0x16a2da4));
    a.Absolute(0x45cf01,0x1aa2d98,Ptr(a.bytes+0x16a2d98));
    Write(a.bytes,0x16a2da4,1U);
    handler_end=reinterpret_cast<std::uintptr_t>(a.bytes+0x45dd99);
    Jump(a.bytes+0x45cfac,reinterpret_cast<std::uintptr_t>(&Endpoint));
    a.Redirect(0x5e61,reinterpret_cast<void*>(&ParticipantType));
    a.Redirect(0xb2b7,reinterpret_cast<void*>(&Held));
    a.Redirect(0x25a8b,reinterpret_cast<void*>(&CopyReference));
    a.Redirect(0x27395,reinterpret_cast<void*>(&Notify));
    a.Redirect(0x19105,reinterpret_cast<void*>(&Setter));
    native_set=reinterpret_cast<SetHealth>(a.bytes+0x9e9f0);
}
void ParticipantCases(Arena& a) {
    Participant attacker,victim,replacement,context;
    Init(attacker,11,37);Init(victim,22,53);Init(replacement,22,53);Init(context,31,37);
    participants={&attacker,&victim,&replacement,&context};expected_victim=victim.object.data();
    Registry registry;registry.Put(attacker);registry.Put(victim);registry.Put(context);
    Write(a.bytes,0x16a7c3c,registry.manager.data());
    using Lookup=void*(__thiscall*)(void*,void**,const void*);
    const auto lookup=reinterpret_cast<Lookup>(a.bytes+0x1fcc80);
    using Assign=void(__thiscall*)(void*,void*);
    const auto clear=reinterpret_cast<Assign>(a.bytes+0x89bd0);
    using Consume=unsigned(__thiscall*)(void*,void*);
    const auto consume=reinterpret_cast<Consume>(a.bytes+0x4563e0);
    using Destroy=void(__thiscall*)(void*);
    const auto destroy=reinterpret_cast<Destroy>(a.bytes+0x456060);
    std::array<unsigned char,0x58> action{},linked{};
    auto reset=[&](){
        action.fill(0);Write(action.data(),8,11U);Write(action.data(),12,37U);
        Write(action.data(),0x28,22U);Write(action.data(),0x2c,53U);
        Write(action.data(),0x10,21U);Write(action.data(),0x18,60.0F);
        Write(action.data(),0x48,linked.data());Write(victim.object.data(),0x5cc,100.0F);
        setters=notifications=0;character_type=true;context_type=false;
    };
    reset();
    void* held=CallerLookup(a.bytes+0x1faacb,action.data(),registry.manager.data());
    Check(held==attacker.object.data()&&attacker.held==1,"real caller resolves original attacker key and retains exact object");
    clear(&held,nullptr);Check(attacker.held==0,"caller output balanced release");++participant_cases;
    std::array<unsigned,2> missing{44,53};held=reinterpret_cast<void*>(1);
    lookup(registry.manager.data(),&held,missing.data());
    Check(held==nullptr,"native absent registry result is null");++participant_cases;
    Check(consume(action.data(),attacker.object.data())==1&&setters==1,"real kind21 dispatch reaches native health prefix");
    Check(Read<void*>(action.data(),0x38)==attacker.object.data()&&Read<void*>(action.data(),0x4c)==victim.object.data(),"consumer retains resolved participants");
    Check(Read<void*>(attacker.object.data(),0xae4)==linked.data(),"consumer restores raw parent link to actor current action");
    Check(attacker.held==1&&victim.held==1,"only persistent action participants remain held");
    destroy(action.data());Check(attacker.held==0&&victim.held==0,"destructor releases both native participant slots");
    Check(Read<void*>(action.data(),0x48)==linked.data(),"destructor leaves raw parent pointer untouched");++participant_cases;
    // Same address/key lookup is live lookup, not an original-object lifetime seal.
    reset();registry.slots[(~(22U^53U))&7]=replacement.object.data();expected_victim=replacement.object.data();
    Check(consume(action.data(),attacker.object.data())==1&&Read<void*>(action.data(),0x4c)==replacement.object.data(),"replacement same-key victim adopted by native lookup");
    destroy(action.data());expected_victim=victim.object.data();registry.slots[(~(22U^53U))&7]=victim.object.data();++participant_cases;
    // Already-retained victim is cleared before re-resolution, even on absence.
    reset();consume(action.data(),attacker.object.data());registry.slots[(~(22U^53U))&7]=nullptr;setters=0;
    Check(consume(action.data(),attacker.object.data())==1&&setters==0&&Read<void*>(action.data(),0x4c)==nullptr&&victim.held==0,"missing victim drops prior slot and return1 cannot prove consumption");
    destroy(action.data());registry.slots[(~(22U^53U))&7]=victim.object.data();++participant_cases;
    reset();consume(action.data(),attacker.object.data());setters=0;
    Check(consume(action.data(),attacker.object.data())==1&&setters==0,"repeat consumes same action without a second health change");
    destroy(action.data());++participant_cases;
    // A directly supplied caller object is accepted even if action key differs.
    reset();Write(action.data(),8,999U);consume(action.data(),attacker.object.data());
    Check(Read<void*>(action.data(),0x38)==attacker.object.data(),"consumer does not independently validate supplied attacker against key");destroy(action.data());++participant_cases;
    // Context lookup runs, unsupported contextual type falls back to global victim.
    reset();Write(action.data(),0x30,31U);Write(action.data(),0x34,37U);
    consume(action.data(),attacker.object.data());
    Check(Read<void*>(action.data(),0x50)==context.object.data()&&Read<void*>(action.data(),0x4c)==victim.object.data(),"context resolution with native global victim fallback");
    destroy(action.data());Check(context.held==0,"context reference released by destructor");++participant_cases;
    // Context interface is selected by the real native conversion routine. Its
    // fixture virtual lookup slot calls the same real native registry wrapper;
    // terminal type masks remain explicit instrumentation, not RTTI proof.
    reset();context_type=true;Registry contextual;
    contextual.Put(replacement);
    std::array<std::uintptr_t,2> context_table{};
    context_table[1]=reinterpret_cast<std::uintptr_t>(a.bytes+0x1fcc80);
    Write(context.object.data(),0,context_table.data());Write(context.object.data(),0x94,contextual.map.data());
    Write(action.data(),0x30,31U);Write(action.data(),0x34,37U);expected_victim=replacement.object.data();
    consume(action.data(),attacker.object.data());
    Check(Read<void*>(action.data(),0x4c)==replacement.object.data(),"context victim takes precedence over same-key global object");
    destroy(action.data());expected_victim=victim.object.data();++participant_cases;
    // Native sparse probing compares both key words, traverses collisions and
    // tombstones. It must not turn a similar key into the intended participant.
    Init(replacement,14,37);registry.slots[2]=replacement.object.data();
    std::array<unsigned,2> collision{14,37};held=nullptr;
    lookup(registry.manager.data(),&held,collision.data());
    Check(held==replacement.object.data(),"real secondary hash probe resolves colliding key");clear(&held,nullptr);++participant_cases;
    registry.slots[4]=reinterpret_cast<void*>(~0U);
    lookup(registry.manager.data(),&held,collision.data());
    Check(held==replacement.object.data(),"real lookup skips tombstone before colliding key");clear(&held,nullptr);++participant_cases;
    registry.slots[4]=victim.object.data();registry.slots[2]=nullptr;
    std::array<unsigned,2> wrong_type{22,61};lookup(registry.manager.data(),&held,wrong_type.data());
    Check(held==nullptr,"native key comparison includes UUID word");++participant_cases;
    reset();Write(action.data(),8,999U);
    held=CallerLookup(a.bytes+0x1faacb,action.data(),registry.manager.data());
    Check(held==nullptr,"caller lookup refuses missing original attacker");++participant_cases;
    // Dispatcher default preserves its return2 and actor-link bookkeeping, but
    // never enters the health prefix. The full handler tail remains excluded.
    reset();Write(action.data(),0x10,99U);
    Check(consume(action.data(),attacker.object.data())==2&&setters==0,"unsupported kind does not become health consumption");
    destroy(action.data());++participant_cases;
    for(auto* p:participants){Check(p->held==0&&p->acquired==p->released,"all instrumented terminal references balanced");}
}
}
int main(int argc,char** argv) {
    if(QualifiedHealthPrefixMain(argc,argv)){return 2;}
    try {
        std::ifstream stream(std::filesystem::path(argv[1]),std::ios::binary|std::ios::ate);
        const auto count=stream.tellg();
        if(!stream||count<=0||count>64*1024*1024){throw std::runtime_error("invalid second image read");}
        std::vector<unsigned char> file(static_cast<std::size_t>(count));
        stream.seekg(0);if(!stream.read(reinterpret_cast<char*>(file.data()),count)){throw std::runtime_error("short second image read");}
        // Recheck the second read before copying or executing any bytes.
        const auto hash=Digest(file.data(),file.size());
        if(hash!="e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e"&&hash!="78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903"){throw std::runtime_error("image changed between reads");}
        Arena arena;if(!arena.bytes){throw std::runtime_error("arena allocation failed");}
        arena_base=reinterpret_cast<std::uintptr_t>(arena.bytes);
        PrepareParticipants(arena,file);
        // Private arena includes writable fixture globals; no game/image memory.
        DWORD prior{};if(!VirtualProtect(arena.bytes,Arena::size,PAGE_EXECUTE_READWRITE,&prior)||!FlushInstructionCache(GetCurrentProcess(),arena.bytes,Arena::size)){throw std::runtime_error("arena protection");}
        ParticipantCases(arena);
        std::printf("{\"participant_cases\":%u,\"failures\":%u,\"scope\":\"native_lookup_dispatch_and_normal_disposal_with_instrumented_terminal_refs\",\"authority\":false}\n",participant_cases,failures);
        return failures?1:0;
    }catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return 2;}
}
