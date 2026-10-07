#include "controls.h"
#include "scene.h"
#include "parent_frame.h"
#include <cstdio>
#include <cstdlib>
using namespace steam_wasd;
void check(bool value,const char* label){if(!value){fprintf(stderr,"FAIL: %s\n",label);exit(1);}}
int main(){
    CameraBasis basis{{0,-1},{1,0},true};Controls controls;
    Scene owner{1,2,3,0,4}, observed=owner, inside{1,2,3,100,4};
    controls.sample(0,basis,true,true);controls.sample(w,basis,true,true);
    check(rebase(owner,inside)==Rebase::parent_changed,"enter structure rebases same actor");
    check(owner.parent==100 && same(owner,inside),"new frame owns subsequent destinations");
    check(controls.sample(w,basis,true,same_identity(observed,inside)).steer,"held W survives entering structure");
    observed=inside;Scene outside{1,2,3,0,4};
    check(rebase(owner,outside)==Rebase::parent_changed,"exit structure rebases");
    check(controls.sample(0,basis,true,same_identity(observed,outside)).stop,"release exactly on exit still stops owner");
    controls.sample(w,basis,true,true);Scene replacement{9,2,3,100,10};
    check(rebase(owner,replacement)==Rebase::retired,"replacement actor never inherits stop authority");
    auto result=controls.sample(w,basis,true,same_identity(owner,replacement));
    check(!result.stop&&!result.steer,"held key cannot command replacement actor");
    check(!controls.sample(w,basis,true,true).steer,"replacement requires neutral sample");
    auto old=owner;Scene world=owner;world.world=8;
    check(rebase(owner,world)==Rebase::retired && same(old,owner),"world transition cannot mutate ownership");
    CameraBasis scaled{{0,-2},{0.5F,0},true};auto d=direction(w|steam_wasd::d,scaled);
    check(std::abs(std::hypot(d.x,d.z)-1)<1e-6F && std::abs(d.z/d.x+4)<1e-5F,"inverse scale preserved until normalized key combination");
    ParentTransform bad{};check(!valid_transform(bad),"singular parent rejected");
    bad.rotation={1,0,0,0};bad.scale={1,1,1};check(valid_transform(bad),"identity parent admitted");
    bad.scale.z=0;check(!valid_transform(bad),"collapsed parent scale rejected");
    puts("Parent entry/exit, boundary release, replacement ownership and scaled direction tests passed.");
}
