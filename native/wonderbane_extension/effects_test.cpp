#include "effects.h"
#include <cstdio>
#include <cmath>
#include <cstring>
#include <limits>
#include <map>
#include <vector>
using namespace wonderbane::extension::effects;
namespace {
int failures=0;
void Check(bool ok,const char* label) { if (!ok) { std::fprintf(stderr,"%s\n",label); ++failures; } }
struct Memory {
    std::map<std::uint32_t,std::vector<unsigned char>> cells;
    template<class T> void Put(std::uint32_t p,T value) { auto& b=cells[p]; b.resize(sizeof(T)); std::memcpy(b.data(),&value,sizeof(T)); }
    static bool Read(void* raw,std::uint32_t p,void* out,std::size_t n) {
        auto& m=*static_cast<Memory*>(raw); const auto it=m.cells.find(p);
        if (it==m.cells.end() || it->second.size()!=n) return false;
        std::memcpy(out,it->second.data(),n); return true;
    }
};
}
int main() {
    Config c{}; Check(Validate(c),"defaults valid");
    c.rate=std::numeric_limits<float>::quiet_NaN(); Check(!Validate(c),"reject nonfinite config"); c={};
    Attachment a{0x10000,1,2,0x20000,0x30000,0x40000,3,4,{100,5,-100},true};
    System s; c.flags=7; c.rate=0; c.burst=1; c.burst_count=10;
    s.Step(c,a,1); Check(s.stats.particles==10,"burst applies once");
    s.Step(c,a,1.1); Check(s.stats.particles==10,"unchanged token not repeated");
    Geometry geometry; s.Build(c,{100,5,-90},{1,0,0},{0,1,0},{0,0,-1},geometry);
    Check(geometry.count==10,"production geometry has particles and no degenerate stationary trail");
    for (int i=2;i<=20;++i) s.Step(c,a,1+static_cast<double>(i)/10);
    Check(s.stats.particles==0,"particles expire");
    a.position.x+=2; s.Step(c,a,3.1); Check(s.stats.samples>1,"moving attachment sampled");
    s.Build(c,{100,5,-90},{1,0,0},{0,1,0},{0,0,-1},geometry);
    for (std::size_t i=0;i<geometry.count;++i) for (const auto& p:geometry.quads[i].points)
        Check(std::isfinite(p.x)&&std::isfinite(p.y)&&std::isfinite(p.z),"finite ribbon geometry");
    a.position.x+=100; s.Step(c,a,3.2); Check(s.stats.samples==1,"teleport starts new ribbon");
    ++a.uuid; ++c.burst; s.Step(c,a,3.3); Check(s.stats.samples==1 && s.stats.particles==10,"UUID reuse resets before fresh burst");
    ++a.zone_uuid; s.Step(c,a,3.4); Check(s.stats.particles==0,"zone change clears particles");
    c.particle_budget=3; c.sample_budget=2; ++c.burst; s.Step(c,a,3.5);
    Check(s.stats.particles==3 && s.stats.dropped>=7,"particle budget bounded with diagnostics");
    a.position.x+=10; s.Step(c,a,3.6); Check(s.stats.samples<=2,"trail budget bounded");
    a.valid=false; s.Step(c,a,3.7); Check(!s.stats.particles&&!s.stats.samples&&s.stats.rejected,"missing attachment clears immediately");
    a.valid=true; s.Step(c,a,3.8); Check(!s.stats.particles,"loss does not replay burst");
    c.flags=0; s.Step(c,a,3.9); Check(!s.stats.samples,"disable clears");
    c.flags=7; s.Step(c,a,4); s.Step(c,a,5); Check(s.stats.samples==1,"long frame gap resets");
    s.Clear(); Check(!s.stats.particles&&!s.stats.samples,"cleanup");
    Memory m; constexpr std::uint32_t base=0x400000;
    m.Put(base+23735704U,a.actor); m.Put(base+23735716U,a.actor);
    m.Put(a.actor,base+18093660U); m.Put(base+18093660U+88U,base+41936U);
    m.Put(a.actor+120U,a.type);m.Put(a.actor+124U,a.uuid);m.Put(a.actor+1200U,a.component);
    m.Put(a.component,a.location);m.Put(a.location+32U,a.position);m.Put(a.actor+3392U,a.zone);
    m.Put(a.zone+120U,a.zone_type);m.Put(a.zone+124U,a.zone_uuid);
    const auto resolved=Resolve(Memory::Read,&m,base,0); Check(SameIdentity(resolved,a),"real layout resolver");
    Check(Resolve(Memory::Read,&m,base,1).valid,"selected actor root resolver");
    m.Put(a.actor+124U,a.uuid+1); Check(!SameIdentity(resolved,Resolve(Memory::Read,&m,base,0)),"reused address has different identity");
    m.Put(base+18093660U+88U,0U); Check(!Resolve(Memory::Read,&m,base,0).valid,"unsupported getter rejected");
    return failures ? 1:0;
}
