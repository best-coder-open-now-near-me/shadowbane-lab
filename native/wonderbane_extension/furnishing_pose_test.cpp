#include "furnishing_pose.h"
#undef NDEBUG
#include <cassert>
#include <cmath>
#include <limits>
namespace f=wonderbane::extension::furnishing;
bool Near(float a,float b) { return std::abs(a-b)<0.0001f; }
int main() {
    f::Selection s{}; s.rectangle={100,200,600,600}; s.dimensions={400,400}; s.offset={64,54}; s.zoom=1; s.layout_scale=6.25f;
    assert(f::LayoutContains(s,164,254) && f::LayoutContains(s,564,654));
    assert(!f::LayoutContains(s,163,254) && !f::LayoutContains(s,164,655));
    s.rectangle[0]=200; assert(!f::LayoutContains(s,164,254)); s.zoom=0; assert(!f::LayoutContains(s,264,254));
    s.building_world={100,20,-100,1,0,0,0,1,1,1}; f::Transform pose{};
    assert(f::CandidatePose(s,{2,3,4},0,pose) && pose==f::Transform({102,23,-96,1,0,0,0,1,1,1}));
    assert(f::CandidatePose(s,{2,3,4},1,pose) && Near(pose[3],std::sqrt(0.5f)) && Near(pose[5],-std::sqrt(0.5f)));
    assert(f::CandidatePose(s,{2,3,4},4,pose) && pose[3]==1 && pose[5]==0);
    s.building_world={100,20,-100,std::sqrt(0.5f),0,std::sqrt(0.5f),0,2,2,2};
    assert(f::CandidatePose(s,{2,3,4},1,pose) && Near(pose[0],108) && Near(pose[1],26) && Near(pose[2],-104));
    assert(Near(pose[3],1) && Near(pose[5],0) && pose[7]==2);
    s.building_world[8]=1; assert(!f::CandidatePose(s,{2,3,4},0,pose) && pose==f::Transform{});
    s.building_world[8]=2;
    assert(!f::CandidatePose(s,{std::numeric_limits<float>::quiet_NaN(),0,0},0,pose));
    s.building_world[0]=std::numeric_limits<float>::max();
    assert(!f::CandidatePose(s,{std::numeric_limits<float>::max(),0,0},0,pose));
}
