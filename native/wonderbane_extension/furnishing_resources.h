#pragma once
#include "furnishing_selection.h"

namespace wonderbane::extension::furnishing {
// The reviewed static family uses one selected mesh and one loaded ColorTexture.
// No loaders, callbacks, vertex programs or shared mesh-index changes are admitted.
class RenderResources {
public:
    static constexpr std::size_t kNodes=64, kParameters=64, kName=1024;
    struct Access {
        void* context=nullptr;
        bool (*read)(void*,Address,void*,std::size_t) noexcept=nullptr;
        bool (*current)(void*) noexcept=nullptr;
        bool (*texture)(void*,std::uint32_t name,std::uint32_t target) noexcept=nullptr;
        Address base=0;
    };
    explicit RenderResources(Access access) noexcept : access_(access) {}
    bool Source(const Selection&) noexcept;
    bool Private(const Selection&,Address clone,Address* renders,std::size_t capacity,std::size_t* count) noexcept;
    // Called for each exact receipt wrapper before the drain begins.
    bool Wrapper(Address wrapper,Address render) noexcept;
private:
    struct Parameter { Address address=0,key=0; std::array<float,4> value{}; };
    struct Node {
        Address render=0,children=0,material=0,mesh_set=0,mesh=0,texture_set=0,texture_vector=0,texture=0,image=0,shader=0;
        Address name=0,map=0; std::size_t parent=kNodes,child_count=0,name_size=0,parameter_count=0;
        Transform local{};
        std::array<unsigned char,kName> text{};
        std::array<Parameter,kParameters> parameters{};
        std::uint32_t flags=0,texture_name=0;
    };
    struct Graph { std::size_t count=0; std::array<Node,kNodes> nodes{}; };
    struct Block { Address at=0; std::size_t size=0; std::array<unsigned char,40> bytes{}; };
    bool Read(Address,void*,std::size_t) noexcept;
    template<class T> bool Read(Address at,T& out) noexcept { return Read(at,&out,sizeof(out)); }
    bool Require(Address,Address) noexcept;
    bool Type(Address,Address) noexcept;
    bool Current() const noexcept;
    bool Verify() const noexcept;
    bool Vector(Address,Address*,std::size_t,std::size_t&,Address&) noexcept;
    bool Metadata(Node&) noexcept;
    bool String(Address) noexcept;
    bool Reference(Address,Address table,Address finalizer) noexcept;
    bool Parameters(Node&,Address at,Address parent,unsigned depth,std::uint64_t low,std::uint64_t high,unsigned& black) noexcept;
    bool Visit(Graph&,Address,std::size_t parent,unsigned depth,bool copied) noexcept;
    bool Shader(Node&,std::uint32_t flags,float opacity,float bias) noexcept;
    bool Capture(Graph&,Address,bool copied) noexcept;
    bool Independent() const noexcept;
    Access access_{};
    Selection selection_{};
    bool running_=false,source_valid_=false,private_valid_=false;
    std::size_t reads_=0,total_parameters_=0,total_text_=0,seen_count_=0;
    std::array<Address,kParameters> seen_parameters_{};
    Graph source_{},private_{};
    std::array<Block,16384> journal_{};
};
}
