#include "actor_publication.h"
#include <sddl.h>
#include <vector>
#include <cstring>
#include <limits>

namespace wonderbane::extension::actor::publication {
namespace {
bool Zero(const auto& value)noexcept{const auto* bytes=reinterpret_cast<const unsigned char*>(&value);
    for(std::size_t i=0;i<sizeof(value);++i){if(bytes[i]){return false;}}return true;}
bool Facts(const Frame& f)noexcept{
    if((f.admission_blocks&~admission::known) || f.unknown>10 || f.complete>1 || f.initiation_clear>1 || f.effect_count>256
        || f.readiness_count>32 || f.application_count>32 || f.descriptor_count>256
        || !Zero(f.reserved) || !Zero(f.padding)){return false;}
    if(!f.complete){return f.unknown && !f.effect_epoch && !f.effect_count && !f.readiness_count
        && !f.application_count && !f.descriptor_count && !f.actor_mode && !f.initiation_clear && !f.admission_blocks
        && Zero(f.effects) && Zero(f.readiness) && Zero(f.applications) && Zero(f.descriptors);}
    if(f.unknown || !f.effect_epoch || !f.readiness_count || f.actor_mode<1 || f.actor_mode>3){return false;}
    for(std::size_t i=0;i<f.effects.size();++i){const auto& e=f.effects[i];
        if(i>=f.effect_count){if(!Zero(e)){return false;}continue;}
        if(!e.descriptor || !e.action || e.native_class>2 || e.source_tag>1 || e.action_class>6 || e.suppression>255){return false;}
    }
    std::uint32_t offset{};
    for(std::size_t i=0;i<f.readiness.size();++i){const auto& r=f.readiness[i];
        if(i>=f.readiness_count){if(!Zero(r)){return false;}continue;}
        if(!selectors::Valid(r.selector) || r.selector.index!=i || r.rank>9999 || r.coverage>3 || r.readiness>8
            || r.descriptor_offset!=offset || !r.descriptor_count || r.descriptor_count>64
            || r.descriptor_count>f.descriptor_count-offset || !Zero(r.reserved)){return false;}
        offset+=r.descriptor_count;
        std::uint32_t present{};bool retained=true;
        for(std::uint32_t j=r.descriptor_offset;j<offset;++j){present+=f.descriptors[j].present;retained&=!f.descriptors[j].suppression;}
        const auto coverage=present==r.descriptor_count?3U:present?2U:retained?1U:0U;
        if(r.coverage!=coverage || (r.selector.kind==3&&r.readiness==1&&!f.initiation_clear)){return false;}
        if(r.selector.kind==3){
            if(!Zero(r.item_key)||!Zero(r.template_key)||r.item_hint||r.template_hint||r.quantity||r.type||r.flags){return false;}
            if(r.readiness==1&&(!r.rank||r.category>1||r.target_mode!=2||r.delivery||r.required_mode<1||r.required_mode>3
                ||(r.required_mode==2&&f.actor_mode>1))){return false;}
        }else if(r.item_hint || r.template_hint || r.quantity){
            if(r.readiness==0){return false;}
            if(!r.item_key[0]||!r.item_key[1]||r.template_key[0]!=r.selector.template_id||r.template_key[1]
                ||!fence::Address(r.item_hint)||!fence::Address(r.template_hint)||r.item_hint==r.template_hint
                ||!r.quantity||r.type!=8||r.flags!=0x0a){return false;}
        }else if(!Zero(r.item_key)||!Zero(r.template_key)||r.type||r.flags||(r.readiness!=8&&r.readiness!=0)){return false;}
    }
    if(offset!=f.descriptor_count){return false;}
    for(std::size_t i=0;i<f.descriptors.size();++i){const auto& d=f.descriptors[i];
        if(i>=f.descriptor_count){if(!Zero(d)){return false;}continue;}
        if(!d.id||!d.action||d.action_class>6||d.present>1||!Zero(d.reserved)){return false;}
        bool observed=false;for(std::uint32_t j=0;j<f.effect_count;++j){observed|=f.effects[j].descriptor==d.id;}
        if(observed!=static_cast<bool>(d.present)){return false;}
    }
    for(std::size_t i=0;i<f.applications.size();++i){const auto& a=f.applications[i];
        if(i>=f.application_count){if(!Zero(a)){return false;}continue;}
        if(!fence::Any(a.intent)||!fence::Any(a.command)||!a.submitted_revision||a.entry>2||a.state>3
            ||a.local_settled>1||a.queued>1||!Zero(a.reserved)||(a.queued&&a.entry!=1)
            ||(a.state==1&&!a.entry)||((a.state==2||a.state==3)&&(!a.entry||a.observed_revision<=a.submitted_revision))
            ||(a.state==3&&(!a.queued||a.entry!=1))
            ||(a.state<2&&a.observed_revision)){return false;}
        for(std::size_t j=0;j<i;++j){if(f.applications[j].command==a.command){return false;}}
    }
    return true;
}
bool SameEligibility(const Frame& a,const Frame& b)noexcept{
    return a.complete==b.complete && a.unknown==b.unknown && a.actor_mode==b.actor_mode
        && a.initiation_clear==b.initiation_clear && a.admission_blocks==b.admission_blocks
        && a.readiness_count==b.readiness_count
        && !std::memcmp(a.readiness.data(),b.readiness.data(),sizeof(a.readiness));
}
bool Same(const Frame& a,const Frame& b)noexcept{
    constexpr auto offset=offsetof(Frame,effect_epoch);
    return !std::memcmp(reinterpret_cast<const char*>(&a)+offset,reinterpret_cast<const char*>(&b)+offset,sizeof(Frame)-offset);
}
bool Security(PSECURITY_DESCRIPTOR& result){
    HANDLE token{};if(!OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token)){return false;}
    DWORD size{};GetTokenInformation(token,TokenUser,nullptr,0,&size);
    std::vector<std::uint8_t> bytes(size);const bool obtained=size&&GetTokenInformation(token,TokenUser,bytes.data(),size,&size);
    CloseHandle(token);if(!obtained){return false;}
    LPWSTR sid{};if(!ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER*>(bytes.data())->User.Sid,&sid)){return false;}
    // The creator retains its writable handle; other opens by the current user
    // receive read permission only. No inherited/everyone/remote access ACE.
    const std::wstring sddl=L"D:P(A;;GR;;;"+std::wstring(sid)+L")";LocalFree(sid);
    return ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl.c_str(),SDDL_REVISION_1,&result,nullptr)!=FALSE;
}
}
bool Valid(const Header& h)noexcept{
    return !std::memcmp(h.magic,"WBAPUB2",8)&&h.version==2&&h.bytes==mapping_size&&h.client_pid
        &&h.slot_bytes==slot_size&&h.slots==2&&!h.reserved&&h.client_creation&&fence::Any(h.actor_lifetime)
        &&fence::Any(h.manifest)&&h.actor_key[0]&&h.actor_key[1]==53&&fence::Address(h.actor_address)
        &&!h.reserved2&&h.scene&&h.active>=-1&&h.active<=1&&Zero(h.padding);
}
bool Valid(const Frame& f)noexcept{
    return f.sequence>0&&!(f.sequence&1)&&f.revision&&f.admission_revision&&fence::Any(f.snapshot)&&f.sampled_tick&&Facts(f);
}
std::wstring Name(std::uint32_t pid,std::uint64_t creation,const Digest& manifest){
    if(!pid||!creation||!fence::Any(manifest)){return {};}
    std::wstring result=L"Local\\WonderBane.ActorPublication.v2."+std::to_wstring(pid)+L"."+std::to_wstring(creation)+L".";
    constexpr wchar_t hex[]=L"0123456789abcdef";for(auto b:manifest){result+=hex[b>>4];result+=hex[b&15];}return result;
}
bool Encode(const selectors::Manifest& manifest,const actor_buffs::Publication& p,
    const actor_actions::ApplicationJournal& journal,Frame& out)noexcept{
    out={};if(!selectors::Valid(manifest)||!p.Complete()||journal.Faulted()||p.count!=manifest.count){return false;}
    out.unknown=0;out.complete=1;out.effect_epoch=p.effect_epoch;out.actor_mode=p.actor_mode;out.initiation_clear=p.initiation_clear;out.admission_blocks=p.admission_blocks;
    const auto effects=p.Effects();if(effects.size()>out.effects.size()){return false;}out.effect_count=static_cast<std::uint32_t>(effects.size());
    for(std::size_t i=0;i<effects.size();++i){const auto& e=effects[i];auto& dest=out.effects[i];
        dest={e.descriptor_id,e.action_id,e.rank,e.native_class,e.source_tag,{e.source_words[0],e.source_words[1],e.source_words[2]},
            static_cast<std::uint32_t>(e.action_class),e.local_add_suppression};
    }
    out.readiness_count=p.count;
    for(std::uint32_t i=0;i<p.count;++i){const auto& facts=p.actions[i];const auto& intent=facts.intent;auto& dest=out.readiness[i];
        const selectors::Record expected{intent.action_index,intent.group_index,intent.power_id?3U:4U,intent.power_id,
            intent.item_template[0],intent.item_template[1],intent.coverage_power_id,static_cast<std::uint32_t>(intent.coverage_kind)};
        if(std::memcmp(&expected,&manifest.records[i],sizeof(expected))||facts.descriptor_count>out.descriptors.size()-out.descriptor_count){return false;}
        dest.selector=expected;dest.rank=facts.learned_rank;dest.category=facts.category;dest.target_mode=facts.target_mode;
        dest.delivery=facts.delivery;dest.required_mode=facts.required_mode;dest.coverage=static_cast<std::uint32_t>(facts.coverage);
        dest.readiness=static_cast<std::uint32_t>(facts.readiness);dest.descriptor_offset=out.descriptor_count;dest.descriptor_count=facts.descriptor_count;
        for(std::uint32_t j=0;j<facts.descriptor_count;++j){const auto& d=facts.descriptors[j];
            out.descriptors[out.descriptor_count++]={d.id,d.action_id,static_cast<std::uint32_t>(d.action_class),d.local_add_suppression,static_cast<std::uint8_t>(d.present),{}};}
        dest.item_key[0]=facts.item_key[0];dest.item_key[1]=facts.item_key[1];dest.template_key[0]=facts.item_template[0];dest.template_key[1]=facts.item_template[1];
        dest.item_hint=facts.item_hint;dest.template_hint=facts.template_hint;dest.quantity=facts.item_quantity;dest.type=facts.item_type;dest.flags=facts.item_flags;
    }
    for(const auto& a:journal.Records()){if(a.reserved){auto& dest=out.applications[out.application_count++];
        dest={a.intent,a.command,a.submitted_revision,a.observed_revision,static_cast<std::uint32_t>(a.entry),
            static_cast<std::uint32_t>(a.state),static_cast<std::uint32_t>(a.local_settled),static_cast<std::uint32_t>(a.queued),{}};}}
    if(!Facts(out)){out={};return false;}return true;
}
bool Writer::Open(const Header& header,std::uint64_t revision_floor,std::uint64_t admission_floor)noexcept{
    const DWORD error=GetLastError();bool ok=false;PSECURITY_DESCRIPTOR descriptor{};
    try{
        if(!mapping_&&!handle_&&!faulted_&&Valid(header)&&header.active==-1
            &&revision_floor<static_cast<std::uint64_t>(std::numeric_limits<LONG64>::max()/2)
            &&admission_floor<static_cast<std::uint64_t>(std::numeric_limits<LONG64>::max()/2)
            &&header.client_pid==GetCurrentProcessId()&&fence::Creation(GetCurrentProcess())==header.client_creation
            &&Security(descriptor)){
            SECURITY_ATTRIBUTES attributes{sizeof(attributes),descriptor,FALSE};const auto name=Name(header.client_pid,header.client_creation,header.manifest);
            handle_=CreateFileMappingW(INVALID_HANDLE_VALUE,&attributes,PAGE_READWRITE,0,mapping_size,name.c_str());
            const bool existing=GetLastError()==ERROR_ALREADY_EXISTS;
            if(handle_&&!existing){mapping_=static_cast<Mapping*>(MapViewOfFile(handle_,FILE_MAP_READ|FILE_MAP_WRITE,0,0,mapping_size));
                if(mapping_){std::memset(mapping_,0,mapping_size);mapping_->header=header;
                    if(revision_<revision_floor){revision_=revision_floor;}
                    if(admission_revision_<admission_floor){admission_revision_=admission_floor;}ok=true;}}
        }
    }catch(...){ok=false;}
    if(descriptor){LocalFree(descriptor);}if(!ok){Close();}SetLastError(error);return ok;
}
bool Writer::TrackAdmission(const Frame& facts)noexcept{
    if(!has_eligibility_||!SameEligibility(eligibility_,facts)){
        if(admission_revision_==static_cast<std::uint64_t>(std::numeric_limits<LONG64>::max()/2)){
            faulted_=true;if(mapping_){InterlockedExchange(&mapping_->header.active,-1);}return false;}
        ++admission_revision_;eligibility_=facts;has_eligibility_=true;
    }return true;
}
bool Writer::ObserveAdmission(std::uint32_t blocks)noexcept{
    if(!mapping_||faulted_||!has_eligibility_||!eligibility_.complete||!blocks||(blocks&~admission::known)){return false;}
    auto facts=eligibility_;facts.admission_blocks=blocks;return TrackAdmission(facts);
}
bool Writer::InvalidateAdmission()noexcept{
    if(!mapping_||faulted_){return false;}Frame facts{};return TrackAdmission(facts);
}
bool Writer::Publish(const Frame& facts)noexcept{
    const DWORD error=GetLastError();if(!mapping_||faulted_){SetLastError(error);return false;}
    if(!Facts(facts)||write_sequence_==static_cast<std::uint64_t>(std::numeric_limits<LONG64>::max()/2)){
        faulted_=true;InterlockedExchange(&mapping_->header.active,-1);SetLastError(error);return false;}
    Frame next=facts;bool ok=TrackAdmission(facts);next.admission_revision=admission_revision_;
    if(!has_last_||!Same(last_,next)){
        if(revision_==static_cast<std::uint64_t>(std::numeric_limits<LONG64>::max()/2)
            ||BCryptGenRandom(nullptr,next.snapshot.data(),static_cast<ULONG>(next.snapshot.size()),BCRYPT_USE_SYSTEM_PREFERRED_RNG)<0){ok=false;}
        else{next.revision=++revision_;}
    }else{next.revision=last_.revision;next.snapshot=last_.snapshot;}
    next.sampled_tick=GetTickCount64();
    if(ok){const LONG slot=mapping_->header.active==0?1:0;auto& dest=mapping_->frames[static_cast<std::size_t>(slot)];
        next.sequence=static_cast<LONG64>(++write_sequence_*2);
        InterlockedExchange64(&dest.sequence,next.sequence-1);
        std::memcpy(reinterpret_cast<char*>(&dest)+8,reinterpret_cast<const char*>(&next)+8,sizeof(Frame)-8);
        MemoryBarrier();InterlockedExchange64(&dest.sequence,next.sequence);InterlockedExchange(&mapping_->header.active,slot);
        last_=next;has_last_=true;
    }else{faulted_=true;InterlockedExchange(&mapping_->header.active,-1);}
    SetLastError(error);return ok;
}
bool Writer::Unknown(std::uint32_t reason)noexcept{Frame frame{};frame.unknown=reason;return reason&&Publish(frame);}
bool Writer::Current(Frame& out)const noexcept{out={};if(!mapping_||!has_last_||faulted_){return false;}out=last_;return Valid(out);}
void Writer::Close()noexcept{
    const DWORD error=GetLastError();if(mapping_){InterlockedExchange(&mapping_->header.active,-1);UnmapViewOfFile(mapping_);mapping_=nullptr;}
    if(handle_){CloseHandle(handle_);handle_=nullptr;}has_last_=false;has_eligibility_=false;SetLastError(error);
}
}
