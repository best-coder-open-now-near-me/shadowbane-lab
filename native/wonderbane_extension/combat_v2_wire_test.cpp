#include "combat_v2_wire.h"
#undef NDEBUG
#include <cassert>
#include <fstream>
#include <filesystem>
#include <string>
namespace w = wonderbane::extension::combat::v2::wire;
namespace f = wonderbane::extension::combat::v3::fence;
namespace m = wonderbane::extension::movement;
template<class T> T ReadHex(const wchar_t* path) {
    std::ifstream file{std::filesystem::path(path)}; std::string value; file>>value;
    assert(file && value.size()==sizeof(T)*2); T result{};
    auto* bytes=reinterpret_cast<unsigned char*>(&result);
    auto digit=[](char c)->unsigned { assert((c>='0'&&c<='9')||(c>='a'&&c<='f')); return c<='9'?c-'0':c-'a'+10; };
    for(std::size_t i=0;i<sizeof(T);++i) { bytes[i]=static_cast<unsigned char>(digit(value[i*2])*16+digit(value[i*2+1])); }
    return result;
}
int wmain(int argc,wchar_t** argv) {
    assert(argc==4);
    const auto golden_command=ReadHex<w::Command>(argv[1]);
    const auto golden_binding=ReadHex<f::Binding>(argv[2]);
    const auto golden_receipt=ReadHex<w::Receipt>(argv[3]);
    f::Binding rebuilt{};
    assert(w::BindingFor(golden_command,golden_binding.client_pid,golden_binding.client_creation,rebuilt));
    assert(!std::memcmp(&golden_binding,&rebuilt,sizeof(rebuilt)));
    assert(w::Correlated(golden_command,golden_receipt.verb,golden_receipt));
    assert(golden_command.authority==w::Authority::manual_player && golden_command.action==w::Action::cast
        && golden_command.power_id==428918601 && golden_command.engagement.back()==1 && golden_command.request.back()==2);

    w::Command command{};
    command.host={GetCurrentProcessId(),3,f::Creation(GetCurrentProcess())};
    command.window=0x10004; command.grant.generation=7; command.grant.scene=9; command.grant.owner=1;
    strcpy_s(command.grant.token.worker,"worker"); strcpy_s(command.grant.token.operation,"operation");
    command.local_key[0]=100; command.local_key[1]=53; command.target_key[0]=200; command.target_key[1]=37;
    command.request.back()=1; command.engagement.back()=1;
    command.local_name.fill(1); command.server.fill(2); command.owner.fill(3);
    command.actor_hint=0x20000; command.target_hint=0x30000;
    assert(w::Hash(&command.grant.token,sizeof(command.grant.token),command.operation));
    f::Binding binding{};
    binding.client_pid=command.host.process; binding.client_creation=command.host.creation;
    binding.producer_pid=command.host.process; binding.producer_creation=command.host.creation;
    binding.producer_generation=command.host.generation; binding.movement_generation=7; binding.scene=9;
    binding.authority=2; binding.actor_hint=command.actor_hint; binding.target_hint=command.target_hint;
    std::memcpy(binding.local_key,command.local_key,8); std::memcpy(binding.target_key,command.target_key,8);
    std::memcpy(binding.engagement,command.engagement.data(),16);
    std::memcpy(binding.owner,command.owner.data(),32); std::memcpy(binding.operation,command.operation.data(),32);
    assert(f::HashBinding(binding,command.binding_digest));
    f::Binding decoded{};
    assert(w::BindingFor(command,binding.client_pid,binding.client_creation,decoded) && f::Same(binding,decoded));
    for (auto verb : {w::Verb::bind,w::Verb::submit,w::Verb::action_status,w::Verb::cancel_action,w::Verb::engagement_status,w::Verb::stop}) {
        for (auto action : {w::Action::none,w::Action::attack,w::Action::cast,w::Action::self_power,static_cast<w::Action>(4)}) {
            for (unsigned power : {0U,428918601U}) {
                const bool expected=w::ActionVerb(verb)
                    ? (action==w::Action::attack&&!power)||((action==w::Action::cast||action==w::Action::self_power)&&power)
                    : action==w::Action::none&&!power;
                assert(w::Valid(action,power,verb)==expected);
            }
        }
    }
    for (unsigned legacy : {34U,35U,36U,43U}) { assert(!w::Valid(static_cast<w::Verb>(legacy))); }
    const auto original=command;
    for (unsigned change=0;change<8;++change) {
        command=original;
        switch(change) {
        case 0:command.version=1;break;
        case 1:command.authority=w::Authority::manual_player;break;
        case 2:command.revision=1;break;
        case 3:command.store[0]=1;break;
        case 4:command.target_name[0]=1;break;
        case 5:command.actor_hint=command.target_hint;break;
        case 6:command.actor_hint=0x20001;break;
        case 7:command.local_key[1]=37;break;
        }
        assert(!w::BindingFor(command,binding.client_pid,binding.client_creation,decoded));
    }
    command=original;
    auto receipt=w::Reply(command,w::Verb::bind,w::Outcome::bound);
    receipt.phase=w::Phase::bound; receipt.flags=w::cleanup_required;
    assert(w::Correlated(command,w::Verb::bind,receipt));
    receipt.flags|=w::outbound_queued; assert(!w::Valid(receipt));
    receipt=w::Reply(command,w::Verb::bind,w::Outcome::deferred);
    assert(!w::Valid(receipt));
    receipt.phase=w::Phase::closed; receipt.closure=w::Closure::never_bound;
    assert(w::Valid(receipt));
    receipt.verb=w::Verb::engagement_status; assert(!w::Valid(receipt));
    command.action=w::Action::cast; command.power_id=428918601;
    assert(w::BindingFor(command,binding.client_pid,binding.client_creation,decoded));
    receipt=w::Reply(command,w::Verb::submit,w::Outcome::client_outbound_queued);
    receipt.phase=w::Phase::bound; receipt.flags=w::cleanup_required|w::outbound_queued; receipt.entry=w::Entry::entered;
    assert(w::Correlated(command,w::Verb::submit,receipt));
    receipt.phase=w::Phase::closed; receipt.closure=w::Closure::native_stopped; receipt.flags&=~w::cleanup_required;
    assert(w::Correlated(command,w::Verb::submit,receipt)); // Closing cannot erase queue history.
    receipt.closure=w::Closure::never_bound; assert(!w::Valid(receipt));
    receipt.closure=w::Closure::native_stopped;
    receipt.entry=w::Entry::unknown; assert(!w::Valid(receipt));
    receipt.outcome=w::Outcome::history_expired; receipt.phase=w::Phase::unknown; receipt.flags=0; receipt.closure=w::Closure::history_expired;
    assert(w::Valid(receipt));
    receipt.outcome=w::Outcome::action_cancelled; receipt.closure=w::Closure::none; assert(!w::Valid(receipt));
    receipt.entry=w::Entry::never_entered; assert(w::Valid(receipt));
    receipt.engagement[15]=2; assert(!w::Correlated(command,w::Verb::submit,receipt));
    auto changed=command; ++changed.request[15]; changed.action=w::Action::attack; changed.power_id=0;
    assert(w::SameEngagement(command,changed)); ++changed.target_hint; assert(!w::SameEngagement(command,changed));
    command.action=w::Action::self_power;
    assert(static_cast<unsigned>(command.action)==3 && w::BindingFor(command,binding.client_pid,binding.client_creation,decoded));
    receipt=w::Reply(command,w::Verb::submit,w::Outcome::client_outbound_queued);
    receipt.phase=w::Phase::bound; receipt.entry=w::Entry::entered;
    receipt.flags=w::cleanup_required|w::outbound_queued;
    assert(w::Correlated(command,w::Verb::submit,receipt) && receipt.target_key[0]==200);
    receipt.action=w::Action::cast; assert(!w::Correlated(command,w::Verb::submit,receipt));
    for(const auto action:{w::Action::cast,w::Action::self_power}) {
        command.action=action;
        auto ready=w::Reply(command,w::Verb::submit,w::Outcome::power_reuse_blocked);
        ready.phase=w::Phase::bound;ready.flags=w::cleanup_required;ready.entry=w::Entry::never_entered;
        assert(w::Valid(ready));
        for(const auto phase:{w::Phase::stopping,w::Phase::blocked}) { ready.phase=phase;assert(w::Valid(ready)); }
        ready.phase=w::Phase::closed;ready.closure=w::Closure::native_stopped;ready.flags=0;assert(w::Valid(ready));
        ready.phase=w::Phase::retired;ready.closure=w::Closure::scene_retired;assert(w::Valid(ready));
        ready.verb=w::Verb::cancel_action;assert(!w::Valid(ready));ready.verb=w::Verb::action_status;
        ready.entry=w::Entry::entered;assert(!w::Valid(ready));ready.entry=w::Entry::never_entered;
        ready.flags=w::uncertain_history;assert(!w::Valid(ready));ready.flags=0;
        ready.phase=w::Phase::closed;ready.closure=w::Closure::never_bound;assert(!w::Valid(ready));
        ready.phase=w::Phase::unknown;ready.closure=w::Closure::none;assert(!w::Valid(ready));
        ready.phase=w::Phase::bound;ready.flags=w::cleanup_required;ready.action=w::Action::attack;ready.power_id=0;
        assert(!w::Valid(ready));
    }
    command.action=static_cast<w::Action>(4); assert(!w::BindingFor(command,binding.client_pid,binding.client_creation,decoded));
    const auto name=f::Name(binding); assert(!name.empty());
    auto other=binding; ++other.movement_generation; assert(f::Name(other)!=name);
    other=binding; ++other.client_creation; assert(f::Name(other)!=name);
    other=binding; other.state=f::State::entered; assert(f::Name(other)==name);
    HANDLE mutex=CreateMutexW(nullptr,FALSE,(name+L".lock").c_str()); assert(mutex);
    HANDLE mapping=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,sizeof(binding),name.c_str()); assert(mapping);
    auto* view=static_cast<f::Binding*>(MapViewOfFile(mapping,FILE_MAP_READ|FILE_MAP_WRITE,0,0,sizeof(binding))); assert(view);
    *view=binding; view->state=f::State::pending;
    f::Ticket ticket; assert(ticket.Open(binding));
    assert(ticket.TryAdmit(binding,false)==f::Result::admitted && view->state==f::State::entered);
    assert(ticket.TryAdmit(binding,false)==f::Result::not_pending);
    assert(ticket.TryAdmit(binding,true)==f::Result::admitted);
    other=binding; ++other.target_hint; assert(ticket.TryAdmit(other,true)==f::Result::invalid);
    view->state=f::State::entered_revoked; assert(ticket.TryAdmit(binding,true)==f::Result::revoked);
    ticket.Close(); assert(UnmapViewOfFile(view)); assert(CloseHandle(mapping)); assert(CloseHandle(mutex));
}
