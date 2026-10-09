#pragma once
#include "combat_v3_fence.h"
#include <type_traits>
namespace wonderbane::extension::actor::fence {
namespace legacy = ::wonderbane::extension::combat::v3::fence;
using State = legacy::State;
using Result = legacy::Result;
using Digest = legacy::Digest;
using Id = std::array<std::uint8_t,16>;
using legacy::Address;
using legacy::Creation;
using legacy::Hash;
using legacy::Revoked;
constexpr std::uint32_t size=320;
// Capability-gated preparation parents own actor work, never movement/targets.
enum class Purpose : std::uint32_t { combat=0, preparation=1 };
#pragma pack(push,1)
struct ActorBinding {
    char magic[8]{'W','B','A','O','W','N','4',0};
    std::uint32_t version=4,bytes=size; State state=State::registering;
    Purpose purpose=Purpose::combat; std::uint32_t client_pid=0,producer_pid=0;
    std::uint64_t client_creation=0,producer_creation=0,producer_generation=0,movement_generation=0,scene=0;
    Id owner_id{}; std::uint32_t actor_key[2]{},actor_hint=0,reserved2=0;
    Digest local_name{},server{},owner{},operation{};
    std::uint8_t padding[88]{};
};
struct ContextBinding {
    char magic[8]{'W','B','A','C','X','T','4',0};
    std::uint32_t version=4,bytes=size; State state=State::registering;
    std::uint32_t reserved=0; Digest parent_digest{}; Id context_id{};
    std::uint32_t authority=0,target_hint=0,target_key[2]{};
    std::uint64_t revision=0; Digest store{},entry{},target_name{};
    std::uint8_t padding[128]{};
};
#pragma pack(pop)
static_assert(sizeof(ActorBinding)==320 && sizeof(ContextBinding)==320);
static_assert(offsetof(ActorBinding,state)==16 && offsetof(ContextBinding,state)==16);
static_assert(offsetof(ActorBinding,owner_id)==72 && offsetof(ActorBinding,local_name)==104);
static_assert(offsetof(ContextBinding,parent_digest)==24 && offsetof(ContextBinding,revision)==88);
template<class T> inline bool Any(const T& value) noexcept {
    for(auto byte:value){if(byte){return true;}}return false;
}
inline bool Valid(const ActorBinding& b) noexcept {
    return !std::memcmp(b.magic,"WBAOWN4",8)&&b.version==4&&b.bytes==320
        &&b.state<=State::entered_revoked&&b.purpose<=Purpose::preparation&&!b.reserved2&&!Any(b.padding)
        &&b.client_pid&&b.producer_pid&&b.client_creation&&b.producer_creation&&b.producer_generation
        &&((b.purpose==Purpose::combat&&b.movement_generation)||(b.purpose==Purpose::preparation&&!b.movement_generation))&&b.scene&&Any(b.owner_id)&&b.actor_key[0]&&b.actor_key[1]==53
        &&Address(b.actor_hint)&&Any(b.local_name)&&Any(b.server)&&Any(b.owner)&&Any(b.operation);
}
inline bool Valid(const ContextBinding& b) noexcept {
    const bool npc=b.authority==2&&b.target_key[1]==37&&!b.revision
        &&!Any(b.store)&&!Any(b.entry)&&!Any(b.target_name);
    const bool manual=b.authority==1&&b.target_key[1]==53&&b.revision
        &&Any(b.store)&&Any(b.entry)&&Any(b.target_name);
    return !std::memcmp(b.magic,"WBACXT4",8)&&b.version==4&&b.bytes==320
        &&b.state<=State::entered_revoked&&!b.reserved&&!Any(b.padding)
        &&Any(b.parent_digest)&&Any(b.context_id)&&b.target_key[0]&&Address(b.target_hint)&&(npc||manual);
}
template<class B> inline bool HashBinding(B b,Digest& out) noexcept {
    b.state=State::registering;return Valid(b)&&Hash(&b,sizeof(b),out);
}
template<class B> inline bool Same(B a,B b) noexcept {
    a.state=b.state=State::registering;return !std::memcmp(&a,&b,sizeof(B));
}
inline bool Parent(const ContextBinding& c,const ActorBinding& p) noexcept {
    Digest d{};return p.purpose==Purpose::combat&&Valid(c)&&HashBinding(p,d)&&d==c.parent_digest
        &&std::memcmp(c.target_key,p.actor_key,8)&&c.target_hint!=p.actor_hint;
}
template<class B> inline std::wstring Name(const B& b) {
    Digest d{};if(!HashBinding(b,d)){return {};}
    std::wstring name=std::is_same_v<B,ActorBinding>?L"Local\\WonderBane.ActorOwner.v4.":L"Local\\WonderBane.ActorContext.v4.";
    constexpr wchar_t digits[]=L"0123456789abcdef";
    for(auto byte:d){name+=digits[byte>>4];name+=digits[byte&15];}return name;
}
// Read only an existing immutable binding by its normalized digest. No creation,
// authority transition or waiting. Caller then validates command namespace and
// retains Ticket handles; this detached copy is not admission permission.
template<class B> inline bool ReadBinding(const Digest& digest,B& out) noexcept {
    out={};if(!Any(digest)){return false;}
    HANDLE mutex=nullptr,mapping=nullptr;const B* view=nullptr;bool held=false,ok=false;
    try {
        std::wstring name=std::is_same_v<B,ActorBinding>?L"Local\\WonderBane.ActorOwner.v4.":L"Local\\WonderBane.ActorContext.v4.";
        constexpr wchar_t digits[]=L"0123456789abcdef";
        for(auto byte:digest){name+=digits[byte>>4];name+=digits[byte&15];}
        mutex=OpenMutexW(SYNCHRONIZE|MUTEX_MODIFY_STATE,FALSE,(name+L".lock").c_str());
        if(mutex){
            const auto wait=WaitForSingleObject(mutex,0);held=wait==WAIT_OBJECT_0||wait==WAIT_ABANDONED;
            if(wait==WAIT_OBJECT_0){
                mapping=OpenFileMappingW(FILE_MAP_READ,FALSE,name.c_str());
                if(mapping){view=static_cast<const B*>(MapViewOfFile(mapping,FILE_MAP_READ,0,0,sizeof(B)));}
                if(view){B copy=*view;Digest observed{};
                    ok=HashBinding(copy,observed)&&observed==digest;
                    if constexpr(std::is_same_v<B,ActorBinding>){
                        ok=ok&&copy.client_pid==GetCurrentProcessId()
                            &&copy.client_creation==Creation(GetCurrentProcess());
                    }
                    if(ok){out=copy;}
                }
            }
        }
    }catch(...){ok=false;}
    if(view){UnmapViewOfFile(view);}if(mapping){CloseHandle(mapping);}
    if(held&&!ReleaseMutex(mutex)){ok=false;}if(mutex){CloseHandle(mutex);}
    if(!ok){out={};}return ok;
}
// Opens existing current-user producer objects only. Caller must retain and
// validate BOTH actor and child tickets before entry, and fresh native ownership.
template<class Binding> class Ticket final {
public:
    Ticket()=default;
    Ticket(const Ticket&)=delete;Ticket& operator=(const Ticket&)=delete;
    ~Ticket(){Close();}
    bool Open(const Binding& expected,const ActorBinding& identity) {
        Close();
        if(!Valid(expected)||!Valid(identity)||identity.client_pid!=GetCurrentProcessId()
            ||identity.client_creation!=Creation(GetCurrentProcess())){return false;}
        if constexpr(std::is_same_v<Binding,ActorBinding>){if(!Same(expected,identity)){return false;}}
        else{if(!Parent(expected,identity)){return false;}}
        expected_=expected;identity_=identity;const auto name=Name(expected);
        if(name.empty()){return false;}
        mutex_=OpenMutexW(SYNCHRONIZE|MUTEX_MODIFY_STATE,FALSE,(name+L".lock").c_str());
        if(!mutex_){Close();return false;}
        mapping_=OpenFileMappingW(FILE_MAP_READ|FILE_MAP_WRITE,FALSE,name.c_str());
        if(!mapping_){Close();return false;}
        view_=static_cast<Binding*>(MapViewOfFile(mapping_,FILE_MAP_READ|FILE_MAP_WRITE,0,0,sizeof(Binding)));
        producer_=OpenProcess(SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,identity.producer_pid);
        if(!view_||!producer_||Creation(producer_)!=identity.producer_creation){Close();return false;}
        return true;
    }
    Result TryAdmit(const Binding& current,bool retained) noexcept {
        if(!Valid(current)||!Same(current,expected_)){return Result::invalid;}
        return Transition(true,retained,nullptr);
    }
    Result Inspect(State& state) noexcept{return Transition(false,false,&state);}
    void Close() noexcept {
        if(view_){UnmapViewOfFile(view_);view_=nullptr;}
        for(auto* h:{&producer_,&mapping_,&mutex_}){if(*h){CloseHandle(*h);*h=nullptr;}}
    }
private:
    Result Transition(bool enter,bool retained,State* observed) noexcept {
        if(!view_||!mutex_||!producer_){return Result::unavailable;}
        const auto wait=WaitForSingleObject(mutex_,0);
        if(wait==WAIT_TIMEOUT){return Result::busy;}
        if(wait!=WAIT_OBJECT_0&&wait!=WAIT_ABANDONED){return Result::unavailable;}
        Result result=Result::invalid;
        if(Valid(*view_)&&Same(*view_,expected_)){
            if(wait==WAIT_ABANDONED||WaitForSingleObject(producer_,0)!=WAIT_TIMEOUT){view_->state=Revoked(view_->state);}
            if(observed){*observed=view_->state;}
            if(view_->state==State::revoked||view_->state==State::entered_revoked){result=Result::revoked;}
            else if(!enter){result=Result::not_pending;}
            else if(view_->state==State::entered&&retained){result=Result::admitted;}
            else if(view_->state!=State::pending){result=Result::not_pending;}
            else{view_->state=State::entered;result=Result::admitted;}
        }
        return ReleaseMutex(mutex_)?result:Result::unavailable;
    }
    Binding expected_{};ActorBinding identity_{};
    HANDLE mutex_=nullptr,mapping_=nullptr,producer_=nullptr;Binding* view_=nullptr;
};
}
