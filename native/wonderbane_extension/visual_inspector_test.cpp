#include "effects.h"
#include <Windows.h>
#undef NDEBUG
#include <cassert>
#include <array>
#include <fstream>
namespace {wonderbane::extension::effects::Attachment owner{};bool change=false;unsigned resolves=0;}
namespace wonderbane::extension::effects {
Attachment Resolve(Reader,void*,std::uint32_t,std::uint32_t selection) noexcept {
    ++resolves;auto result=owner;if(selection!=1)result.valid=false;
    if(change && resolves%2==0)++result.uuid;return result;
}
bool SameIdentity(const Attachment& a,const Attachment& b) noexcept {
    return a.valid&&b.valid&&a.actor==b.actor&&a.uuid==b.uuid;
}
}
#include "visual_inspector.cpp"
int main(int argc,char** argv){
    using namespace wonderbane::extension::visual;
    std::array<std::uint32_t,128> actor{},root{},left{},right{};
    auto ptr=[](auto& v){return static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(v.data()));};
    std::array<std::uint32_t,2> children{ptr(left),ptr(right)};
    actor[0xc0/4]=ptr(root);root[0]=left[0]=right[0]=0x1549dbc;
    root[4]=100;left[4]=right[4]=9996101;
    root[0x3c/4]=ptr(children);root[0x40/4]=ptr(children)+8;
    owner.valid=true;owner.actor=ptr(actor);owner.type=1;owner.uuid=7;
    auto take=[&](){return Capture(Read,nullptr,0x400000,1);};
    auto s=take();assert(!s.status&&s.count==3&&s.uuid==7);
    assert(s.nodes[0].parent==0xFFFFFFFFU&&s.nodes[1].parent==0&&s.nodes[2].parent==0);
    assert(s.nodes[1].resource==9996101&&s.nodes[1].address!=s.nodes[2].address);
    change=true;resolves=0;s=take();assert(s.status==3&&s.count==0);change=false;
    children[1]=ptr(root);s=take();assert(s.status==2&&s.count==0);children[1]=ptr(right);
    right[0]=0;s=take();assert(s.status==2&&s.count==0);right[0]=0x1549dbc;
    root[0x40/4]++;s=take();assert(s.status==2&&s.count==0);root[0x40/4]--;
    actor[0xc0/4]=0;s=take();assert(s.status==2&&s.count==0);actor[0xc0/4]=ptr(root);
    assert(Capture(Read,nullptr,0x400000,0).status==1);
    assert(Capture(Read,nullptr,0x400000,2).status==1);
    owner.valid=false;assert(take().status==1);owner.valid=true;
    // Exact bound and overflow, including cycles/aliases rejected above.
    std::array<std::array<std::uint32_t,128>,128> many{};
    std::array<std::uint32_t,128> pointers{};
    for(unsigned n=0;n<128;++n){many[n][0]=0x1549dbc;pointers[n]=ptr(many[n]);}
    root[0x3c/4]=ptr(pointers);root[0x40/4]=ptr(pointers)+127*4;
    assert(take().count==128);root[0x40/4]+=4;s=take();assert(s.status==2&&s.count==0);
    root[0x3c/4]=ptr(children);root[0x40/4]=ptr(children)+8;
    Start(0x400000);assert(channel);channel->request=2;Poll(true);
    assert(channel->applied==2&&!channel->status&&channel->count==3&&channel->publication==2);
    if(argc==2){std::ofstream out(argv[1],std::ios::binary);out.write(reinterpret_cast<const char*>(channel),sizeof(Channel));assert(out.good());}
    Poll(true);assert(channel->publication==2); // No per-frame capture unless requested.
    channel->request=3;Poll(true);assert(channel->publication==2);
    channel->request=4;owner.valid=false;Poll(true);assert(channel->count==0&&channel->status==1&&channel->nodes[1].resource==0);
    channel->request=6;channel->selection=2;Poll(true);assert(channel->status==4&&channel->count==0);
    channel->request=8;channel->selection=1;owner.valid=true;Poll(false);assert(channel->status==1);
    Stop();assert(!channel&&!mapping);
}
