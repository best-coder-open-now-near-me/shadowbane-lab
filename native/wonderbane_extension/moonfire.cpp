#include "moonfire.h"
#include "scene_draw.h"
#include <Windows.h>
#include <gl/GL.h>
#include <array>
#include <algorithm>
#include <cmath>
namespace wonderbane::extension::weapon {
namespace {
struct Point {float x,y,z;};
struct Draw {
    FireSettings s;double seconds;std::array<float,16> matrix;
    bool scissor=false,stencil=false;std::array<bool,6> clip{};
    Point At(float x,float y,float z=0) const noexcept {
        const auto& m=matrix;
        return {m[0]*x+m[4]*y+m[8]*z+m[12],m[1]*x+m[5]*y+m[9]*z+m[13],m[2]*x+m[6]*y+m[10]*z+m[14]};
    }
};
void Vertex(Point p,float a,bool core=false) noexcept {
    glColor4f(core?1.F:.87F,core?1.F:.94F,1.F,a);glVertex3f(p.x,p.y,p.z);
}
void Paint(void* raw) noexcept {
    const auto& d=*static_cast<Draw*>(raw);const auto& s=d.s;const auto& m=d.matrix;
    const float scale=std::sqrt(m[0]*m[0]+m[1]*m[1]+m[2]*m[2]);
    const float projected=std::hypot(m[4],m[5]);
    const float ax=projected>.00001F?m[4]/projected:0.F,ay=projected>.00001F?m[5]/projected:1.F;
    const float bx=ay,by=-ax;
    glLoadIdentity();glShadeModel(GL_SMOOTH);
    // Keep native clipping. The shared state guard restores every changed value.
    if(d.scissor)glEnable(GL_SCISSOR_TEST);if(d.stencil){glEnable(GL_STENCIL_TEST);glStencilMask(0);}
    for(unsigned n=0;n<6;++n)if(d.clip[n])glEnable(GL_CLIP_PLANE0+n);
    // A narrow additive ribbon, with feathered edges and tip/root fade.
    glBlendFunc(GL_SRC_ALPHA,GL_ONE);
    glBegin(GL_TRIANGLES);
    constexpr unsigned slices=24,bands=12;
    for(unsigned j=0;j<slices;++j)for(unsigned i=0;i<bands;++i){
        const auto ribbon=[&](unsigned u,unsigned v){
            const float x=static_cast<float>(u)/bands*2.F-1.F;
            const float f=static_cast<float>(v)/slices;
            Point p=d.At(-.003F+.017F*f,.18F+2.21F*f);
            const float radius=.16F*s.width*scale;
            p.x+=bx*radius*x;p.y+=by*radius*x;p.z+=.05F*scale;
            const float edge=std::max(0.F,1.F-std::pow(std::abs(x),8.F));
            const float ends=std::min(1.F,std::min(f,1.F-f)*12.F);
            glColor4f(.72F,.86F,1.F,std::exp(-5.F*x*x)*edge*ends*s.strength*.55F);
            glVertex3f(p.x,p.y,p.z);
        };
        ribbon(i,j);ribbon(i+1,j);ribbon(i+1,j+1);
        ribbon(i,j);ribbon(i+1,j+1);ribbon(i,j+1);
    }
    glEnd();glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);
    const auto diamond=[&](Point p,float width,float wave,float alpha){
        const float radius=width*(1.F+s.pulse*wave)*scale*.5F;
        p.z+=.05F*scale;
        const auto point=[&](unsigned n,float r){
            constexpr float corners[4][2]{{0,1},{1,0},{0,-1},{-1,0}};
            return Point{p.x+radius*r*(bx*corners[n][0]+ax*corners[n][1]),
                         p.y+radius*r*(by*corners[n][0]+ay*corners[n][1]),p.z};
        };
        for(unsigned n=0;n<4;++n){
            const unsigned next=(n+1)%4;
            Vertex(p,alpha,true);Vertex(point(n,.93F),alpha);Vertex(point(next,.93F),alpha);
            Vertex(point(n,.93F),alpha);Vertex(point(n,1.F),0);Vertex(point(next,1.F),0);
            Vertex(point(n,.93F),alpha);Vertex(point(next,1.F),0);Vertex(point(next,.93F),alpha);
        }
    };
    glBegin(GL_TRIANGLES);
    constexpr double tau=6.283185307179586;
    const float anchor=static_cast<float>(std::sin(d.seconds*tau/3.6));
    diamond(d.At(-.003F,.29F,.016F),.1404F*s.hilt,anchor,.8F+.08F*s.pulse/.35F*anchor);
    const float step=.108F*s.spacing;
    const auto count=static_cast<unsigned>((2.28F-.415F)/step)+1;
    for(unsigned i=0;i<count && i<64;++i){
        const float y=.415F+static_cast<float>(i)*step,fraction=(y-.415F)/(2.28F-.415F);
        const float wave=static_cast<float>(std::sin(d.seconds*tau/1.8-static_cast<double>(i)*.65));
        diamond(d.At(-.003F+.017F*fraction,y,.015F),.108F*s.size,wave,.66F+.12F*s.pulse/.35F*wave);
    }
    glEnd();
    // Model-space collar follows the blade rather than facing the camera.
    constexpr float rim[4][2]{{-.05F,-.014F},{.044F,-.014F},{.044F,.014F},{-.05F,.014F}};
    glBegin(GL_QUADS);
    for(unsigned n=0;n<4;++n){
        const auto next=(n+1)%4;
        Vertex(d.At(rim[n][0],.18F,rim[n][1]),.86F);
        Vertex(d.At(rim[next][0],.18F,rim[next][1]),.86F);
        Vertex(d.At(rim[next][0],.208F,rim[next][1]),.86F);
        Vertex(d.At(rim[n][0],.208F,rim[n][1]),.86F);
    }
    glEnd();
}
}
unsigned DrawMoonfire(const FireSettings& settings,double seconds) noexcept {
    if(!ValidFire(settings) || !settings.enabled || !std::isfinite(seconds))return 1;
    GLint mode=0,depth=0,render=0;GLboolean color[4]{};
    glGetIntegerv(GL_MATRIX_MODE,&mode);glGetIntegerv(GL_DEPTH_FUNC,&depth);glGetIntegerv(GL_RENDER_MODE,&render);
    glGetBooleanv(GL_COLOR_WRITEMASK,color);
    if(mode!=GL_MODELVIEW || render!=GL_RENDER || !glIsEnabled(GL_DEPTH_TEST)
        || (depth!=GL_LESS && depth!=GL_LEQUAL) || !color[0] || !color[1] || !color[2])return 2;
    const auto* version=reinterpret_cast<const char*>(glGetString(GL_VERSION));
    if(!version)return 2;
    if(version[0]>='2'){GLint program=-1;glGetIntegerv(0x8B8D,&program);if(program!=0)return 2;}
    Draw draw{settings,seconds,{}};glGetFloatv(GL_MODELVIEW_MATRIX,draw.matrix.data());
    for(const auto v:draw.matrix)if(!std::isfinite(v))return 2;
    const auto& m=draw.matrix;
    const float scale=std::sqrt(m[0]*m[0]+m[1]*m[1]+m[2]*m[2]);
    if(scale<.0001F || scale>100.F || std::abs(m[3])+std::abs(m[7])+std::abs(m[11])>1e-5F || std::abs(m[15]-1.F)>1e-5F)return 2;
    draw.scissor=glIsEnabled(GL_SCISSOR_TEST)!=0;draw.stencil=glIsEnabled(GL_STENCIL_TEST)!=0;
    for(unsigned n=0;n<6;++n)draw.clip[n]=glIsEnabled(GL_CLIP_PLANE0+n)!=0;
    return RenderSceneGeometry(nullptr,Paint,&draw)?0:3;
}
}
