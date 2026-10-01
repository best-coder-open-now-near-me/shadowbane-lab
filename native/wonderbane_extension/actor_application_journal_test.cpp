#include "actor_application_journal.h"
#include <cstdio>
namespace a=wonderbane::extension::actor_actions;
namespace {
unsigned failures{};
void Check(bool ok,const char* label){if(!ok){++failures;std::fprintf(stderr,"%s\n",label);}}
a::JournalDigest Id(unsigned value){a::JournalDigest out{};out[0]=static_cast<std::uint8_t>(value);out[1]=static_cast<std::uint8_t>(value>>8);return out;}
}
int main(){
    a::ApplicationJournal journal;
    const auto potion=Id(1),precision=Id(2),first=Id(100),second=Id(101);
    auto slot=journal.Reserve(potion,first,10);
    Check(slot!=a::ApplicationJournal::invalid && journal.LocalPending(),"reserve responsibility before native entry");
    Check(journal.Record(slot,first,a::ApplicationEntry::entered,true,true),"queued potion locally completed");
    Check(journal.Pending(potion)&&!journal.LocalPending(),"pending potion is not local arbitration barrier");
    Check(journal.Reserve(potion,second,11)==a::ApplicationJournal::invalid,"another request cannot duplicate pending potion");
    const auto other=journal.Reserve(precision,second,11);
    Check(other!=a::ApplicationJournal::invalid,"independent buff can proceed during delayed potion");
    Check(journal.Record(other,second,a::ApplicationEntry::entered,true,false),"entered power retains local responsibility");
    Check(journal.Observe(precision,12,true,true)&&journal.LocalPending(),"effect presence never settles native power responsibility");
    Check(journal.Record(other,second,a::ApplicationEntry::entered,true,true),"independent local completion closes power responsibility");
    Check(journal.Observe(potion,10,true,true)&&journal.Pending(potion),"same publication cannot confirm application");
    Check(journal.Observe(potion,99,false,true)&&journal.Pending(potion),"incomplete observation cannot confirm application");
    Check(journal.Observe(potion,100,true,false)&&journal.Pending(potion),"missing or elapsed observations never permit retry");
    Check(journal.Observe(potion,101,true,true)&&!journal.Pending(potion),"later complete native presence confirms application");
    Check(journal.Reserve(potion,Id(102),102)!=a::ApplicationJournal::invalid,"subsequent native absence may refresh after observed application");
    a::ApplicationJournal uncertain;
    slot=uncertain.Reserve(potion,first,1);
    Check(uncertain.Record(slot,first,a::ApplicationEntry::uncertain,false,true),"remote uncertainty may have separate local settlement");
    Check(uncertain.Pending(potion)&&!uncertain.LocalPending(),"uncertainty suppresses duplicate without global barrier");
    Check(!uncertain.Record(slot,first,a::ApplicationEntry::never_entered,false,true)&&uncertain.Faulted(),"possible entry cannot silently downgrade into retry");
    Check(uncertain.Reserve(precision,second,3)==a::ApplicationJournal::invalid,"history contradiction disables later reservations");
    a::ApplicationJournal bounded;
    for(unsigned i=0;i<a::ApplicationJournal::capacity;++i){
        const auto n=bounded.Reserve(Id(i+1),Id(i+100),1);
        Check(n!=a::ApplicationJournal::invalid,"bounded unique reservation");
        Check(bounded.Record(n,Id(i+100),a::ApplicationEntry::entered,true,true),"bounded pending application");
    }
    Check(bounded.Reserve(Id(40),Id(140),2)==a::ApplicationJournal::invalid,"capacity never evicts pending application");
    Check(bounded.Observe(Id(1),3,true,true),"one application observed");
    Check(bounded.Reserve(Id(40),Id(140),4)!=a::ApplicationJournal::invalid,"only settled observed capacity reusable");
    Check(!bounded.Record(0,Id(100),a::ApplicationEntry::entered,true,true),"old command cannot mutate recycled record");
    a::ApplicationJournal refused;
    slot=refused.Reserve(potion,first,1);
    Check(refused.Record(slot,first,a::ApplicationEntry::never_entered,false,true)&&!refused.Pending(potion),"definitive pre-entry refusal has no remote obligation");
    Check(refused.Reserve(potion,second,2)!=a::ApplicationJournal::invalid,"fresh request after definitive refusal");
    std::printf("application journal: %u failures\n",failures);return failures?1:0;
}
