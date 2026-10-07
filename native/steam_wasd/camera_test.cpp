#include "controls.h"
#include "camera_fixture.h"
#include <cstdio>
#include <cstdlib>
#include <limits>
using namespace steam_wasd;
void check(bool value,const char* label) {if(!value){fprintf(stderr,"FAIL: %s\n",label);exit(1);}}
bool near(Direction a,Direction b) {return std::hypot(a.x-b.x,a.z-b.z)<0.0002F;}
int main() {
    unsigned cases=0;
    for(int degrees=0;degrees<360;degrees+=5) for(int pitch:{0,15,45,80,90})
    for(double scale:{0.00001,0.001,0.1}) for(bool mirrored:{false,true}) {
        auto f=test::camera(degrees*3.141592653589793/180,pitch*3.141592653589793/180,scale,mirrored);
        auto b=camera_basis(f.matrix,f.eye);
        check(b.valid,"rendered camera admitted");
        check(near(direction(w,b),f.forward),"W follows rendered forward across orbit/pitch/zoom");
        check(near(direction(d,b),f.right),"D follows screen-right, including handedness");
        check(near(direction(s,b),{-f.forward.x,-f.forward.z}),"S reverses rendered forward");
        check(near(direction(a,b),{-f.right.x,-f.right.z}),"A reverses screen-right");
        check(std::abs(std::hypot(direction(w|d,b).x,direction(w|d,b).z)-1)<0.00001F,"camera diagonal remains normalized");
        ++cases;
    }
    auto f=test::camera(0,0.5,0.001);auto b=camera_basis(f.matrix,f.eye);
    Controls c;c.sample(0,b,true,true);check(c.sample(w,b,true,true).steer,"moving owner");
    auto tracked=test::camera(1.57079632679,0.5,0.001);auto changed=camera_basis(tracked.matrix,tracked.eye);
    check(near(c.sample(w,changed,true,true).vector,tracked.forward),"held W follows auto-track's rendered quarter-turn");
    check(c.sample(w,{},true,true).stop,"bad matrix stops owned movement");
    check(!c.sample(w,b,true,true).steer,"good camera cannot resume held input after failure");
    check(!camera_basis({},f.eye).valid,"zero matrix rejected");
    f.matrix[0]=std::numeric_limits<float>::quiet_NaN();check(!camera_basis(f.matrix,f.eye).valid,"NaN rejected");
    f=test::camera(0,0,0.001);f.matrix[0]=f.matrix[1]=f.matrix[2]=0;check(!camera_basis(f.matrix,f.eye).valid,"collapsed screen axis rejected");
    printf("%u camera combinations and tracking/invalid-view boundary tests passed.\n",cases);
}
