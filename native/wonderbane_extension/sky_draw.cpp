#include "sky.h"
#include "scene_draw.h"
#include <gl/GL.h>
namespace wonderbane::extension::sky {
namespace {
struct Draw { const Asset& asset; const Settings& settings; const GraphicsCameraState& camera; Vec fog;bool fog_enabled; };
void Paint(void* pointer) noexcept {
    const auto& d=*static_cast<Draw*>(pointer);
    glDisable(GL_DEPTH_TEST);glDepthMask(GL_FALSE);glDisable(GL_BLEND);
    glMatrixMode(GL_PROJECTION);glLoadIdentity();glMatrixMode(GL_MODELVIEW);glLoadIdentity();
    glShadeModel(GL_SMOOTH);
    constexpr int columns=64,rows=32;
    // A bounded screen mesh samples an authored directional field. Translation is
    // absent from Ray; the camera rotation and asymmetric projection remain exact.
    for(int row=0;row<rows;++row){
        glBegin(GL_TRIANGLE_STRIP);
        for(int column=0;column<=columns;++column)for(int edge=0;edge<2;++edge){
            const float x=-1+2.0F*column/columns,y=-1+2.0F*(row+edge)/rows;
            const auto rgb=Shade(d.asset,d.settings,Ray(d.camera,x,y,d.settings.orientation),d.fog,d.fog_enabled);
            glColor4f(rgb.x,rgb.y,rgb.z,1);glVertex2f(x,y);
        }
        glEnd();
    }
}
}
bool Render(const Asset& asset,const Settings& settings,const GraphicsCameraState& camera) noexcept {
    if(!Valid(settings)||!settings.enabled||!ValidAsset(asset))return false;
    GLint buffer=0;glGetIntegerv(GL_DRAW_BUFFER,&buffer);
    if(buffer!=GL_BACK)return false;
    float fog[4]{};glGetFloatv(GL_FOG_COLOR,fog);
    Draw draw{asset,settings,camera,{fog[0],fog[1],fog[2]},glIsEnabled(GL_FOG)!=0};
    return RenderSceneGeometry(&camera,Paint,&draw);
}
}
