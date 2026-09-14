#include "door_targeting.h"
#include <iostream>
#include <limits>
using namespace wonderbane::extension::movement;
namespace {
int failures = 0;
void Check(bool ok, const char* message) { if (!ok) { std::cerr << message << '\n'; ++failures; } }
DoorGeometry Door(unsigned id, float x, float z, bool clear = true) { return {{1,id},{x,0,z},true,clear}; }
unsigned Chosen(const DoorRanking& rank) { const auto c = rank.Choice(); return c ? c->door.identity[1] : 0; }
}
int main() {
    DoorRanking forward({}, {0,-1});
    forward.Consider(Door(1,0,1)); forward.Consider(Door(2,0,-7));
    auto upstairs=Door(3,0,-1); upstairs.center.y=3; forward.Consider(upstairs);
    forward.Consider(Door(4,2,-1)); Check(!forward.Choice(),"behind, far, upstairs and side doors excluded");
    forward.Consider(Door(5,0,-1,false)); Check(!forward.Choice(),"blocked aligned door excluded");
    forward.Consider(Door(6,1,-2)); Check(Chosen(forward)==6,"forgiving cone accepts off-axis door");
    forward.Consider(Door(7,0,-1.5F)); Check(Chosen(forward)==7,"closer aligned eligible door preferred");
    DoorRanking rotated({}, {1,0}); rotated.Consider(Door(7,0,-1.5F)); rotated.Consider(Door(8,2,0));
    Check(Chosen(rotated)==8,"character rotation changes target independently of camera");
    DoorRanking translated({100,10,-200}, {0,-9});
    auto local=Door(9,101,-202);local.center.y=10;translated.Consider(local);
    Check(Chosen(translated)==9,"world translation and forward magnitude preserve ranking");
    DoorRanking tie({}, {0,-1});tie.Consider(Door(11,1,-2));tie.Consider(Door(10,-1,-2));
    Check(Chosen(tie)==10,"equal scores have stable identity ordering");
    DoorRanking stable({}, {0,-1}, {1,11});stable.Consider(Door(11,1,-2));stable.Consider(Door(10,-1,-2));
    Check(Chosen(stable)==11,"near-equivalent previous target remains stable");
    DoorRanking blocked({}, {0,-1}, {1,11});blocked.Consider(Door(11,1,-2,false));blocked.Consider(Door(10,-1,-2));
    Check(Chosen(blocked)==10,"previous target cannot survive new obstruction");
    DoorRanking siblings({}, {0,-1});
    auto first=Door(12,0,-3); first.identity={1,12,0,1};
    auto second=Door(12,0,-2); second.identity={1,12,0,2};
    siblings.Consider(first); siblings.Consider(second);
    Check(siblings.Choice() && siblings.Choice()->door.identity==second.identity,"doors sharing a structure retain distinct identities");
    DoorRanking invalid({}, {});invalid.Consider(Door(1,0,-1));Check(!invalid.Choice(),"invalid facing fails closed");
    DoorRanking malformed({}, {0,-1});auto bad=Door(1,0,-1);bad.center.x=std::numeric_limits<float>::quiet_NaN();
    malformed.Consider(bad);bad=Door(2,0,-1);bad.eligible=false;malformed.Consider(bad);
    Check(!malformed.Choice(),"malformed or ineligible native observation rejected");
    return failures ? 1 : 0;
}
