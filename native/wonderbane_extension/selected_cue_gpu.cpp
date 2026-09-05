#include "selected_cue_gpu.h"
#include "scene_draw.h"
#include <gl/GL.h>
#include <cstring>

namespace wonderbane::extension::cue {
namespace {
constexpr GLenum kTexture0=0x84C0, kFramebuffer=0x8D40, kColorAttachment=0x8CE0;
using GetQuery=void(APIENTRY*)(GLenum,GLenum,GLint*);
using BlendEquation=void(APIENTRY*)(GLenum);
using ActiveTexture=void(APIENTRY*)(GLenum);
using GenFramebuffers=void(APIENTRY*)(GLsizei,GLuint*);
using DeleteFramebuffers=void(APIENTRY*)(GLsizei,const GLuint*);
using BindFramebuffer=void(APIENTRY*)(GLenum,GLuint);
using FramebufferTexture=void(APIENTRY*)(GLenum,GLenum,GLenum,GLuint,GLint);
using CheckFramebuffer=GLenum(APIENTRY*)(GLenum);
using CreateShader=GLuint(APIENTRY*)(GLenum);
using ShaderSource=void(APIENTRY*)(GLuint,GLsizei,const char* const*,const GLint*);
using ShaderOp=void(APIENTRY*)(GLuint);
using GetShader=void(APIENTRY*)(GLuint,GLenum,GLint*);
using CreateProgram=GLuint(APIENTRY*)();
using AttachShader=void(APIENTRY*)(GLuint,GLuint);
using GetUniform=GLint(APIENTRY*)(GLuint,const char*);
using Uniform1i=void(APIENTRY*)(GLint,GLint);
using Uniform1f=void(APIENTRY*)(GLint,GLfloat);
using Uniform2f=void(APIENTRY*)(GLint,GLfloat,GLfloat);
using Uniform4f=void(APIENTRY*)(GLint,GLfloat,GLfloat,GLfloat,GLfloat);
struct Api {
    GetQuery query=nullptr;
    BlendEquation equation=nullptr;
    ActiveTexture active=nullptr; GenFramebuffers gen=nullptr; DeleteFramebuffers del=nullptr;
    BindFramebuffer bind=nullptr; FramebufferTexture attach=nullptr; CheckFramebuffer check=nullptr;
    CreateShader create_shader=nullptr; ShaderSource source=nullptr; ShaderOp compile=nullptr, delete_shader=nullptr;
    GetShader shader_status=nullptr, program_status=nullptr;
    CreateProgram create_program=nullptr; AttachShader attach_shader=nullptr;
    ShaderOp link=nullptr, use=nullptr, delete_program=nullptr;
    GetUniform uniform=nullptr; Uniform1i i=nullptr; Uniform1f f=nullptr; Uniform2f f2=nullptr; Uniform4f f4=nullptr;
};
thread_local Api a;
struct Resources {
    HGLRC context=nullptr;
    GLuint textures[4]{}; // before, after/final, accumulated mask, translucent mesh depth
    GLuint framebuffer=0, geometry_framebuffer=0, mask_program=0, glow_program=0;
    GLint viewport[4]{};
    bool active=false, before=false, captured=false, extra=false, legacy=false, single_channel=false;
};
thread_local Resources g;
PROC Proc(const char* name) noexcept {
    auto p=wglGetProcAddress(name); auto v=reinterpret_cast<std::uintptr_t>(p);
    return v<=3 || v==UINTPTR_MAX ? nullptr : p;
}
bool Load() noexcept {
#define CUE_GL(member,type,name) a.member=reinterpret_cast<type>(Proc(name)); if(!a.member) return false
    CUE_GL(active,ActiveTexture,"glActiveTexture");
    CUE_GL(equation,BlendEquation,"glBlendEquation");
    CUE_GL(query,GetQuery,"glGetQueryiv");
    CUE_GL(gen,GenFramebuffers,"glGenFramebuffers");
    CUE_GL(del,DeleteFramebuffers,"glDeleteFramebuffers");
    CUE_GL(bind,BindFramebuffer,"glBindFramebuffer");
    CUE_GL(attach,FramebufferTexture,"glFramebufferTexture2D");
    CUE_GL(check,CheckFramebuffer,"glCheckFramebufferStatus");
    CUE_GL(create_shader,CreateShader,"glCreateShader"); CUE_GL(source,ShaderSource,"glShaderSource");
    CUE_GL(compile,ShaderOp,"glCompileShader"); CUE_GL(delete_shader,ShaderOp,"glDeleteShader");
    CUE_GL(shader_status,GetShader,"glGetShaderiv"); CUE_GL(program_status,GetShader,"glGetProgramiv");
    CUE_GL(create_program,CreateProgram,"glCreateProgram"); CUE_GL(attach_shader,AttachShader,"glAttachShader");
    CUE_GL(link,ShaderOp,"glLinkProgram"); CUE_GL(use,ShaderOp,"glUseProgram");
    CUE_GL(delete_program,ShaderOp,"glDeleteProgram"); CUE_GL(uniform,GetUniform,"glGetUniformLocation");
    CUE_GL(i,Uniform1i,"glUniform1i"); CUE_GL(f,Uniform1f,"glUniform1f");
    CUE_GL(f2,Uniform2f,"glUniform2f"); CUE_GL(f4,Uniform4f,"glUniform4f");
#undef CUE_GL
    return true;
}
GLuint Program(const char* fragment) noexcept {
    const char* vertex="#version 120\nvoid main(){gl_Position=gl_Vertex;gl_TexCoord[0]=gl_MultiTexCoord0;}";
    GLuint shaders[2]{a.create_shader(0x8B31),a.create_shader(0x8B30)};
    GLuint program=a.create_program(); bool ok=program && shaders[0] && shaders[1];
    const char* sources[]{vertex,fragment};
    for(int n=0;n<2 && ok;++n) {
        a.source(shaders[n],1,&sources[n],nullptr); a.compile(shaders[n]);
        GLint status=0; a.shader_status(shaders[n],0x8B81,&status); ok=status!=0;
        if(ok) a.attach_shader(program,shaders[n]);
    }
    if(ok) { a.link(program); GLint status=0; a.program_status(program,0x8B82,&status); ok=status!=0; }
    for(auto shader:shaders) if(shader) a.delete_shader(shader);
    if(!ok && program) { a.delete_program(program); program=0; }
    return program;
}
void Quad() noexcept {
    glBegin(GL_QUADS);
    glTexCoord2f(0,0);glVertex2f(-1,-1);glTexCoord2f(1,0);glVertex2f(1,-1);
    glTexCoord2f(1,1);glVertex2f(1,1);glTexCoord2f(0,1);glVertex2f(-1,1);
    glEnd();
}
void Texture(GLuint texture,unsigned unit) noexcept {
    a.active(kTexture0+unit);glBindTexture(GL_TEXTURE_2D,texture);
}
bool DefaultTarget() noexcept {
    GLint fbo=0, samples=0;
    glGetIntegerv(0x8CA6,&fbo);glGetIntegerv(0x80A9,&samples);
    return fbo==0 && samples==0; // Never silently resolve multisample depth.
}
bool SameTarget() noexcept {
    GLint viewport[4]{};glGetIntegerv(GL_VIEWPORT,viewport);
    return g.context==wglGetCurrentContext() && DefaultTarget()
        && std::memcmp(viewport,g.viewport,sizeof(viewport))==0;
}
struct Operation { int kind; const Settings* settings=nullptr; const Direction* direction=nullptr; bool ok=false; };
void Pass(void* raw) noexcept {
    auto& op=*static_cast<Operation*>(raw);
    GLint old_program=0;glGetIntegerv(0x8B8D,&old_program);
    glDisable(GL_DEPTH_TEST);
    if(op.kind==0) {
        glGenTextures(4,g.textures);
        for(unsigned n=0;n<4;++n) {
            Texture(g.textures[n],0);
            glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
            glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
            glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,0x812F);
            glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,0x812F);
            if(n==1 || n==3)glTexImage2D(GL_TEXTURE_2D,0,0x81A6,g.viewport[2],g.viewport[3],0,
                                       GL_DEPTH_COMPONENT,GL_FLOAT,nullptr);
        }
        const auto* version=reinterpret_cast<const char*>(glGetString(GL_VERSION));
        const auto* extensions=reinterpret_cast<const char*>(glGetString(GL_EXTENSIONS));
        g.single_channel=(version && version[0]>='3')
            || (extensions && std::strstr(extensions,"GL_ARB_texture_rg"));
        a.gen(1,&g.geometry_framebuffer);a.bind(kFramebuffer,g.geometry_framebuffer);
        a.attach(kFramebuffer,0x8D00,GL_TEXTURE_2D,g.textures[3],0);
        glDrawBuffer(GL_NONE);glReadBuffer(GL_NONE);
        op.ok=a.check(kFramebuffer)==0x8CD5;
        a.bind(kFramebuffer,0);
        if(op.ok) {
            g.mask_program=Program(MaskFragmentSource());g.glow_program=Program(GlowFragmentSource());
            op.ok=g.mask_program && g.glow_program;
        }
    } else if(op.kind==1) {
        glViewport(0,0,g.viewport[2],g.viewport[3]);
        if(g.framebuffer){
            a.bind(kFramebuffer,g.framebuffer);glDrawBuffer(kColorAttachment);
            glClearColor(1,1,1,1);glClear(GL_COLOR_BUFFER_BIT);
        }
        a.bind(kFramebuffer,g.geometry_framebuffer);
        glDepthMask(GL_TRUE);glClearDepth(1);glClear(GL_DEPTH_BUFFER_BIT);
        a.bind(kFramebuffer,0);op.ok=true;
    } else if(op.kind==7){
        Texture(g.textures[0],0);
        glTexImage2D(GL_TEXTURE_2D,0,0x81A6,g.viewport[2],g.viewport[3],0,GL_DEPTH_COMPONENT,GL_FLOAT,nullptr);
        Texture(g.textures[2],0);
        glTexImage2D(GL_TEXTURE_2D,0,g.single_channel?0x822E:0x8814,g.viewport[2],g.viewport[3],0,
                     g.single_channel?GL_RED:GL_RGBA,GL_FLOAT,nullptr);
        a.gen(1,&g.framebuffer);a.bind(kFramebuffer,g.framebuffer);
        a.attach(kFramebuffer,kColorAttachment,GL_TEXTURE_2D,g.textures[2],0);
        glDrawBuffer(kColorAttachment);glReadBuffer(kColorAttachment);
        op.ok=a.check(kFramebuffer)==0x8CD5;
        if(op.ok){glClearColor(1,1,1,1);glClear(GL_COLOR_BUFFER_BIT);}
        a.bind(kFramebuffer,0);
    } else if(op.kind==6){
        a.bind(kFramebuffer,g.framebuffer);glDrawBuffer(kColorAttachment);
        glViewport(0,0,g.viewport[2],g.viewport[3]);glEnable(GL_BLEND);a.equation(0x8007);
        a.use(g.mask_program);Texture(g.textures[0],0);Texture(g.textures[1],1);Texture(g.textures[3],2);
        a.i(a.uniform(g.mask_program,"beforeDepth"),0);a.i(a.uniform(g.mask_program,"afterDepth"),1);
        a.i(a.uniform(g.mask_program,"geometryDepth"),2);a.i(a.uniform(g.mask_program,"geometryOnly"),1);
        Quad();a.bind(kFramebuffer,0);op.ok=true;
    } else if(op.kind==2 || op.kind==3 || op.kind==4) {
        const unsigned unit=op.kind==2 ? 0U : 1U;
        Texture(g.textures[unit],0);
        glCopyTexSubImage2D(GL_TEXTURE_2D,0,0,0,g.viewport[0],g.viewport[1],g.viewport[2],g.viewport[3]);
        op.ok=true;
        if(op.kind==3) {
            a.bind(kFramebuffer,g.framebuffer);glDrawBuffer(kColorAttachment);
            glViewport(0,0,g.viewport[2],g.viewport[3]);glEnable(GL_BLEND);
            a.equation(0x8007); // MIN retains nearest owned surface across passes.
            a.use(g.mask_program);Texture(g.textures[0],0);Texture(g.textures[1],1);
            Texture(g.textures[g.extra?3:1],2);
            a.i(a.uniform(g.mask_program,"beforeDepth"),0);a.i(a.uniform(g.mask_program,"afterDepth"),1);
            a.i(a.uniform(g.mask_program,"geometryDepth"),2);
            a.i(a.uniform(g.mask_program,"geometryOnly"),0);
            Quad();a.bind(kFramebuffer,0);
        } else if(op.kind==4 && (g.captured || g.extra)) {
            const auto& s=*op.settings;
            a.use(g.glow_program);Texture(g.textures[g.captured?2:3],0);Texture(g.textures[1],1);
            a.i(a.uniform(g.glow_program,"maskDepth"),0);a.i(a.uniform(g.glow_program,"sceneDepth"),1);
            a.f2(a.uniform(g.glow_program,"pixel"),1.0F/g.viewport[2],1.0F/g.viewport[3]);
            a.f(a.uniform(g.glow_program,"radius"),s.radius);
            a.f4(a.uniform(g.glow_program,"tint"),s.color[0],s.color[1],s.color[2],s.opacity);
            Quad();
        }
    }
    a.use(static_cast<GLuint>(old_program));
}
bool Run(int kind,const Settings* settings=nullptr) noexcept {
    GLint query=0;a.query(0x8914,0x8865,&query);
    if(query && (kind==3 || kind==4 || kind==6))return false;
    Operation op{kind,settings};
    return RenderSceneGeometry(nullptr,Pass,&op) && op.ok;
}
void Indicator(void* raw) noexcept {
    const auto& op=*static_cast<Operation*>(raw);const auto& s=*op.settings;const auto& d=*op.direction;
    if(!d.available || !d.offscreen) return;
    GLint viewport[4]{};glGetIntegerv(GL_VIEWPORT,viewport);
    const float w=static_cast<float>(viewport[2]),h=static_cast<float>(viewport[3]);
    const float size=s.indicator_size;
    const float x=d.turn<0 ? size+20 : (d.turn>0 ? w-size-20 : w*0.5F);
    const float y=h*(1-s.indicator_y);
    glDisable(GL_DEPTH_TEST);glMatrixMode(GL_PROJECTION);glLoadIdentity();glOrtho(0,w,0,h,-1,1);
    glMatrixMode(GL_MODELVIEW);glLoadIdentity();
    glColor4f(0,0,0,s.opacity*0.65F);glBegin(GL_QUADS);
    glVertex2f(x-size,y-size);glVertex2f(x+size,y-size);glVertex2f(x+size,y+size);glVertex2f(x-size,y+size);glEnd();
    glColor4f(s.color[0],s.color[1],s.color[2],s.opacity);glBegin(GL_TRIANGLES);
    if(d.turn==0) { glVertex2f(x,y+size*0.7F);glVertex2f(x-size*0.55F,y-size*0.45F);glVertex2f(x+size*0.55F,y-size*0.45F); }
    else { const float dx=static_cast<float>(d.turn)*size*0.7F;
        glVertex2f(x+dx,y);glVertex2f(x-dx*0.7F,y+size*0.6F);glVertex2f(x-dx*0.7F,y-size*0.6F); }
    glEnd();
}
}
const char* MaskFragmentSource() noexcept { return R"glsl(#version 120
uniform sampler2D beforeDepth,afterDepth,geometryDepth;uniform bool geometryOnly;
void main(){vec2 uv=gl_TexCoord[0].xy;float b=1.0,d=texture2D(geometryDepth,uv).r;
if(!geometryOnly){b=texture2D(beforeDepth,uv).r;d=min(texture2D(afterDepth,uv).r,d);}
if(d>=1.0 || abs(d-b)<0.00000003)discard;
gl_FragColor=vec4(d,0.0,0.0,1.0);})glsl"; }
const char* GlowFragmentSource() noexcept { return R"glsl(#version 120
uniform sampler2D maskDepth,sceneDepth;uniform vec2 pixel;uniform float radius;uniform vec4 tint;
float visible(vec2 uv,float here){vec4 m=texture2D(maskDepth,uv);float z=texture2D(sceneDepth,uv).r;
return m.r<1.0 && m.r<=z && here>=m.r ? 1.0:0.0;}
void main(){vec2 uv=gl_TexCoord[0].xy;float here=texture2D(sceneDepth,uv).r;
float center=visible(uv,here),halo=0.0;
for(int i=0;i<16;++i){float angle=float(i)*0.3926990817;vec2 v=vec2(cos(angle),sin(angle))*pixel;
halo=max(halo,visible(uv+v*radius,here)*0.35);
halo=max(halo,visible(uv+v*radius*0.5,here)*0.7);}
gl_FragColor=vec4(tint.rgb,tint.a*max(center*0.18,halo*(1.0-center)));})glsl"; }
void DiscardMask() noexcept {g.active=false;g.before=false;g.captured=false;g.extra=false;g.legacy=false;}
std::uint64_t AllocatedMaskBytes() noexcept {
    if(!g.geometry_framebuffer)return 0;
    const std::uint64_t pixels=static_cast<std::uint64_t>(g.viewport[2])*g.viewport[3];
    return pixels*(8U+(g.framebuffer?(g.single_channel?8U:20U):0U));
}
void ReleaseMask() noexcept {
    DiscardMask();if(g.context!=wglGetCurrentContext())return;
    if(g.textures[0])glDeleteTextures(4,g.textures);
    if(g.geometry_framebuffer && a.del)a.del(1,&g.geometry_framebuffer);
    if(g.framebuffer && a.del)a.del(1,&g.framebuffer);
    if(g.mask_program && a.delete_program)a.delete_program(g.mask_program);
    if(g.glow_program && a.delete_program)a.delete_program(g.glow_program);
    g={};
}
bool BeginMask() noexcept {
    DiscardMask();auto context=wglGetCurrentContext();if(!context)return false;
    // Resource IDs are context-owned. Never delete IDs from another context.
    if(g.context && g.context!=context)return false;
    if(!Load() || !DefaultTarget())return false;
    GLint viewport[4]{};glGetIntegerv(GL_VIEWPORT,viewport);
    if(viewport[2]<480 || viewport[3]<360 || viewport[2]>3840 || viewport[3]>2160)return false;
    if(g.geometry_framebuffer && std::memcmp(viewport,g.viewport,sizeof(viewport))!=0)ReleaseMask();
    g.context=context;std::memcpy(g.viewport,viewport,sizeof(viewport));
    if(!g.geometry_framebuffer && !Run(0)){ReleaseMask();return false;}
    g.active=Run(1);return g.active;
}
bool BeforeOwnedDraw() noexcept {
    g.legacy=false;g.before=g.active && SameTarget();return g.before;
}
bool BeforeLegacyGeometry() noexcept {
    if(!g.before || !SameTarget())return false;
    if(!g.framebuffer && !Run(7)){ReleaseMask();return false;}
    if(!g.legacy)g.legacy=Run(2);
    return g.legacy;
}
bool CaptureGeometry(GeometryDraw draw,void* user) noexcept {
    if(!g.before || !draw || !SameTarget())return false;
    GLboolean depth_write=GL_TRUE;glGetBooleanv(GL_DEPTH_WRITEMASK,&depth_write);
    GLint stack=0,maximum=0,mode=0,query=0,depth_function=0;
    glGetIntegerv(GL_DEPTH_FUNC,&depth_function);
    a.query(0x8914,0x8865,&query); // Never double-count an active native samples query.
    glGetIntegerv(GL_ATTRIB_STACK_DEPTH,&stack);glGetIntegerv(GL_MAX_ATTRIB_STACK_DEPTH,&maximum);
    glGetIntegerv(GL_RENDER_MODE,&mode);
    if(query || stack>=maximum || mode!=GL_RENDER || glIsEnabled(GL_STENCIL_TEST) || glIsEnabled(GL_COLOR_LOGIC_OP)
        || g.viewport[0]!=0 || g.viewport[1]!=0
        || (glIsEnabled(GL_DEPTH_TEST) && depth_function!=GL_LESS && depth_function!=GL_LEQUAL && depth_function!=GL_EQUAL))
        return depth_write && BeforeLegacyGeometry();
    GLboolean color[4]{};glGetBooleanv(GL_COLOR_WRITEMASK,color);
    if(!depth_write && !color[0] && !color[1] && !color[2])return true;
    // Capture only the raw driver submission. Native transforms, texture/alpha
    // state, programs and vertex arrays stay active; no game render is replayed.
    glPushAttrib(GL_ALL_ATTRIB_BITS);
    a.bind(kFramebuffer,g.geometry_framebuffer);glDrawBuffer(GL_NONE);
    glColorMask(GL_FALSE,GL_FALSE,GL_FALSE,GL_FALSE);glDepthMask(GL_TRUE);
    glEnable(GL_DEPTH_TEST);glDepthFunc(depth_function==GL_EQUAL?GL_EQUAL:GL_LEQUAL);
    if(glIsEnabled(GL_BLEND) && !glIsEnabled(GL_ALPHA_TEST)){
        GLint src=0,dst=0,equation=0;glGetIntegerv(GL_BLEND_SRC,&src);glGetIntegerv(GL_BLEND_DST,&dst);
        glGetIntegerv(0x8009,&equation);
        if((equation==0x8006 || equation==0x800B)
            && (src==GL_SRC_ALPHA || src==GL_SRC_ALPHA_SATURATE)
            && (dst==GL_ONE_MINUS_SRC_ALPHA || dst==GL_ONE)){
            glEnable(GL_ALPHA_TEST);glAlphaFunc(GL_GREATER,0.0F);
        }
    }
    draw(user);
    a.bind(kFramebuffer,0);glPopAttrib();g.extra=true;return true;
}
bool AfterOwnedDraw() noexcept {
    if(!g.before || !SameTarget()){DiscardMask();return false;}
    g.before=false;if(!g.legacy)return true;
    const bool ok=Run(3);g.captured=g.captured||ok;g.legacy=false;return ok;
}
bool CompositeMask(const Settings& s,const Direction& d) noexcept {
    bool ok=true;
    if(g.active){
        ok=SameTarget();
        if(ok && g.extra && g.captured)ok=Run(6);
        if(ok && (g.captured || g.extra))ok=Run(4,&s);
    }
    Operation op{5,&s,&d};
    if(d.available && d.offscreen)ok=RenderSceneGeometry(nullptr,Indicator,&op)&&ok;
    DiscardMask();return ok;
}
}
