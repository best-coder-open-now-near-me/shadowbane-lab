#include "controls.h"
#include <cstdio>
#include <cstdlib>
using namespace steam_wasd;
void check(bool value, const char* label) { if (!value) { std::fprintf(stderr, "FAIL: %s\n", label); std::exit(1); } }
int main() {
    Controls c;
    check(!c.sample(w, 0, true, true).steer, "startup held key cannot move");
    c.sample(0, 0, true, true);
    check(c.sample(w, 0, true, true).steer, "neutral arms movement");
    check(c.sample(0, 0, true, true).stop, "release requests stop once");
    check(!c.sample(0, 0, true, true).stop, "no duplicate stop");
    c.sample(w, 0, true, true);
    check(c.sample(w, 0, false, true).stop, "chat or focus loss stops owner");
    check(!c.sample(w, 0, true, true).steer, "held key after focus cannot resume");
    c.sample(0, 0, true, true); c.sample(w, 0, true, true);
    auto scene = c.sample(w, 0, true, false);
    check(!scene.steer && !scene.stop, "new scene receives no stale command");
    c.sample(0, 0, true, true); c.sample(w, 0, true, true);
    check(c.sample(w|s, 0, true, true).stop, "opposing keys stop");
    auto v = direction(w|d, 0);
    check(std::abs(std::hypot(v.x,v.z)-1) < 0.00001F, "diagonal normalized");
    check(v.x > 0 && v.z < 0, "camera forward and right basis");
    check(direction(w|s|a|d, 1).x == 0, "all opposing keys cancel");
    check(direction(w, INFINITY).x == 0, "nonfinite camera rejected");
    puts("Steam WASD control boundary tests passed.");
}
