#include "furnishing_pose.h"
#include <cmath>
namespace wonderbane::extension::furnishing {
bool LayoutContains(const Selection& s, int x, int y) noexcept {
    if (s.dimensions[0]<=0 || s.dimensions[1]<=0 || !std::isfinite(s.zoom) || s.zoom<=0
        || !std::isfinite(s.layout_scale) || s.layout_scale<=0
        || !std::isfinite(s.offset[0]) || !std::isfinite(s.offset[1])) { return false; }
    const double left=double(s.rectangle[0])+s.offset[0], top=double(s.rectangle[1])+s.offset[1];
    return x>=left && x<=left+s.dimensions[0] && y>=top && y<=top+s.dimensions[1];
}
bool CandidatePose(const Selection& s, const std::array<float,3>& p, unsigned turns, Transform& out) noexcept {
    out={}; const auto& b=s.building_world;
    if (!ValidTransform(b) || b[7]<=0 || b[7]!=b[8] || b[7]!=b[9]) { return false; }
    for (float value:p) { if (!std::isfinite(value)) { return false; } }
    // q * (scale * p) * inverse(q), followed by building translation.
    const double x=double(p[0])*b[7], y=double(p[1])*b[8], z=double(p[2])*b[9];
    const double w=b[3], qx=b[4], qy=b[5], qz=b[6];
    const double tx=2*(qy*z-qz*y), ty=2*(qz*x-qx*z), tz=2*(qx*y-qy*x);
    Transform candidate{};
    candidate[0]=static_cast<float>(b[0]+x+w*tx+qy*tz-qz*ty);
    candidate[1]=static_cast<float>(b[1]+y+w*ty+qz*tx-qx*tz);
    candidate[2]=static_cast<float>(b[2]+z+w*tz+qx*ty-qy*tx);
    constexpr double half_pi=1.57079632679489661923;
    const double angle=-double(turns%4)*half_pi/2, cw=std::cos(angle), cy=std::sin(angle);
    candidate[3]=static_cast<float>(w*cw-qy*cy);
    candidate[4]=static_cast<float>(qx*cw-qz*cy);
    candidate[5]=static_cast<float>(w*cy+qy*cw);
    candidate[6]=static_cast<float>(qx*cy+qz*cw);
    // Normalize the product so a tolerated native quaternion error does not
    // compound across successive private child compositions.
    const double norm=std::sqrt(double(candidate[3])*candidate[3]+double(candidate[4])*candidate[4]
        +double(candidate[5])*candidate[5]+double(candidate[6])*candidate[6]);
    for (unsigned i=3;i<7;++i) { candidate[i]=static_cast<float>(candidate[i]/norm); }
    candidate[7]=b[7]; candidate[8]=b[8]; candidate[9]=b[9];
    if (!ValidTransform(candidate)) { return false; } out=candidate; return true;
}
}
