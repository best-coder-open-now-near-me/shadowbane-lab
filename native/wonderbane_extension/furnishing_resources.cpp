#include "furnishing_resources.h"
#include <algorithm>
#include <cmath>
#include <cstring>

namespace wonderbane::extension::furnishing {
namespace {
bool Pointer(Address a) noexcept { return a>=0x10000 && a<0x7fff0000 && a%4==0; }
struct Busy { bool& value; explicit Busy(bool& v):value(v){value=true;} ~Busy(){value=false;} };
}
bool RenderResources::Current() const noexcept { return access_.current && access_.current(access_.context); }
bool RenderResources::Read(Address at,void* out,std::size_t size) noexcept {
    if(!Pointer(at)||!size||size>40||at>0x7fff0000-size||reads_==journal_.size()||!access_.read) { return false; }
    auto& b=journal_[reads_];
    if(!access_.read(access_.context,at,b.bytes.data(),size)) { return false; }
    b.at=at; b.size=size; ++reads_; std::memcpy(out,b.bytes.data(),size); return true;
}
bool RenderResources::Require(Address at,Address value) noexcept { Address v=0; return Read(at,v)&&v==value; }
bool RenderResources::Type(Address at,Address rva) noexcept { return Require(at,access_.base+rva); }
bool RenderResources::Verify() const noexcept {
    std::array<unsigned char,40> next{};
    for(auto i=reads_;i>0;--i) {
        const auto& b=journal_[i-1];
        if(!access_.read(access_.context,b.at,next.data(),b.size)||std::memcmp(next.data(),b.bytes.data(),b.size)) { return false; }
    }
    return Current();
}
bool RenderResources::Vector(Address at,Address* out,std::size_t limit,std::size_t& count,Address& storage) noexcept {
    std::array<Address,3> v{}; count=0; storage=0;
    if(!Read(at,v)) { return false; } if(v==std::array<Address,3>{}) { return true; }
    if(!Pointer(v[0])||!Pointer(v[1])||!Pointer(v[2])||v[0]>v[1]||v[1]>v[2]||(v[1]-v[0])/4>limit) { return false; }
    storage=v[0];
    for(Address p=v[0];p<v[1];p+=4) {
        Address value=0;
        if(!Read(p,value)||!Pointer(value)||std::find(out,out+count,value)!=out+count) { return false; }
        out[count++]=value;
    }
    return true;
}
bool RenderResources::Parameters(Node& n,Address at,Address parent,unsigned depth,std::uint64_t low,std::uint64_t high,unsigned& black) noexcept {
    if(!at) { black=1; return true; }
    if(at==n.map||depth>16||seen_count_==kParameters
        ||std::find(seen_parameters_.begin(),seen_parameters_.begin()+seen_count_,at)!=seen_parameters_.begin()+seen_count_) { return false; }
    seen_parameters_[seen_count_++]=at;
    struct Raw { Address color,parent,left,right,key; std::array<float,4> value; } raw{};
    if(!Read(at,raw)||raw.parent!=parent||(raw.color&255)>1||raw.key<low||raw.key>=high) { return false; }
    for(float v:raw.value) { if(!std::isfinite(v)) { return false; } }
    unsigned left=0,right=0;
    if(!Parameters(n,raw.left,at,depth+1,low,raw.key,left)||n.parameter_count==kParameters) { return false; }
    n.parameters[n.parameter_count++]={at,raw.key,raw.value};
    if(!Parameters(n,raw.right,at,depth+1,std::uint64_t(raw.key)+1,high,right)||left!=right) { return false; }
    if(!(raw.color&255)) {
        for(Address child:{raw.left,raw.right}) { Address color=0; if(child&&(!Read(child,color)||!(color&255))) { return false; } }
    }
    black=left+(raw.color&255); return true;
}
bool RenderResources::Reference(Address at,Address table,Address finalizer) noexcept {
    Address count=0;
    return Type(at,table)&&Read(at+4,count)&&count&&count<=0x1000000
        &&Require(access_.base+table+4,access_.base+finalizer)&&Require(access_.base+table+8,access_.base+0x26f49);
}
bool RenderResources::String(Address object) noexcept {
    std::array<Address,3> text{};
    if(!Read(object+4,text)) { return false; }
    if(text==std::array<Address,3>{}) { return true; }
    if(!Pointer(text[0])||text[1]<text[0]||text[2]<text[1]||text[2]>=0x7fff0000
        ||text[1]%2||text[2]%2||text[1]-text[0]>1024) { return false; }
    const auto size=text[1]-text[0]; total_text_+=size;
    if(total_text_>8192) { return false; }
    std::array<unsigned char,32> bytes{};
    for(Address i=0;i<size;i+=32) { if(!Read(text[0]+i,bytes.data(),(std::min)(Address{32},size-i))) { return false; } }
    return true;
}
bool RenderResources::Metadata(Node& n) noexcept {
    std::array<Address,3> name{}; Address count=0; std::array<Address,3> tree{};
    if(!Read(n.render+0x120,name)) { return false; }
    if(name!=std::array<Address,3>{}) {
        if(!Pointer(name[0])||name[1]<name[0]||name[2]<name[1]||name[2]>=0x7fff0000||name[1]-name[0]>kName) { return false; }
        n.name=name[0]; n.name_size=name[1]-name[0]; total_text_+=n.name_size;
        if(total_text_>8192) { return false; }
        for(std::size_t i=0;i<n.name_size;i+=32) {
            if(!Read(n.name+static_cast<Address>(i),n.text.data()+i,(std::min)(std::size_t{32},n.name_size-i))) { return false; }
        }
    }
    if(!Read(n.render+0x12c,n.map)||!Read(n.render+0x130,count)||count>kParameters
        ||!Read(n.map+4,tree)) { return false; }
    total_parameters_+=count; if(total_parameters_>256) { return false; }
    n.parameter_count=0; seen_count_=0; unsigned height=0;
    if(!Parameters(n,tree[0],n.map,0,0,std::uint64_t{1}<<32,height)||n.parameter_count!=count) { return false; }
    if(!count) { return !tree[0]&&tree[1]==n.map&&tree[2]==n.map; }
    Address color=0;
    return Read(tree[0],color)&&(color&255)==1&&tree[1]==n.parameters[0].address&&tree[2]==n.parameters[count-1].address;
}
bool RenderResources::Shader(Node& n,std::uint32_t flags,float opacity,float bias) noexcept {
    // Same selector arithmetic as native 0x1c3f30, with inactive vertex programs.
    // Evaluate the copied flag word, not the borrowed source's bit 0/shadow flags.
    Address globals=0,program=0,lod=0,lod_enabled=0,lod_count=0,material_flags=0,material_alpha=0,texture_alpha=0;
    if(bias!=0||!Read(access_.base+0x16a7c30,globals)||(globals&255)
        ||!Read(n.render+0x114,program)||(program&255)||!Read(n.render+0x13c,lod)
        ||!Read(access_.base+0x16a7bd4,lod_enabled)||!Read(access_.base+0x16a740c,lod_count)
        ||!Read(n.material+0x30,material_flags)||!Read(n.material+0x40,material_alpha)
        ||!Read(n.texture+0x18,texture_alpha)) { return false; }
    const Address special=(lod&255)&&((lod_enabled>>16)&255)&&lod_count ? 1U:0U;
    Address index=(texture_alpha?1U:0U)+(material_alpha?2U:0U);
    index=(opacity<0.995f?1U:0U)+index*2;
    index=((flags>>2)&1)+index*2;
    index=(((material_flags>>16)&255)?1U:0U)+index*4;
    index=(flags&1)+index*2;
    index=special+index*4;
    if(index>=1024||!Read(access_.base+0x13883f0+index*4,n.shader)) { return false; }
    Address type=0;
    if(!Read(n.shader,type)) { return false; }
    const bool alpha=type==access_.base+0x1149c84;
    if(!alpha&&type!=access_.base+0x1149ca8) { return false; }
    return Require(type+4,access_.base+0x6023)&&Require(type+8,access_.base+(alpha?0xfeacU:0x2339eU))
        &&Require(type+12,access_.base+(alpha?0xcd1fU:0x1fc3U))
        &&Require(type+16,access_.base+(alpha?0x227d7U:0x220fcU))&&Require(type+20,access_.base+0x25577);
}
bool RenderResources::Visit(Graph& graph,Address render,std::size_t parent,unsigned depth,bool copied) noexcept {
    if(graph.count==kNodes||depth>8) { return false; }
    for(std::size_t i=0;i<graph.count;++i) { if(graph.nodes[i].render==render) { return false; } }
    const auto index=graph.count++; auto& n=graph.nodes[index]; n={}; n.render=render; n.parent=parent;
    Address callbacks=0,special=0,borrowed=0; Transform world{}; std::array<float,6> draw{};
    if(!Type(render,0x1149dbc)||!Type(render+0x30,0x1149d94)
        ||!Require(render+8,access_.base+0x1149e04)||!Require(access_.base+0x1149e08,0x14c)
        ||!Reference(render+0x154,0x1149d70,0x127ab)
        ||!Require(access_.base+0x1149dbc+0x2c,access_.base+0x119eb)
        ||!Require(access_.base+0x1149d94+0xc,access_.base+0x199ac)||!String(render+0x98)||!Read(render+0x38,callbacks)||(callbacks&1)
        ||!Read(render+0xf0,special)||(special&65535)||!Read(render+0xf4,borrowed)||borrowed
        ||!Read(render+0x148,n.flags)||(n.flags&0xe000)||!Read(render+0x48,world)||!ValidTransform(world)
        ||!Read(render+0x70,n.local)||!ValidTransform(n.local)||!Read(render+0xcc,draw)) { return false; }
    for(float v:draw) { if(!std::isfinite(v)) { return false; } }
    if(draw[0]<=0||draw[0]>1) { return false; }
    const Address target_flags=(n.flags&0x1f2e)|0x10;
    if(copied&&(n.flags&0xffff)!=target_flags) { return false; }
    std::array<Address,kNodes> children{};
    if(!Vector(render+0x3c,children.data(),children.size(),n.child_count,n.children)
        ||!Read(render+0xc4,n.material)||!Reference(n.material,0x114a074,0x28ba)
        ||!Read(n.material+0x1c,n.mesh_set)||!Type(n.mesh_set,0x11499f4)) { return false; }
    std::array<Address,1> member{}; std::size_t count=0; Address storage=0;
    if(!Vector(n.mesh_set+0x24,member.data(),1,count,storage)||count!=1||!Require(n.mesh_set+0x30,0)) { return false; }
    n.mesh=member[0];
    if(!Reference(n.mesh,0x11498a0,0x1020d)||!Read(render+0xe8,n.texture_set)||!Type(n.texture_set,0x114a5a4)
        ||!Vector(n.texture_set+0x24,member.data(),1,count,n.texture_vector)||count!=1||!Require(n.texture_set+0x30,0)) { return false; }
    n.texture=member[0];
    if(!Reference(n.texture,0x114a39c,0x15578)||!String(n.texture+0x20)||!String(n.texture+0x38)
        ||!Require(access_.base+0x114a39c+0x7c,access_.base+0xc36f)||!Require(access_.base+0x114a39c+0x80,access_.base+0x24ee7)
        ||!Require(access_.base+0x114a39c+0x58,access_.base+0x10631)
        ||!Read(n.texture+0x5c,n.image)||!Type(n.image,0x11490f0)
        ||!Require(n.image+8,access_.base+0x114912c)||!Require(access_.base+0x1149130,0x100)
        ||!Reference(n.image+0x108,0x11490dc,0x11a9f)
        ||!Read(n.image+0x44,n.texture_name)||!n.texture_name||n.texture_name==0xffffffff
        ||!Require(n.image+0xfc,0xde1)||!access_.texture||!access_.texture(access_.context,n.texture_name,0xde1)
        ||!Metadata(n)||!Shader(n,target_flags,draw[0],draw[4])) { return false; }
    for(std::size_t i=0;i<n.child_count;++i) { if(!Visit(graph,children[i],index,depth+1,copied)) { return false; } }
    return true;
}
bool RenderResources::Capture(Graph& graph,Address root,bool copied) noexcept {
    graph.count=0; reads_=0; total_parameters_=0; total_text_=0;
    return Current()&&Pointer(access_.base)&&access_.base<=0x7d000000&&Visit(graph,root,kNodes,0,copied)&&Verify();
}
bool RenderResources::Independent() const noexcept {
    if(private_.count!=source_.count) { return false; }
    for(std::size_t i=0;i<source_.count;++i) {
        const auto& s=source_.nodes[i]; const auto& p=private_.nodes[i];
        if(p.parent!=s.parent||p.child_count!=s.child_count||p.local!=s.local||p.material!=s.material
            ||p.mesh_set!=s.mesh_set||p.mesh!=s.mesh||p.image!=s.image||p.name_size!=s.name_size
            ||p.parameter_count!=s.parameter_count||p.text!=s.text||(p.flags&0xffff)!=((s.flags&0x1f2e)|0x10)) { return false; }
        for(std::size_t j=0;j<p.parameter_count;++j) {
            if(p.parameters[j].key!=s.parameters[j].key||p.parameters[j].value!=s.parameters[j].value) { return false; }
        }
        // No private ownership edge may alias any source node's owned storage.
        for(std::size_t j=0;j<source_.count;++j) {
            const auto& a=source_.nodes[j];
            if(p.render==a.render||p.texture_set==a.texture_set||p.texture==a.texture||p.texture_vector==a.texture_vector
                ||p.map==a.map||(p.name&&p.name==a.name)||(p.children&&p.children==a.children)) { return false; }
            for(std::size_t x=0;x<p.parameter_count;++x) {
                for(std::size_t y=0;y<a.parameter_count;++y) { if(p.parameters[x].address==a.parameters[y].address) { return false; } }
            }
        }
        for(std::size_t j=0;j<i;++j) {
            const auto& a=private_.nodes[j];
            if(p.texture_set==a.texture_set||p.texture==a.texture||p.texture_vector==a.texture_vector||p.map==a.map
                ||(p.name&&p.name==a.name)||(p.children&&p.children==a.children)) { return false; }
        }
    }
    return true;
}
bool RenderResources::Source(const Selection& selection) noexcept {
    if(running_) { return false; } const Busy busy(running_); source_valid_=false; private_valid_=false;
    reads_=0;
    if(!Current()||!Type(selection.model,0x1143540)||!Require(selection.model+0xc0,selection.render)||!Verify()) { return false; }
    if(!Capture(source_,selection.render,false)) { return false; }
    selection_=selection; source_valid_=true; return true;
}
bool RenderResources::Private(const Selection& selection,Address clone,Address* renders,std::size_t capacity,std::size_t* count) noexcept {
    if(!count) { return false; } *count=0;
    if(running_) { return false; } const Busy busy(running_); private_valid_=false;
    if(!source_valid_||!selection.SameIdentity(selection_)||!renders||!Capture(private_,clone,true)
        ||!Independent()||capacity<private_.count) { return false; }
    for(std::size_t i=0;i<private_.count;++i) { renders[i]=private_.nodes[i].render; }
    *count=private_.count; private_valid_=true; return true;
}
bool RenderResources::Wrapper(Address wrapper,Address render) noexcept {
    if(running_||!private_valid_) { return false; } const Busy busy(running_); reads_=0;
    for(std::size_t i=0;i<private_.count;++i) {
        const auto& n=private_.nodes[i];
        if(n.render==render) {
            return Current()&&Type(wrapper,0x1149d38)&&Require(wrapper+0x1c,render)
                &&Require(wrapper+0x18,n.shader)&&Require(wrapper+8,n.texture_name)&&Verify();
        }
    }
    return false;
}
}
