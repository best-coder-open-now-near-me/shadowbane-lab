#include "actor_buff_observation.cpp"
#include <cstdio>
namespace b=wonderbane::extension::actor_buffs;
namespace e=wonderbane::extension::actor_effects;
namespace inv=wonderbane::extension::combat::inventory;
namespace {
unsigned failures{},checks{};std::uint64_t effect_epoch=1,power_epoch=1;
bool actor_current=true,foreign_use=false,effect_present=false,item_present=false,item_current=true;
unsigned inventory_mutation{};bool item_unknown=false;
unsigned char* image{};
alignas(4) std::array<unsigned char,0xe00> actor{};
alignas(4) std::array<unsigned char,0x30> state{};
alignas(4) std::array<unsigned char,0x2b0> definition{};
alignas(4) std::array<unsigned char,0x94> action{};
alignas(4) std::array<unsigned char,0x60> fixture_descriptor{};
std::array<std::uint32_t,2> power_manager{},effect_manager{};
std::array<std::uint32_t,4> power_sentinel{},effect_sentinel{};
std::array<std::uint32_t,6> power_node{},effect_node{};
std::array<std::array<unsigned char,0x50>,2> actions{};
std::array<std::array<std::uint32_t,4>,2> learned{};
std::array<std::uint32_t,2> reuse_head{},reuse_sentinel{};
std::array<std::uint32_t,4> reuse_node{};
e::Context context{};
void Check(bool ok,const char* label){++checks;if(!ok){++failures;std::fprintf(stderr,"%s\n",label);}}
std::uintptr_t Address(auto& value){return reinterpret_cast<std::uintptr_t>(value.data());}
template<class T>void Put(std::uintptr_t at,const T& value){std::memcpy(reinterpret_cast<void*>(at),&value,sizeof(value));}
bool Current(void*)noexcept{return actor_current;}
void Reset(){
    actor.fill(0);state.fill(0);definition.fill(0);action.fill(0);fixture_descriptor.fill(0);actions={};learned={};
    actor_current=true;foreign_use=false;effect_present=false;item_present=false;item_current=true;
    inventory_mutation=0;item_unknown=false;
    effect_epoch=power_epoch=1;const auto base=reinterpret_cast<std::uintptr_t>(image);
    context={base,Address(actor),{4050960,53},1,Current,nullptr};
    Put(Address(actor)+0xad0,static_cast<std::uint32_t>(Address(state)));Put(Address(state)+0x10,std::uint32_t{5});Put(Address(state)+0x18,std::uint32_t{1});
    Put(base+0x16a2d70,100.0);Put(Address(actor)+0x67c,99.0f);
    Put(base+0x1389560,static_cast<std::uint32_t>(base+0x1141a24));Put(base+0x1389564,std::uint32_t{5});
    Put(base+0x1389568,static_cast<std::uint32_t>(base+0x12e86b4));Put(base+0x1389570,std::uint8_t{0});
    power_manager={static_cast<std::uint32_t>(Address(power_sentinel)),1};power_sentinel={0,static_cast<std::uint32_t>(Address(power_node)),0,0};
    power_node={0,static_cast<std::uint32_t>(Address(power_sentinel)),0,0,111,static_cast<std::uint32_t>(Address(definition))};
    effect_manager={static_cast<std::uint32_t>(Address(effect_sentinel)),1};effect_sentinel={0,static_cast<std::uint32_t>(Address(effect_node)),0,0};
    effect_node={0,static_cast<std::uint32_t>(Address(effect_sentinel)),0,0,222,static_cast<std::uint32_t>(Address(fixture_descriptor))};
    Put(base+0x138757c,static_cast<std::uint32_t>(Address(power_manager)));Put(base+0x1387098,static_cast<std::uint32_t>(Address(effect_manager)));
    Put(Address(definition)+0x138,std::uint32_t{111});Put(Address(definition)+0x1a8,std::uint32_t{2});Put(Address(definition)+0x1f0,std::uint32_t{3});
    const auto a=static_cast<std::uint32_t>(Address(actions));Put(Address(definition)+0x2a0,b::Header{a,a+0x50,a+0xa0});
    Put(Address(actions),static_cast<std::uint32_t>(Address(action)));Put(Address(action),static_cast<std::uint32_t>(base+0x1148b48));
    Put(Address(action)+0x1c,std::uint32_t{333});Put(Address(action)+0x88,std::uint32_t{222});
    Put(Address(fixture_descriptor),static_cast<std::uint32_t>(base+0x1147930));Put(Address(fixture_descriptor)+0x14,std::uint32_t{222});
    learned[0]={111,20,30,40};const auto l=static_cast<std::uint32_t>(Address(learned));Put(Address(actor)+0x670,b::Header{l,l+16,l+32});
}
b::Request Request(){b::Request result;result.count=1;result.actions[0]={0,0,111,{},111,b::CoverageKind::all_descriptors};return result;}
void Capture(b::Publication& result,b::Request request=Request()){
    b::State state_owner;const auto reason=b::Capture(context,request,state_owner,result);
    Check(reason==b::Unknown::none,"fixture publication complete");Check(b::Release(state_owner),"fixture refs released");
}
}
namespace wonderbane::extension::actor_effects {
Unknown Capture(const Context& c,Snapshot& out)noexcept{
    out={};if(!c.current(c.owner)){return Unknown::identity;}out.unknown=Unknown::none;out.actor_key=c.actor_key;out.scene=c.scene;out.epoch=effect_epoch;
    if(effect_present){out.count=1;out.effects[0].descriptor_id=222;out.effects[0].action_id=333;}
    return Unknown::none;
}
bool Revalidate(const Context& c,const Snapshot& s)noexcept{return c.current(c.owner)&&s.Complete()&&s.epoch==effect_epoch&&s.actor_key==c.actor_key&&s.scene==c.scene;}
}
namespace wonderbane::extension::combat::power {
std::uint64_t InitiationEpoch()noexcept{return power_epoch;}
bool NativeUseInFlight()noexcept{return foreign_use;}
}
namespace wonderbane::extension::combat::inventory {
void Mutate()noexcept{
    if(inventory_mutation==1){learned[0][3]=39;}
    if(inventory_mutation==2){Put(Address(state)+0x10,std::uint32_t{6});}
    if(inventory_mutation==3){++power_epoch;}
    if(inventory_mutation==4){fixture_descriptor[0x4c]=1;}
    if(inventory_mutation==5){Put(Address(state)+0x1c,std::uint32_t{3});}
}
Result Observe(const Context& c,State&,Observation& out)noexcept{
    Mutate();
    out={};if(item_unknown){return Result::unknown;}out.generation=1;
    if(!item_present){out.result=Result::no_eligible;return out.result;}out.count=1;out.result=Result::available;
    out.items[0]={{55,30},c.template_key,0x21000000,0x22000000,3,8,0x0a};return out.result;
}
bool Revalidate(const Context&,State&,const Observation&)noexcept{Mutate();return item_current;}
bool Release(State&)noexcept{return true;}
}
int RunActorBuffFixtureCases(){
    image=static_cast<unsigned char*>(VirtualAlloc(nullptr,0x16b0000,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));if(!image){return 1;}
    Reset();b::Publication publication;Capture(publication);Check(publication.actions[0].coverage==b::Coverage::missing && publication.actions[0].readiness==b::Readiness::ready,"known retained absent fixture_descriptor and native ready");
    Check(publication.actions[0].learned_rank==40 && publication.actions[0].descriptors[0].action_id==333,"native +C rank and distinct action identity copied");
    effect_present=true;Capture(publication);Check(publication.actions[0].coverage==b::Coverage::present,"observed fixture_descriptor presence");
    effect_present=false;fixture_descriptor[0x4c]=1;Capture(publication);Check(publication.actions[0].coverage==b::Coverage::unknown,"unretained absent fixture_descriptor never missing");
    Reset();Put(Address(actor)+0x67c,101.0f);Capture(publication);Check(publication.actions[0].readiness==b::Readiness::global_recovery,"native global recovery predicate");
    Reset();const auto sentinel=static_cast<std::uint32_t>(Address(reuse_sentinel)),node=static_cast<std::uint32_t>(Address(reuse_node));
    reuse_head={sentinel,0};reuse_sentinel={node,node};reuse_node={sentinel,sentinel,111,0};Put(Address(actor)+0x5c8,static_cast<std::uint32_t>(Address(reuse_head)));
    Capture(publication);Check(publication.actions[0].readiness==b::Readiness::power_reuse,"expired reuse node still blocks natively");
    Reset();Put(Address(state)+0x10,std::uint32_t{6});Capture(publication);Check(publication.actions[0].readiness==b::Readiness::initiation_pending,"foreign initiation preserved");
    Reset();Put(Address(state)+0x18,std::uint32_t{2});Put(Address(definition)+0x1f0,std::uint32_t{2});Capture(publication);Check(publication.actions[0].readiness==b::Readiness::stance_ineligible,"shape peace stance mismatch read-only");
    Put(Address(definition)+0x1f0,std::uint32_t{3});Capture(publication);Check(publication.actions[0].readiness==b::Readiness::ready,"either stance buff no forced toggle");
    Reset();learned[0][3]=0;Capture(publication);Check(publication.actions[0].readiness==b::Readiness::not_learned,"zero native learned rank never ready");
    Reset();b::State owner;b::Publication original;Check(b::Capture(context,Request(),owner,original)==b::Unknown::none,"owned publication captured");
    Check(b::Revalidate(context,owner,original),"same owner publication revalidates");learned[0][3]=39;Check(!b::Revalidate(context,owner,original),"changed learned rank rejects publication");learned[0][3]=40;
    b::State foreign;Check(!b::Revalidate(context,foreign,original),"other State cannot claim publication");
    Check(b::Release(owner) && !b::Revalidate(context,owner,original),"release invalidates old generation");
    b::Publication replacement;Check(b::Capture(context,Request(),owner,replacement)==b::Unknown::none && !b::Revalidate(context,owner,original),"reuse never revives old publication");b::Release(owner);
    Reset();auto item=Request();item.actions[0].power_id=0;item.actions[0].item_template={980066,0};item_present=true;
    Check(b::Capture(context,item,owner,publication)==b::Unknown::none && publication.actions[0].item_quantity==3 && publication.actions[0].readiness==b::Readiness::ready,"explicit item template/coverage association uses owned inventory");
    inv::Facts operand{};
    Check(b::ItemOperand(context,owner,publication,0,operand)
        && operand.item_address==publication.actions[0].item_hint
        && operand.template_address==publication.actions[0].template_hint,"retained item operand matches copied echo hints");
    Check(!b::ItemOperand(context,owner,publication,1,operand),"unpublished item selector refused");
    item_current=false;Check(!b::Revalidate(context,owner,publication),"native item membership loss rejects publication");b::Release(owner);
    for(auto activity:{5U,6U,7U}) {
        Reset();item_present=true;std::array<std::uint32_t,2> retained{429021400,429021400};
        const auto begin=static_cast<std::uint32_t>(Address(retained));
        Put(Address(actor)+0x65c,b::Header{begin,begin+8,begin+8});Put(Address(state)+0x10,activity);
        Check(b::Capture(context,item,owner,publication)==b::Unknown::none,"retained IDs remain coherently observable");
        Check(!publication.initiation_clear && (publication.actions[0].readiness==b::Readiness::ready)==(activity==5),
            "stationary item readiness is independent of old protocol IDs; active/moving remain deferred");
        Put(Address(state)+0x10,activity==5?6U:5U);
        Check(!b::Revalidate(context,owner,publication),"activity change invalidates stationary item fact");b::Release(owner);
    }
    for(auto activity:{5U,6U,7U}){for(unsigned count:{0U,1U,3U}){
        Reset();std::array<std::uint32_t,3> retained{111,111,429021400};
        const auto begin=static_cast<std::uint32_t>(Address(retained));
        Put(Address(actor)+0x65c,b::Header{begin,begin+count*4,begin+12});Put(Address(state)+0x10,activity);
        Capture(publication);
        Check((publication.actions[0].readiness==b::Readiness::ready)==(activity==5),
            "self power stationary5 permits retained same/other IDs without admitting manual initiation or movement");
        Check(publication.initiation_clear==(activity!=6&&count==0)&&publication.item_stationary==(activity==5),
            "stationary fact never rewrites clear protocol bookkeeping");
        if(activity==5){
            Put(Address(state)+0x1c,std::uint32_t{3});Capture(publication);
            Check(publication.actions[0].readiness==b::Readiness::initiation_pending,"qualified auxiliary3 veto remains per-definition");
            Put(Address(definition)+0x275,std::uint8_t{1});Capture(publication);
            Check(publication.actions[0].readiness==b::Readiness::ready,"native auxiliary flag permits the state without clearing IDs");
            Put(Address(definition)+0x274,std::uint8_t{1});Capture(publication);
            Check(publication.actions[0].readiness==b::Readiness::ready,"special non-casting-state path has the same stationary readiness contract");
        }
    }}
    for(unsigned mutation:std::array<unsigned,3>{2,3,4}){
        Reset();item_present=true;inventory_mutation=mutation;
        Check(b::Capture(context,item,owner,publication)==b::Unknown::changed&&!publication.Complete(),"inventory callback mutation invalidates complete publication");b::Release(owner);
    }
    Reset();auto power_and_item=Request();power_and_item.count=2;power_and_item.actions[1]=item.actions[0];power_and_item.actions[1].action_index=1;
    item_present=true;inventory_mutation=5;
    Check(b::Capture(context,power_and_item,owner,publication)==b::Unknown::changed,
        "auxiliary mutation during inventory callback cannot publish stale ready power");b::Release(owner);
    Reset();item_present=true;auto combined=item;combined.count=2;combined.actions[1]=Request().actions[0];combined.actions[1].action_index=1;
    inventory_mutation=1;Check(b::Capture(context,combined,owner,publication)==b::Unknown::changed,"native inventory callback cannot publish stale learned rank");b::Release(owner);
    Reset();item_present=true;Check(b::Capture(context,item,owner,publication)==b::Unknown::none,"item publication for revalidation callback test");
    inventory_mutation=3;Check(!b::ItemOperand(context,owner,publication,0,operand),"item operand rejects protocol mutation during native revalidation");b::Release(owner);
    Reset();Capture(publication,item);Check(publication.actions[0].readiness==b::Readiness::item_unavailable,"no candidate is unavailable not invented inventory absence");
    Reset();item_unknown=true;auto mixed=Request();mixed.count=2;
    mixed.actions[1]={1,1,0,{980066,0},111,b::CoverageKind::all_descriptors};
    Check(b::Capture(context,mixed,owner,publication)==b::Unknown::none
        &&publication.actions[0].readiness==b::Readiness::ready
        &&publication.actions[1].readiness==b::Readiness::unknown
        &&publication.actions[1].coverage==b::Coverage::missing
        &&!publication.actions[1].item_hint,"unknown inventory preserves independent ready power and effect coverage");
    Check(b::Revalidate(context,owner,publication),"unknown resource does not globally block unrelated ready power");
    inv::Facts absent;Check(!b::ItemOperand(context,owner,publication,1,absent),"unknown resource never supplies item operand");b::Release(owner);
    Reset();Check(b::Capture(context,item,owner,publication)==b::Unknown::none,"complete noeligible publication");
    item_current=false;Check(!b::Revalidate(context,owner,publication),"noeligible must revalidate, not bypass empty state");b::Release(owner);
    Reset();auto transform=Request();transform.actions[0].coverage_kind=b::CoverageKind::transform_marker;
    Put(Address(action),static_cast<std::uint32_t>(context.image+0x114853c));Capture(publication,transform);Check(publication.actions[0].descriptors[0].action_class==e::ActionClass::transform,"transform coverage uses actual marker action");
    Reset();auto invalid=Request();invalid.count=2;invalid.actions[1]=invalid.actions[0];Check(b::Capture(context,invalid,owner,publication)==b::Unknown::request,"duplicate action index rejected");
    auto unknown=[&](const char* label){b::State local;b::Publication result;Check(b::Capture(context,Request(),local,result)!=b::Unknown::none&&!result.Complete(),label);b::Release(local);};
    Reset();learned[1]=learned[0];auto l=static_cast<std::uint32_t>(Address(learned));Put(Address(actor)+0x670,b::Header{l,l+32,l+32});unknown("duplicate native learned ID rejects");
    Reset();effect_node[5]=4;unknown("missing fixture_descriptor definition cannot prove absence");
    Reset();Put(Address(action),std::uint32_t{0});unknown("unknown action mapping rejects");
    Reset();power_node[4]=112;power_node[2]=static_cast<std::uint32_t>(Address(power_node));unknown("cyclic definition tree rejected");
    Reset();foreign_use=true;unknown("prepublication foreign Use blocks capture");
    Reset();actor_current=false;unknown("actor owner revocation prevents complete publication");
    std::printf("checks=%u failures=%u\n",checks,failures);return failures?1:0;
}
#ifndef ACTOR_BUFF_OBSERVATION_PROBE
int main(){return RunActorBuffFixtureCases();}
#endif
