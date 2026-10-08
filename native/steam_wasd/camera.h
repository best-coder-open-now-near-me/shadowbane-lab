#pragma once
#include <array>
#include <cmath>
namespace steam_wasd {
struct Direction { float x{}, z{}; };
struct CameraPoint { double x{}, y{}, z{}; };
struct CameraBasis { Direction forward{}, right{}; bool valid{}; };
using CameraMatrix = std::array<float,16>;
inline CameraPoint subtract(CameraPoint a,CameraPoint b) { return {a.x-b.x,a.y-b.y,a.z-b.z}; }
inline double dot(CameraPoint a,CameraPoint b) { return a.x*b.x+a.y*b.y+a.z*b.z; }
inline bool finite(CameraPoint p) { return std::isfinite(p.x)&&std::isfinite(p.y)&&std::isfinite(p.z); }
inline bool normalize(CameraPoint& p) {
    const double length=std::sqrt(dot(p,p));
    if(!std::isfinite(length) || length<1e-10) return false;
    p={p.x/length,p.y/length,p.z/length}; return true;
}
// Matches native 235df0 -> 191880 -> c62160: column-major matrix times
// [screen x, screen y, depth, 1], then homogeneous division. Double scratch
// avoids losing pixel-sized differences at the world's large coordinates.
inline bool unproject(const CameraMatrix& m,double x,double y,double depth,CameraPoint& out) {
    std::array<double,4> h{};
    for(unsigned row=0;row<4;++row) h[row]=m[row]*x+m[row+4]*y+m[row+8]*depth+m[row+12];
    if(!std::isfinite(h[3]) || std::abs(h[3])<1e-10) return false;
    out={h[0]/h[3],h[1]/h[3],h[2]/h[3]}; return finite(out);
}
inline CameraBasis camera_basis(const CameraMatrix& matrix,CameraPoint eye) {
    if(!finite(eye)) return {};
    for(float v:matrix) if(!std::isfinite(v)) return {};
    CameraPoint origin{},side{},down{};
    if(!unproject(matrix,0,0,0.5,origin) || !unproject(matrix,256,0,0.5,side)
        || !unproject(matrix,0,256,0.5,down)) return {};
    side=subtract(side,origin); down=subtract(down,origin);
    if(!normalize(side) || !normalize(down)) return {};
    CameraPoint view{side.y*down.z-side.z*down.y,side.z*down.x-side.x*down.z,side.x*down.y-side.y*down.x};
    if(!normalize(view)) return {};
    const double facing=dot(view,subtract(origin,eye));
    if(!std::isfinite(facing) || std::abs(facing)<1e-6) return {};
    if(facing<0) view={-view.x,-view.y,-view.z};
    double length=std::hypot(view.x,view.z);
    // Exactly overhead: screen-up still defines an unambiguous ground direction.
    if(length<1e-4) {view={-down.x,0,-down.z};length=std::hypot(view.x,view.z);}
    if(!std::isfinite(length) || length<1e-6) return {};
    CameraBasis result{{float(view.x/length),float(view.z/length)},{},true};
    result.right={-result.forward.z,result.forward.x};
    const double right_sign=result.right.x*side.x+result.right.z*side.z;
    if(!std::isfinite(right_sign) || std::abs(right_sign)<1e-6) return {};
    if(right_sign<0) result.right={-result.right.x,-result.right.z};
    return result;
}
}
