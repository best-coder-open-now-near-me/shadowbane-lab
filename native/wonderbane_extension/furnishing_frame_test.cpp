#include "furnishing_frame.h"
#undef NDEBUG
#include <cassert>
using wonderbane::extension::furnishing::FrameGate;
int main() {
    FrameGate f; assert(!f.Enter()&&!f.Leave(true));
    f.Clear(true); const auto one=f.Enter(); assert(one); assert(!f.Enter()); assert(!f.Leave(true)); assert(f.Leave(true)==one);
    assert(!f.Enter()&&!f.Leave(true)); f.Clear(true); f.Clear(false); assert(!f.Enter()&&!f.Leave(true));
    f.Clear(true); const auto two=f.Enter(); assert(two>one); f.Invalidate(); assert(!f.Leave(true)&&f.Broken());
    f.Clear(true); assert(!f.Enter()&&!f.Leave(true));
    FrameGate missing; assert(!missing.Leave(true)&&missing.Broken());
    FrameGate shader; shader.Clear(true); assert(shader.Enter()); assert(!shader.Leave(false)&&shader.Broken());
    FrameGate nested_clear; nested_clear.Clear(true); assert(nested_clear.Enter()); nested_clear.Clear(true);
    assert(!nested_clear.Leave(true)&&nested_clear.Broken());
    FrameGate stopped; stopped.Clear(true); stopped.Invalidate(); assert(!stopped.Enter()&&!stopped.Leave(true)&&!stopped.Broken());
}
