#include "actor_action_wire.h"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <cassert>
namespace w=wonderbane::extension::actor::wire;
namespace f=wonderbane::extension::actor::fence;
template<class T>T Hex(const std::string& text){
    assert(text.size()==sizeof(T)*2);T result{};auto* bytes=reinterpret_cast<unsigned char*>(&result);
    auto digit=[](char c){assert((c>='0'&&c<='9')||(c>='a'&&c<='f'));return c<='9'?c-'0':c-'a'+10;};
    for(std::size_t i=0;i<sizeof(T);++i){bytes[i]=static_cast<unsigned char>(digit(text[i*2])*16+digit(text[i*2+1]));}return result;
}
template<class T>T Read(const wchar_t* path){std::ifstream file{std::filesystem::path(path)};std::string text;file>>text;assert(file);return Hex<T>(text);}
int Consumer(){
    std::cout<<GetCurrentProcessId()<<" "<<f::Creation(GetCurrentProcess())<<std::endl;
    std::string p,c;std::getline(std::cin,p);std::getline(std::cin,c);
    const auto parent=Hex<f::ActorBinding>(p);const auto child=Hex<f::ContextBinding>(c);
    f::Digest pd{},cd{};assert(f::HashBinding(parent,pd)&&f::HashBinding(child,cd));
    f::ActorBinding read_parent{};f::ContextBinding read_child{};
    assert(f::ReadBinding(pd,read_parent)&&f::Same(read_parent,parent));
    assert(f::ReadBinding(cd,read_child)&&f::Same(read_child,child)&&f::Parent(read_child,parent));
    f::Ticket<f::ActorBinding> pt;f::Ticket<f::ContextBinding> ct;
    assert(pt.Open(parent,parent)&&ct.Open(child,parent));std::cout<<"open"<<std::endl;
    std::string line;
    while(std::getline(std::cin,line)){
        if(line=="enter"){
            const auto a=pt.TryAdmit(parent,false);const auto b=ct.TryAdmit(child,false);
            std::cout<<(a==f::Result::admitted&&b==f::Result::admitted?"admitted":"denied")<<std::endl;
        }else if(line=="inspect"){
            f::State a{},b{};const auto ar=pt.Inspect(a),br=ct.Inspect(b);
            std::cout<<static_cast<int>(ar)<<" "<<static_cast<int>(a)<<" "
                <<static_cast<int>(br)<<" "<<static_cast<int>(b)<<std::endl;
        }else if(line=="exit"){return 0;}else{return 2;}
    }return 0;
}
int wmain(int argc,wchar_t** argv){
    if(argc==2&&!std::wcscmp(argv[1],L"--consumer")){return Consumer();}
    if(argc==4&&!std::wcscmp(argv[1],L"--group")){
        const auto c=Read<w::Command>(argv[2]);const auto r=Read<w::Receipt>(argv[3]);
        assert(w::Valid(w::Verb::submit,c)&&c.action==w::Action::group_chat);
        const auto chat=w::Chat(c);assert(chat.length==20&&chat.group[0]==0x67);
        assert(!std::memcmp(chat.text.data(),"Hunt Foe: Alice, Bob",20));
        assert(w::Correlated(c,w::Verb::submit,r)&&r.application==w::Application::none);
        assert(r.flags&w::outbound_queued);
        auto bad=c;bad.reserved[sizeof(bad.reserved)-1]=1;assert(!w::Valid(bad));
        assert(!w::Valid(w::Verb::cancel_action,c));
        std::cout<<"group chat queued wire accepted"<<std::endl;return 0;
    }
    assert(argc==5);
    const auto p=Read<f::ActorBinding>(argv[1]);const auto x=Read<f::ContextBinding>(argv[2]);
    const auto c=Read<w::Command>(argv[3]);const auto r=Read<w::Receipt>(argv[4]);
    assert(f::Valid(p)&&f::Valid(x)&&f::Parent(x,p));
    assert(w::Valid(w::Verb::submit,c)&&w::Bindings(c,p)&&w::Correlated(c,w::Verb::submit,r));
    assert(c.item_key[0]==5802955&&c.item_key[1]==30&&c.template_key[0]==980066&&!c.template_key[1]);
    assert(r.local_settlement==w::LocalSettlement::settled&&r.application==w::Application::pending);
    auto interrupted=r;interrupted.application=w::Application::interrupted;interrupted.flags&=~w::application_pending;
    assert(w::Correlated(c,w::Verb::submit,interrupted));
    interrupted.flags&=~w::outbound_queued;assert(!w::Valid(interrupted));
    for(unsigned i=0;i<12;++i){auto bad=c;switch(i){
        case 0:bad.version=2;break;case 1:bad.reserved[0]=1;break;
        case 2:bad.template_key[1]=40;break;case 3:bad.item_key[1]=0;break;
        case 4:bad.template_hint=0;break;case 5:bad.item_hint=bad.template_hint;break;
        case 6:bad.recipient=w::Recipient::target;break;case 7:bad.power_id=42;break;
        case 8:bad.selector_index=32;break;case 9:bad.publication_revision=0;break;
        case 10:bad.snapshot_id={};break;case 11:bad.context_id[15]=1;break;
    }assert(!w::Valid(bad));}
    auto changed=c;changed.template_hint+=4;assert(w::Valid(changed)&&!w::Correlated(changed,w::Verb::submit,r));
    auto target=c;target.context_id=x.context_id;assert(f::HashBinding(x,target.context_digest));
    target.action=w::Action::self_power;target.power_id=429545819;
    std::memset(target.item_key,0,8);std::memset(target.template_key,0,8);target.item_hint=target.template_hint=0;
    assert(w::Bindings(target,p,&x));
    auto refused=w::Reply(target,w::Verb::submit,w::Outcome::power_reuse_blocked);
    refused.owner_phase=refused.context_phase=w::Phase::bound;
    refused.flags=w::owner_cleanup|w::context_cleanup;refused.entry=w::Entry::never_entered;
    refused.local_settlement=w::LocalSettlement::settled;refused.reason=w::Reason::power_reuse;
    assert(w::Correlated(target,w::Verb::submit,refused));
    refused.verb=w::Verb::action_status;refused.context_phase=w::Phase::closed;refused.flags=w::owner_cleanup;
    refused.closure=w::Closure::native_stopped;refused.closure_scope=w::ClosureScope::context;refused.mode=1;
    assert(w::Correlated(target,w::Verb::action_status,refused));
    auto bad_scope=refused;bad_scope.owner_phase=w::Phase::closed;bad_scope.flags=0;
    assert(!w::Valid(bad_scope));
    bad_scope.closure_scope=w::ClosureScope::owner;bad_scope.context_phase=w::Phase::retired;
    assert(!w::Valid(bad_scope));
    for(unsigned reason=7;reason<=11;++reason){auto typed=refused;
        typed.outcome=w::Outcome::deferred;typed.reason=static_cast<w::Reason>(reason);
        assert(w::Valid(typed)); // Historical positive context closure retains the exact refusal.
        typed.verb=w::Verb::submit;typed.context_phase=w::Phase::bound;typed.closure=w::Closure::none;
        typed.closure_scope=w::ClosureScope::none;typed.flags=w::owner_cleanup|w::context_cleanup;
        assert(w::Valid(typed));
        for(unsigned bad=0;bad<6;++bad){auto invalid=typed;
            if(bad==0){invalid.entry=w::Entry::entered;}
            if(bad==1){invalid.local_settlement=w::LocalSettlement::pending;}
            if(bad==2){invalid.flags|=w::outbound_queued;}
            if(bad==3){invalid.verb=w::Verb::cancel_action;}
            if(bad==4){invalid.application=w::Application::observed;}
            if(bad==5){invalid.outcome=w::Outcome::rejected;}
            assert(!w::Valid(invalid));}
    }
    refused.verb=w::Verb::cancel_action;assert(!w::Valid(refused));
    auto readonly=c;readonly.grant={};readonly.parent_id={};readonly.parent_digest={};readonly.action=w::Action::none;
    readonly.power_id=0;std::memset(readonly.item_key,0,8);std::memset(readonly.template_key,0,8);
    readonly.item_hint=readonly.template_hint=0;readonly.recipient=w::Recipient::none;
    assert(w::Valid(w::Verb::observe_actor,readonly)&&!w::Valid(w::Verb::open_owner,readonly));
    auto actor=p;actor.state=f::State::entered;f::Digest before{},after{};
    assert(f::HashBinding(p,before)&&f::HashBinding(actor,after)&&before==after);
    actor.actor_hint+=4;assert(f::HashBinding(actor,after)&&before!=after);
    std::cout<<"actor v3/v4 golden and negative checks passed"<<std::endl;return 0;
}
