#include "effects_draw.h"
#include "scene_draw.h"
#include <gl/GL.h>
namespace wonderbane::extension {
bool RenderEffectsGeometry(const effects::Config& config, const effects::Geometry& geometry,
                           const GraphicsCameraState& camera) noexcept {
    if (!effects::Validate(config) || !(config.flags&1U) || !geometry.count
        || geometry.count>effects::kQuads) return false;
    struct Draw { const effects::Config& config; const effects::Geometry& geometry; };
    Draw args{config,geometry};
    return RenderSceneGeometry(&camera,[](void* raw) noexcept {
        const auto& args=*static_cast<Draw*>(raw);
        if (args.config.flags&8U) glBlendFunc(GL_SRC_ALPHA,GL_ONE);
        glBegin(GL_QUADS);
        for (std::size_t i=0;i<args.geometry.count;++i) {
            const auto& q=args.geometry.quads[i];
            glColor4f(args.config.red,args.config.green,args.config.blue,q.alpha);
            for (const auto& p:q.points) glVertex3f(p.x,p.y,p.z);
        }
        glEnd();
    },&args);
}
}
