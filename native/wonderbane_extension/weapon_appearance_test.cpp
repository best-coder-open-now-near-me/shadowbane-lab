#include <Windows.h>
#include <gl/GL.h>
#include "effects.h"
#include <array>
#include <cmath>
#undef NDEBUG
#include <cassert>
namespace {
bool query_safe=true;float yscale=1.F,saved=1.F;int pushes=0,pops=0,mock_attrs=0;
HGLRC current=reinterpret_cast<HGLRC>(1);
void APIENTRY GetInt(GLenum name,GLint* v){
    *v=name==GL_MATRIX_MODE?GL_MODELVIEW:(name==GL_MAX_MODELVIEW_STACK_DEPTH||name==GL_MAX_ATTRIB_STACK_DEPTH?16:1);
}
void APIENTRY PushMatrix(){++pushes;saved=yscale;}
void APIENTRY PopMatrix(){++pops;yscale=saved;}
void APIENTRY PushAttrib(GLbitfield){++mock_attrs;}
void APIENTRY PopAttrib(){--mock_attrs;}
void APIENTRY Enable(GLenum){}
void APIENTRY Scale(GLfloat x,GLfloat y,GLfloat z){assert(x==1.F&&z==1.F);yscale*=y;}
HGLRC WINAPI Context(){return current;}
wonderbane::extension::effects::Attachment actor{};
}
namespace wonderbane::extension {
bool AreNativeDrawQueriesSafe() noexcept{return query_safe;}
namespace effects {
Attachment Resolve(Reader,void*,std::uint32_t,std::uint32_t) noexcept{return actor;}
bool SameIdentity(const Attachment& a,const Attachment& b) noexcept{return a.valid&&b.valid&&a.actor==b.actor&&a.uuid==b.uuid;}
}}
#define glGetIntegerv GetInt
#define glPushMatrix PushMatrix
#define glPopMatrix PopMatrix
#define glPushAttrib PushAttrib
#define glPopAttrib PopAttrib
#define glEnable Enable
#define glScalef Scale
#define wglGetCurrentContext Context
#include "weapon_appearance.cpp"
int main(){
 using namespace wonderbane::extension::weapon;
 std::array<std::uint32_t,128> player{},root{},left{},right{},foreign{},submission{};
 auto ptr=[](auto& v){return static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(v.data()));};
 std::array<std::uint32_t,2> children{ptr(left),ptr(right)};
 player[0xc0/4]=ptr(root);root[0]=left[0]=right[0]=foreign[0]=0x1549dbc;
 root[0x3c/4]=ptr(children);root[0x40/4]=ptr(children)+8;
 left[4]=right[4]=foreign[4]=9996101;
 actor.valid=true;actor.actor=ptr(player);actor.uuid=7;
 Start(0x400000);assert(control);
 control->length=.85F;control->desired=2;BeginScene(true);
 assert(control->matches==2&&control->applied==2&&WantsDraws());
 submission[7]=ptr(left);
 {RenderScope scope(submission.data());{DrawScale draw;assert(std::abs(yscale-.85F)<1e-6F);{DrawScale nested;assert(pushes==1);}}
  assert(yscale==1.F&&pushes==pops&&mock_attrs==0);}
 submission[7]=ptr(right);{RenderScope scope(submission.data());DrawScale draw;assert(yscale==.85F);}
 assert(yscale==1.F);
 const int before=pushes;submission[7]=ptr(foreign);{RenderScope scope(submission.data());DrawScale draw;assert(pushes==before);}
 submission[7]=ptr(left);++actor.uuid;{RenderScope scope(submission.data());DrawScale draw;assert(pushes==before);}--actor.uuid;
 query_safe=false;{RenderScope scope(submission.data());DrawScale draw;assert(pushes==before);}query_safe=true;
 current=reinterpret_cast<HGLRC>(2);{RenderScope scope(submission.data());DrawScale draw;assert(pushes==before);}current=reinterpret_cast<HGLRC>(1);
 control->length=1.F;control->desired=4;BeginScene(true);{RenderScope scope(submission.data());DrawScale draw;assert(pushes==before);}
 for(float value:{.6F,1.2F}){control->length=value;control->desired+=2;BeginScene(true);{RenderScope scope(submission.data());DrawScale draw;assert(yscale==value);}assert(yscale==1.F);}
 control->length=NAN;BeginScene(true);assert(control->error==ERROR_INVALID_DATA&&!WantsDraws());
 control->length=.85F;control->desired|=1;BeginScene(true);assert(control->error==ERROR_INVALID_DATA);++control->desired;
 children[1]=ptr(root);BeginScene(true);assert(!WantsDraws()&&control->error==ERROR_NOT_FOUND);children[1]=ptr(right);
 BeginScene(true);EndScene();{RenderScope scope(submission.data());DrawScale draw;assert(yscale==1.F);}
 Stop();assert(!control&&pushes==pops&&mock_attrs==0);
}
