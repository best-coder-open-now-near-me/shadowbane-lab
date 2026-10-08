#pragma once
#include "camera.h"
#include <cstddef>
namespace steam_wasd {
struct NativePoint { float x{},y{},z{}; };
// Same 40-byte world transform copied by native screen picking (a25fce).
// Quaternion order is w,x,y,z; native helpers own inversion and application.
struct ParentTransform { NativePoint position; std::array<float,4> rotation; NativePoint scale; };
static_assert(sizeof(ParentTransform)==40 && offsetof(ParentTransform,rotation)==12 && offsetof(ParentTransform,scale)==28);
using InvertTransform = ParentTransform*(*)(ParentTransform*);
using ApplyTransform = NativePoint*(*)(const ParentTransform*,NativePoint*,const NativePoint*);
inline bool valid_transform(const ParentTransform& t) {
    for(float v:{t.position.x,t.position.y,t.position.z,t.scale.x,t.scale.y,t.scale.z}) if(!std::isfinite(v)) return false;
    double norm=0;for(float v:t.rotation) {if(!std::isfinite(v)) return false;norm+=double(v)*v;}
    return norm>1e-12 && std::abs(t.scale.x)>1e-6F && std::abs(t.scale.y)>1e-6F && std::abs(t.scale.z)>1e-6F;
}
inline CameraBasis parent_basis(CameraBasis world,ParentTransform transform,InvertTransform invert,ApplyTransform apply) {
    if(!world.valid || !valid_transform(transform) || !invert || !apply) return {};
    // Directions have no translation. Removing it before native inversion also
    // avoids subtracting two large translated float positions to obtain a step.
    transform.position={};invert(&transform);
    if(!valid_transform(transform)) return {};
    NativePoint f{},r{},wf{world.forward.x,0,world.forward.z},wr{world.right.x,0,world.right.z};
    apply(&transform,&f,&wf);apply(&transform,&r,&wr);
    for(float v:{f.x,f.y,f.z,r.x,r.y,r.z}) if(!std::isfinite(v)) return {};
    const double fl=std::hypot(f.x,f.z),rl=std::hypot(r.x,r.z);
    const double area=double(f.x)*r.z-double(f.z)*r.x;
    if(!std::isfinite(fl) || !std::isfinite(rl) || !std::isfinite(area)
        || fl<1e-6 || rl<1e-6 || std::abs(area)/(fl*rl)<1e-6) return {};
    // Preserve the inverse scale between axes. Normalize after keys are combined,
    // so diagonal movement has the correct bearing and native look-ahead length.
    return {{f.x,f.z},{r.x,r.z},true};
}
}
