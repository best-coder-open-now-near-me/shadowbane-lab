#include "furnishing_resources.h"
#undef NDEBUG
#include <cassert>
#include <limits>
#include <map>
#include <memory>
#include <vector>

namespace f=wonderbane::extension::furnishing;
using A=f::Address; using R=f::RenderResources;
namespace {
constexpr A base=0x400000,model=0x900000,source=0x1000000,copy=0x1800000;
constexpr A material=0x2100000,mesh_set=0x2101000,mesh=0x2102000,image=0x2103000,shader=0x2104000,wrapper=0x2105000;
const f::Transform local{0.001f,0.001f,-0.001f,1,0,0,0,1,1,1};
f::Selection Selection(){f::Selection s{};s.model=model;s.render=source;s.epoch=7;s.floor=1;return s;}
struct Fixture {
    std::map<A,unsigned char> memory;
    std::map<A,unsigned> reads;
    A changed=0; bool current=true,texture=true,reenter=false; R* resources=nullptr;
    template<class T> void Put(A at,const T& value) {
        const auto* b=reinterpret_cast<const unsigned char*>(&value);
        for(std::size_t i=0;i<sizeof(T);++i){memory[at+static_cast<A>(i)]=b[i];}
    }
    void Words(A at,std::initializer_list<A> values){for(A v:values){Put(at,v);at+=4;}}
    void Type(A at,A type){Put(at,base+type);}
    void Ref(A at,A type,A finalizer){Type(at,type);Put(at+4,A{1});Words(base+type+4,{base+finalizer,base+0x26f49});}
    A Params(A root,unsigned low,unsigned high,A parent,unsigned depth){
        if(low==high){return 0;}const auto mid=low+(high-low)/2;const A at=root+0x6100+mid*40;
        const A left=Params(root,low,mid,at,depth+1),right=Params(root,mid+1,high,at,depth+1);
        Words(at,{depth==6?0U:1U,parent,left,right,mid});Put(at+20,std::array<float,4>{1,2,3,4});return at;
    }
    void Node(A at){
        Type(at,0x1149dbc);Type(at+0x30,0x1149d94);Put(at+8,base+0x1149e04);Ref(at+0x154,0x1149d70,0x127ab);
        Put(base+0x1149e08,A{0x14c});Put(base+0x1149dbc+0x2c,base+0x119eb);Put(base+0x1149d94+0xc,base+0x199ac);Words(at+0x9c,{0,0,0});Put(at+0x38,A{2});Words(at+0x3c,{0,0,0});
        Put(at+0x48,local);Put(at+0x70,local);Put(at+0xcc,std::array<float,6>{1,0,0,1,0,0});
        Words(at+0xf0,{0,0});Put(at+0x148,A{0x1030});Put(at+0xc4,material);
        Put(at+0xe8,at+0x2000);Type(at+0x2000,0x114a5a4);Words(at+0x2024,{at+0x3000,at+0x3004,at+0x3004});Put(at+0x2030,A{0});
        Put(at+0x3000,at+0x4000);Ref(at+0x4000,0x114a39c,0x15578);Words(at+0x4024,{0,0,0});Words(at+0x403c,{0,0,0});Put(at+0x4018,A{0});Put(at+0x405c,image);
        Words(at+0x120,{at+0x5000,at+0x5004,at+0x5005});const char text[4]={'t','e','s','t'};Put(at+0x5000,text);
        Put(at+0x12c,at+0x6000);Put(at+0x130,A{1});Words(at+0x6004,{at+0x6100,at+0x6100,at+0x6100});
        Words(at+0x6100,{1,at+0x6000,0,0,9});Put(at+0x6114,std::array<float,4>{1,2,3,4});
        Put(at+0x114,A{0});Put(at+0x13c,A{0});
    }
    Fixture(){
        Type(model,0x1143540);Put(model+0xc0,source);Node(source);Node(copy);
        Ref(material,0x114a074,0x28ba);Put(material+0x1c,mesh_set);Put(material+0x30,A{0});Put(material+0x40,A{0});
        Type(mesh_set,0x11499f4);Words(mesh_set+0x24,{mesh_set+0x100,mesh_set+0x104,mesh_set+0x104});Put(mesh_set+0x30,A{0});Put(mesh_set+0x100,mesh);Ref(mesh,0x11498a0,0x1020d);
        Type(image,0x11490f0);Put(image+8,base+0x114912c);Put(base+0x1149130,A{0x100});Ref(image+0x108,0x11490dc,0x11a9f);Put(image+0x44,A{77});Put(image+0xfc,A{0xde1});
        Put(base+0x114a39c+0x7c,base+0xc36f);Put(base+0x114a39c+0x80,base+0x24ee7);Put(base+0x114a39c+0x58,base+0x10631);
        Put(base+0x16a7c30,A{0});Put(base+0x16a7bd4,A{0});Put(base+0x16a740c,A{0});
        Put(base+0x13883f0,shader);Type(shader,0x1149ca8);Words(base+0x1149ca8+4,{base+0x6023,base+0x2339e,base+0x1fc3,base+0x220fc,base+0x25577});
        Type(wrapper,0x1149d38);Put(wrapper+8,A{77});Put(wrapper+0x18,shader);Put(wrapper+0x1c,copy);
    }
    static bool Read(void* ctx,A at,void* out,std::size_t size) noexcept{
        auto& f=*static_cast<Fixture*>(ctx);auto* b=static_cast<unsigned char*>(out);const auto n=++f.reads[at];
        for(std::size_t i=0;i<size;++i){auto found=f.memory.find(at+static_cast<A>(i));if(found==f.memory.end()){return false;}b[i]=found->second;}
        if(at==f.changed&&n==2){b[0]^=4;}
        if(f.reenter){f.reenter=false;assert(!f.resources->Source(Selection()));}
        return true;
    }
    static bool Current(void* ctx) noexcept{return static_cast<Fixture*>(ctx)->current;}
    static bool Texture(void* ctx,A name,A target) noexcept{assert(name==77&&target==0xde1);return static_cast<Fixture*>(ctx)->texture;}
    std::unique_ptr<R> Make(){auto r=std::make_unique<R>(R::Access{this,Read,Current,Texture,base});resources=r.get();return r;}
    bool Private(R& r){std::array<A,64> renders{};std::size_t count=99;return r.Private(Selection(),copy,renders.data(),renders.size(),&count);}
};
void Reject(Fixture& f){auto r=f.Make();assert(!r->Source(Selection()));}
void Normal(){Fixture f;auto r=f.Make();assert(r->Source(Selection())&&f.Private(*r)&&r->Wrapper(wrapper,copy));
    auto moved=local;moved[0]+=100;f.Put(copy+0x48,moved);assert(f.Private(*r));
    for(A field:{wrapper,wrapper+8,wrapper+0x18,wrapper+0x1c}){A saved=0;Fixture::Read(&f,field,&saved,4);f.Put(field,A{0});assert(!r->Wrapper(wrapper,copy));f.Put(field,saved);}
    f.Put(copy+0x70,moved);assert(!f.Private(*r));
}
void UnsafeSource(){
    for(A at:{source,source+0x30,material,mesh_set,mesh,source+0x2000,source+0x4000,image}){Fixture f;f.Put(at,A{0});Reject(f);}
    for(A at:{source+0x38,source+0xf0,source+0xf4,source+0x114,mesh_set+0x30,source+0x2030,base+0x16a7c30}){Fixture f;f.Put(at,A{1});Reject(f);}
    for(A at:{source+0x48,source+0x70,source+0xcc,source+0xdc,source+0x6114}){Fixture f;f.Put(at,std::numeric_limits<float>::quiet_NaN());Reject(f);}
    for(A at:{source+0x158,material+4,mesh+4,source+0x4004,image+0x10c}){Fixture f;f.Put(at,A{0});Reject(f);}
    {Fixture f;f.Put(source+0xdc,1.0f);Reject(f);}
    {Fixture f;f.Put(image+0xfc,A{0x8513});Reject(f);}
    {Fixture f;f.Put(image+0x44,A{0});Reject(f);}
    {Fixture f;f.texture=false;Reject(f);}
    {Fixture f;f.Put(source+0x405c,A{0});Reject(f);}
    {Fixture f;f.Put(source+0x148,A{0x8030});Reject(f);}
    {Fixture f;f.Words(source+0x3c,{source+0x1000,source+0x1004,source+0x1004});f.Put(source+0x1000,source);Reject(f);}
    {Fixture f;f.Put(mesh_set+0x28,mesh_set+0x108);f.Put(mesh_set+0x2c,mesh_set+0x108);Reject(f);}
    {Fixture f;f.Put(base+0x114a39c+0x80,A{0});Reject(f);}
    {Fixture f;f.Put(base+0x1149ca8+16,A{0});Reject(f);}
    {Fixture f;f.Type(shader,0x1149bf4);Reject(f);}
}
void Metadata(){
    for(A at:{source+0x130,source+0x6100,source+0x6104,source+0x6008}){Fixture f;f.Put(at,A{0});Reject(f);}
    {Fixture f;f.Put(source+0x6108,source+0x6100);Reject(f);}
    {Fixture f;f.Put(source+0x124,source+0x5000+1025);f.Put(source+0x128,source+0x5000+1026);Reject(f);}
    {Fixture f;f.Words(source+0x120,{0,0,0});f.Put(source+0x130,A{0});f.Words(source+0x6004,{0,source+0x6000,source+0x6000});auto r=f.Make();assert(r->Source(Selection()));}
}
void Independent(){
    for(A field:{copy+0xe8,copy+0x2024,copy+0x3000,copy+0x120,copy+0x12c}){
        Fixture f;auto r=f.Make();assert(r->Source(Selection()));A original=0;Fixture::Read(&f,field-(copy-source),&original,4);f.Put(field,original);assert(!f.Private(*r));
    }
    {Fixture f;auto r=f.Make();assert(r->Source(Selection()));f.Put(copy+0x6114,9.0f);assert(!f.Private(*r));}
    {Fixture f;auto r=f.Make();assert(r->Source(Selection()));f.Put(copy+0x148,A{0x1031});assert(!f.Private(*r));}
    {Fixture f;auto r=f.Make();assert(r->Source(Selection()));auto s=Selection();++s.floor;A out[64]{};std::size_t count=1;assert(!r->Private(s,copy,out,64,&count)&&!count);}
}
void ShaderSelection(){
    for(A mask=0;mask<64;++mask){
        Fixture f;const A expected=(mask&1?1U:0U)+(mask&2?8U:0U)+(mask&4?32U:0U)+(mask&8?64U:0U)+(mask&16?128U:0U)+(mask&32?256U:0U);
        f.Put(base+0x13883f0,A{0});f.Put(base+0x13883f0+expected*4,shader);
        f.Put(base+0x16a7bd4,A{0x10000});f.Put(base+0x16a740c,A{1});f.Put(material+0x30,mask&2?A{0x10000}:0U);f.Put(material+0x40,mask&32?1U:0U);
        for(A at:{source,copy}){f.Put(at+0x13c,mask&1?1U:0U);f.Put(at+0x148,mask&4?A{0x1034}:A{0x1030});f.Put(at+0xcc,mask&8?0.5f:1.0f);f.Put(at+0x4018,mask&16?1U:0U);}
        auto r=f.Make();assert(r->Source(Selection())&&f.Private(*r));
    }
    Fixture f;f.Put(source+0xcc,0.5f);f.Put(copy+0xcc,0.5f);f.Put(base+0x13883f0+64*4,shader);f.Type(shader,0x1149c84);
    f.Words(base+0x1149c84+4,{base+0x6023,base+0xfeac,base+0xcd1f,base+0x227d7,base+0x25577});auto r=f.Make();assert(r->Source(Selection())&&f.Private(*r));
}
void Bounds(){
    {Fixture f;for(A at:{source,copy}){const A root=f.Params(at,0,64,at+0x6000,0);f.Put(at+0x130,A{64});f.Words(at+0x6004,{root,at+0x6100,at+0x6100+63*40});
       f.Words(at+0x120,{at+0x5000,at+0x5400,at+0x5401});std::array<char,1024> text{};text.fill('a');f.Put(at+0x5000,text);}
     auto r=f.Make();assert(r->Source(Selection())&&f.Private(*r));f.Put(source+0x130,A{65});assert(!r->Source(Selection()));}
    Fixture f;
    for(A i=1;i<64;++i){f.Node(source+i*0x10000);f.Node(copy+i*0x10000);f.Put(source+0x1000+(i-1)*4,source+i*0x10000);f.Put(copy+0x1000+(i-1)*4,copy+i*0x10000);}
    for(A at:{source,copy}){f.Words(at+0x3c,{at+0x1000,at+0x1000+63*4,at+0x1000+63*4});}
    auto r=f.Make();assert(r->Source(Selection())&&f.Private(*r));
    f.Node(source+64*0x10000);f.Put(source+0x1000+63*4,source+64*0x10000);f.Words(source+0x3c,{source+0x1000,source+0x1100,source+0x1100});assert(!r->Source(Selection()));
}
void Changing(){
    std::vector<A> addresses;{Fixture f;auto r=f.Make();assert(r->Source(Selection()));for(auto [at,count]:f.reads){assert(count>=2);addresses.push_back(at);}}
    for(A at:addresses){Fixture f;f.changed=at;Reject(f);}
    {Fixture f;auto r=f.Make();f.reenter=true;assert(r->Source(Selection()));f.current=false;assert(!f.Private(*r));}
}
}
int main(){Normal();UnsafeSource();Metadata();Independent();ShaderSelection();Bounds();Changing();}
