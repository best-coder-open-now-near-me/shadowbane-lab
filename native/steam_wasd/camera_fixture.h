#pragma once
#include "camera.h"
namespace steam_wasd::test {
struct CameraFixture { CameraMatrix matrix; CameraPoint eye; Direction forward,right; };
inline CameraFixture camera(double angle,double pitch,double scale,bool mirrored=false) {
    const double sn=std::sin(angle),cs=std::cos(angle),sp=std::sin(pitch),cp=std::cos(pitch);
    CameraPoint forward{sn*cp,-sp,-cs*cp},right{cs,0,sn},down{-sn*sp,-cp,cs*sp};
    CameraFixture out{};out.eye={90000.25,40.75,-50000.5};
    out.forward={float(sn),float(-cs)};out.right={float(cs),float(sn)};
    if(mirrored) {right={-right.x,0,-right.z};out.right={-out.right.x,-out.right.z};}
    const double eye[3]={out.eye.x,out.eye.y,out.eye.z};
    const double f[3]={forward.x,forward.y,forward.z},r[3]={right.x,right.y,right.z},d[3]={down.x,down.y,down.z};
    for(unsigned i=0;i<3;++i) {
        out.matrix[i]=float(r[i]*scale);out.matrix[4+i]=float(d[i]*scale);
        out.matrix[8+i]=float(-0.249*eye[i]);
        out.matrix[12+i]=float(0.25*eye[i]+f[i]-r[i]*0.8-d[i]*0.5);
    }
    out.matrix[11]=-0.249F;out.matrix[15]=0.25F;
    return out;
}
}
