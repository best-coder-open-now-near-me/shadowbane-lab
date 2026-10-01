#include "actor_inventory_native.cpp"
#include <cstdio>
#include <stdexcept>
namespace iv=wonderbane::extension::combat::inventory;
namespace {
std::array<std::uint32_t,0xf00/4> actor{};
std::array<std::array<std::uint32_t,0x800/4>,17> objects{};
std::array<std::uint32_t,0x200/4> definition{};
std::array<std::uint32_t,8> heads[2]{};
std::array<std::array<std::uint32_t,8>,17> nodes{};
iv::Context context{};
unsigned failures{},cases{},lookups{},releases{},refs{},checks{};
bool current=true,missing=false,wrong_output=false,fault_lookup=false,throw_lookup=false,fault_release=false;
bool change_during_lookup=false,change_final_check=false;
void* replacement{};
std::uint32_t P(const void* p){return static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(p));}
void Put(std::uintptr_t at,std::uintptr_t value){*reinterpret_cast<std::uintptr_t*>(at)=value;}
void Check(bool value,const char* label){++cases;if(!value){++failures;std::fprintf(stderr,"%s\n",label);}}
bool Current(void*) noexcept {
    ++checks;
    if(change_final_check && checks==2){objects[0][0x744/4]++;}
    return current;
}
void* __fastcall Lookup(void* self,void*,void** out,const iv::Key* key){
    ++lookups;
    Check(self==reinterpret_cast<void*>(context.actor+0xea4) && !*out,"exact native interface/output");
    if(!missing){
        for(auto& object:objects){if(object[0x18/4]==(*key)[0]&&object[0x1c/4]==(*key)[1]){
            *out=replacement?replacement:object.data();++refs;break;}}
    }
    if(change_during_lookup){objects[0][0x744/4]++;}
    if(fault_lookup){RaiseException(0xe0420401,0,0,nullptr);}
    if(throw_lookup){throw std::runtime_error("lookup");}
    return wrong_output?reinterpret_cast<void*>(1):out;
}
void __fastcall Drop(void** out,void*,void* value){
    Check(!value&&*out&&refs,"known native reference release");++releases;
    if(fault_release){RaiseException(0xe0420401,0,0,nullptr);}
    *out=nullptr;--refs;
}
iv::Calls Calls(){return {reinterpret_cast<iv::Lookup>(&Lookup),reinterpret_cast<iv::NativeRelease>(&Drop)};}
bool Observe(iv::State& s,iv::Observation& o){return iv::Access::ObserveBound(context,s,o,Calls());}
bool Revalidate(iv::State& s,const iv::Observation& o){return iv::Access::RevalidateBound(context,s,o,Calls());}
void Reset(unsigned count=1,unsigned container=0){
    actor={};objects={};definition={};nodes={};heads[0]={};heads[1]={};
    lookups=releases=refs=checks=0;current=true;missing=wrong_output=fault_lookup=throw_lookup=fault_release=false;
    change_during_lookup=change_final_check=false;replacement=nullptr;
    const auto b=iv::base;
    actor[0]=static_cast<std::uint32_t>(b+0x114165c);actor[2]=static_cast<std::uint32_t>(b+0x11417d4);
    actor[0x18/4]=4050960;actor[0x1c/4]=53;actor[0xea4/4]=static_cast<std::uint32_t>(b+0x1141570);
    actor[0x688/4]=static_cast<std::uint32_t>(b+0x11415e4);actor[0x6f0/4]=static_cast<std::uint32_t>(b+0x11415cc);
    actor[0x6cc/4]=P(heads[0].data());actor[0x734/4]=P(heads[1].data());
    for(auto& h:heads){h[2]=h[3]=P(h.data());}
    definition[0]=static_cast<std::uint32_t>(b+0x11428f0);definition[0xf4/4]=8;definition[0x11c/4]=10;
    for(unsigned i=0;i<count;++i){
        auto& o=objects[i];o[0]=static_cast<std::uint32_t>(b+0x1142748);o[0x10/4]=980066;
        o[0x18/4]=5802955+i;o[0x1c/4]=30;o[0x68c/4]=P(definition.data());o[0x744/4]=3;
        auto& n=nodes[i];n[1]=i?P(nodes[i-1].data()):P(heads[container].data());
        n[3]=i+1<count?P(nodes[i+1].data()):0;n[4]=o[0x18/4];n[5]=30;n[6]=P(o.data());
    }
    if(count){heads[container][1]=heads[container][2]=P(nodes[0].data());heads[container][3]=P(nodes[count-1].data());}
    context={b,reinterpret_cast<std::uintptr_t>(actor.data()),{4050960,53},{980066,0},Current,nullptr};
    Put(b+0x16a2d98,context.actor);
}
void Denied(const char* label){iv::State s;iv::Observation o;Check(!Observe(s,o)&&!o.count&&!s.Quarantined()&&refs==0,label);}
}
namespace wonderbane::extension {
bool GraphicsExecutableSha256Matches(const char*) noexcept{return false;}
namespace movement {bool VerifyNativeMovementImage(std::uintptr_t&) noexcept{return false;}}
}
int main(){
    iv::base=reinterpret_cast<std::uintptr_t>(VirtualAlloc(nullptr,0x16b0000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    if(!iv::base){return 2;}
    for(unsigned tree:{0U,1U}){
        Reset(1,tree);iv::State s;iv::Observation o;
        Check(Observe(s,o)&&o.count==1&&o.items[0].quantity==3&&o.items[0].item_key==iv::Key{5802955,30}&&refs==1,"owned candidate each tree");
        Check(Revalidate(s,o)&&refs==1,"fresh native membership verification balances scratch");
        auto changed=o;changed.items[0].quantity=99;Check(!Revalidate(s,changed),"caller cannot forge published facts");
        const auto old=o;Check(iv::Release(s)&&refs==0,"explicit balanced release");
        Check(Observe(s,o)&&o.generation!=old.generation&&!Revalidate(s,old),"old publication cannot revive after State reuse");
        Check(iv::Release(s),"reused state released");
    }
    Reset(0);Denied("empty inventory unavailable, not absence");
    Reset();definition[0xf4/4]=6;Denied("unknown route not eligible");
    Reset();objects[0][0x744/4]=0;Denied("zero quantity unavailable");
    Reset();objects[0][0x10/4]++;Denied("other template unavailable");
    Reset();objects[0][0x18/4]++;Denied("tree/object key mismatch");
    Reset();actor[0x6cc/4]=0;Denied("null root container rejects");
    Reset();nodes[0][3]=P(nodes[0].data());Denied("cycle rejected");
    Reset();heads[0][3]=P(heads[0].data());Denied("sentinel extrema mismatch");
    Reset();nodes[0][1]=1;Denied("bad root parent");
    Reset();heads[1]=heads[0];Denied("shared node across containers rejected");
    Reset();current=false;Denied("invalid owner rejected before native lookup");Check(!lookups,"no calls under invalid owner");
    Reset();missing=true;Denied("native lookup absence rejects discovery");
    Reset();auto copy=objects[0];replacement=copy.data();Denied("same-key replacement cannot inherit discovery");
    Reset();change_during_lookup=true;Denied("facts changed while lookup rejects with balanced release");
    Reset();change_final_check=true;Denied("final owner callback mutation caught by recapture");
    Reset(16);{iv::State s;iv::Observation o;Check(Observe(s,o)&&o.count==16&&refs==16,"complete bounded sixteen candidates");Check(iv::Release(s)&&refs==0,"all candidates balanced");}
    Reset(17);Denied("candidate overflow never publishes partial");Check(!lookups,"overflow before retain");
    Reset();{iv::Budget b;b.deadline=0;iv::Census c;Check(!iv::Capture(context,c,b),"expired shared work budget");}
    Reset();{iv::Budget b;iv::Census c;c.count=iv::kMaxNodes;std::uintptr_t f{},l{};
        Check(!iv::Walk(context,c,P(nodes[0].data()),0,P(heads[0].data()),nullptr,nullptr,0,f,l,b),"node work bound");}
    Reset();{iv::State s;iv::Observation o;Check(Observe(s,o),"stale fixture starts owned");
        heads[0][1]=0;heads[0][2]=heads[0][3]=P(heads[0].data());
        Check(!Revalidate(s,o)&&refs==1,"removed readable object no longer member");
        heads[0][1]=heads[0][2]=heads[0][3]=P(nodes[0].data());
        Check(!Revalidate(s,o),"failed publication cannot resurrect");Check(iv::Release(s)&&!refs,"stale ownership still releases");}
    for(unsigned fault=0;fault<4;++fault){
        Reset();fault_lookup=fault==0;throw_lookup=fault==1;wrong_output=fault==2;
        iv::State s;iv::Observation o;
        if(fault==3){Check(Observe(s,o),"release fault starts retained");fault_release=true;Check(!iv::Release(s),"release fault caught");}
        else{Check(!Observe(s,o),"lookup exception/ABI failure caught");}
        const auto before=lookups+releases;
        Check(s.Quarantined()&&!iv::Release(s)&&!Observe(s,o)&&lookups+releases==before,"quarantine never retries uncertain ownership");
    }
    std::printf("inventory observation: %u checks, %u failures\n",cases,failures);return failures?1:0;
}
