#include "actor_publication.cpp"
#include <cstdio>
#include <iostream>
namespace p=wonderbane::extension::actor::publication;
namespace {
unsigned checks{},failures{};
void Check(bool value,const char* label){++checks;if(!value){++failures;std::fprintf(stderr,"%s\n",label);}}
p::Frame Sample(){
    p::Frame f{};f.unknown=0;f.complete=1;f.effect_epoch=1;f.actor_mode=1;f.initiation_clear=1;f.readiness_count=1;f.descriptor_count=1;
    f.readiness[0].selector={0,0,3,111,0,0,111,0};f.readiness[0].rank=40;f.readiness[0].target_mode=2;f.readiness[0].required_mode=3;
    f.readiness[0].coverage=1;f.readiness[0].readiness=1;f.readiness[0].descriptor_count=1;f.descriptors[0]={222,333,0,0,0,{}};return f;
}
void EncodeCases(){
    namespace a=wonderbane::extension::actor;namespace b=wonderbane::extension::actor_buffs;
    a::selectors::Manifest manifest;manifest.client_pid=123;manifest.producer_pid=321;
    manifest.client_creation=456;manifest.producer_creation=654;manifest.producer_generation=1;
    manifest.local_name.fill(1);manifest.server.fill(2);manifest.count=manifest.groups=1;
    manifest.records[0]={0,0,3,111,0,0,111,0};
    b::Publication source{};source.unknown=b::Unknown::none;source.actor_key={4050960,53};source.scene=1;
    source.effect_epoch=1;source.count=1;source.actor_mode=1;source.initiation_clear=true;
    auto& action=source.actions[0];action.intent={0,0,111,{},111,b::CoverageKind::all_descriptors};
    action.learned_rank=40;action.target_mode=2;action.required_mode=3;action.descriptor_count=1;
    action.descriptors[0]={222,333,wonderbane::extension::actor_effects::ActionClass::apply,0,false};
    action.coverage=b::Coverage::missing;action.readiness=b::Readiness::ready;
    wonderbane::extension::actor_actions::ApplicationJournal journal;p::Digest intent{},command{};command.fill(7);
    Check(a::selectors::GroupDigest(manifest,0,intent),"native canonical group digest");
    const auto record=journal.Reserve(intent,command,1);
    Check(journal.Record(record,command,wonderbane::extension::actor_actions::ApplicationEntry::uncertain,false,true),"independent local settlement/remote uncertainty retained");
    p::Frame frame{};Check(p::Encode(manifest,source,journal,frame)&&p::Facts(frame),"canonical resolver and journal encode");
    Check(frame.applications[0].entry==2&&frame.applications[0].state==1&&frame.applications[0].local_settled
        &&!frame.applications[0].queued&&frame.applications[0].intent==intent,"exact pending application copied without invented receipt fields");
    auto item=Sample();item.readiness[0].selector={0,0,4,0,980066,0,111,0};
    item.readiness[0].rank=0;item.readiness[0].readiness=0;
    Check(p::Facts(item),"unknown empty item with independently known coverage is representable");
    for(unsigned i=0;i<9;++i){auto bad=item;auto* operands=&bad.readiness[0].item_key[0];operands[i]=1;
        Check(!p::Facts(bad),"unknown item cannot advertise partial operand");}
    auto forged=item;auto& f=forged.readiness[0];f.item_key[0]=55;f.item_key[1]=30;f.template_key[0]=980066;
    f.item_hint=0x20000000;f.template_hint=0x20001000;f.quantity=3;f.type=8;f.flags=10;
    Check(!p::Facts(forged),"unknown item cannot advertise even otherwise valid operand");
    forged.initiation_clear=0;f.readiness=1;
    Check(p::Facts(forged),"qualified stationary item can be ready with retained initiation IDs");
    item.readiness[0].readiness=1;Check(!p::Facts(item),"empty item never ready");
    item.readiness[0].readiness=8;Check(p::Facts(item),"complete noeligible remains unavailable");
    action.intent.power_id=112;Check(!p::Encode(manifest,source,journal,frame),"foreign selector operand cannot publish");
    for(unsigned failure=0;failure<4;++failure){auto invalid=Sample();
        if(failure==0){invalid.readiness[0].rank=0;}
        if(failure==1){invalid.initiation_clear=0;}
        if(failure==2){invalid.readiness[0].coverage=3;}
        if(failure==3){invalid.descriptors[0].present=1;invalid.readiness[0].coverage=3;}
        Check(!p::Facts(invalid),"inconsistent readiness/coverage fails before publication");
    }
}
}
int Ipc(){
    wonderbane::extension::actor::selectors::Manifest manifest;
    manifest.client_pid=manifest.producer_pid=GetCurrentProcessId();
    manifest.client_creation=manifest.producer_creation=wonderbane::extension::actor::fence::Creation(GetCurrentProcess());
    manifest.producer_generation=1;manifest.count=manifest.groups=1;manifest.local_name.fill(1);manifest.server.fill(2);
    manifest.records[0]={0,0,3,111,0,0,111,0};
    p::Header h{};h.client_pid=manifest.client_pid;h.client_creation=manifest.client_creation;
    h.actor_key[0]=4050960;h.actor_key[1]=53;h.actor_address=0x21000000;h.scene=1;
    if(!wonderbane::extension::actor::selectors::Hash(manifest,h.manifest)
        ||BCryptGenRandom(nullptr,h.actor_lifetime.data(),16,BCRYPT_USE_SYSTEM_PREFERRED_RNG)<0){return 2;}
    p::Writer writer;auto sample=Sample();if(!writer.Open(h)||!writer.Publish(sample)){return 3;}
    std::cout<<h.client_pid<<" "<<h.client_creation<<"\n"<<std::flush;
    std::string command;
    while(std::getline(std::cin,command)){
        if(command=="same"){if(!writer.Publish(sample)){return 4;}}
        else if(command=="journal"){
            sample.application_count=1;auto& a=sample.applications[0];a.intent.fill(1);a.command.fill(2);
            ++a.command[0];a.submitted_revision=writer.Revision();a.local_settled=1;
            if(!writer.Publish(sample)){return 9;}
        }
        else if(command=="occupied"){sample.admission_blocks=8;if(!writer.Publish(sample)){return 10;}}
        else if(command=="clear"){sample.admission_blocks=0;if(!writer.Publish(sample)){return 11;}}
        else if(command=="race"){if(!writer.ObserveAdmission(8)){return 12;}sample.admission_blocks=0;if(!writer.Publish(sample)){return 13;}}
        else if(command=="reuse"){sample.readiness[0].readiness=5;if(!writer.Publish(sample)){return 5;}}
        else if(command=="unknown"){if(!writer.Unknown(6)){return 6;}}
        else if(command=="close"){writer.Close();std::cout<<"closed\n"<<std::flush;return 0;}
        else{return 7;}
        std::cout<<"published\n"<<std::flush;
    }return 8;
}
int main(int argc,char** argv){
    if(argc==2&&!std::strcmp(argv[1],"ipc")){return Ipc();}
    EncodeCases();
    p::Header h{};h.client_pid=GetCurrentProcessId();h.client_creation=wonderbane::extension::actor::fence::Creation(GetCurrentProcess());
    h.actor_key[0]=4050960;h.actor_key[1]=53;h.actor_address=0x21000000;h.scene=1;
    BCryptGenRandom(nullptr,h.actor_lifetime.data(),16,BCRYPT_USE_SYSTEM_PREFERRED_RNG);
    BCryptGenRandom(nullptr,h.manifest.data(),32,BCRYPT_USE_SYSTEM_PREFERRED_RNG);
    Check(p::Valid(h),"exact lifetime header valid");p::Writer writer;SetLastError(345);Check(writer.Open(h)&&GetLastError()==345,"native writer creates current lifetime mapping");
    const auto name=p::Name(h.client_pid,h.client_creation,h.manifest);
    const HANDLE reader=OpenFileMappingW(FILE_MAP_READ,FALSE,name.c_str());Check(reader!=nullptr,"same-user read-only open allowed");
    const HANDLE denied=OpenFileMappingW(FILE_MAP_WRITE,FALSE,name.c_str());Check(!denied,"same-user writable reopen denied");if(denied){CloseHandle(denied);}
    const auto* mapping=static_cast<const p::Mapping*>(MapViewOfFile(reader,FILE_MAP_READ,0,0,p::mapping_size));Check(mapping!=nullptr,"read-only mapping view");
    p::Writer duplicate;Check(!duplicate.Open(h),"existing publication never adopted/overwritten");
    auto sample=Sample();Check(writer.Publish(sample),"complete facts published");p::Frame first{};Check(writer.Current(first)&&p::Valid(first),"complete current frame valid");
    Check(mapping&&mapping->header.active>=0&&p::Valid(mapping->frames[static_cast<std::size_t>(mapping->header.active)]),"published slot validates across actual mapping");
    Check(writer.Publish(sample),"identical facts refreshed");p::Frame same{};writer.Current(same);
    Check(same.revision==first.revision&&same.snapshot==first.snapshot&&same.sequence>first.sequence,"content identity stable but transport sequence advances");
    sample.application_count=1;auto& history=sample.applications[0];history.intent.fill(1);history.command.fill(2);
    history.submitted_revision=first.revision;history.local_settled=1;
    Check(writer.Publish(sample),"never-entered journal record published");p::Frame history_frame{};writer.Current(history_frame);
    Check(history_frame.revision>same.revision&&history_frame.admission_revision==same.admission_revision,
        "journal-only revision cannot create renewed admission");
    for(unsigned i=0;i<32;++i){history.command[0]=static_cast<std::uint8_t>(i+3);history.submitted_revision++;
        Check(writer.Publish(sample),"journal record replacement remains valid");p::Frame fresh{};writer.Current(fresh);
        Check(fresh.admission_revision==same.admission_revision,"repeated no-entry history never advances admission");}
    Check(writer.ObserveAdmission(wonderbane::extension::actor::admission::foreign_target),"actual failed target predicate recorded privately");
    p::Frame prior{};writer.Current(prior);Check(!prior.admission_blocks,"historical failed predicate is not published as current occupancy");
    Check(writer.Publish(sample),"actual clear capture after raced block");p::Frame clear{};writer.Current(clear);
    Check(clear.admission_revision>prior.admission_revision+1,"observed block then clear allows a genuinely recovered retry");
    Check(writer.InvalidateAdmission()&&writer.Publish(sample),"unknown admission must be positively recaptured");
    p::Frame recovered{};writer.Current(recovered);Check(recovered.admission_revision>clear.admission_revision,"unknown recovery advances admission");
    sample.admission_blocks=wonderbane::extension::actor::admission::foreign_target;
    Check(writer.Publish(sample),"real occupancy can coexist with resource-ready metadata");sample.admission_blocks=0;
    sample.readiness[0].readiness=5;Check(writer.Publish(sample),"readiness change published");p::Frame changed{};writer.Current(changed);
    Check(changed.revision>same.revision&&changed.snapshot!=same.snapshot,"readiness change advances full content identity");
    Check(writer.Unknown(6),"failed capture publishes unknown");p::Frame unknown{};writer.Current(unknown);
    Check(p::Valid(unknown)&&!unknown.complete&&!unknown.effect_count&&!unknown.readiness_count,"unknown never retains stale absence/readiness");
    Check(writer.Publish(sample),"fresh valid capture after unknown");p::Frame restored{};writer.Current(restored);Check(restored.revision>unknown.revision,"fresh capture after unknown is new content");
    auto invalid=Sample();invalid.readiness[0].descriptor_count=2;Check(!writer.Publish(invalid)&&mapping->header.active==-1,"invalid content disables prior authority");
    writer.Close();Check(mapping->header.active==-1,"closure invalidates retained reader view");
    if(mapping){UnmapViewOfFile(mapping);}if(reader){CloseHandle(reader);}
    h.manifest[0]^=1;p::Writer replacement;
    Check(replacement.Open(h,100,200)&&replacement.Publish(Sample()),"new manifest preserves retained actor revision high-water");
    p::Frame migrated{};Check(replacement.Current(migrated)&&migrated.revision==101&&replacement.Revision()==101&&migrated.admission_revision==201,
        "new mapping revision follows prior application history");replacement.Close();
    p::Writer exhausted;Check(!exhausted.Open(h,0,UINT64_MAX),"admission generation overflow never wraps into an old permission");
    std::printf("publication: %u checks, %u failures\n",checks,failures);return failures?1:0;
}
