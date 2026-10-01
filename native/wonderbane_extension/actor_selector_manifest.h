#pragma once
#include "actor_action_fence.h"
#include <algorithm>
namespace wonderbane::extension::actor::selectors {
using Digest=fence::Digest;
#pragma pack(push,1)
struct Record {
    std::uint32_t index{},group{},kind{},power{},template_id{},template_zero{},coverage_power{},coverage_kind{};
};
struct Manifest {
    char magic[8]{'W','B','A','B','U','F','1',0};
    std::uint32_t version=1,size=1152,count{},groups{},client_pid{},producer_pid{};
    std::uint64_t client_creation{},producer_creation{},producer_generation{};
    Digest local_name{},server{};std::uint8_t reserved[8]{};
    std::array<Record,32> records{};
};
#pragma pack(pop)
static_assert(sizeof(Record)==32&&sizeof(Manifest)==1152&&offsetof(Manifest,records)==128);
inline bool Valid(const Record& r) noexcept {
    return r.index<32&&r.group<32&&!r.template_zero&&r.coverage_power&&r.coverage_kind<=1
        &&((r.kind==3&&r.power&&!r.template_id&&r.coverage_power==r.power)
            ||(r.kind==4&&!r.power&&r.template_id&&!r.coverage_kind));
}
inline bool Valid(const Manifest& m) noexcept {
    if(std::memcmp(m.magic,"WBABUF1",8)||m.version!=1||m.size!=1152||!m.count||m.count>32
        ||!m.groups||m.groups>32||!m.client_pid||!m.producer_pid||!m.client_creation
        ||!m.producer_creation||!m.producer_generation||!fence::Any(m.local_name)
        ||!fence::Any(m.server)||fence::Any(m.reserved)){return false;}
    std::array<bool,32> groups{};
    for(std::uint32_t i=0;i<32;++i){
        const auto& r=m.records[i];
        if(i>=m.count){const Record zero{};if(std::memcmp(&r,&zero,sizeof(r))){return false;}continue;}
        if(!Valid(r)||r.index!=i||r.group>=m.groups){return false;}groups[r.group]=true;
        for(std::uint32_t j=0;j<i;++j){
            if(!std::memcmp(&r.kind,&m.records[j].kind,24)){return false;}
        }
    }
    for(std::uint32_t i=0;i<m.groups;++i){if(!groups[i]){return false;}}return true;
}
inline bool Hash(const Manifest& m,Digest& out) noexcept{return Valid(m)&&fence::Hash(&m,sizeof(m),out);}
inline std::wstring Name(const Digest& digest){
    if(!fence::Any(digest)){return {};}
    std::wstring value=L"Local\\WonderBane.ActorSelectors.v1.";
    constexpr wchar_t digits[]=L"0123456789abcdef";
    for(auto byte:digest){value+=digits[byte>>4];value+=digits[byte&15];}return value;
}
inline bool Copy(const void* source,Manifest& out) noexcept {
    __try{std::memcpy(&out,source,sizeof(out));return true;}
    __except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
inline bool Read(const Digest& expected,Manifest& out) noexcept {
    try{
        const auto name=Name(expected);if(name.empty()){return false;}
        const HANDLE mapping=OpenFileMappingW(FILE_MAP_READ,FALSE,name.c_str());
        if(!mapping){return false;}
        const void* view=MapViewOfFile(mapping,FILE_MAP_READ,0,0,sizeof(Manifest));
        Manifest first{},second{};Digest hash{};
        const bool ok=view&&Copy(view,first)&&Hash(first,hash)&&hash==expected
            &&Copy(view,second)&&!std::memcmp(&first,&second,sizeof(first));
        if(view){UnmapViewOfFile(view);}CloseHandle(mapping);if(ok){out=first;}return ok;
    }catch(...){return false;}
}
inline bool GroupDigest(const Manifest& m,std::uint32_t group,Digest& out) noexcept {
    if(!Valid(m)||group>=m.groups){return false;}
    std::array<std::array<std::uint8_t,24>,32> records{};std::size_t count{};
    for(std::uint32_t i=0;i<m.count;++i){if(m.records[i].group==group){
        std::memcpy(records[count++].data(),&m.records[i].kind,24);
    }}
    std::sort(records.begin(),records.begin()+count);
    std::array<std::uint8_t,8+32*24> bytes{};
    std::memcpy(bytes.data(),"WBAGRP1",8);
    for(std::size_t i=0;i<count;++i){std::memcpy(bytes.data()+8+i*24,records[i].data(),24);}
    return fence::Hash(bytes.data(),static_cast<ULONG>(8+count*24),out);
}
}
