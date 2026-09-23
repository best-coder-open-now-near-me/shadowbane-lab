#include "selected_cue.h"
#undef NDEBUG
#include <cassert>
#include <limits>
using namespace wonderbane::extension;
int main() {
    cue::Tracker t;
    cue::Identity id{1, 2, 3, 4, 5};
    GraphicsCameraState c{};
    c.viewport[2] = 800; c.viewport[3] = 600; c.forward[2] = -1;
    for (int i = 0; i < 4; ++i) c.view_matrix[i*5] = 1;
    c.projection_matrix[0] = 1; c.projection_matrix[5] = 1;
    c.projection_matrix[10] = -1.002F; c.projection_matrix[11] = -1;
    c.projection_matrix[14] = -0.2002F;
    float p[]{0, 0, -10};
    assert(!t.Update(id,p,&c,true).offscreen);
    p[0]=11; auto d=t.Update(id,p,&c,true); assert(d.offscreen && d.turn==1);
    p[0]=10; assert(t.Update(id,p,&c,true).offscreen);
    p[0]=9.5F; assert(!t.Update(id,p,&c,true).offscreen);
    p[0]=-11; d=t.Update(id,p,&c,true); assert(d.offscreen && d.turn==-1);
    p[0]=-0.1F; p[2]=10; assert(t.Update(id,p,&c,true).turn==-1);
    p[0]=0.1F; assert(t.Update(id,p,&c,true).turn==-1);
    p[0]=1; assert(t.Update(id,p,&c,true).turn==1);
    p[0]=-0.1F; ++id.uuid; assert(t.Update(id,p,&c,true).turn==-1);
    assert(!t.Update({},p,&c,true).available);
    assert(!t.Update(id,p,nullptr,true).available);
    assert(!t.Update(id,p,&c,false).available);
    p[0]=0.1F; assert(t.Update(id,p,&c,true).turn==1);
    p[0]=std::numeric_limits<float>::quiet_NaN(); assert(!t.Update(id,p,&c,true).available);
    p[0]=0; p[1]=11; p[2]=-10;
    d=t.Update(id,p,&c,true); assert(d.offscreen && d.turn==0);
    c.forward[2]=0; assert(!t.Update(id,p,&c,true).available);
    cue::Settings s{}; assert(cue::ValidSettings(s));
    s.radius=13; assert(!cue::ValidSettings(s));
    s.radius=5; s.opacity=std::numeric_limits<float>::infinity(); assert(!cue::ValidSettings(s));
}
