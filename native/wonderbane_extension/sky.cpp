#include "sky.h"
#include <algorithm>
#include <cmath>
#include <cstring>
namespace wonderbane::extension::sky {
namespace {
float Clamp(float x) { return std::clamp(x,0.0F,1.0F); }
float Dot(Vec a,Vec b) { return a.x*b.x+a.y*b.y+a.z*b.z; }
Vec Mix(Vec a,Vec b,float t) { return {a.x+(b.x-a.x)*t,a.y+(b.y-a.y)*t,a.z+(b.z-a.z)*t}; }
bool Range(float x,float a,float b) { return std::isfinite(x)&&x>=a&&x<=b; }
bool Color(Vec a) { return Range(a.x,0,1)&&Range(a.y,0,1)&&Range(a.z,0,1); }
}
bool Valid(const Settings& s) noexcept {
    return s.enabled<=1 && Range(s.orientation,-180,180)&&Range(s.intensity,0,2)
        &&Range(s.horizon_height,-0.4F,0.4F)&&Range(s.horizon_width,0.02F,0.8F)
        &&Range(s.clouds,0,1)&&Range(s.sun,0,1)&&Range(s.fog_match,0,1);
}
bool ValidAsset(const Asset& a) noexcept {
    if(a.magic!=0x594b5357U||a.version!=1||a.count!=12||a.size!=sizeof(Asset)
        ||!Color(a.zenith)||!Color(a.horizon)||!Color(a.nadir)
        ||!Color(a.sun_color)||!Color(a.cloud_color)||!Range(Dot(a.sun,a.sun),0.98F,1.02F))return false;
    for(const auto& c:a.clouds)if(!Range(Dot(c.direction,c.direction),0.99F,1.01F)
        ||!Range(Dot(c.right,c.right),0.99F,1.01F)||!Range(c.width,0.01F,1)
        ||!Range(c.height,0.01F,1)||!Range(c.opacity,0,1))return false;
    return true;
}
Vec Ray(const GraphicsCameraState& c,float x,float y,float yaw) noexcept {
    const auto& p=c.projection_matrix;const auto& v=c.view_matrix;
    const float ex=(x+p[8])/p[0],ey=(y+p[9])/p[5];
    Vec d{v[0]*ex+v[1]*ey-v[2],v[4]*ex+v[5]*ey-v[6],v[8]*ex+v[9]*ey-v[10]};
    const float n=std::sqrt(Dot(d,d));d={d.x/n,d.y/n,d.z/n};
    const float a=yaw*0.01745329252F,cs=std::cos(a),sn=std::sin(a);
    return {cs*d.x-sn*d.z,d.y,sn*d.x+cs*d.z};
}
Vec Shade(const Asset& a,const Settings& s,Vec d,Vec fog,bool fog_enabled) noexcept {
    Vec horizon=a.horizon;
    if(fog_enabled&&Color(fog))horizon=Mix(horizon,fog,s.fog_match);
    const float h=d.y-s.horizon_height;
    const float t=Clamp(std::abs(h)/s.horizon_width);
    Vec color=Mix(horizon,h>=0?a.zenith:a.nadir,t*t*(3-2*t));
    const float glow=std::pow(Clamp(Dot(d,a.sun)),24.0F)*s.sun*0.55F;
    color=Mix(color,a.sun_color,glow*Clamp(h/s.horizon_width));
    float cloud=0;
    for(const auto& c:a.clouds){
        const float facing=Dot(d,c.direction);
        if(facing<=0)continue;
        const Vec up{c.direction.y*c.right.z-c.direction.z*c.right.y,
            c.direction.z*c.right.x-c.direction.x*c.right.z,
            c.direction.x*c.right.y-c.direction.y*c.right.x};
        const float x=Dot(d,c.right)/c.width,y=Dot(d,up)/c.height;
        const float ellipse=Clamp(1-x*x-y*y);
        cloud=std::max(cloud,ellipse*ellipse*c.opacity*s.clouds);
    }
    color=Mix(color,a.cloud_color,cloud*Clamp(h/s.horizon_width));
    // Preserve the fog seam at zero elevation while scaling the appearance above it.
    const float gain=1+(s.intensity-1)*t;
    return {Clamp(color.x*gain),Clamp(color.y*gain),Clamp(color.z*gain)};
}
void Authority::Upload(const float* matrix,std::uintptr_t owner,std::uint64_t epoch) noexcept {
    Reset();if(!matrix||!owner||!epoch)return;
    std::memcpy(view.data(),matrix,sizeof(float)*16);context=owner;generation=epoch;fresh=true;
}
bool Authority::Consume(const GraphicsCameraState* camera,std::uintptr_t owner,std::uint64_t epoch,bool scene) noexcept {
    const bool valid=fresh&&scene&&camera&&context==owner&&owner&&generation==epoch
        &&!std::memcmp(view.data(),camera->view_matrix,sizeof(camera->view_matrix));
    fresh=false;painted=false;return valid;
}
}
