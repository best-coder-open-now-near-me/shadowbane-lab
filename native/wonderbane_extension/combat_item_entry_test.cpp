#include "combat_item_entry.cpp"
#include <cstdio>
#include <cstdlib>
#include <stdexcept>
#include <vector>
namespace it=wonderbane::extension::combat::item;
namespace sb=wonderbane::extension::combat::submission;
namespace {
unsigned failures{},lookups{},releases{},uses{},sends{},appends{},message_releases{};
unsigned item_refs{},message_refs{};
bool current=true,queue_current=true,missing=false,wrong_output=false;
bool fault_lookup=false,throw_lookup=false,fault_release=false,fault_use=false,throw_use=false;
bool missing_after_lookup=false,revoke_use=false,wrong_ticket=false,fault_after_send=false;
bool nested=false,unrelated=false;
const char* digest="";std::uintptr_t verified{};
sb::AppendObserver registered{};
std::array<std::uint32_t,0xf00/4> actor{};
std::array<std::uint32_t,0x800/4> object{};
std::array<std::uint32_t,0x200/4> definition{};
std::array<std::uint32_t,0x88/4> message{},other_message{};
void* current_message=message.data();
void* lookup_result=object.data();
void* sender{};void* queue{};
it::Use native_use{};
it::Context context{};
void Check(bool ok,const char* label) { if(!ok){++failures;std::fprintf(stderr,"%s\n",label);} }
bool Current(void*) noexcept { return current; }
bool QueueCurrent(void*) noexcept { return queue_current; }
void* __fastcall Lookup(void* self,void*,void** out,const it::Key* key) {
    ++lookups;
    Check(self==reinterpret_cast<void*>(context.actor+0xea4) && *key==context.item_key,"exact inventory interface and key");
    Check(!*out,"native lookup receives empty persistent output");
    if(!missing){*out=lookup_result;++item_refs;}
    if(missing_after_lookup && lookups==1){missing=true;}
    if(fault_lookup){RaiseException(0xe0420301,0,0,nullptr);}
    if(throw_lookup){throw std::runtime_error("lookup");}
    return wrong_output ? reinterpret_cast<void*>(1) : out;
}
void __fastcall Release(void** out,void*,void* replacement) {
    Check(replacement==nullptr && *out==lookup_result,"owned release exact slot");
    ++releases;
    if(fault_release){RaiseException(0xe0420301,0,0,nullptr);}
    *out=nullptr;--item_refs;
}
void __fastcall MessageRelease(void*,void*,void** empty) {
    Check(!*empty && message_refs>0,"message transferred ownership release");++message_releases;--message_refs;
}
void __fastcall Send(void* self,void*,void* value) {
    Check(self==sender,"ordinary sender this pointer");++sends;
    const auto claim=registered.claim(queue,value,0x2c6eb7);
    if(unrelated){Check(claim.decision==sb::AppendDecision::unrelated,"foreign frame never claims scope");}
    else {Check(claim.decision!=sb::AppendDecision::unrelated,"owned item ticket claimed");}
    if(claim.decision==sb::AppendDecision::allow){++appends;registered.complete(claim.owner,sb::AppendResult::queued);}
    else if(claim.decision==sb::AppendDecision::deny){registered.complete(claim.owner,sb::AppendResult::denied);}
    it::Consume(value);
    SetLastError(1234);
}
void __cdecl BeforeUse(void* value,void* actor_value,unsigned flag) {
    ++uses;
    Check(value==object.data()&&actor_value==actor.data()&&flag==0,"ordinary thiscall use(item, actor, false)");
    if(!unrelated){Check(it::active && it::active->receipt.native_entered,"entry history precedes native use");}
    if(fault_use){RaiseException(0xe0420301,0,0,nullptr);}
    if(throw_use){throw std::runtime_error("use");}
    if(nested){
        nested=false;unrelated=true;current_message=other_message.data();
        native_use(object.data(),actor.data(),false);
        current_message=message.data();unrelated=false;
    }
    if(revoke_use){current=false;}
    if(wrong_ticket){message[0x78/4]++;}
    message_refs+=2; // Native caller local and separately retained sender argument.
}
void __cdecl AfterUse() {
    Check(message_refs>0,"caller still owns message after queue");--message_refs;
    if(fault_after_send){RaiseException(0xe0420301,0,0,nullptr);}
}
void Put(std::uintptr_t at,std::uintptr_t value){*reinterpret_cast<std::uintptr_t*>(at)=value;}
void Emit(unsigned char* at,const std::vector<unsigned char>& bytes){std::memcpy(at,bytes.data(),bytes.size());}
void U32(std::vector<unsigned char>& code,std::uintptr_t value){for(unsigned i=0;i<4;++i){code.push_back(static_cast<unsigned char>(value>>(i*8)));}}
void CallAbsolute(std::vector<unsigned char>& code,std::uintptr_t function){code.push_back(0xb8);U32(code,function);code.insert(code.end(),{0xff,0xd0});}
void Synthetic(unsigned char* image){
    std::vector<unsigned char> code{0x55,0x8b,0xec,0x56,0x8b,0xf1,0xff,0x75,0x0c,0xff,0x75,0x08,0x56};
    CallAbsolute(code,reinterpret_cast<std::uintptr_t>(&BeforeUse));code.insert(code.end(),{0x83,0xc4,0x0c,0xff,0x35});
    U32(code,reinterpret_cast<std::uintptr_t>(&current_message));code.push_back(0xb9);U32(code,reinterpret_cast<std::uintptr_t>(sender));
    const auto next=reinterpret_cast<std::uintptr_t>(image+0xae810)+code.size()+5;
    code.push_back(0xe9);U32(code,reinterpret_cast<std::uintptr_t>(image+0xaea65)-next);
    Emit(image+0xae810,code);std::memcpy(image+0xaea65,it::site.bytes.data(),5);
    code.clear();CallAbsolute(code,reinterpret_cast<std::uintptr_t>(&AfterUse));code.insert(code.end(),{0x5e,0x8b,0xe5,0x5d,0xc2,0x08,0x00});
    Emit(image+0xaea6a,code);
}
void Reset(){
    current=queue_current=true;missing=wrong_output=fault_lookup=throw_lookup=fault_release=fault_use=throw_use=false;
    missing_after_lookup=revoke_use=wrong_ticket=fault_after_send=nested=unrelated=false;
    lookups=releases=uses=sends=appends=message_releases=item_refs=message_refs=0;
    object[0x18/4]=context.item_key[0];object[0x1c/4]=context.item_key[1];
    definition[0xf4/4]=context.template_type;definition[0x11c/4]=context.template_flags;
    message[0x78/4]=context.item_key[0];message[0x7c/4]=context.item_key[1];
    other_message=message;current_message=message.data();lookup_result=object.data();SetLastError(77);
}
it::Receipt Run(it::State& state,it::Receipt& receipt){
    return it::InvokeBound(context,state,receipt,{reinterpret_cast<it::Lookup>(&Lookup),
        reinterpret_cast<it::Release>(&Release),native_use});
}
it::Receipt Run(){it::State state;it::Receipt receipt;return Run(state,receipt);}
}
namespace wonderbane::extension {
bool GraphicsExecutableSha256Matches(const char* expected) noexcept{return std::strcmp(expected,digest)==0;}
namespace movement {bool VerifyNativeMovementImage(std::uintptr_t& out) noexcept{out=verified;return out!=0;}}
namespace combat::submission {
bool RegisterAppendObserver(AppendObserverKind kind,const AppendObserver& observer) noexcept{
    Check(kind==AppendObserverKind::item,"item fixed observer slot");registered=observer;return true;
}
}
}
int main(int argc,char** argv){
    (void)argc;(void)argv;
    auto* image=static_cast<unsigned char*>(VirtualAlloc(nullptr,0x16ac000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    if(!image){return 2;}
    const auto base=reinterpret_cast<std::uintptr_t>(image);
    sender=image+0x16ab888;queue=image+0x1600000;
    context={base,reinterpret_cast<std::uintptr_t>(actor.data()),base+0x1600100,
        reinterpret_cast<std::uintptr_t>(queue),reinterpret_cast<std::uintptr_t>(object.data()),
        reinterpret_cast<std::uintptr_t>(definition.data()),{4050960,53},{5802955,30},{980066,0},8,10,Current,QueueCurrent,nullptr};
    Put(base+0x16a2d98,context.actor);Put(base+0x16ab88c,context.writer);
    Put(context.writer,base+0x116036c);Put(context.writer+0x44,context.container);Put(context.container,base+0x114ce9c);
    actor[0]=static_cast<std::uint32_t>(base+0x114165c);actor[2]=static_cast<std::uint32_t>(base+0x11417d4);
    actor[0x18/4]=4050960;actor[0x1c/4]=53;actor[0xea4/4]=static_cast<std::uint32_t>(base+0x1141570);
    object[0]=static_cast<std::uint32_t>(base+0x1142748);object[0x10/4]=980066;
    object[0x68c/4]=reinterpret_cast<std::uint32_t>(definition.data());definition[0]=static_cast<std::uint32_t>(base+0x11428f0);
    message[0]=static_cast<std::uint32_t>(base+0x1155680);message[0x70/4]=2;message[0x74/4]=1;
    Put(base+0x1155688,reinterpret_cast<std::uintptr_t>(&MessageRelease));
    Synthetic(image);native_use=reinterpret_cast<it::Use>(image+0xae810);
    DWORD prior{};Check(VirtualProtect(image,0x16ac000,PAGE_EXECUTE_READWRITE,&prior)!=FALSE,"fixture executable arena");
    FlushInstructionCache(GetCurrentProcess(),image,0x16ac000);
    Check(!it::Start(base),"unknown image never installs");
    Check(it::StartBound(base,reinterpret_cast<it::Send>(&Send)),"exact synthetic callsite install");
    Reset();auto receipt=Run();
    Check(receipt.result==it::Result::queued&&receipt.native_entered&&receipt.append_observed&&!receipt.ownership_quarantined,"owned simple item queues");
    Check(lookups==3&&item_refs==0&&message_refs==0&&releases==3&&uses==1&&appends==1,"lookup and transferred refs balanced");
    Check(it::active==nullptr,"normal TLS restore");
    context.item_key[1]=40;Reset();receipt=Run();Check(receipt.append_observed,"UUID40 exact ArcItem also admitted");context.item_key[1]=30;
    for(auto type:{6U,10U,11U,26U,33U}){Reset();context.template_type=type;receipt=Run();Check(!receipt.native_entered&&uses==0,"special item route denied");context.template_type=8;}
    Reset();missing=true;receipt=Run();Check(!receipt.native_entered&&item_refs==0,"missing item no entry");
    Reset();missing_after_lookup=true;receipt=Run();Check(!receipt.native_entered&&uses==0&&item_refs==0,"removed held item cannot enter");
    Reset();object[0x18/4]++;receipt=Run();Check(!receipt.native_entered&&item_refs==0,"wrong item key releases known ref");
    Reset();auto replacement=object;lookup_result=replacement.data();receipt=Run();
    Check(!receipt.native_entered&&item_refs==0&&uses==0,"same-key replacement address denied");
    Reset();auto replaced_definition=definition;object[0x68c/4]=reinterpret_cast<std::uint32_t>(replaced_definition.data());receipt=Run();
    Check(!receipt.native_entered&&item_refs==0,"same template identity at replacement address denied");
    object[0x68c/4]=reinterpret_cast<std::uint32_t>(definition.data());
    Reset();definition[0xf4/4]=10;receipt=Run();Check(!receipt.native_entered&&item_refs==0,"changed template denied");
    Reset();current=false;receipt=Run();Check(!receipt.native_entered&&lookups==0,"revoked owner never resolves");
    Reset();queue_current=false;receipt=Run();Check(!receipt.native_entered&&uses==0,"pre-entry scalar admission revoked");
    Reset();revoke_use=true;receipt=Run();Check(receipt.native_entered&&!receipt.append_observed&&sends==0&&message_refs==0,"entry revocation consumes only sender ref");
    Reset();wrong_ticket=true;receipt=Run();Check(receipt.native_entered&&!receipt.append_observed&&sends==0&&message_refs==0,"malformed message denied");
    Reset();nested=true;receipt=Run();Check(receipt.append_observed&&uses==2&&sends==2&&appends==1&&message_refs==0,"foreign reentrant call cannot borrow scope");
    Reset();fault_after_send=true;receipt=Run();Check(receipt.append_observed&&receipt.ownership_quarantined&&receipt.result==it::Result::uncertain,"SEH preserves queued history and quarantines");Check(!it::active,"fault TLS restore");
    for(unsigned mode=0;mode<5;++mode){
        Reset();fault_lookup=mode==0;throw_lookup=mode==1;wrong_output=mode==2;fault_release=mode==3;fault_use=mode==4;
        it::State state;it::Receipt saved;receipt=Run(state,saved);const auto calls=lookups;
        Check(state.quarantined&&receipt.ownership_quarantined&&!receipt.append_observed,"uncertain owned reference quarantined");
        (void)Run(state,saved);Check(lookups==calls,"quarantined action never retries");Check(!it::active,"all faults restore TLS");
    }
    Reset();throw_use=true;receipt=Run();Check(receipt.ownership_quarantined&&!it::active,"C++ use failure restores TLS");
    Reset();it::State state;it::Receipt saved;(void)Run(state,saved);const auto count=uses;(void)Run(state,saved);Check(uses==count,"same action storage invokes once");
    std::array<std::uint8_t,5> code=it::site.bytes;const auto disk=code;code[0]=0xcc;
    Check(it::NormalizeOwnedCode(base,it::site.rva,code,disk)&&code==disk,"normalize exact owned trap");
    code[0]=0xcc;code[1]^=1;Check(!it::NormalizeOwnedCode(base,it::site.rva,code,disk),"foreign patch cannot normalize");
    std::printf("item entry checks: %s\n",failures?"FAILED":"PASS");return failures?1:0;
}
