#include "image.h"
#include "camera_fixture.h"
#include "parent_frame.h"
#include "controls.h"
#include <map>
#include <random>
#include <algorithm>
#include <cstdio>
#include <cstdlib>
struct Value { double when{}; unsigned action{}; };
struct Node { Node *left, *parent, *right; unsigned char color, nil; unsigned char pad[6]; std::uint64_t key; Value value; };
struct Map { Node* head; size_t size; };
static_assert(sizeof(Node)==56);
static_assert(sizeof(std::map<std::uint64_t,Value>)==sizeof(Map));
void check(bool value, const char* label) { if (!value) { fprintf(stderr,"FAIL: %s\n",label); exit(1); } }
int main(int argc, char** argv) {
    if (argc != 2) { fprintf(stderr,"Supply the official SBOnlinex64.exe path.\n"); return 2; }
    auto bytes = steam_wasd::read_file(argv[1]);
    check(steam_wasd::verified_file(bytes), "exact official image hash");
    bytes[0x1000] ^= 1;
    check(!steam_wasd::verified_file(bytes), "modified executable rejected");
    HMODULE module = LoadLibraryExW(std::filesystem::path(argv[1]).c_str(), nullptr, DONT_RESOLVE_DLL_REFERENCES);
    check(module != nullptr, "map image without initialization");
    auto detach = reinterpret_cast<Node*(*)(Map*, Node*)>(reinterpret_cast<std::uintptr_t>(module) + steam_wasd::profile::detach);
    std::mt19937 random(4371680);
    // Exercise the exact native detach/rotation instructions against the matching
    // MSVC node layout. Test owns and frees nodes; no game process is accessed.
    for (int round=0; round<200; ++round) {
        std::map<std::uint64_t,Value> tree;
        std::vector<std::uint64_t> keys;
        for (int i=0; i<64; ++i) keys.push_back((std::uint64_t(random())<<32) | random());
        for (auto key:keys) tree.emplace(key, Value{});
        auto* map = reinterpret_cast<Map*>(&tree);
        check(map->size==keys.size() && map->head->nil==1, "map ABI");
        std::shuffle(keys.begin(),keys.end(),random);
        for (auto key:keys) {
            Node* node=map->head->parent;
            while (!node->nil && node->key!=key) node=key<node->key ? node->left : node->right;
            check(!node->nil, "find key");
            auto before=tree.size();
            check(detach(map,node)==node, "detach returns exact node");
            ::operator delete(node);
            check(tree.size()+1==before && !tree.contains(key), "size and membership updated");
            std::uint64_t previous{}; size_t visited{};
            for (const auto& entry:tree) { check(!visited || previous<entry.first,"ordered intact survivors"); previous=entry.first; ++visited; }
            check(visited==tree.size(), "all survivors reachable");
        }
        check(tree.empty(), "sentinel restored after final erase");
    }
    auto native_unproject=reinterpret_cast<void(*)(float*,int,int,float)>(reinterpret_cast<std::uintptr_t>(module)+steam_wasd::profile::unproject);
    for(int degrees=0;degrees<360;degrees+=15) {
        auto fixture=steam_wasd::test::camera(degrees*3.141592653589793/180,0.7,0.001);
        std::memcpy(reinterpret_cast<char*>(module)+steam_wasd::profile::camera_matrix,fixture.matrix.data(),sizeof(fixture.matrix));
        for(int x:{0,256,1024}) for(int y:{0,256,768}) {
            float actual[3]{};steam_wasd::CameraPoint expected{};
            native_unproject(actual,x,y,0.5F);
            check(steam_wasd::unproject(fixture.matrix,x,y,0.5,expected),"unprojection succeeds");
            check(std::abs(actual[0]-expected.x)<0.04 && std::abs(actual[1]-expected.y)<0.04
                && std::abs(actual[2]-expected.z)<0.04,"camera math agrees with exact native unprojection");
        }
    }
    puts("216 screen rays matched the exact native Steam unprojection code.");
    auto invert=reinterpret_cast<steam_wasd::InvertTransform>(reinterpret_cast<std::uintptr_t>(module)+steam_wasd::profile::invert_transform);
    auto apply=reinterpret_cast<steam_wasd::ApplyTransform>(reinterpret_cast<std::uintptr_t>(module)+steam_wasd::profile::apply_transform);
    unsigned parent_cases=0;
    for(int parent_degrees=0;parent_degrees<360;parent_degrees+=15) for(float scale:{0.25F,1.0F,4.0F}) {
        const double angle=parent_degrees*3.141592653589793/180;
        steam_wasd::ParentTransform transform{{90000,40,-50000},{float(std::cos(angle/2)),0,float(std::sin(angle/2)),0},{scale,scale,scale}};
        for(int view_degrees=0;view_degrees<360;view_degrees+=15) {
            auto fixture=steam_wasd::test::camera(view_degrees*3.141592653589793/180,0.6,0.001);
            auto world=steam_wasd::camera_basis(fixture.matrix,fixture.eye);
            auto local=steam_wasd::parent_basis(world,transform,invert,apply);
            check(local.valid,"native parent inverse conversion admitted");
            for(unsigned keys:{unsigned(steam_wasd::w),unsigned(steam_wasd::a),unsigned(steam_wasd::s),unsigned(steam_wasd::d),unsigned(steam_wasd::w|steam_wasd::d)}) {
                auto direction=steam_wasd::direction(keys,local);auto expected=steam_wasd::direction(keys,world);
                steam_wasd::NativePoint input{direction.x,0,direction.z},output{};
                auto rotation_only=transform;rotation_only.position={};apply(&rotation_only,&output,&input);
                auto length=std::hypot(output.x,output.z);
                check(length>0 && std::abs(output.x/length-expected.x)<0.0002F
                    && std::abs(output.z/length-expected.z)<0.0002F,"parent-local step maps back to intended world direction");
                ++parent_cases;
            }
        }
    }
    // Anisotropic native inverse scale must survive until key combination.
    steam_wasd::ParentTransform scaled{{90000,40,-50000},{1,0,0,0},{2,1,0.5F}};
    auto local=steam_wasd::parent_basis({{0,-1},{1,0},true},scaled,invert,apply);
    auto diagonal=steam_wasd::direction(steam_wasd::w|steam_wasd::d,local);
    check(local.valid && std::abs(diagonal.z/diagonal.x+4)<0.0001F,"native nonuniform scale retained");
    printf("%u native parent-frame directions matched their intended world bearings.\n",parent_cases);
    FreeLibrary(module);
    puts("Exact Steam image and 12,800 native tree erases passed.");
}
