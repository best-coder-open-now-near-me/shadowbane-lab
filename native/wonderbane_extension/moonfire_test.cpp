#include "moonfire.h"
#include <Windows.h>
#include <gl/GL.h>
#include <array>
#include <vector>
#include <cstdio>
#include <cmath>
#include <algorithm>
#include <fstream>
#undef NDEBUG
#include <cassert>
namespace {
constexpr int width=256,height=512;
std::vector<unsigned char> Pixels(){std::vector<unsigned char> p(width*height*3);glReadPixels(0,0,width,height,GL_RGB,GL_UNSIGNED_BYTE,p.data());return p;}
std::vector<float> Depth(){std::vector<float> p(width*height);glReadPixels(0,0,width,height,GL_DEPTH_COMPONENT,GL_FLOAT,p.data());return p;}
std::array<float,40> State(){
 std::array<float,40> r{};glGetFloatv(GL_MODELVIEW_MATRIX,r.data());glGetFloatv(GL_PROJECTION_MATRIX,r.data()+16);
 glGetFloatv(GL_CURRENT_COLOR,r.data()+32);glGetFloatv(GL_DEPTH_FUNC,r.data()+36);glGetFloatv(GL_DEPTH_WRITEMASK,r.data()+37);
 r[38]=glIsEnabled(GL_BLEND);r[39]=glIsEnabled(GL_LIGHTING);return r;
}
}
int main(int argc,char** argv){
 using namespace wonderbane::extension::weapon;
 WNDCLASSW cls{};cls.style=CS_OWNDC;cls.lpfnWndProc=DefWindowProcW;cls.hInstance=GetModuleHandleW(nullptr);cls.lpszClassName=L"MoonfireQualification";
 assert(RegisterClassW(&cls));
 HWND window=CreateWindowW(cls.lpszClassName,L"Moonfire qualification",WS_POPUP,0,0,width,height,nullptr,nullptr,cls.hInstance,nullptr);assert(window);
 HDC dc=GetDC(window);PIXELFORMATDESCRIPTOR pfd{};pfd.nSize=sizeof(pfd);pfd.nVersion=1;
 pfd.dwFlags=PFD_DRAW_TO_WINDOW|PFD_SUPPORT_OPENGL;pfd.iPixelType=PFD_TYPE_RGBA;pfd.cColorBits=24;pfd.cDepthBits=24;pfd.cStencilBits=8;
 int format=ChoosePixelFormat(dc,&pfd);assert(format && SetPixelFormat(dc,format,&pfd));
 HGLRC context=wglCreateContext(dc);assert(context && wglMakeCurrent(dc,context));
 glViewport(0,0,width,height);glMatrixMode(GL_PROJECTION);glLoadIdentity();glOrtho(-.4,.4,-.2,2.6,-10,10);
 glMatrixMode(GL_MODELVIEW);glLoadIdentity();glEnable(GL_DEPTH_TEST);glDepthFunc(GL_LEQUAL);glDepthMask(GL_TRUE);
 glColor4f(.2F,.3F,.4F,.5F);glClearColor(0,0,0,0);glClearDepth(1);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT|GL_STENCIL_BUFFER_BIT);
 const auto before=State();const auto depth=Depth();FireSettings settings{};
 assert(DrawMoonfire(settings,0)==0);assert(State()==before);assert(Depth()==depth);assert(glGetError()==GL_NO_ERROR);
 const auto first=Pixels();assert(std::count_if(first.begin(),first.end(),[](auto c){return c>20;})>500);
 if(argc==2){std::ofstream out(argv[1],std::ios::binary);out<<"P6\n"<<width<<" "<<height<<"\n255\n";for(int y=height-1;y>=0;--y)out.write(reinterpret_cast<const char*>(first.data()+y*width*3),width*3);}
 glClear(GL_COLOR_BUFFER_BIT);assert(DrawMoonfire(settings,.9)==0);assert(Pixels()!=first);
 settings.pulse=0;glClear(GL_COLOR_BUFFER_BIT);assert(DrawMoonfire(settings,0)==0);const auto still=Pixels();
 glClear(GL_COLOR_BUFFER_BIT);assert(DrawMoonfire(settings,.9)==0);assert(Pixels()==still);
 // An opaque foreground completely occludes the effect and depth is unchanged.
 glClearDepth(0);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);const auto blocked_depth=Depth();
 assert(DrawMoonfire(settings,0)==0);const auto blocked=Pixels();assert(std::all_of(blocked.begin(),blocked.end(),[](auto c){return c==0;}));assert(Depth()==blocked_depth);
 glClearDepth(1);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);glEnable(GL_SCISSOR_TEST);glScissor(0,0,width/2,height);
 assert(DrawMoonfire(settings,0)==0);auto clipped=Pixels();for(int y=0;y<height;++y)for(int x=width/2;x<width;++x)for(int c=0;c<3;++c)assert(clipped[(y*width+x)*3+c]==0);
 assert(glIsEnabled(GL_SCISSOR_TEST));glDisable(GL_SCISSOR_TEST);
 // Native stencil tests still clip, but fire cannot modify their stencil values.
 glClearStencil(7);glClear(GL_STENCIL_BUFFER_BIT);glEnable(GL_STENCIL_TEST);glStencilFunc(GL_ALWAYS,7,255);glStencilOp(GL_ZERO,GL_ZERO,GL_ZERO);
 assert(DrawMoonfire(settings,0)==0);std::vector<unsigned char> stencil(width*height);glReadPixels(0,0,width,height,GL_STENCIL_INDEX,GL_UNSIGNED_BYTE,stencil.data());
 assert(std::all_of(stencil.begin(),stencil.end(),[](auto v){return v==7;}));glDisable(GL_STENCIL_TEST);
 // Invalid parameters, non-modelview and unreviewed depth modes fail closed.
 settings.size=NAN;assert(DrawMoonfire(settings,0)==1);settings.size=1;settings.enabled=0;assert(DrawMoonfire(settings,0)==1);settings.enabled=1;
 glDepthFunc(GL_ALWAYS);assert(DrawMoonfire(settings,0)==2);glDepthFunc(GL_LEQUAL);
 glMatrixMode(GL_PROJECTION);assert(DrawMoonfire(settings,0)==2);glMatrixMode(GL_MODELVIEW);
 for(float length:{.6F,.8F,1.F,1.2F}){glLoadIdentity();glScalef(-.9F,length,1.F);glRotatef(40,0,1,0);assert(DrawMoonfire(settings,.3)==0);}
 assert(glGetError()==GL_NO_ERROR);
 wglMakeCurrent(nullptr,nullptr);wglDeleteContext(context);ReleaseDC(window,dc);DestroyWindow(window);
 std::puts("Moon-fire pixels, pulse, occlusion, clipping, stencil/depth preservation, mirrored scale and GL state passed.");
}
