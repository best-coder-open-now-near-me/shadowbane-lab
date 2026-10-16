#include "vendor_recycle_native.cpp"
#include <iostream>
#include <iomanip>
#include <sstream>
#include <fstream>
#include <vector>
#undef NDEBUG
#include <cassert>
namespace r = wonderbane::extension::vendor_recycle;
namespace v = wonderbane::extension::vendor;
namespace m = wonderbane::extension::movement;
bool live=true, qualified=true, allowed=true;
constexpr const char* previous_prepared="6bd0e391edc1c773b4c96d8a9801db45f96db9e34202afcfc8d383d4971fe5ad";
constexpr const char* prepared22="346122811441e01437d572b32916aef29de78a088d5f328874d5c759097e8747";
constexpr const char* current_prepared="4bf1a24a268d0ed13227d766105f3595cdc264e930436ca08748a10b04293ffa";
const char* selected_prepared=current_prepared;
unsigned clones=0, selections=0, sends=0, fail_selection=0, fail_gate=0, gate_calls=0;
std::uint32_t base=0, manager=0, tree=0;
void Word(std::uint32_t at,std::uint32_t value){std::memcpy(reinterpret_cast<void*>(at),&value,4);}
std::uint32_t Get(std::uint32_t at){std::uint32_t value{};std::memcpy(&value,reinterpret_cast<void*>(at),4);return value;}
void* __fastcall Clone(void* self,void*,void** out) {
    ++clones;*out=reinterpret_cast<void*>(Get(reinterpret_cast<std::uint32_t>(self)+0x24));return out;
}
void __fastcall Add(void*,void*,const wonderbane::extension::vendor_production::Key* key,void* instance) {
    ++selections;
    if(selections==fail_selection){return;}
    const auto count=Get(manager+0x3dc), node=base+0x400000+count*32;
    Word(node+4,count?Get(tree+12):tree); Word(node+8,0); Word(node+12,0);
    Word(node+16,(*key)[0]); Word(node+20,(*key)[1]);Word(node+24,reinterpret_cast<std::uint32_t>(instance));
    if(count){Word(Get(tree+12)+12,node);}else{Word(tree+4,node);Word(tree+8,node);}
    Word(tree+12,node);Word(manager+0x3dc,count+1);
}
void __fastcall Send(void*,void*){++sends;}
bool Admit(void*) noexcept {return allowed && ++gate_calls!=fail_gate;}
void Jump(std::uint32_t at,void* target){auto* p=reinterpret_cast<unsigned char*>(at);p[0]=0xe9;Word(at+1,reinterpret_cast<std::uint32_t>(target)-at-5);}
namespace wonderbane::extension {
bool GraphicsExecutableSha256Matches(const char* sha) noexcept {
    assert(!std::strcmp(sha,previous_prepared)||!std::strcmp(sha,prepared22)||!std::strcmp(sha,current_prepared));
    return qualified&&!std::strcmp(sha,selected_prepared);
}
namespace movement {
bool NativeMovementLifetimeCurrent(const NativeScene& scene) noexcept {return live && scene.epoch==1;}
}
}
struct KeyArg {std::uint32_t id,type;};
std::uint32_t message=0, msg_table=0, ref_table=0;
unsigned message_clones=0,message_releases=0,reference_count=0;
std::array<KeyArg,r::kItems> sent_references{};
void* __cdecl Allocate(std::size_t size){assert(size==0x120);return reinterpret_cast<void*>(message);}
void* __fastcall Construct(void* self,void*) {
    assert(reinterpret_cast<std::uint32_t>(self)==message);
    std::memset(self,0,0x120);Word(message,msg_table);Word(message+8,ref_table);return self;
}
void __cdecl Wrap(void** out,unsigned zero,void* value){assert(!zero);*out=value;}
void* __fastcall Dereference(void** self,void*){return *self;}
void __fastcall Reference(void* self,void*,const KeyArg* key) {
    assert(reinterpret_cast<std::uint32_t>(self)==message && reference_count<r::kItems);
    sent_references[reference_count++]=*key;
}
void __fastcall Vendor(void* self,void*,KeyArg key){assert(reinterpret_cast<std::uint32_t>(self)==message);Word(message+0x80,key.id);Word(message+0x84,key.type);}
void __fastcall Building(void* self,void*,KeyArg key){assert(reinterpret_cast<std::uint32_t>(self)==message);Word(message+0x78,key.id);Word(message+0x7c,key.type);}
void __fastcall RefAdd(void* self,void*,void** value) {
    if(reinterpret_cast<std::uint32_t>(*value)==message){assert(self==*value);++message_clones;}
    else{assert(reinterpret_cast<std::uint32_t>(self)==reinterpret_cast<std::uint32_t>(*value)+8);++clones;}
}
void __fastcall MsgRelease(void* self,void*,void** value){assert(reinterpret_cast<std::uint32_t>(self)==message);*value=nullptr;++message_releases;}
void* __cdecl Network(){return reinterpret_cast<void*>(base+0x730000);}
void __fastcall NetworkSend(void* self,void*,void* value) {
    assert(self==Network() && reinterpret_cast<std::uint32_t>(value)==message);
    assert(Get(message+0x70)==3 && Get(message+0x78)==2229645 && Get(message+0x7c)==8);
    assert(Get(message+0x80)==2517204 && Get(message+0x84)==42);
    ++sends;MsgRelease(value,nullptr,&value);
}
void ClientFunctions(const char* filename) {
    std::ifstream stream(filename,std::ios::binary|std::ios::ate);assert(stream);
    const auto size=stream.tellg();assert(size>0 && size<128*1024*1024);
    std::vector<unsigned char> file(static_cast<std::size_t>(size));stream.seekg(0);
    stream.read(reinterpret_cast<char*>(file.data()),size);assert(stream);
    r::Hash hash;r::Digest digest{};assert(hash.Add(file.data(),file.size()) && hash.Finish(digest));
    std::ostringstream hex;for(auto byte:digest){hex<<std::hex<<std::setw(2)<<std::setfill('0')<<static_cast<unsigned>(byte);}
    assert(hex.str()==previous_prepared||hex.str()==prepared22||hex.str()==current_prepared);
    const auto* dos=reinterpret_cast<const IMAGE_DOS_HEADER*>(file.data());assert(dos->e_magic==IMAGE_DOS_SIGNATURE);
    assert(dos->e_lfanew>0 && static_cast<std::size_t>(dos->e_lfanew)+sizeof(IMAGE_NT_HEADERS32)<file.size());
    const auto* pe=reinterpret_cast<const IMAGE_NT_HEADERS32*>(file.data()+dos->e_lfanew);
    assert(pe->Signature==IMAGE_NT_SIGNATURE && pe->FileHeader.Machine==IMAGE_FILE_MACHINE_I386);
    const auto* sections=IMAGE_FIRST_SECTION(pe);
    auto copy=[&](std::uint32_t address,std::uint32_t bytes) {
        bool copied=false;
        for(unsigned i=0;i<pe->FileHeader.NumberOfSections;++i){const auto& section=sections[i];
            if(address<section.VirtualAddress || address+bytes>section.VirtualAddress+section.SizeOfRawData){continue;}
            const auto offset=section.PointerToRawData+address-section.VirtualAddress;assert(offset+bytes<=file.size());
            std::memcpy(reinterpret_cast<void*>(base+address),file.data()+offset,bytes);copied=true;break;}
        assert(copied);
    };
    // Execute the actual client's getter, key copy/getter, tree successor and
    // batch builder. Heap/refcount/network endpoints are instrumented: no game,
    // process attachment or network send is involved.
    for(const auto [address,bytes]:std::array<std::pair<std::uint32_t,std::uint32_t>,9>{{
        {0x26b70,5},{0x5bd150,0x36},{0x195b,5},{0x567f90,0x23},
        {0x25581,5},{0x1117b0,0x16},{0x12cc9,5},{0x3fae0,0x3a},{0x6e4180,0x148}}}){copy(address,bytes);}
    message=base+0x700000;msg_table=base+0x710000;ref_table=base+0x720000;
    Word(msg_table+8,reinterpret_cast<std::uint32_t>(&MsgRelease));Word(ref_table+4,0);
    Jump(base+0x8d88e6,reinterpret_cast<void*>(&Allocate));Jump(base+0x2569e,reinterpret_cast<void*>(&Construct));
    Jump(base+0x27e12,reinterpret_cast<void*>(&Wrap));Jump(base+0x23e8e,reinterpret_cast<void*>(&Reference));
    Jump(base+0x3f08,reinterpret_cast<void*>(&Dereference));Jump(base+0x387d,reinterpret_cast<void*>(&Vendor));
    Jump(base+0x21a8f,reinterpret_cast<void*>(&Building));Jump(base+0xb2b7,reinterpret_cast<void*>(&RefAdd));
    Jump(base+0x7dab,reinterpret_cast<void*>(&Network));Jump(base+0x5a65,reinterpret_cast<void*>(&NetworkSend));
}
LONG WINAPI ProbeException(EXCEPTION_POINTERS* info) {
    if(info->ExceptionRecord->ExceptionCode==EXCEPTION_ACCESS_VIOLATION) {
        std::cerr<<"client probe access violation rva="<<std::hex<<info->ContextRecord->Eip-base
            <<" eip="<<info->ContextRecord->Eip<<" app="<<GetModuleHandleW(nullptr)
            <<" at="<<info->ExceptionRecord->ExceptionInformation[1]
            <<" ecx="<<info->ContextRecord->Ecx<<" eax="<<info->ContextRecord->Eax<<'\n';
        ExitProcess(86);
    }
    return EXCEPTION_CONTINUE_SEARCH;
}
int main(int argc,char** argv) {
    std::cout<<std::unitbuf;
    auto* arena=static_cast<unsigned char*>(VirtualAlloc(nullptr,0x1800000,MEM_RESERVE|MEM_COMMIT,PAGE_EXECUTE_READWRITE));
    assert(arena);base=reinterpret_cast<std::uint32_t>(arena);manager=base+0x2000;
    const auto root=base+0x1000, menu=base+0x3000, hireling=base+0x4000;
    const auto inv=base+0x5000, list=base+0x6000, control=base+0x100000, entry=base+0x101000;
    const auto head=base+0x9000, node=base+0xa000, inv_node=base+0xb000;
    const auto controls=base+0xc000, children=base+0xd000, prod_list=base+0xe000;
    const auto prod_control=base+0xf000, prod_entry=base+0x10000, prod_controls=base+0x11000;
    tree=base+0x12000;
    Word(base+0x16a7bfc,root);Word(root,base+0x1174884);Word(root+0x64,2);Word(root+0xa4,manager);
    Word(manager,base+0x1171adc);Word(manager+0x78,menu);Word(manager+0x7c,inv);
    Word(manager+0x48,1);Word(manager+0x58,1);Word(manager+0x1cc,205328);
    Word(manager+0xf0,2229645);Word(manager+0xf4,8);Word(manager+0xf8,2229645);Word(manager+0xfc,8);
    Word(manager+0x384,hireling);Word(hireling,base+0x1169518);Word(hireling+0x10,2517204);Word(hireling+0x14,42);
    Word(menu,base+0x116a058);Word(menu+0x104,manager);
    Word(menu+0x54,children);Word(menu+0x58,children+4);Word(menu+0x5c,children+4);Word(children,prod_list);
    Word(prod_list,base+0x116acf0);Word(prod_list+0x3bc,menu);
    Word(prod_list+0x408,prod_controls);Word(prod_list+0x40c,prod_controls+4);Word(prod_list+0x410,prod_controls+4);
    Word(prod_controls,prod_control);Word(prod_control,base+0x116aebc);Word(prod_control+0x3bc,menu);
    Word(prod_control+0x458,prod_list);Word(prod_control+0x44c,prod_entry);Word(prod_entry,base+0x1169560);
    Word(root+0x20,head);Word(head,node);Word(head+4,inv_node);
    Word(node,inv_node);Word(node+4,head);Word(node+8,menu);
    Word(inv_node,head);Word(inv_node+4,node);Word(inv_node+8,inv);
    Word(inv,base+0x116c64c);Word(inv+0x104,manager);Word(inv+0x3f4,manager);Word(inv+0x3f0,list);
    Word(inv+0x54,children+4);Word(inv+0x58,children+8);Word(inv+0x5c,children+8);Word(children+4,list);
    Word(list,base+0x116acf0);Word(list+0x3bc,inv);
    constexpr unsigned count=7;
    Word(list+0x408,controls);Word(list+0x40c,controls+count*4);Word(list+0x410,controls+count*4);
    r::Items ids{};
    for(unsigned i=0;i<count;++i) {
        const auto c=control+i*0x20000,e=entry+i*0x20000,instance=e+0x1000,native=e+0x2000;
        const auto effect=e+0x3000,effects=e+0x4000,name=e+0x5000;
        const auto id=4294904956U+i; ids[i]=id;
        Word(controls+i*4,c);Word(c,base+0x116aebc);Word(c+0x3bc,inv);Word(c+0x458,list);Word(c+0x44c,e);
        Word(e,base+0x11696c8);Word(e+0x10,id);Word(e+0x14,40);Word(e+0x20,instance);Word(e+0x24,native);
        Word(instance,base+0x114bb68);Word(instance+8,0x101);Word(instance+0x10,26990);Word(instance+0x18,id);Word(instance+0x1c,40);
        Word(instance+0x60,0x41f00000);Word(instance+0x64,0x41f00000);Word(instance+0x70,151);Word(instance+0x74,5201);
        Word(instance+0xb4,effects);Word(instance+0xb8,effects+4);Word(instance+0xbc,effects+4);Word(effects,effect);
        Word(effect,123);Word(effect+8,1);
        Word(native,base+0x1142748);Word(native+0x10,26990);Word(native+0x18,id);Word(native+0x1c,40);
        constexpr wchar_t label[]=L"Gilded Scepter of Frost";std::memcpy(reinterpret_cast<void*>(name),label,sizeof(label));
        Word(native+0xdc,name);Word(native+0xe0,name+sizeof(label)-2);Word(native+0xe4,name+sizeof(label));
    }
    auto clear=[&](){Word(manager+0x3d8,tree);Word(manager+0x3dc,0);Word(tree+4,0);Word(tree+8,tree);Word(tree+12,tree);
        clones=selections=sends=gate_calls=fail_gate=fail_selection=0;allowed=live=qualified=true;};
    clear();
    m::NativeScene scene{};scene.epoch=1;scene.window=root;
    v::wire::Snapshot owner{};bool present=false,top=false;
    assert(v::Capture(base,scene,owner,0,present,top) && top);owner.revision=1;
    r::Manifest manifest{};assert(r::Capture(base,scene,owner,ids,count,manifest));
    assert(manifest.count==7 && manifest.gold==205328 && manifest.refund==1057);
    r::Manifest prior_identity{};
    for(const auto* digest:{previous_prepared,prepared22,current_prepared}) {
        selected_prepared=digest;
        assert(r::Capture(base,scene,owner,ids,count,prior_identity)&&prior_identity.digest==manifest.digest);
    }
    selected_prepared="unreviewed";
    assert(!r::Capture(base,scene,owner,ids,count,prior_identity));
    selected_prepared=current_prepared;
    std::ostringstream digest;for(const auto b:manifest.digest){digest<<std::hex<<std::setw(2)<<std::setfill('0')<<static_cast<unsigned>(b);}
    std::cout<<"base="<<base<<" digest="<<digest.str()<<'\n';
    auto rejects=[&](std::uint32_t at,std::uint32_t value){const auto old=Get(at);Word(at,value);r::Manifest out{};
        assert(!r::Capture(base,scene,owner,ids,count,out));Word(at,old);};
    rejects(entry+0x14,0);rejects(entry+0x20,0);rejects(entry+0x1000+0x10,1);
    rejects(entry+0x2000+0x18,1);rejects(entry+0x1000+8,0x100);rejects(entry+0x1000+0x70,0);
    rejects(entry+0x3000+4,1);rejects(entry+0x3000+8,2);rejects(entry+0x1000+0xb8,entry+0x4000+65*4);
    rejects(control+0x458,menu);rejects(manager+0x1cc,INT32_MAX);rejects(manager+0x3dc,1);
    rejects(tree+8,0);rejects(prod_entry+0x10,1);rejects(manager+0xf8,1);
    r::Manifest changed{};Word(entry+0x3000,124);assert(r::Capture(base,scene,owner,ids,count,changed));
    assert(changed.digest!=manifest.digest);Word(entry+0x3000,123);
    qualified=false;assert(!r::Capture(base,scene,owner,ids,count,changed));qualified=true;
    live=false;assert(!r::Capture(base,scene,owner,ids,count,changed));live=true;
    auto bad=ids;bad[1]=bad[0];assert(!r::Capture(base,scene,owner,bad,count,changed));
    bad=ids;bad[count]=1;assert(!r::Capture(base,scene,owner,bad,count,changed));
    assert(!r::Capture(base,scene,owner,ids,0,changed));assert(!r::Capture(base,scene,owner,ids,49,changed));
    Jump(base+0x26b70,reinterpret_cast<void*>(&Clone));Jump(base+0x6c9a30,reinterpret_cast<void*>(&Add));Jump(base+0x6e4180,reinterpret_cast<void*>(&Send));
    assert(r::Invoke(base,scene,manifest,&Admit,nullptr)==v::wire::Outcome::submitted && sends==1 && clones==7 && selections==7);
    // An existing manual selection never enters the sender or silently gets cleared.
    assert(r::Invoke(base,scene,manifest,&Admit,nullptr)==v::wire::Outcome::stale && sends==1);
    clear();fail_selection=3;assert(r::Invoke(base,scene,manifest,&Admit,nullptr)==v::wire::Outcome::uncertain && sends==0);
    clear();fail_gate=4;assert(r::Invoke(base,scene,manifest,&Admit,nullptr)==v::wire::Outcome::uncertain && sends==0);
    clear();allowed=false;assert(r::Invoke(base,scene,manifest,&Admit,nullptr)==v::wire::Outcome::stale && sends==0);
    clear();auto stale=manifest;stale.digest[0]^=1;assert(r::Invoke(base,scene,stale,&Admit,nullptr)==v::wire::Outcome::stale && sends==0);
    clear();assert(r::Invoke(base,scene,manifest,&Admit,nullptr)==v::wire::Outcome::submitted);
    r::Reader reader;r::SelectionTree walk{reader,manifest,tree,count};assert(walk.Walk(Get(tree+4),tree,0));
    // Extra, cyclic, or nonreciprocal tree links cannot reach a batch send.
    Word(Get(tree+12)+12,base+0x410000);r::Reader extra;assert(!r::Selection(extra,manifest,count));
    Word(Get(tree+12)+12,0);Word(Get(tree+4)+4,0);r::Reader parent;assert(!r::Selection(parent,manifest,count));
    if(argc==2) {
        assert(AddVectoredExceptionHandler(1,&ProbeException));
        ClientFunctions(argv[1]);clear();
        for(unsigned i=0;i<count;++i){Word(manifest.native_items[i]+8,ref_table);}
        assert(r::Invoke(base,scene,manifest,&Admit,nullptr)==v::wire::Outcome::submitted);
        assert(sends==1 && clones==count && reference_count==count && message_clones==1 && message_releases==2);
        for(unsigned i=0;i<count;++i){assert(sent_references[i].id==ids[i] && sent_references[i].type==40);}
        std::cout<<"actual .19 getter/key/iterator/batch-builder passed; network endpoint instrumented\n";
    }
    assert(VirtualFree(arena,0,MEM_RELEASE));return 0;
}
