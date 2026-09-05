#include "selected_cue_gpu.h"
#include "scene_draw.h"
#include <cmath>
#include <gl/GL.h>
#include <array>
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <chrono>
#include <cstdlib>
#include <cstdint>
using namespace wonderbane::extension;
namespace {
int failures=0;
void Check(bool ok,const char* label){if(!ok){std::fprintf(stderr,"%s\n",label);++failures;}}
struct State {
    GLint program{},active{},fbo{},draw{},read{},matrix{},viewport[4]{},textures[3]{};
    GLint depth_func{},blend_src{},blend_dst{},equation{};
    GLboolean alpha_test{};GLfloat alpha_ref{};
    GLboolean depth{},blend{},mask{}; GLfloat clear[4]{};
};
using Active=void(APIENTRY*)(GLenum);
State Snapshot(){
    State s{}; auto active=reinterpret_cast<Active>(wglGetProcAddress("glActiveTexture"));
    glGetIntegerv(0x8B8D,&s.program);glGetIntegerv(0x84E0,&s.active);glGetIntegerv(0x8CA6,&s.fbo);
    glGetIntegerv(GL_DRAW_BUFFER,&s.draw);glGetIntegerv(GL_READ_BUFFER,&s.read);
    glGetIntegerv(GL_MATRIX_MODE,&s.matrix);glGetIntegerv(GL_VIEWPORT,s.viewport);
    s.depth=glIsEnabled(GL_DEPTH_TEST);s.blend=glIsEnabled(GL_BLEND);
    glGetIntegerv(GL_DEPTH_FUNC,&s.depth_func);glGetIntegerv(GL_BLEND_SRC,&s.blend_src);
    glGetIntegerv(GL_BLEND_DST,&s.blend_dst);glGetIntegerv(0x8009,&s.equation);
    s.alpha_test=glIsEnabled(GL_ALPHA_TEST);glGetFloatv(GL_ALPHA_TEST_REF,&s.alpha_ref);
    glGetBooleanv(GL_DEPTH_WRITEMASK,&s.mask);glGetFloatv(GL_COLOR_CLEAR_VALUE,s.clear);
    for(unsigned n=0;n<3;++n){active(0x84C0+n);glGetIntegerv(GL_TEXTURE_BINDING_2D,&s.textures[n]);}
    active(static_cast<GLenum>(s.active));return s;
}
void Same(const State& a,const State& b){
    Check(a.program==b.program && a.active==b.active && a.fbo==b.fbo
        && a.draw==b.draw && a.read==b.read && a.matrix==b.matrix
        && a.depth_func==b.depth_func && a.blend_src==b.blend_src && a.blend_dst==b.blend_dst
        && a.equation==b.equation && a.alpha_test==b.alpha_test && a.alpha_ref==b.alpha_ref
        && a.depth==b.depth && a.blend==b.blend && a.mask==b.mask
        && std::memcmp(a.viewport,b.viewport,sizeof(a.viewport))==0
        && std::memcmp(a.textures,b.textures,sizeof(a.textures))==0
        && std::memcmp(a.clear,b.clear,sizeof(a.clear))==0,"graphics state restored");
}
void Rect(float x0,float x1,float y0,float y1,float z){
    glBegin(GL_QUADS);glVertex3f(x0,y0,z);glVertex3f(x1,y0,z);
    glVertex3f(x1,y1,z);glVertex3f(x0,y1,z);glEnd();
}
std::array<unsigned char,4> NativeTransparency(bool late_composite,bool depth_write,bool foreground){
    glDepthMask(GL_TRUE);glDisable(GL_BLEND);glColor4f(0,0,0,1);
    glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
    Check(cue::BeginMask() && cue::BeforeOwnedDraw(),"native foreground selected mesh begin");
    auto mesh=[](void*) noexcept {Rect(-.4F,.4F,-.5F,.5F,0);};
    Check(cue::CaptureGeometry(mesh,nullptr),"native foreground selected mesh capture");mesh(nullptr);
    Check(cue::AfterOwnedDraw(),"native foreground selected mesh end");
    cue::Settings settings{};settings.enabled=1;
    if(!late_composite)Check(cue::CompositeMask(settings,{}),"reference cue before native foreground");
    glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);
    glDepthMask(depth_write?GL_TRUE:GL_FALSE);glColor4f(1,0,0,.5F);
    Rect(-.6F,.6F,-.6F,.6F,foreground?-.5F:.5F);
    if(late_composite)Check(cue::CompositeMask(settings,{}),"candidate cue after native foreground");
    std::array<unsigned char,4> pixel{};glReadPixels(foreground?230:190,240,1,1,GL_RGBA,GL_UNSIGNED_BYTE,pixel.data());
    glDepthMask(GL_TRUE);glDisable(GL_BLEND);return pixel;
}
// A bound separable fragment stage must not shade extension geometry, even
// though glUseProgram(0) makes it eligible to execute in the native pipeline.
int PipelineGuardRegression(){
    const auto* version=reinterpret_cast<const char*>(glGetString(GL_VERSION));
    const auto* extensions=reinterpret_cast<const char*>(glGetString(GL_EXTENSIONS));
    const auto* arb=extensions ? std::strstr(extensions,"GL_ARB_separate_shader_objects") : nullptr;
    constexpr std::size_t arb_length=sizeof("GL_ARB_separate_shader_objects")-1;
    const bool arb_supported=arb && (arb==extensions || arb[-1]==' ')
        && (arb[arb_length]==' ' || arb[arb_length]=='\0');
    const bool supported=version && (version[0]>'4'
        || (version[0]=='4' && version[1]=='.' && version[2]>='1')
        || arb_supported);
    if(!supported){std::puts("SKIP: pipeline guard regression unavailable: unsupported context");return 77;}
    const auto procedure=[](const char* name){
        const PROC p=wglGetProcAddress(name);const auto value=reinterpret_cast<std::uintptr_t>(p);
        return value<=3U || value==UINTPTR_MAX ? nullptr : p;
    };
    using Generate=void(APIENTRY*)(GLsizei,GLuint*);
    using Delete=void(APIENTRY*)(GLsizei,const GLuint*);
    using Bind=void(APIENTRY*)(GLuint);
    using Create=GLuint(APIENTRY*)(GLenum,GLsizei,const char* const*);
    using Stages=void(APIENTRY*)(GLuint,GLbitfield,GLuint);
    using Get=void(APIENTRY*)(GLuint,GLenum,GLint*);
    const auto gen=reinterpret_cast<Generate>(procedure("glGenProgramPipelines"));
    const auto remove=reinterpret_cast<Delete>(procedure("glDeleteProgramPipelines"));
    const auto bind=reinterpret_cast<Bind>(procedure("glBindProgramPipeline"));
    const auto create=reinterpret_cast<Create>(procedure("glCreateShaderProgramv"));
    const auto stages=reinterpret_cast<Stages>(procedure("glUseProgramStages"));
    const auto get=reinterpret_cast<Get>(procedure("glGetProgramiv"));
    const auto use=reinterpret_cast<Bind>(procedure("glUseProgram"));
    const auto delete_program=reinterpret_cast<Bind>(procedure("glDeleteProgram"));
    if(!gen || !remove || !bind || !create || !stages || !get || !delete_program || !use){
        Check(false,"supported pipeline context exposes required entry points");return 1;
    }
    const char* fragment="#version 120\nvoid main(){gl_FragColor=vec4(0,1,0,1);}";
    const GLuint program=create(0x8B30U,1,&fragment);
    GLint linked=0;get(program,0x8B82U,&linked);
    Check(linked!=0,"separable fragment shader links");
    if(!linked){delete_program(program);return 1;}
    GLuint pipeline=0;gen(1,&pipeline);bind(pipeline);stages(pipeline,2U,program);
    const auto sample=[](){
        std::array<unsigned char,4> rgba{};
        glReadPixels(320,240,1,1,GL_RGBA,GL_UNSIGNED_BYTE,rgba.data());return rgba;
    };
    glColor4f(1,0,0,1);Rect(-.4F,.4F,-.4F,.4F,0);
    auto pixel=sample();Check(pixel[0]==0 && pixel[1]==255,"native pipeline actually shades green");
    glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
    const auto before=Snapshot();
    Check(RenderSceneGeometry(nullptr,[](void*) noexcept {
        GLint binding=-1;glGetIntegerv(0x825AU,&binding);
        Check(binding==0,"extension geometry runs without native program pipeline");
        glColor4f(1,0,0,1);Rect(-.4F,.4F,-.4F,.4F,0);
    },nullptr),"scene guard accepts supported bound pipeline");
    pixel=sample();Check(pixel[0]==255 && pixel[1]==0,"extension uses intended fixed-function red");
    GLint restored=-1;glGetIntegerv(0x825AU,&restored);
    Check(static_cast<GLuint>(restored)==pipeline,"native program pipeline binding restored");
    GLint fragment_program=0;
    const auto get_pipeline=reinterpret_cast<Get>(procedure("glGetProgramPipelineiv"));
    Check(get_pipeline!=nullptr,"pipeline stage inspection available");
    if(get_pipeline){get_pipeline(pipeline,0x8B30U,&fragment_program);
        Check(static_cast<GLuint>(fragment_program)==program,"native pipeline stage attachment unchanged");}
    Same(before,Snapshot());
    glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);Rect(-.4F,.4F,-.4F,.4F,0);
    pixel=sample();Check(pixel[0]==0 && pixel[1]==255,"native rendering resumes its pipeline");
    // A regular current program overrides the pipeline. Both bindings must
    // survive the guard independently, including the formerly hidden pipeline.
    use(program);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
    const auto with_program=Snapshot();
    Check(RenderSceneGeometry(nullptr,[](void*) noexcept {
        GLint pipeline_binding=-1,current=-1;
        glGetIntegerv(0x825AU,&pipeline_binding);glGetIntegerv(0x8B8DU,&current);
        Check(pipeline_binding==0 && current==0,"guard disables both programmable bindings");
        glColor4f(1,0,0,1);Rect(-.4F,.4F,-.4F,.4F,0);
    },nullptr),"guard handles current program plus pipeline");
    pixel=sample();Check(pixel[0]==255 && pixel[1]==0,"guard bypasses current program plus pipeline");
    Same(with_program,Snapshot());glGetIntegerv(0x825AU,&restored);
    Check(static_cast<GLuint>(restored)==pipeline,"hidden pipeline restored with current program");
    use(0);bind(0);remove(1,&pipeline);delete_program(program);
    std::puts("pipeline guard regression executed: native pixels, extension pixels, both bindings and stage restoration");
    glColor4f(1,1,1,1);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
    Check(glGetError()==GL_NO_ERROR,"pipeline guard regression leaves no GL errors");
    return failures?1:0;
}
int QueryGuardRegression(){
    const auto* version=reinterpret_cast<const char*>(glGetString(GL_VERSION));
    if(!version || version[0]<'4' || (version[0]=='4' && version[2]<'3')){
        std::puts("SKIP: query guard regression requires all three core occlusion targets");return 77;
    }
    using Generate=void(APIENTRY*)(GLsizei,GLuint*);
    using Delete=void(APIENTRY*)(GLsizei,const GLuint*);
    using Begin=void(APIENTRY*)(GLenum,GLuint);
    using End=void(APIENTRY*)(GLenum);
    using Current=void(APIENTRY*)(GLenum,GLenum,GLint*);
    using Result=void(APIENTRY*)(GLuint,GLenum,GLuint*);
    const auto generate=reinterpret_cast<Generate>(wglGetProcAddress("glGenQueries"));
    const auto remove=reinterpret_cast<Delete>(wglGetProcAddress("glDeleteQueries"));
    const auto begin=reinterpret_cast<Begin>(wglGetProcAddress("glBeginQuery"));
    const auto end=reinterpret_cast<End>(wglGetProcAddress("glEndQuery"));
    const auto current=reinterpret_cast<Current>(wglGetProcAddress("glGetQueryiv"));
    const auto result=reinterpret_cast<Result>(wglGetProcAddress("glGetQueryObjectuiv"));
    if(!generate || !remove || !begin || !end || !current || !result)return 1;
    for(GLenum target : {0x8914U,0x8C2FU,0x8D6AU,0x8C87U}){
        GLuint queries[2]{};generate(2,queries);
        glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
        begin(target,queries[0]);Rect(-.4F,.4F,-.4F,.4F,0);end(target);
        GLuint native=0;result(queries[0],0x8866U,&native);
        Check(native>0,"native geometry contributes to its sample or primitive query");
        glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
        begin(target,queries[1]);const auto before=Snapshot();int calls=0;
        Check(!RenderSceneGeometry(nullptr,[](void* raw) noexcept {
            ++*static_cast<int*>(raw);Rect(-.4F,.4F,-.4F,.4F,0);
        },&calls),"supplemental scene draw rejected inside native query");
        Check(calls==0,"native query excludes extension callback");
        Same(before,Snapshot());GLint bound=0;current(target,0x8865U,&bound);
        Check(static_cast<GLuint>(bound)==queries[1],"native query binding remains owned");
        end(target);GLuint supplemental=1;result(queries[1],0x8866U,&supplemental);
        Check(supplemental==0,"extension draw does not alter native query result");
        Check(RenderSceneGeometry(nullptr,[](void*) noexcept {
            Rect(-.4F,.4F,-.4F,.4F,0);
        },nullptr),"ordinary scene drawing resumes after native query ends");
        remove(2,queries);Check(glGetError()==GL_NO_ERROR,"query guard leaves no GL errors");
    }
    std::puts("query guard executed: native samples, both any-sample targets, generated primitives");
    return failures?1:0;
}
unsigned Pixel(int x,int y){std::array<unsigned char,4> p{};glReadPixels(x,y,1,1,GL_RGBA,GL_UNSIGNED_BYTE,p.data());return p[0]+p[1]+p[2];}
}
#include "selected_cue_source_experiment.h"
int main(int argc,char** argv){
    if(argc>2 || (argc==2 && std::strcmp(argv[1],"--cost")!=0
        && std::strcmp(argv[1],"--native-transparency")!=0
        && std::strcmp(argv[1],"--source-feasibility")!=0
        && std::strcmp(argv[1],"--pipeline-guard")!=0
        && std::strcmp(argv[1],"--query-guard")!=0)){
        std::fprintf(stderr,"usage: selected_cue_gpu_test [--cost|--native-transparency|--source-feasibility|--pipeline-guard|--query-guard]\n");return 2;
    }
    WNDCLASSW wc{};wc.style=CS_OWNDC;wc.lpfnWndProc=DefWindowProcW;
    wc.hInstance=GetModuleHandleW(nullptr);wc.lpszClassName=L"SelectedCueGpuTest";
    if(!RegisterClassW(&wc))return 2;
    HWND window=CreateWindowW(wc.lpszClassName,L"",WS_OVERLAPPEDWINDOW,0,0,680,540,nullptr,nullptr,wc.hInstance,nullptr);
    if(!window)return 3;
    HDC dc=GetDC(window);PIXELFORMATDESCRIPTOR pf{};pf.nSize=sizeof(pf);pf.nVersion=1;
    pf.dwFlags=PFD_DRAW_TO_WINDOW|PFD_SUPPORT_OPENGL|PFD_DOUBLEBUFFER;
    pf.iPixelType=PFD_TYPE_RGBA;pf.cColorBits=24;pf.cDepthBits=24;pf.cStencilBits=8;
    if(argc==2 && std::strcmp(argv[1],"--source-feasibility")==0)pf.cAlphaBits=8;
    if(!SetPixelFormat(dc,ChoosePixelFormat(dc,&pf),&pf))return 4;
    HGLRC context=wglCreateContext(dc);if(!context || !wglMakeCurrent(dc,context))return 5;
    if(!wglGetProcAddress("glGenFramebuffers")) {
        std::fprintf(stderr,"SKIP: context lacks framebuffer objects\n");return 77;
    }
    glViewport(0,0,640,480);glMatrixMode(GL_PROJECTION);glLoadIdentity();
    glMatrixMode(GL_MODELVIEW);glLoadIdentity();glEnable(GL_DEPTH_TEST);glDepthFunc(GL_LESS);
    glClearColor(0,0,0,0);glClearDepth(1);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
    if(argc==2 && std::strcmp(argv[1],"--query-guard")==0){
        const int result=QueryGuardRegression();
        wglMakeCurrent(nullptr,nullptr);wglDeleteContext(context);ReleaseDC(window,dc);DestroyWindow(window);
        return result;
    }
    if(argc==2 && std::strcmp(argv[1],"--pipeline-guard")==0){
        const int result=PipelineGuardRegression();
        wglMakeCurrent(nullptr,nullptr);wglDeleteContext(context);ReleaseDC(window,dc);DestroyWindow(window);
        return result;
    }
    if(argc==2 && std::strcmp(argv[1],"--source-feasibility")==0){
        const int result=source_experiment::Run();
        wglMakeCurrent(nullptr,nullptr);wglDeleteContext(context);ReleaseDC(window,dc);DestroyWindow(window);
        return result;
    }
    if(argc==2 && std::strcmp(argv[1],"--native-transparency")==0){
        const auto equal=[](const auto& x,const auto& y){
            for(int n=0;n<3;++n)if(std::abs(int(x[n])-int(y[n]))>1)return false;
            return true;
        };
        for(bool foreground:{true,false})for(bool depth_write:{false,true}){
            // Foreground must blend over the glow; background must remain below
            // its halo. Sample the halo for background, outside native mesh depth.
            const auto expected=NativeTransparency(!foreground,depth_write,foreground);
            const auto actual=NativeTransparency(true,depth_write,foreground);
            const bool correct=equal(expected,actual);
            std::printf("native alpha=.5 foreground=%d depth_write=%d expected_rgb=%u,%u,%u actual_rgb=%u,%u,%u\n",
                int(foreground),int(depth_write),unsigned(expected[0]),unsigned(expected[1]),unsigned(expected[2]),unsigned(actual[0]),unsigned(actual[1]),unsigned(actual[2]));
            Check(correct,"cue must preserve native transparency on both sides of its depth");
            if(!foreground){
                const auto early=NativeTransparency(false,depth_write,foreground);
                Check(!equal(expected,early),"background halo case must reject wholesale early composition");
                std::printf("wholesale-early-counterexample depth_write=%d early_rgb=%u,%u,%u\n",
                    int(depth_write),unsigned(early[0]),unsigned(early[1]),unsigned(early[2]));
            }
        }
        cue::ReleaseMask();wglMakeCurrent(nullptr,nullptr);wglDeleteContext(context);ReleaseDC(window,dc);DestroyWindow(window);
        return failures?1:0;
    }
    auto initial=Snapshot();Check(cue::BeginMask(),"mask resource creation");Same(initial,Snapshot());
    Check(cue::AllocatedMaskBytes()==640ULL*480*8,"normal mesh uses only two depth textures");
    Check(cue::BeforeOwnedDraw() && cue::BeforeLegacyGeometry(),"before legacy capture");
    Check(cue::AllocatedMaskBytes()>640ULL*480*8 && cue::AllocatedMaskBytes()<=640ULL*480*28,"legacy storage allocated only on demand");Same(initial,Snapshot());
    glColor3f(0,0,0);Rect(-0.4F,0.4F,-0.5F,0.5F,0);
    Check(cue::AfterOwnedDraw(),"after capture");Same(initial,Snapshot());
    // A later nearer obstacle hides half of the selected silhouette.
    Rect(0,0.6F,-0.6F,0.6F,-0.5F);
    cue::Settings s{};s.enabled=1;s.radius=8;
    Check(cue::CompositeMask(s,{}),"mask composite");Same(initial,Snapshot());
    Check(Pixel(230,240)>0,"selected visible silhouette is tinted");
    Check(Pixel(380,240)==0,"later obstacle hides selected coverage");
    Check(Pixel(189,240)>0,"glow extends beyond true silhouette");
    Check(Pixel(170,240)==0,"glow has bounded radius");
    glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
    Check(cue::BeginMask(),"fresh scene clears previous mask");
    Check(cue::CompositeMask(s,{}),"empty scene composite");
    Check(Pixel(230,240)==0,"no stale carryover");
    cue::Direction d{true,true,-1,-1};
    Check(cue::CompositeMask(s,d),"offscreen direction draw");Same(initial,Snapshot());
    Check(Pixel(44,394)>0,"indicator is in the client viewport");
    Check(cue::BeginMask(),"begin before viewport transition");
    glViewport(0,0,600,400);
    Check(!cue::CompositeMask(s,{}),"viewport change rejects stale capture");
    Check(cue::BeginMask(),"resize recreates matching resources");
    Check(cue::CompositeMask(s,{}),"resized scene composite");
    glViewport(0,0,640,480);
    // Real non-depth-writing mesh: same client arrays/material, private depth
    // capture, original native color submission, then normal cue composite.
    const GLfloat vertices[]{-.4F,-.5F,0,.4F,-.5F,0,.4F,.5F,0,-.4F,.5F,0};
    const GLfloat texcoords[]{0,0,1,0,1,1,0,1};
    glEnableClientState(GL_VERTEX_ARRAY);glVertexPointer(3,GL_FLOAT,0,vertices);
    auto mesh=[](void*) noexcept {glDrawArrays(GL_QUADS,0,4);};
    glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
    Check(cue::BeginMask() && cue::BeforeOwnedDraw(),"begin translucent mesh");
    glDepthMask(GL_FALSE);glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);
    glColor4f(0,0,0,.5F);auto material=Snapshot();
    Check(cue::CaptureGeometry(mesh,nullptr),"capture native translucent mesh");Same(material,Snapshot());
    mesh(nullptr);Check(cue::AfterOwnedDraw(),"finish translucent mesh");
    glDepthMask(GL_TRUE);glDisable(GL_BLEND);glColor4f(0,0,0,1);
    Rect(0,.6F,-.6F,.6F,-.5F); // nearer opaque foreground
    Rect(-.6F,0,-.6F,.6F,.5F); // farther opaque background
    Check(cue::CompositeMask(s,{}),"translucent silhouette composite");
    Check(Pixel(230,240)>0,"translucent mesh glows in front of farther background");
    Check(Pixel(380,240)==0,"nearer opaque foreground occludes translucent mesh");
    using MultiDraw=void(APIENTRY*)(GLenum,const GLsizei*,GLenum,const void* const*,GLsizei);
    auto multi=reinterpret_cast<MultiDraw>(wglGetProcAddress("glMultiDrawElements"));
    if(!multi)multi=reinterpret_cast<MultiDraw>(wglGetProcAddress("glMultiDrawElementsEXT"));
    Check(multi!=nullptr,"observed optimized multi-draw API available");
    if(multi){
        const GLushort elements[]{0,1,2,0,2,3};const GLsizei counts[]{3,3};
        const void* indices[]{elements,elements+3};
        struct MultiArgs{MultiDraw draw;const GLsizei* count;const void* const* indices;};
        MultiArgs args{multi,counts,indices};
        const auto submit=[](void* value) noexcept {
            const auto& a=*static_cast<const MultiArgs*>(value);
            a.draw(GL_TRIANGLES,a.count,GL_UNSIGNED_SHORT,a.indices,2);
        };
        for(bool depth_write:{false,true}){
            glDepthMask(GL_TRUE);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
            Check(cue::BeginMask() && cue::BeforeOwnedDraw(),"optimized multi-draw begin");
            glDepthMask(depth_write?GL_TRUE:GL_FALSE);glEnable(GL_BLEND);
            glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);glColor4f(1,0,0,.5F);
            material=Snapshot();void* vertex_pointer=nullptr;glGetPointerv(GL_VERTEX_ARRAY_POINTER,&vertex_pointer);
            Check(cue::CaptureGeometry(submit,&args),"production mask captures both multi-draw primitives");Same(material,Snapshot());
            void* restored_pointer=nullptr;glGetPointerv(GL_VERTEX_ARRAY_POINTER,&restored_pointer);
            Check(vertex_pointer==restored_pointer,"multi-draw preserves native client arrays");
            submit(&args);Check(cue::AfterOwnedDraw(),"optimized multi-draw end");
            for(int x:{230,380}){
                std::array<unsigned char,4> pixel{};glReadPixels(x,240,1,1,GL_RGBA,GL_UNSIGNED_BYTE,pixel.data());
                Check(pixel[0]>=126 && pixel[0]<=129 && pixel[1]==0 && pixel[2]==0,"multi-draw reaches native color buffer once");
            }
            Check(cue::CompositeMask(s,{}),"optimized multi-draw composite");
            Check(Pixel(189,240)>0 && Pixel(450,240)>0,"whole silhouette includes both optimized primitives");
        }
        glDepthMask(GL_TRUE);glDisable(GL_BLEND);
    }
    for(GLenum destination:{GL_ONE_MINUS_SRC_ALPHA,GL_ONE}){
        glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
        Check(cue::BeginMask() && cue::BeforeOwnedDraw(),"begin zero-alpha mesh");
        glDepthMask(GL_FALSE);glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,destination);
        glColor4f(1,1,1,0);material=Snapshot();
        Check(cue::CaptureGeometry(mesh,nullptr),"capture zero-alpha mesh");Same(material,Snapshot());
        mesh(nullptr);Check(cue::AfterOwnedDraw(),"finish zero-alpha mesh");
        glDepthMask(GL_TRUE);glDisable(GL_BLEND);
        Check(cue::CompositeMask(s,{}),"zero-alpha composite");
        Check(Pixel(230,240)==0,"zero-alpha source-over/additive material has no silhouette");
    }
    using BlendColor=void(APIENTRY*)(GLfloat,GLfloat,GLfloat,GLfloat);
    const auto blend_color=reinterpret_cast<BlendColor>(wglGetProcAddress("glBlendColor"));
    Check(blend_color!=nullptr,"constant-alpha blend helper available");
    if(blend_color){
        for(bool depth_write:{false,true})for(bool inverse:{false,true})
        for(float contribution:{0.0F,0.5F,1.0F}){
            glDepthMask(GL_TRUE);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
            Check(cue::BeginMask() && cue::BeforeOwnedDraw(),"begin constant-alpha mesh");
            glDepthMask(depth_write?GL_TRUE:GL_FALSE);glEnable(GL_BLEND);
            glBlendFunc(inverse?0x8004:0x8003,inverse?0x8003:0x8004);
            const float alpha=inverse?1.0F-contribution:contribution;
            blend_color(.2F,.3F,.4F,alpha);glColor4f(.2F,.2F,.2F,1);
            material=Snapshot();
            Check(cue::CaptureGeometry(mesh,nullptr),"capture constant-alpha mesh");Same(material,Snapshot());
            GLfloat restored[4]{};glGetFloatv(0x8005,restored);
            Check(restored[0]==.2F && restored[1]==.3F && restored[2]==.4F && restored[3]==alpha,
                "native blend constant restored");
            mesh(nullptr);Check(cue::AfterOwnedDraw(),"finish constant-alpha mesh");
            glDepthMask(GL_TRUE);glDisable(GL_BLEND);
            Check(cue::CompositeMask(s,{}),"constant-alpha composite");
            Check(contribution==0?Pixel(189,240)==0:Pixel(189,240)>0,
                "constant-alpha zero coverage excluded and visible coverage retained");
        }
        glDepthMask(GL_TRUE);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
        Check(cue::BeginMask() && cue::BeforeOwnedDraw(),"begin constant-alpha depth prepass");
        glEnable(GL_BLEND);glBlendFunc(0x8003,0x8004);blend_color(0,0,0,0);
        glColor4f(.2F,.2F,.2F,1);
        Check(cue::CaptureGeometry(mesh,nullptr),"capture constant-alpha depth prepass");
        mesh(nullptr);Check(cue::AfterOwnedDraw(),"finish constant-alpha depth prepass");
        glDisable(GL_BLEND);glDepthMask(GL_FALSE);glDepthFunc(GL_EQUAL);
        Check(cue::BeforeOwnedDraw(),"begin visible equal pass after constant-alpha depth prepass");
        Check(cue::CaptureGeometry(mesh,nullptr),"capture visible equal pass after constant-alpha depth prepass");
        glColor4f(0,0,0,1);mesh(nullptr);
        Check(cue::AfterOwnedDraw(),"finish visible equal pass after constant-alpha depth prepass");
        Check(cue::CompositeMask(s,{}),"constant-alpha prepass plus equal composite");
        Check(Pixel(230,240)>0,"constant-alpha depth prepass supports later visible equal pass");
        glDepthMask(GL_TRUE);glDepthFunc(GL_LESS);
        blend_color(0,0,0,0);
    }
    glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
    Check(cue::BeginMask() && cue::BeforeOwnedDraw(),"begin RGB additive mesh");
    glDepthMask(GL_FALSE);glEnable(GL_BLEND);glBlendFunc(GL_ONE,GL_ONE);
    glColor4f(.2F,.2F,.2F,0);material=Snapshot();
    Check(cue::CaptureGeometry(mesh,nullptr),"RGB additive source does not depend on alpha");Same(material,Snapshot());
    mesh(nullptr);Check(cue::AfterOwnedDraw(),"finish RGB additive mesh");
    Check(cue::CompositeMask(s,{}),"RGB additive composite");
    Check(Pixel(189,240)>0,"RGB additive alpha-zero material retains visible silhouette");
    glDepthMask(GL_TRUE);glDisable(GL_BLEND);
    GLuint texture=0;glGenTextures(1,&texture);glBindTexture(GL_TEXTURE_2D,texture);
    const GLubyte texels[]{255,255,255,0,255,255,255,255};
    glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,2,1,0,GL_RGBA,GL_UNSIGNED_BYTE,texels);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
    glEnable(GL_TEXTURE_2D);glEnableClientState(GL_TEXTURE_COORD_ARRAY);
    glTexCoordPointer(2,GL_FLOAT,0,texcoords);glEnable(GL_ALPHA_TEST);glAlphaFunc(GL_GREATER,.25F);
    glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
    Check(cue::BeginMask() && cue::BeforeOwnedDraw(),"begin textured alpha cutout");
    glDepthMask(GL_FALSE);glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);
    glColor4f(1,1,1,.5F);material=Snapshot();
    Check(cue::CaptureGeometry(mesh,nullptr),"capture original alpha-test texture");Same(material,Snapshot());
    mesh(nullptr);const auto native_pixel=Pixel(400,240);
    Check(cue::AfterOwnedDraw(),"finish textured alpha cutout");
    Check(cue::CompositeMask(s,{}),"textured alpha cutout composite");
    Check(Pixel(230,240)==0,"native texture alpha hole is preserved");
    Check(Pixel(400,240)>native_pixel,"visible textured alpha coverage glows");
    glDepthMask(GL_TRUE);glDisable(GL_BLEND);glDisable(GL_ALPHA_TEST);glDisable(GL_TEXTURE_2D);
    glDisableClientState(GL_TEXTURE_COORD_ARRAY);glDisableClientState(GL_VERTEX_ARRAY);glDeleteTextures(1,&texture);
    glEnableClientState(GL_VERTEX_ARRAY);glVertexPointer(3,GL_FLOAT,0,vertices);
    glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
    Check(cue::BeginMask() && cue::BeforeOwnedDraw(),"begin native depth prepass");
    glColorMask(GL_FALSE,GL_FALSE,GL_FALSE,GL_FALSE);
    Check(cue::CaptureGeometry(mesh,nullptr),"capture color-disabled native depth prepass");
    mesh(nullptr);Check(cue::AfterOwnedDraw(),"finish native depth prepass");
    glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);glDepthMask(GL_FALSE);glDepthFunc(GL_EQUAL);
    Check(cue::BeforeOwnedDraw(),"begin native equal-depth material pass");
    Check(cue::CaptureGeometry(mesh,nullptr),"capture native equal-depth material pass");
    glColor4f(0,0,0,1);mesh(nullptr);Check(cue::AfterOwnedDraw(),"finish equal-depth material pass");
    Check(cue::CompositeMask(s,{}),"depth-prepass character composite");
    Check(Pixel(230,240)>0,"depth prepass plus equal color pass retains character coverage");
    glDepthMask(GL_TRUE);glDepthFunc(GL_LESS);glDisableClientState(GL_VERTEX_ARRAY);
    // Whole-character union stays correct when raw and legacy nodes interleave.
    const GLfloat left_vertices[]{-.8F,-.5F,0,-.2F,-.5F,0,-.2F,.5F,0,-.8F,.5F,0};
    glEnableClientState(GL_VERTEX_ARRAY);glVertexPointer(3,GL_FLOAT,0,left_vertices);
    glColor4f(0,0,0,1);
    for(bool raw_first:{false,true}){
        glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);Check(cue::BeginMask(),"mixed mask begin");
        for(int part=0;part<2;++part){
            Check(cue::BeforeOwnedDraw(),"mixed owned begin");
            if((part==0)==raw_first){Check(cue::CaptureGeometry(mesh,nullptr),"mixed raw");mesh(nullptr);}
            else{Check(cue::BeforeLegacyGeometry(),"mixed legacy");Rect(.2F,.8F,-.5F,.5F,0);}
            Check(cue::AfterOwnedDraw(),"mixed owned end");
        }
        Check(cue::CompositeMask(s,{}),"mixed whole-character composite");
        Check(Pixel(160,240)>0 && Pixel(480,240)>0,"both native submission paths remain in silhouette");
        Check(Pixel(320,240)==0,"empty space between character pieces remains empty");
    }
    glDisableClientState(GL_VERTEX_ARRAY);
    Check(cue::BeginMask() && cue::BeforeOwnedDraw(),"begin stencil safety case");
    glDepthMask(GL_FALSE);glEnable(GL_STENCIL_TEST);material=Snapshot();
    Check(!cue::CaptureGeometry(mesh,nullptr),"active native stencil is not replayed");Same(material,Snapshot());
    Check(glIsEnabled(GL_STENCIL_TEST)==GL_TRUE,"stencil enable remains native");
    glDisable(GL_STENCIL_TEST);cue::DiscardMask();
    using Queries=void(APIENTRY*)(GLsizei,GLuint*);
    using DeleteQueries=void(APIENTRY*)(GLsizei,const GLuint*);
    using BeginQuery=void(APIENTRY*)(GLenum,GLuint);
    using EndQuery=void(APIENTRY*)(GLenum);
    using QueryResult=void(APIENTRY*)(GLuint,GLenum,GLuint*);
    auto gen_query=reinterpret_cast<Queries>(wglGetProcAddress("glGenQueries"));
    auto delete_query=reinterpret_cast<DeleteQueries>(wglGetProcAddress("glDeleteQueries"));
    auto begin_query=reinterpret_cast<BeginQuery>(wglGetProcAddress("glBeginQuery"));
    auto end_query=reinterpret_cast<EndQuery>(wglGetProcAddress("glEndQuery"));
    auto query_result=reinterpret_cast<QueryResult>(wglGetProcAddress("glGetQueryObjectuiv"));
    Check(gen_query && delete_query && begin_query && end_query && query_result,"native query test APIs");
    if(gen_query && delete_query && begin_query && end_query && query_result){
        int major=0,minor=0;
        const auto* version=reinterpret_cast<const char*>(glGetString(GL_VERSION));
        const auto* extensions=reinterpret_cast<const char*>(glGetString(GL_EXTENSIONS));
        if(version)sscanf_s(version,"%d.%d",&major,&minor);
        const auto has=[&](const char* name){
            if(!extensions)return false;
            const auto length=std::strlen(name);
            for(const char* at=extensions;(at=std::strstr(at,name))!=nullptr;at+=length)
                if((at==extensions || at[-1]==' ') && (at[length]==' ' || at[length]=='\0'))return true;
            return false;
        };
        const GLenum targets[]{0x8914U,0x8C2FU,0x8D6AU,0x8C87U};
        for(const GLenum target:targets){
            if(target==0x8C87U && !(major>=3 || has("GL_EXT_transform_feedback")))continue;
            if(target==0x8C2FU && !(major>3 || (major==3 && minor>=3)
                || has("GL_ARB_occlusion_query2")))continue;
            if(target==0x8D6AU && !(major>4 || (major==4 && minor>=3)
                || has("GL_ARB_ES3_compatibility")))continue;
            for(const bool depth_write:{false,true}){
                glDepthMask(GL_TRUE);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
                Check(cue::BeginMask() && cue::BeforeOwnedDraw(),"begin query safety case");
                glDepthMask(depth_write?GL_TRUE:GL_FALSE);
                GLuint query=0,result=1;gen_query(1,&query);
                begin_query(target,query);material=Snapshot();
                bool submitted=false;
                Check(!cue::CaptureGeometry([](void* value) noexcept {
                    *static_cast<bool*>(value)=true;Rect(-.4F,.4F,-.4F,.4F,0);
                },&submitted),"active native query rejects selected geometry capture");
                Check(!submitted,"selected capture never invokes geometry during native query");
                Same(material,Snapshot());
                const cue::Direction indicator{true,true,-1,-1};
                Check(!cue::CompositeMask(s,indicator),"active query rejects cue and indicator composition");
                Same(material,Snapshot());
                end_query(target);query_result(query,0x8866,&result);
                Check(result==0,"cue cannot add samples or primitives to native queries");
                delete_query(1,&query);cue::DiscardMask();
                std::printf("cue query safety executed target=0x%x depth_write=%d\n",target,int(depth_write));
            }
        }
    }
    glDepthMask(GL_TRUE);
    cue::ReleaseMask();Check(glGetError()==GL_NO_ERROR,"no GL errors after cleanup");
    Check(cue::AllocatedMaskBytes()==0,"cleanup releases tracked mask storage");
    Check(cue::BeginMask(),"resources recreate after cleanup");
    Check(cue::AllocatedMaskBytes()==640ULL*480*8,"recreation starts without legacy allocations");cue::ReleaseMask();
    if(argc==2 && std::strcmp(argv[1],"--cost")==0){
        glEnableClientState(GL_VERTEX_ARRAY);glVertexPointer(3,GL_FLOAT,0,vertices);
        for(int width:{640,1920}){
            const int height=width==640?480:1080;
            RECT rect{0,0,width,height};AdjustWindowRect(&rect,WS_OVERLAPPEDWINDOW,FALSE);
            SetWindowPos(window,nullptr,0,0,rect.right-rect.left,rect.bottom-rect.top,SWP_NOMOVE|SWP_NOZORDER|SWP_NOACTIVATE);
            glViewport(0,0,width,height);glFinish();
            const auto frame=[&](bool capture){
                glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
                if(capture)Check(cue::BeginMask(),"cost mask begin");
                for(int node=0;node<46;++node){
                    if(capture){
                        Check(cue::BeforeOwnedDraw(),"cost owned begin");
                        Check(cue::CaptureGeometry(mesh,nullptr),"cost mesh capture");
                    }
                    mesh(nullptr);
                    if(capture)Check(cue::AfterOwnedDraw(),"cost owned end");
                }
                if(capture)Check(cue::CompositeMask(s,{}),"cost composite");
                glFinish();
            };
            const auto timed=[&](bool capture){
                const auto start=std::chrono::steady_clock::now();frame(capture);
                return std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
            };
            const double cold=timed(true);
            for(int warmup=0;warmup<3;++warmup){frame(false);frame(true);}
            std::array<double,16> native{},enabled{};
            for(std::size_t sample=0;sample<native.size();++sample){
                // Alternate order to reduce systematic warm-cache/order bias.
                if(sample%2){enabled[sample]=timed(true);native[sample]=timed(false);}
                else{native[sample]=timed(false);enabled[sample]=timed(true);}
            }
            std::sort(native.begin(),native.end());std::sort(enabled.begin(),enabled.end());
            const double native_median=(native[7]+native[8])/2,enabled_median=(enabled[7]+enabled[8])/2;
            std::printf("production-mask-cost viewport=%dx%d owned_nodes=46 samples=16 cold_ms=%.3f native_median_ms=%.3f enabled_median_ms=%.3f enabled_min_ms=%.3f enabled_max_ms=%.3f median_difference_ms=%.3f nominal_mib=%.3f (host test context, synthetic mesh, synchronized CPU/GPU frame time; not a live-client budget)\n",
                width,height,cold,native_median,enabled_median,enabled.front(),enabled.back(),enabled_median-native_median,
                static_cast<double>(cue::AllocatedMaskBytes())/(1024*1024));
            cue::ReleaseMask();
        }
        glDisableClientState(GL_VERTEX_ARRAY);
    }
    wglMakeCurrent(nullptr,nullptr);wglDeleteContext(context);ReleaseDC(window,dc);DestroyWindow(window);
    return failures ? 1:0;
}
