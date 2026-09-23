#include "effects.h"
#include <cmath>

namespace wonderbane::extension::effects {
bool SameIdentity(const Attachment& a, const Attachment& b) noexcept {
    return a.valid && b.valid && a.actor==b.actor && a.type==b.type && a.uuid==b.uuid
        && a.component==b.component && a.location==b.location && a.zone==b.zone
        && a.zone_type==b.zone_type && a.zone_uuid==b.zone_uuid;
}
Attachment Resolve(Reader reader, void* context, std::uint32_t base, std::uint32_t selection) noexcept {
    Attachment invalid{};
    if (!reader || selection>1 || base<0x10000U || base>0x70000000U) return invalid;
    const auto read=[&](std::uint32_t address, auto& value) {
        return address>=0x10000U && address<=0x7FFEFFFFU-sizeof(value)
            && reader(context,address,&value,sizeof(value));
    };
    const auto pointer=[](std::uint32_t p) { return p>=0x10000U && p<=0x7FFEEFFFU; };
    const auto capture=[&](Attachment& a) {
        std::uint32_t table=0,getter=0,player=0;
        if (!read(base+23735704U,player) || !pointer(player)
            || !read(base+(selection ? 23735716U:23735704U),a.actor) || !pointer(a.actor)
            || !read(a.actor,table) || table<base+18092032U || table>=base+19664896U
            || !read(table+88U,getter) || getter!=base+41936U
            || !read(a.actor+120U,a.type) || !read(a.actor+124U,a.uuid) || !(a.type|a.uuid)
            || !read(a.actor+1200U,a.component) || !pointer(a.component)
            || !read(a.component,a.location) || !pointer(a.location)
            || !read(a.location+32U,a.position)
            || !read(player+3392U,a.zone) || !pointer(a.zone)
            || !read(a.zone+120U,a.zone_type) || !read(a.zone+124U,a.zone_uuid)) return false;
        a.valid=std::isfinite(a.position.x) && std::isfinite(a.position.y) && std::isfinite(a.position.z)
            && a.position.x>=0 && a.position.x<=200000 && a.position.z<=0 && a.position.z>=-200000
            && a.position.y>=-2000 && a.position.y<=20000;
        return a.valid;
    };
    Attachment first{},second{};
    if (!capture(first) || !capture(second) || !SameIdentity(first,second)) return invalid;
    const float x=first.position.x-second.position.x,y=first.position.y-second.position.y,z=first.position.z-second.position.z;
    return x*x+y*y+z*z<=10000 ? second:invalid;
}
} // namespace wonderbane::extension::effects
