#include "actor_buff_observation.h"
#include "combat_initiation.h"
#include "combat_power_observer.h"
#include "combat_power_readiness.h"
#include <Windows.h>
#include <algorithm>
#include <cstring>

namespace wonderbane::extension::actor_buffs {
struct Access {
    static bool Begin(State& state)noexcept{
        if(state.occupied_ || state.quarantined_ || state.generation_==UINT64_MAX){return false;}
        ++state.generation_;state.occupied_=true;return true;
    }
    static std::uint64_t Generation(const State& state)noexcept{return state.occupied_&&!state.quarantined_?state.generation_:0;}
    static bool Drop(State& state)noexcept{
        if(state.quarantined_){return false;}bool ok=true;
        for(auto& inventory:state.inventory_){if(!combat::inventory::Release(inventory)){ok=false;}}
        if(!ok || state.generation_==UINT64_MAX){state.quarantined_=true;return false;}
        ++state.generation_;state.occupied_=false;state.observations_={};return true;
    }
    static bool Item(const State& state,std::uint32_t index,combat::inventory::Facts& out)noexcept{
        if(!state.occupied_ || state.quarantined_ || index>=kMaxActions || !state.observations_[index].count){return false;}
        out=state.observations_[index].items[0];return true;
    }
    static Unknown Items(const actor_effects::Context& c,const Request& request,State& state,Publication& out,bool revalidate)noexcept{
        for(std::uint32_t i=0;i<request.count;++i){
            const auto& intent=request.actions[i];if(intent.power_id){continue;}
            const combat::inventory::Context context{c.image,c.actor,c.actor_key,intent.item_template,c.current,c.owner};
            auto& inventory=state.inventory_[i];auto& observation=state.observations_[i];
            auto& facts=out.actions[i];
            using Result=combat::inventory::Result;
            if(revalidate){
                if(observation.result!=Result::unknown
                    && !combat::inventory::Revalidate(context,inventory,observation)){return Unknown::inventory;}
            }else{
                combat::inventory::Observe(context,inventory,observation);
                if(observation.result==Result::unknown
                    && (inventory.Quarantined() || !combat::inventory::Release(inventory))){
                    state.quarantined_=true;return Unknown::inventory;
                }
            }
            if(observation.result==Result::unknown){facts.readiness=Readiness::unknown;continue;}
            if(observation.result==Result::no_eligible){
                if(observation.count){return Unknown::inventory;}
                facts.readiness=Readiness::item_unavailable;continue;
            }
            if(!observation.count){return Unknown::inventory;}
            if(observation.count>combat::inventory::kMaxItems){return Unknown::inventory;}
            const auto& item=observation.items[0];
            if(item.template_key!=intent.item_template || !item.quantity || item.type!=8 || item.flags!=0x0a){return Unknown::inventory;}
            facts.item_key=item.item_key;facts.item_template=item.template_key;facts.item_quantity=item.quantity;
            facts.item_type=item.type;facts.item_flags=item.flags;
            facts.item_hint=static_cast<std::uint32_t>(item.item_address);facts.template_hint=static_cast<std::uint32_t>(item.template_address);
            facts.readiness=out.initiation_clear?Readiness::ready:Readiness::initiation_pending;
        }
        return Unknown::none;
    }
};
namespace {
struct Budget { std::uint32_t reads{}; std::size_t bytes{}; ULONGLONG start=GetTickCount64(); bool exhausted{}; };
thread_local Budget* budget{};
bool Copy(void* out,std::uintptr_t at,std::size_t size) noexcept {
    if(at<0x10000 || size>65536 || at>0x7fff0000-size){return false;}
    if(budget && (++budget->reads>32768 || (budget->bytes+=size)>2*1024*1024 || GetTickCount64()-budget->start>100)){
        budget->exhausted=true;return false;
    }
    __try{std::memcpy(out,reinterpret_cast<const void*>(at),size);return true;}
    __except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
template<class T>bool Read(std::uintptr_t at,T& value)noexcept{return Copy(&value,at,sizeof(value));}
std::uint32_t Word(const auto& bytes,std::size_t offset)noexcept{
    std::uint32_t value{};std::memcpy(&value,bytes.data()+offset,4);return value;
}
struct Header{std::uint32_t begin{},end{},capacity{};bool operator==(const Header&)const=default;};
bool Geometry(const Header& h,std::size_t stride,std::size_t maximum)noexcept{
    return (!h.begin && !h.end && !h.capacity) || (h.begin>=0x10000 && !(h.begin&3)
        && h.begin<=h.end && h.end<=h.capacity && h.capacity<=0x7fff0000
        && (h.end-h.begin)%stride==0 && (h.capacity-h.begin)%stride==0
        && (h.capacity-h.begin)/stride<=maximum);
}
struct MapPath {
    std::uint32_t manager{},sentinel{},root{},count{},matched{},used{};
    std::array<std::uint32_t,64> addresses{};
    std::array<std::array<std::uint32_t,6>,64> nodes{};
};
Unknown Lookup(std::uintptr_t image,std::uint32_t manager_rva,std::uint32_t id,bool counted,MapPath& path)noexcept{
    if(!id || !Read(image+manager_rva,path.manager) || !path.manager
        || !Read(path.manager,path.sentinel) || !path.sentinel
        || !Read(path.sentinel+4,path.root)){return Unknown::read_fault;}
    if(counted && (!Read(path.manager+4,path.count) || !path.count || path.count>4096)){return Unknown::geometry;}
    auto node=path.root;std::uint64_t low=0,high=UINT32_MAX;
    while(node && node!=path.sentinel){
        if(path.used==path.nodes.size() || (node&3)){return Unknown::geometry;}
        for(std::uint32_t i=0;i<path.used;++i){if(path.addresses[i]==node){return Unknown::geometry;}}
        auto& raw=path.nodes[path.used];if(!Read(node,raw)){return Unknown::read_fault;}
        path.addresses[path.used++]=node;const auto key=raw[4];
        if(!key || key<=low || key>high){return Unknown::geometry;}
        if(key==id){path.matched=raw[5];return path.matched?Unknown::none:Unknown::geometry;}
        if(id<key){high=static_cast<std::uint64_t>(key)-1;node=raw[2];}
        else{low=key;node=raw[3];}
    }
    return Unknown::unsupported;
}
bool MapCurrent(std::uintptr_t image,std::uint32_t rva,bool counted,const MapPath& path)noexcept{
    std::uint32_t manager{},sentinel{},root{},count{};
    if(!Read(image+rva,manager) || manager!=path.manager || !Read(manager,sentinel) || sentinel!=path.sentinel
        || !Read(sentinel+4,root) || root!=path.root
        || (counted && (!Read(manager+4,count) || count!=path.count))){return false;}
    for(std::uint32_t i=0;i<path.used;++i){std::array<std::uint32_t,6> raw{};
        if(!Read(path.addresses[i],raw) || raw!=path.nodes[i]){return false;}}
    return true;
}
Unknown Learned(std::uintptr_t actor,std::uint32_t id,std::uint32_t& rank)noexcept{
    Header h{},last{};using Entry=std::array<std::uint32_t,4>;std::array<Entry,256> entries{},again{};
    if(!Read(actor+0x670,h)){return Unknown::read_fault;}if(!Geometry(h,16,entries.size())){return Unknown::geometry;}
    const auto count=(h.end-h.begin)/16;
    if(count && !Copy(entries.data(),h.begin,count*16)){return Unknown::read_fault;}
    std::uint32_t prior{};
    for(std::uint32_t i=0;i<count;++i){const auto& entry=entries[i];
        // Native9B400 uses ordered lower_bound and returns the +C rank word.
        if(!entry[0] || entry[0]<=prior || entry[3]>INT32_MAX){return Unknown::geometry;}
        prior=entry[0];if(entry[0]==id){rank=std::min(entry[3],std::uint32_t{9999});}
    }
    if(!Read(actor+0x670,last) || last!=h || (count && !Copy(again.data(),h.begin,count*16)) || again!=entries){return Unknown::changed;}
    return Unknown::none;
}
bool Classify(std::uintptr_t image,std::uint32_t table,actor_effects::ActionClass& kind)noexcept{
    constexpr std::array<std::uint32_t,7> tables{0x1148b48,0x1148b84,0x114853c,0x1148bc0,0x1148c38,0x1148cb0,0x114dfa0};
    for(std::size_t i=0;i<tables.size();++i){if(table==image+tables[i]){kind=static_cast<actor_effects::ActionClass>(i);return true;}}
    return false;
}
Unknown AddDescriptor(std::uintptr_t image,std::uint32_t id,std::uint32_t action_id,
    actor_effects::ActionClass kind,const actor_effects::Snapshot& effects,ActionFacts& out)noexcept{
    if(!id || !action_id){return Unknown::geometry;}
    for(std::uint32_t i=0;i<out.descriptor_count;++i){
        if(out.descriptors[i].id==id){return out.descriptors[i].action_id==action_id && out.descriptors[i].action_class==kind?Unknown::none:Unknown::unsupported;}
    }
    if(out.descriptor_count==kMaxDescriptors){return Unknown::geometry;}
    MapPath path{};auto reason=Lookup(image,0x1387098,id,false,path);if(reason!=Unknown::none){return reason;}
    std::array<std::uint8_t,0x50> definition{},again{};
    if(!Read(path.matched,definition)){return Unknown::read_fault;}
    if(Word(definition,0)!=image+0x1147930 || Word(definition,0x14)!=id){return Unknown::unsupported;}
    if(!Read(path.matched,again) || again!=definition || !MapCurrent(image,0x1387098,false,path)){return Unknown::changed;}
    auto& descriptor=out.descriptors[out.descriptor_count++];descriptor.id=id;descriptor.action_id=action_id;
    descriptor.action_class=kind;descriptor.local_add_suppression=definition[0x4c];
    for(std::uint32_t i=0;i<effects.count;++i){if(effects.effects[i].descriptor_id==id){descriptor.present=true;}}
    return Unknown::none;
}
Unknown Selectors(std::uintptr_t image,std::uintptr_t definition,const Intent& intent,
    const actor_effects::Snapshot& effects,ActionFacts& out)noexcept{
    Header h{},last{};using Entry=std::array<std::uint8_t,0x50>;std::array<Entry,64> entries{},again{};
    if(!Read(definition+0x2a0,h)){return Unknown::read_fault;}if(!Geometry(h,sizeof(Entry),entries.size())){return Unknown::geometry;}
    const auto count=(h.end-h.begin)/sizeof(Entry);if(!count){return Unknown::unsupported;}
    if(!Copy(entries.data(),h.begin,count*sizeof(Entry))){return Unknown::read_fault;}
    for(std::size_t i=0;i<count;++i){
        const auto action_address=Word(entries[i],0);std::array<std::uint8_t,0x94> action{},action_again{};
        if(!Copy(action.data(),action_address,0x20)){return Unknown::read_fault;}
        actor_effects::ActionClass kind{};if(!Classify(image,Word(action,0),kind)){return Unknown::unsupported;}
        const std::size_t action_size=kind==actor_effects::ActionClass::apply_many?0x94U:0x8cU;
        if(!Copy(action.data(),action_address,action_size)){return Unknown::read_fault;}
        const bool include=intent.coverage_kind==CoverageKind::all_descriptors || kind==actor_effects::ActionClass::transform;
        if(include){
            if(kind==actor_effects::ActionClass::apply_many){
                Header ids{Word(action,0x88),Word(action,0x8c),Word(action,0x90)};
                if(!Geometry(ids,4,kMaxDescriptors)){return Unknown::geometry;}
                const auto size=(ids.end-ids.begin)/4;std::array<std::uint32_t,kMaxDescriptors> values{},after{};
                if(!size || !Copy(values.data(),ids.begin,size*4)){return Unknown::read_fault;}
                for(std::uint32_t j=0;j<size;++j){auto reason=AddDescriptor(image,values[j],Word(action,0x1c),kind,effects,out);if(reason!=Unknown::none){return reason;}}
                if(!Copy(after.data(),ids.begin,size*4) || values!=after){return Unknown::changed;}
            }else{
                auto reason=AddDescriptor(image,Word(action,0x88),Word(action,0x1c),kind,effects,out);if(reason!=Unknown::none){return reason;}
            }
        }
        if(!Copy(action_again.data(),action_address,action_size) || action!=action_again){return Unknown::changed;}
    }
    if(!Read(definition+0x2a0,last) || last!=h || !Copy(again.data(),h.begin,count*sizeof(Entry)) || entries!=again){return Unknown::changed;}
    if(!out.descriptor_count){return Unknown::unsupported;}
    unsigned present{};bool all_retained=true;
    for(std::uint32_t i=0;i<out.descriptor_count;++i){present+=out.descriptors[i].present?1U:0U;all_retained&=out.descriptors[i].local_add_suppression==0;}
    out.coverage=present==out.descriptor_count?Coverage::present:present?Coverage::partial:all_retained?Coverage::missing:Coverage::unknown;
    return Unknown::none;
}
Unknown ResolvePower(const actor_effects::Context& c,const Intent& intent,
    const actor_effects::Snapshot& effects,std::uint32_t actor_mode,bool initiation_clear,
    const combat::power::readiness::Snapshot& readiness,ActionFacts& out)noexcept{
    out.intent=intent;MapPath path{};auto reason=Lookup(c.image,0x138757c,intent.coverage_power_id,true,path);
    if(reason!=Unknown::none){return reason;}
    std::array<std::uint8_t,0x28c> definition{},again{};
    if(!Read(path.matched,definition)){return Unknown::read_fault;}
    if(Word(definition,0x138)!=intent.coverage_power_id){return Unknown::unsupported;}
    out.category=Word(definition,0x204);out.target_mode=Word(definition,0x1a8);
    out.delivery=Word(definition,0x1b4);out.required_mode=Word(definition,0x1f0);
    reason=Selectors(c.image,path.matched,intent,effects,out);if(reason!=Unknown::none){return reason;}
    if(intent.power_id){
        reason=Learned(c.actor,intent.power_id,out.learned_rank);if(reason!=Unknown::none){return reason;}
        if(!out.learned_rank){out.readiness=Readiness::not_learned;}
        else if(out.category>1 || out.target_mode!=2 || out.delivery!=0 || out.required_mode<1 || out.required_mode>3){out.readiness=Readiness::unsupported;}
        else if(!initiation_clear){out.readiness=Readiness::initiation_pending;}
        else if(out.required_mode==2 && static_cast<std::int32_t>(actor_mode)>1){out.readiness=Readiness::stance_ineligible;}
        else {
            out.readiness=readiness.now<readiness.recovery?Readiness::global_recovery:Readiness::ready;
            if(out.readiness==Readiness::ready && !readiness.bypass){
                for(std::size_t i=0;i<readiness.count;++i){if(readiness.nodes[i].id==intent.power_id){out.readiness=Readiness::power_reuse;}}
            }
        }
    }
    if(!Read(path.matched,again) || definition!=again || !MapCurrent(c.image,0x138757c,true,path)){return Unknown::changed;}
    return Unknown::none;
}
bool Valid(const Request& request)noexcept{
    if(!request.count || request.count>kMaxActions){return false;}
    for(std::uint32_t i=0;i<request.count;++i){const auto& action=request.actions[i];
        if(action.action_index>=kMaxActions || action.group_index>=kMaxActions || !action.coverage_power_id
            || (action.coverage_kind!=CoverageKind::all_descriptors && action.coverage_kind!=CoverageKind::transform_marker)
            || (action.power_id? action.item_template!=Key{} || action.coverage_power_id!=action.power_id
                : !action.item_template[0] || action.item_template[1]!=0 || action.coverage_kind!=CoverageKind::all_descriptors)){return false;}
        for(std::uint32_t j=0;j<i;++j){if(request.actions[j].action_index==action.action_index){return false;}}
    }
    return true;
}
Unknown CapturePowers(const actor_effects::Context& c,const Request& request,
    const actor_effects::Snapshot& effects,Publication& out)noexcept{
    std::uint32_t state{},mode{},state_after{},mode_after{};combat::initiation::Snapshot initiation{},after{};
    if(!Read(c.actor+0xad0,state) || !state || !Read(state+0x18,mode) || mode<1 || mode>3
        || !combat::initiation::Capture(c.actor,state,initiation,[](std::uintptr_t at,auto& value)noexcept{return Read(at,value);})){return Unknown::read_fault;}
    const auto power_epoch=combat::power::InitiationEpoch();
    if(!power_epoch || combat::power::NativeUseInFlight()){return Unknown::changed;}
    combat::power::readiness::Snapshot readiness{},readiness_after{};
    const auto read=[](std::uintptr_t at,auto& value)noexcept{return Read(at,value);};
    if(!combat::power::readiness::Capture(c.image,c.actor,read,readiness)){return Unknown::read_fault;}
    out.actor_mode=mode;out.initiation_clear=initiation.Clear();
    std::size_t total_descriptors{};
    for(std::uint32_t i=0;i<request.count;++i){
        auto reason=ResolvePower(c,request.actions[i],effects,mode,out.initiation_clear,readiness,out.actions[i]);if(reason!=Unknown::none){return reason;}
        total_descriptors+=out.actions[i].descriptor_count;
        if(total_descriptors>kMaxPublicationDescriptors){return Unknown::geometry;}
    }
    if(!Read(c.actor+0xad0,state_after) || state_after!=state || !Read(state+0x18,mode_after) || mode_after!=mode
        || !combat::initiation::Capture(c.actor,state,after,[](std::uintptr_t at,auto& value)noexcept{return Read(at,value);})
        || after!=initiation || !combat::power::readiness::Capture(c.image,c.actor,read,readiness_after)
        || !combat::power::readiness::Stable(readiness,readiness_after)
        || combat::power::InitiationEpoch()!=power_epoch || combat::power::NativeUseInFlight()){return Unknown::changed;}
    out.count=request.count;return Unknown::none;
}
bool PowerFactsCurrent(const actor_effects::Context& c,const Request& request,
    const actor_effects::Snapshot& effects,const Publication& first)noexcept{
    Publication last{};
    if(CapturePowers(c,request,effects,last)!=Unknown::none || last.count!=first.count
        || last.actor_mode!=first.actor_mode || last.initiation_clear!=first.initiation_clear){return false;}
    for(std::uint32_t i=0;i<first.count;++i){
        auto before=first.actions[i];
        // Item ownership is independently revalidated. Compare all power and
        // descriptor facts again after the native inventory getter callbacks.
        if(!before.intent.power_id){
            before.item_key={};before.item_template={};before.item_quantity=0;
            before.item_type=0;before.item_flags=0;before.item_hint=0;before.template_hint=0;
            before.readiness=Readiness::unknown;
        }
        if(before!=last.actions[i]){return false;}
    }
    return true;
}
}
Unknown Capture(const actor_effects::Context& c,const Request& request,State& state,Publication& out)noexcept{
    const DWORD error=GetLastError();Budget work;auto* previous=budget;budget=&work;
    const auto epoch=combat::power::InitiationEpoch();
    out={};Unknown reason=Valid(request)?Unknown::none:Unknown::request;
    if(reason==Unknown::none && !Access::Begin(state)){reason=Unknown::inventory;}
    if(reason==Unknown::none && actor_effects::Capture(c,out.effects_)!=actor_effects::Unknown::none){reason=Unknown::effects;}
    if(reason==Unknown::none){reason=CapturePowers(c,request,out.effects_,out);}
    if(reason==Unknown::none){reason=Access::Items(c,request,state,out,false);}
    if(reason==Unknown::none && (!PowerFactsCurrent(c,request,out.effects_,out)
        || !epoch || epoch!=combat::power::InitiationEpoch())){reason=Unknown::changed;}
    if(reason==Unknown::none && !actor_effects::Revalidate(c,out.effects_)){reason=Unknown::changed;}
    if(reason==Unknown::none && (work.exhausted || GetTickCount64()-work.start>100)){reason=Unknown::changed;}
    if(reason!=Unknown::none){out={};}else{
        out.actor_key=c.actor_key;out.scene=c.scene;out.effect_epoch=out.effects_.epoch;out.request_=request;
        out.state_=&state;out.state_generation_=Access::Generation(state);
    }
    out.unknown=reason;budget=previous;SetLastError(error);return reason;
}
bool Revalidate(const actor_effects::Context& c,State& state,const Publication& publication)noexcept{
    const DWORD error=GetLastError();Publication fresh{};Budget work;auto* previous=budget;budget=&work;
    const auto epoch=combat::power::InitiationEpoch();
    const bool ok=publication.Complete() && publication.state_==&state
        && publication.state_generation_==Access::Generation(state) && actor_effects::Revalidate(c,publication.effects_)
        && CapturePowers(c,publication.request_,publication.effects_,fresh)==Unknown::none
        && Access::Items(c,publication.request_,state,fresh,true)==Unknown::none && fresh.count==publication.count
        && fresh.actor_mode==publication.actor_mode && fresh.initiation_clear==publication.initiation_clear && fresh.actions==publication.actions
        && PowerFactsCurrent(c,publication.request_,publication.effects_,fresh)
        && epoch && epoch==combat::power::InitiationEpoch() && actor_effects::Revalidate(c,publication.effects_)
        && !work.exhausted && GetTickCount64()-work.start<=100;
    budget=previous;SetLastError(error);return ok;
}
bool Release(State& state)noexcept{const DWORD error=GetLastError();const bool ok=Access::Drop(state);SetLastError(error);return ok;}
bool ItemOperand(const actor_effects::Context& c,State& state,const Publication& publication,
    std::uint32_t action_index,combat::inventory::Facts& out)noexcept{
    out={};if(!Revalidate(c,state,publication)){return false;}
    for(std::uint32_t i=0;i<publication.count;++i){
        if(publication.actions[i].intent.action_index==action_index && !publication.actions[i].intent.power_id){return Access::Item(state,i,out);}
    }return false;
}
}
