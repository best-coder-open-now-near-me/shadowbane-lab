#include "image.h"
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
    FreeLibrary(module);
    puts("Exact Steam image and 12,800 native tree erases passed.");
}
