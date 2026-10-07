#include "controls.h"
#include <cstdio>
#include <cstdlib>
using namespace steam_wasd;
void check(bool value, const char* label) { if (!value) { std::fprintf(stderr, "FAIL: %s\n", label); std::exit(1); } }
int main() {
    Controls c;
    const CameraBasis basis{{0,-1},{1,0},true};
    check(!c.sample(w, basis, true, true).steer, "startup held key cannot move");
    c.sample(0, basis, true, true);
    check(c.sample(w, basis, true, true).steer, "neutral arms movement");
    check(c.sample(0, basis, true, true).stop, "release requests stop once");
    check(!c.sample(0, basis, true, true).stop, "no duplicate stop");
    c.sample(w, basis, true, true);
    check(c.sample(w, basis, false, true).stop, "chat or focus loss stops owner");
    check(!c.sample(w, basis, true, true).steer, "held key after focus cannot resume");
    c.sample(0, basis, true, true); c.sample(w, basis, true, true);
    auto scene = c.sample(w, basis, true, false);
    check(!scene.steer && !scene.stop, "new scene receives no stale command");
    c.sample(0, basis, true, true); c.sample(w, basis, true, true);
    check(c.sample(w|s, basis, true, true).stop, "opposing keys stop");
    auto v = direction(w|d, basis);
    check(std::abs(std::hypot(v.x,v.z)-1) < 0.00001F, "diagonal normalized");
    check(v.x > 0 && v.z < 0, "camera forward and right basis");
    check(direction(w|s|a|d, basis).x == 0, "all opposing keys cancel");
    check(direction(w, {}).x == 0, "invalid camera rejected");
    c.sample(0,basis,true,true); c.sample(w,basis,true,true);
    check(c.sample(w,{},true,true).stop, "invalid camera stops movement");
    check(!c.sample(w,basis,true,true).steer, "camera recovery requires key release");
    puts("Steam WASD control boundary tests passed.");
}
