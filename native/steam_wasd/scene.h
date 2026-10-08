#pragma once
#include <cstdint>
namespace steam_wasd {
struct Scene { std::uintptr_t actor{},window{},world{},parent{}; std::uint64_t id{}; };
inline bool same_identity(const Scene& a,const Scene& b) {
    return a.actor && a.window && a.world && a.id && a.actor==b.actor && a.window==b.window && a.world==b.world && a.id==b.id;
}
inline bool same(const Scene& a,const Scene& b) { return same_identity(a,b) && a.parent==b.parent; }
enum class Rebase { unchanged, parent_changed, retired };
inline Rebase rebase(Scene& owned,const Scene& current) {
    if(!same_identity(owned,current)) return Rebase::retired;
    if(owned.parent==current.parent) return Rebase::unchanged;
    owned.parent=current.parent;return Rebase::parent_changed;
}
}
