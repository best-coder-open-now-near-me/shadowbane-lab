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
    a::ApplicationJournal interrupted;
    slot=interrupted.Reserve(potion,first,10);
    Check(interrupted.Record(slot,first,a::ApplicationEntry::entered,true,false),"owned power queued with local responsibility");
    Check(!interrupted.Interrupt(slot,second,10,11)&&!interrupted.Interrupt(slot,first,9,11)
        &&!interrupted.Interrupt(slot,first,10,10),"terminal evidence cannot substitute command, submission or same observation");
    Check(interrupted.Interrupt(slot,first,10,11)&&interrupted.LocalPending(),"semantic interruption does not itself settle local responsibility");
    Check(interrupted.Reserve(potion,second,12)==a::ApplicationJournal::invalid,"unsettled local work still blocks retry");
    Check(interrupted.Record(slot,first,a::ApplicationEntry::entered,true,true)
        &&interrupted.Records()[slot].state==a::ApplicationState::interrupted,"late exact settlement cannot reinsert interrupted application");
    Check(!interrupted.Pending(potion),"positive interruption permits fresh ordinary eligibility evaluation");
    const auto replacement=interrupted.Reserve(potion,second,12);
    Check(replacement!=a::ApplicationJournal::invalid&&interrupted.Record(replacement,second,a::ApplicationEntry::entered,true,true),"new generation reserved after settled interruption");
    Check(!interrupted.Interrupt(slot,first,10,13)&&interrupted.Pending(potion),"old terminal cannot clear newer reused slot");
    a::ApplicationJournal no_queue;
    slot=no_queue.Reserve(potion,first,10);
    Check(no_queue.Record(slot,first,a::ApplicationEntry::uncertain,false,true)
        &&!no_queue.Interrupt(slot,first,10,11)&&no_queue.Pending(potion),"uncertain entry is not semantic queued activation proof");
    Check(no_queue.Observe(potion,12,true,true)&&!no_queue.Pending(potion),"canonical presence independently resolves unknown association");
    const auto stamp=[](double value){return std::bit_cast<std::uint64_t>(value);};
    a::ApplicationJournal renewal;
    const std::array baseline{a::CoverageDeadline{222,stamp(115)},a::CoverageDeadline{333,stamp(120)}};
    slot=renewal.Reserve(potion,first,10,baseline);
    Check(renewal.Record(slot,first,a::ApplicationEntry::entered,true,true),"covered renewal queues with exact descriptor deadlines");
    for(const auto& current:std::array{
        baseline,
        std::array{a::CoverageDeadline{222,stamp(400)},a::CoverageDeadline{333,stamp(120)}},
        std::array{a::CoverageDeadline{222,stamp(400)},a::CoverageDeadline{444,stamp(500)}},
        std::array{a::CoverageDeadline{222,0},a::CoverageDeadline{333,stamp(500)}}}){
        Check(renewal.Observe(potion,20,true,true,current)&&renewal.Pending(potion),"partial, replaced or unknown descriptor cannot confirm renewal");
        Check(renewal.Reserve(potion,second,21)==a::ApplicationJournal::invalid,"old PRESENT cannot permit duplicate potion");
    }
    const std::array refreshed{a::CoverageDeadline{333,stamp(500)},a::CoverageDeadline{222,stamp(400)}};
    Check(renewal.Observe(potion,10,true,true,refreshed)&&renewal.Pending(potion),"new deadlines need later exact publication");
    Check(renewal.Observe(potion,22,true,true,refreshed)&&!renewal.Pending(potion),"each native deadline advancement confirms covered renewal despite ordering");
    const std::array varied{a::CoverageDeadline{222,stamp(115)},a::CoverageDeadline{333,stamp(1000)}};
    slot=renewal.Reserve(potion,second,23,varied);
    Check(slot!=a::ApplicationJournal::invalid&&renewal.Record(slot,second,a::ApplicationEntry::entered,true,true),"next generation retains varied descriptor durations");
    const std::array varied_new{a::CoverageDeadline{222,stamp(400)},a::CoverageDeadline{333,stamp(1285)}};
    Check(renewal.Observe(potion,24,true,true,varied_new)&&!renewal.Pending(potion),"each deadline advances without requiring new minimum beyond old maximum");
    a::CoverageDeadlines duplicates{};
    Check(duplicates.Add(222,stamp(115))&&duplicates.Add(222,stamp(120))&&duplicates.count==1
        &&duplicates.values[0].stamp==stamp(120),"duplicate descriptor retains longest existing deadline");
    Check(!duplicates.Add(333,0)&&!duplicates.Add(333,stamp(-1000)),"sentinel timing cannot become renewal baseline");
    std::printf("application journal: %u failures\n",failures);return failures?1:0;
}
