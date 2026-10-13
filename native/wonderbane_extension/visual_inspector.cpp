#include "visual_inspector.h"
#include <Windows.h>
#include <strsafe.h>
#include <cstring>
#include <cstddef>
namespace wonderbane::extension::visual {
namespace {
bool Word(effects::Reader reader,void* context,std::uint32_t at,std::uint32_t& out) {
    return at>=0x10000 && at<=0x7FFEFFFF-4 && reader(context,at,&out,4);
}
bool Tree(effects::Reader reader,void* context,std::uint32_t base,std::uint32_t actor,Snapshot& s) {
    if(!Word(reader,context,actor+0xc0,s.nodes[0].address) || !s.nodes[0].address)return false;
    s.count=1;s.nodes[0].parent=0xFFFFFFFFU;
    for(unsigned n=0;n<s.count;++n){
        auto& node=s.nodes[n];std::uint32_t table=0,begin=0,end=0;
        if(node.address<0x10000 || node.address>0x7FFEEFFF
            || !Word(reader,context,node.address,table) || table!=base+0x1149dbc
            || !Word(reader,context,node.address+0x10,node.resource)
            || !Word(reader,context,node.address+0x3c,begin)
            || !Word(reader,context,node.address+0x40,end)
            || end<begin || (end-begin)%4 || end-begin>kNodes*4)return false;
        for(auto p=begin;p<end;p+=4){
            std::uint32_t child=0;if(!Word(reader,context,p,child) || !child)return false;
            for(unsigned k=0;k<s.count;++k)if(s.nodes[k].address==child)return false;
            if(s.count==kNodes)return false;
            s.nodes[s.count++]={child,n,0,0};
        }
    }
    return true;
}
#pragma pack(push,4)
struct Channel {
    std::uint32_t magic=0x49564257,version=1,size=2112,pid=0;
    std::uint64_t creation=0;
    volatile LONG request=0;std::uint32_t selection=1;
    volatile LONG publication=0,applied=0;
    std::uint32_t status=1,type=0,uuid=0,count=0;
    std::uint64_t tick=0;
    std::array<Node,kNodes> nodes{};
};
#pragma pack(pop)
static_assert(sizeof(Channel)==2112 && offsetof(Channel,nodes)==64);
SRWLOCK publish_lock=SRWLOCK_INIT;
HANDLE mapping=nullptr;Channel* channel=nullptr;std::uint32_t base=0;std::uint64_t creation=0;
bool Read(void*,std::uint32_t at,void* out,std::size_t bytes) {
    if(at<0x10000 || at>0x7FFEFFFF || bytes>0x7FFEFFFF-at)return false;
    SIZE_T copied=0;
    return ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(at),out,bytes,&copied) && copied==bytes;
}
}
Snapshot Capture(effects::Reader reader,void* context,std::uint32_t image,std::uint32_t selection) noexcept {
    Snapshot s{};if(!reader || selection>1 || image<0x10000 || image>0x70000000)return s;
    const auto owner=effects::Resolve(reader,context,image,selection);
    if(!owner.valid)return s;
    if(!Tree(reader,context,image,owner.actor,s)){s={};s.status=2;return s;}
    Snapshot second{};
    if(!Tree(reader,context,image,owner.actor,second) || s.count!=second.count
        || std::memcmp(s.nodes.data(),second.nodes.data(),s.count*sizeof(Node))
        || !effects::SameIdentity(owner,effects::Resolve(reader,context,image,selection))){
        s={};s.status=3;return s;
    }
    s.status=0;s.type=owner.type;s.uuid=owner.uuid;return s;
}
void Start(std::uint32_t image) noexcept {
    if(mapping)return;
    FILETIME made{},exit{},kernel{},user{};
    if(!GetProcessTimes(GetCurrentProcess(),&made,&exit,&kernel,&user))return;
    creation=(static_cast<std::uint64_t>(made.dwHighDateTime)<<32)|made.dwLowDateTime;
    wchar_t name[128]{};StringCchPrintfW(name,128,L"Local\\WonderBaneVisuals-%lu-%llu",GetCurrentProcessId(),creation);
    mapping=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,sizeof(Channel),name);
    const auto error=GetLastError();
    if(!mapping || error==ERROR_ALREADY_EXISTS){if(mapping)CloseHandle(mapping);mapping=nullptr;return;}
    channel=static_cast<Channel*>(MapViewOfFile(mapping,FILE_MAP_ALL_ACCESS,0,0,sizeof(Channel)));
    if(!channel){CloseHandle(mapping);mapping=nullptr;return;}
    Channel initial{};initial.pid=GetCurrentProcessId();initial.creation=creation;
    std::memcpy(channel,&initial,sizeof(initial));base=image;
}
void Stop() noexcept {
    if(channel)UnmapViewOfFile(channel);if(mapping)CloseHandle(mapping);
    channel=nullptr;mapping=nullptr;base=0;
}
void Poll(bool available) noexcept {
    if(!TryAcquireSRWLockExclusive(&publish_lock))return;
    struct Unlock { ~Unlock(){ReleaseSRWLockExclusive(&publish_lock);} } unlock;
    if(!channel)return;
    const auto request=InterlockedCompareExchange(&channel->request,0,0);
    if(!request || request&1 || request==InterlockedCompareExchange(&channel->applied,0,0))return;
    const auto selection=channel->selection;MemoryBarrier();
    if(request!=InterlockedCompareExchange(&channel->request,0,0))return;
    Snapshot s{};
    if(channel->magic!=0x49564257 || channel->version!=1 || channel->size!=sizeof(Channel)
        || channel->pid!=GetCurrentProcessId() || channel->creation!=creation || selection>1)s.status=4;
    else if(available)s=Capture(Read,nullptr,base,selection);
    InterlockedIncrement(&channel->publication);
    channel->status=s.status;channel->type=s.type;channel->uuid=s.uuid;channel->count=s.count;
    channel->tick=GetTickCount64();std::memcpy(channel->nodes.data(),s.nodes.data(),sizeof(s.nodes));
    InterlockedExchange(&channel->applied,request);
    InterlockedIncrement(&channel->publication);
}
}
