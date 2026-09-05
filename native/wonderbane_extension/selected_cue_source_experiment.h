// Actual-GL feasibility regression only. No client hook, ownership authority,
// capture API or runtime feature path. Included by the existing cue GPU test.
namespace source_experiment {
PROC Procedure(const char* name) {
    const auto value=wglGetProcAddress(name);
    const auto address=reinterpret_cast<std::uintptr_t>(value);
    return address<=3 || address==UINTPTR_MAX?nullptr:value;
}
constexpr int width=64, height=64, pixels=width*height;
constexpr GLenum framebuffer=0x8D40, read_fbo=0x8CA8, draw_fbo=0x8CA9;
constexpr GLenum color_attachment=0x8CE0, depth_stencil_attachment=0x821A;
using Bind=void(APIENTRY*)(GLenum,GLuint);
using Gen=void(APIENTRY*)(GLsizei,GLuint*);
using Del=void(APIENTRY*)(GLsizei,const GLuint*);
using Attach=void(APIENTRY*)(GLenum,GLenum,GLenum,GLuint,GLint);
using Status=GLenum(APIENTRY*)(GLenum);
using Blit=void(APIENTRY*)(GLint,GLint,GLint,GLint,GLint,GLint,GLint,GLint,GLbitfield,GLenum);
using Equation=void(APIENTRY*)(GLenum);
struct Image {
    std::array<unsigned char,pixels*4> rgba{};
    std::array<float,pixels> depth{};
    std::array<unsigned char,pixels> stencil{};
};
Image Read() {
    Image result;
    glReadPixels(0,0,width,height,GL_RGBA,GL_UNSIGNED_BYTE,result.rgba.data());
    glReadPixels(0,0,width,height,GL_DEPTH_COMPONENT,GL_FLOAT,result.depth.data());
    glReadPixels(0,0,width,height,GL_STENCIL_INDEX,GL_UNSIGNED_BYTE,result.stencil.data());
    return result;
}
struct NativeState {
    State common{};
    std::array<GLint,41> integers{};
    std::array<GLfloat,61> values{};
    std::array<GLint,32> unit_enables{},unit_bindings{};
};
NativeState Observe() {
    NativeState result;result.common=Snapshot();
    constexpr GLenum names[]{GL_STENCIL_FUNC,GL_STENCIL_REF,GL_STENCIL_VALUE_MASK,
        GL_STENCIL_WRITEMASK,GL_STENCIL_FAIL,GL_STENCIL_PASS_DEPTH_FAIL,GL_STENCIL_PASS_DEPTH_PASS,
        GL_ALPHA_TEST_FUNC,GL_SCISSOR_TEST,GL_STENCIL_TEST,GL_TEXTURE_2D,GL_PACK_ALIGNMENT,
        GL_UNPACK_ALIGNMENT,0x80CB,0x80CA,0x883D,GL_FOG,GL_LIGHTING,GL_CULL_FACE,GL_DITHER,
        0x8800,0x8CA4,0x8CA3,0x8CA5,0x8801,0x8802,0x8803,
        GL_COLOR_LOGIC_OP,GL_POLYGON_OFFSET_FILL,GL_POLYGON_STIPPLE,GL_POLYGON_SMOOTH};
    for(std::size_t i=0;i<std::size(names);++i)glGetIntegerv(names[i],&result.integers[i]);
    glGetIntegerv(GL_COLOR_WRITEMASK,result.integers.data()+31);
    glGetIntegerv(GL_SCISSOR_BOX,result.integers.data()+35);
    glGetIntegerv(GL_POLYGON_MODE,result.integers.data()+39);
    glGetFloatv(GL_CURRENT_COLOR,result.values.data());
    glGetFloatv(GL_CURRENT_TEXTURE_COORDS,result.values.data()+4);
    glGetFloatv(GL_CURRENT_NORMAL,result.values.data()+8);
    glGetFloatv(GL_TEXTURE_MATRIX,result.values.data()+11);
    glGetFloatv(GL_MODELVIEW_MATRIX,result.values.data()+27);
    glGetFloatv(GL_PROJECTION_MATRIX,result.values.data()+43);
    glGetFloatv(GL_DEPTH_RANGE,result.values.data()+59);
    const auto active=reinterpret_cast<Active>(Procedure("glActiveTexture"));
    GLint units=0;glGetIntegerv(0x84E2,&units);Check(units>0 && units<=32,"bounded test texture units");
    for(GLint i=0;i<std::min(units,32);++i){active(0x84C0+i);
        glGetIntegerv(GL_TEXTURE_2D,&result.unit_enables[i]);
        glGetIntegerv(GL_TEXTURE_BINDING_2D,&result.unit_bindings[i]);}
    active(static_cast<GLenum>(result.common.active));
    return result;
}
void SameNative(const NativeState& a,const NativeState& b) {
    Same(a.common,b.common);
    Check(a.integers==b.integers && a.values==b.values
        && a.unit_enables==b.unit_enables && a.unit_bindings==b.unit_bindings,"source experiment restores material/current/client state");
}
struct Packet {
    float x0=-.8F,x1=.8F,z=0,alpha_ref=128.0F/255.0F;
    GLenum function=GL_LESS;
    bool depth_write=false,alpha_write=true,flip=false;
    std::array<float,4> color{.75F,.5F,1,1};
};
constexpr std::array<unsigned char,32> texels{
    255,64,128,0, 128,255,64,63, 64,128,255,128, 192,96,48,255,
    32,192,224,255, 224,32,192,128, 192,224,32,63, 96,160,224,0};
struct Scratch {
    HGLRC owner=wglGetCurrentContext();
    GLuint fbo=0,textures[2]{},material=0;
    Bind bind=reinterpret_cast<Bind>(Procedure("glBindFramebuffer"));
    Gen gen=reinterpret_cast<Gen>(Procedure("glGenFramebuffers"));
    Del del=reinterpret_cast<Del>(Procedure("glDeleteFramebuffers"));
    Attach attach=reinterpret_cast<Attach>(Procedure("glFramebufferTexture2D"));
    Status status=reinterpret_cast<Status>(Procedure("glCheckFramebufferStatus"));
    Blit blit=reinterpret_cast<Blit>(Procedure("glBlitFramebuffer"));
    Active active=reinterpret_cast<Active>(Procedure("glActiveTexture"));
    Equation equation=reinterpret_cast<Equation>(Procedure("glBlendEquation"));
    bool Create() {
        if(!bind || !gen || !del || !attach || !status || !blit || !active || !equation)return false;
        gen(1,&fbo);glGenTextures(2,textures);glGenTextures(1,&material);
        active(0x84C0);bind(framebuffer,fbo);
        for(int i=0;i<2;++i){
            glBindTexture(GL_TEXTURE_2D,textures[i]);
            glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
            glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
            glTexImage2D(GL_TEXTURE_2D,0,i?0x88F0:GL_RGBA8,width,height,0,
                i?0x84F9:GL_RGBA,i?0x84FA:GL_UNSIGNED_BYTE,nullptr);
            attach(framebuffer,i?depth_stencil_attachment:color_attachment,GL_TEXTURE_2D,textures[i],0);
        }
        glDrawBuffer(color_attachment);glReadBuffer(color_attachment);
        const bool complete=status(framebuffer)==0x8CD5;
        bind(framebuffer,0);glDrawBuffer(GL_BACK);glReadBuffer(GL_BACK);
        glBindTexture(GL_TEXTURE_2D,material);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,0x812F);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,0x812F);
        glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,4,2,0,GL_RGBA,GL_UNSIGNED_BYTE,texels.data());
        return complete;
    }
    void Release() {
        Check(wglGetCurrentContext()==owner,"scratch released on owning context");
        if(wglGetCurrentContext()!=owner)return;
        if(fbo)del(1,&fbo);glDeleteTextures(2,textures);glDeleteTextures(1,&material);
        Check(!glIsTexture(textures[0]) && !glIsTexture(textures[1]) && !glIsTexture(material),"scratch texture cleanup");
        fbo=0;textures[0]=textures[1]=material=0;
    }
    void Apply(const Packet& p) {
        active(0x84C0);glEnable(GL_TEXTURE_2D);glBindTexture(GL_TEXTURE_2D,material);
        glTexEnvi(GL_TEXTURE_ENV,GL_TEXTURE_ENV_MODE,GL_MODULATE);
        glEnable(GL_DEPTH_TEST);glDepthFunc(p.function);glDepthMask(p.depth_write?GL_TRUE:GL_FALSE);
        glEnable(GL_ALPHA_TEST);glAlphaFunc(GL_GEQUAL,p.alpha_ref);
        glEnable(GL_BLEND);equation(0x8006);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);
        glDisable(GL_STENCIL_TEST);glDisable(GL_DITHER);glDisable(GL_CULL_FACE);
        glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,p.alpha_write?GL_TRUE:GL_FALSE);
        glColor4fv(p.color.data());
    }
};
void Quad(const Packet& p) {
    const float u0=p.flip?1.0F:0.0F,u1=1-u0;
    glBegin(GL_QUADS);
    glTexCoord2f(u0,0);glVertex3f(p.x0,-.8F,p.z);
    glTexCoord2f(u1,0);glVertex3f(p.x1,-.8F,p.z);
    glTexCoord2f(u1,1);glVertex3f(p.x1,.8F,p.z);
    glTexCoord2f(u0,1);glVertex3f(p.x0,.8F,p.z);glEnd();
}
struct Operation {Scratch* scratch;const Packet* packet;Image* output;};
void CapturePass(void* raw) noexcept {
    auto& op=*static_cast<Operation*>(raw);auto& s=*op.scratch;
    // The shared scene guard owns attrib/matrix restoration. FBO binding is
    // callback-owned and balanced before returning, as its contract requires.
    s.bind(read_fbo,0);s.bind(draw_fbo,s.fbo);
    s.blit(0,0,width,height,0,0,width,height,GL_DEPTH_BUFFER_BIT,GL_NEAREST);
    s.bind(framebuffer,s.fbo);glDrawBuffer(color_attachment);glReadBuffer(color_attachment);
    glStencilMask(255);glClearStencil(0);glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);
    glClearColor(0,0,0,0);glClear(GL_COLOR_BUFFER_BIT|GL_STENCIL_BUFFER_BIT);
    s.Apply(*op.packet);glDisable(GL_BLEND);glDepthMask(GL_TRUE);
    glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);glEnable(GL_STENCIL_TEST);
    glStencilFunc(GL_ALWAYS,1,255);glStencilOp(GL_KEEP,GL_KEEP,GL_REPLACE);
    Quad(*op.packet);
    if(op.output)*op.output=Read();
    s.bind(framebuffer,0);glDrawBuffer(GL_BACK);glReadBuffer(GL_BACK);
}
bool Capture(Scratch& s,const Packet& p,Image* output) {
    if(wglGetCurrentContext()!=s.owner)return false;
    using Query=void(APIENTRY*)(GLenum,GLenum,GLint*);
    const auto query=reinterpret_cast<Query>(Procedure("glGetQueryiv"));
    GLint active_query=-1;if(query)query(0x8914,0x8865,&active_query);
    if(active_query!=0)return false; // The controlled fixture has no other query kinds.
    Operation op{&s,&p,output};return RenderSceneGeometry(nullptr,CapturePass,&op);
}
void Background(const std::array<unsigned char,4>& color) {
    glDisable(GL_SCISSOR_TEST);glDepthMask(GL_TRUE);glStencilMask(255);
    glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);glClearStencil(7);glClearDepth(.5);
    glClearColor(color[0]/255.0F,color[1]/255.0F,color[2]/255.0F,color[3]/255.0F);
    glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT|GL_STENCIL_BUFFER_BIT);
    // Nondefault disabled stencil state must survive scratch capture.
    glStencilFunc(GL_NOTEQUAL,5,0x35);glStencilOp(GL_INCR,GL_DECR,GL_INVERT);glStencilMask(0x57);
}
bool ExpectedCoverage(const Packet& p,int index) {
    const float x=2*(static_cast<float>(index%width)+.5F)/width-1;
    const float y=2*(static_cast<float>(index/width)+.5F)/height-1;
    if(p.x1<=p.x0 || x<p.x0 || x>=p.x1 || y<-.8F || y>=.8F)return false;
    float u=(x-p.x0)/(p.x1-p.x0);if(p.flip)u=1-u;
    const int tx=std::clamp(static_cast<int>(u*4),0,3),ty=y<0?0:1;
    const float alpha=texels[(ty*4+tx)*4+3]/255.0F*p.color[3];
    const bool depth=p.function==GL_EQUAL ? p.z==0 : p.function==GL_LEQUAL ? p.z<=0 : p.z<0;
    return alpha>=p.alpha_ref && depth;
}
std::array<float,4> ExpectedSource(const Packet& p,int index) {
    const float x=2*(static_cast<float>(index%width)+.5F)/width-1;
    const float y=2*(static_cast<float>(index/width)+.5F)/height-1;
    float u=(x-p.x0)/(p.x1-p.x0);if(p.flip)u=1-u;
    const int tx=std::clamp(static_cast<int>(u*4),0,3),ty=y<0?0:1;
    std::array<float,4> color{};
    for(int c=0;c<4;++c)color[c]=texels[(ty*4+tx)*4+c]*p.color[c];
    return color;
}
void Compare(const Packet& p,const Image& before,const Image& source,const Image& native) {
    bool coverage_ok=true,color_ok=true,depth_ok=true,stencil_ok=true,source_ok=true;
    for(int i=0;i<pixels;++i){
        const bool covered=source.stencil[i]==1;
        coverage_ok=coverage_ok && covered==ExpectedCoverage(p,i) && source.stencil[i]<=1;
        if(covered){const auto expected=ExpectedSource(p,i);
            for(int c=0;c<4;++c)source_ok=source_ok && std::abs(expected[c]-source.rgba[i*4+c])<=1.5F;}
        const float alpha=source.rgba[i*4+3]/255.0F;
        for(int c=0;c<4;++c){
            const float expected=(!covered || (c==3 && !p.alpha_write))?before.rgba[i*4+c]
                :source.rgba[i*4+c]*alpha+before.rgba[i*4+c]*(1-alpha);
            color_ok=color_ok && std::abs(expected-native.rgba[i*4+c])<=2.0F;
        }
        const float expected_depth=covered && p.depth_write?source.depth[i]:before.depth[i];
        depth_ok=depth_ok && std::abs(expected_depth-native.depth[i])<0.000001F;
        if(covered)depth_ok=depth_ok && std::abs(source.depth[i]-(p.z+1)*.5F)<0.000001F;
        stencil_ok=stencil_ok && native.stencil[i]==before.stencil[i];
    }
    Check(coverage_ok,"scratch coverage matches independent alpha/depth/raster expectation");
    Check(source_ok,"unblended source RGBA preserves texel/current color including zero-alpha RGB");
    Check(color_ok,"source RGBA predicts native RGB and alpha over known background within 2/255");
    Check(depth_ok,"source depth preserves native depth-write semantics");
    Check(stencil_ok,"native stencil remains untouched");
}

struct VisibilityPixel {
    std::array<unsigned char,4> rgba{},before_rgba{};
    float depth=0,before_depth=0;
};
VisibilityPixel VisibilityFrame(int kind,bool with_cue,bool behind,
    const std::array<unsigned char,4>* matched_opaque=nullptr) {
    glViewport(0,0,640,480);glDisable(GL_TEXTURE_2D);glDisable(GL_BLEND);
    glDisable(GL_ALPHA_TEST);glDisable(GL_STENCIL_TEST);glDisable(GL_DITHER);
    glDepthMask(GL_TRUE);glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);
    glEnable(GL_DEPTH_TEST);glDepthFunc(GL_LESS);glClearDepth(1);glClearColor(0,0,0,0);
    glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT|GL_STENCIL_BUFFER_BIT);
    glColor4f(0,0,0,0);
    Check(cue::BeginMask() && cue::BeforeOwnedDraw(),"opaque visibility actual cue mask");
    auto geometry=[](void*) noexcept {Rect(-.4F,.4F,-.5F,.5F,0);};
    Check(cue::CaptureGeometry(geometry,nullptr),"opaque visibility owned geometry");
    geometry(nullptr);Check(cue::AfterOwnedDraw(),"opaque visibility owned geometry complete");
    cue::Settings settings{};settings.enabled=1;
    const int x=behind?190:230;
    VisibilityPixel result;
    glReadPixels(x,240,1,1,GL_RGBA,GL_UNSIGNED_BYTE,result.before_rgba.data());
    glReadPixels(x,240,1,1,GL_DEPTH_COMPONENT,GL_FLOAT,&result.before_depth);
    // Reference: cue under native foreground alpha. A later opaque submission
    // erases that cue, even when its depth is identical to the preceding alpha.
    if(with_cue && kind!=0 && !behind)Check(cue::CompositeMask(settings,{}),"cue before alpha visibility reference");
    glDepthFunc(GL_LEQUAL);glDepthMask(GL_TRUE);
    const auto opaque_color=[&](){Check(matched_opaque!=nullptr,"matched opaque reference supplied");
        if(matched_opaque)glColor4ubv(matched_opaque->data());};
    if(kind==0){glDisable(GL_BLEND);opaque_color();}
    else {glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);glColor4f(1,0,0,.5F);}
    Rect(-.6F,.6F,-.6F,.6F,behind?.5F:-.5F);
    if(kind==2){glDisable(GL_BLEND);opaque_color();Rect(-.6F,.6F,-.6F,.6F,-.5F);}
    if(with_cue && (kind==0 || behind))Check(cue::CompositeMask(settings,{}),"cue opaque depth visibility reference");
    glReadPixels(x,240,1,1,GL_RGBA,GL_UNSIGNED_BYTE,result.rgba.data());
    glReadPixels(x,240,1,1,GL_DEPTH_COMPONENT,GL_FLOAT,&result.depth);
    return result;
}
void VisibilityWitness() {
    const auto alpha=VisibilityFrame(1,false,false);
    // Choose an opaque material with the same quantized native output. This is
    // a test counterexample construction, never framebuffer/source inversion.
    const auto opaque=VisibilityFrame(0,false,false,&alpha.rgba);
    const auto late_opaque=VisibilityFrame(2,false,false,&alpha.rgba);
    const auto opaque_cue=VisibilityFrame(0,true,false,&alpha.rgba),alpha_cue=VisibilityFrame(1,true,false);
    const auto late_opaque_cue=VisibilityFrame(2,true,false,&alpha.rgba);
    Check(opaque.rgba==alpha.rgba && opaque.depth==alpha.depth,
        "opaque and depth-writing alpha can have identical final RGBA and depth");
    Check(alpha.rgba==late_opaque.rgba && alpha.depth==late_opaque.depth
        && alpha.before_rgba==late_opaque.before_rgba && alpha.before_depth==late_opaque.before_depth,
        "late equal-depth opaque leaves final inputs and earlier alpha packet indistinguishable");
    Check(opaque_cue.rgba==opaque.rgba && late_opaque_cue.rgba==late_opaque.rgba,
        "opaque foreground blocks the actual cue including late equal-depth opaque");
    Check(alpha_cue.rgba!=alpha.rgba && alpha_cue.rgba!=late_opaque_cue.rgba,
        "same final inputs require different cue visibility for alpha versus late opaque");
    for(int kind=0;kind<2;++kind){const auto plain=VisibilityFrame(kind,false,true,&alpha.rgba);
        const auto cue_pixel=VisibilityFrame(kind,true,true,&alpha.rgba);
        Check(plain.rgba!=cue_pixel.rgba,"opaque or alpha behind retained halo depth does not hide cue");}
    std::printf("visibility witness same native rgba=%u,%u,%u,%u depth=%.6f; alpha cue rgb=%u,%u,%u late opaque cue=%u,%u,%u\n",
        unsigned(alpha.rgba[0]),unsigned(alpha.rgba[1]),unsigned(alpha.rgba[2]),unsigned(alpha.rgba[3]),alpha.depth,
        unsigned(alpha_cue.rgba[0]),unsigned(alpha_cue.rgba[1]),unsigned(alpha_cue.rgba[2]),
        unsigned(late_opaque_cue.rgba[0]),unsigned(late_opaque_cue.rgba[1]),unsigned(late_opaque_cue.rgba[2]));
    cue::ReleaseMask();glViewport(0,0,width,height);
}
std::array<float,4> ForegroundAt(const Image& source,int pixel,float tap_depth,
    const std::array<float,4>& effect) {
    std::array<float,4> result=effect;
    if(source.stencil[pixel] && source.depth[pixel]<=tap_depth){
        const float a=source.rgba[pixel*4+3]/255.0F;
        for(int c=0;c<4;++c)result[c]=source.rgba[pixel*4+c]/255.0F*a+effect[c]*(1-a);
    }
    return result;
}
void TapWitness(Scratch& scratch) {
    Packet p;p.x0=0;p.x1=.8F;p.z=0;p.alpha_ref=0;p.function=GL_LEQUAL;p.color[3]=.5F;
    const std::array<unsigned char,4> background{51,102,153,77};
    Background(background);glClearDepth(1);glDepthMask(GL_TRUE);glClear(GL_DEPTH_BUFFER_BIT);
    scratch.Apply(p);Image source;Check(Capture(scratch,p,&source),"destination tap source capture");
    Quad(p);const Image final_native=Read();
    const int destination=(height/4)*width+3*width/4,neighbor=(height/4)*width+width/4;
    Check(source.stencil[destination]==1 && source.stencil[neighbor]==0,"native foreground covers destination but not tap neighbor");
    const std::array<float,4> effect{.1F,.8F,.6F,.75F};
    std::array<std::array<unsigned char,4>,2> reference{};
    const float depths[]{.25F,.75F};
    for(int tap=0;tap<2;++tap){
        Background(background);glClearDepth(1);glDepthMask(GL_TRUE);glClear(GL_DEPTH_BUFFER_BIT);
        glDisable(GL_TEXTURE_2D);glDisable(GL_ALPHA_TEST);glDisable(GL_BLEND);glDisable(GL_STENCIL_TEST);
        glColor4fv(effect.data());glEnable(GL_DEPTH_TEST);glDepthFunc(GL_LESS);
        Rect(-1,1,-1,1,depths[tap]*2-1); // fully covered cue sample at retained owned depth
        scratch.Apply(p);Quad(p);const Image actual=Read();
        const auto expected=ForegroundAt(source,destination,depths[tap],effect);
        for(int c=0;c<4;++c){reference[tap][c]=actual.rgba[destination*4+c];
            Check(std::abs(expected[c]*255-reference[tap][c])<=2,
                "destination-pixel native transform matches actual GL at each retained tap depth");}
    }
    Check(reference[0]!=reference[1],"equal-strength taps at distinct depths cannot discard their depths before native transform");
    const auto wrong_neighbor=ForegroundAt(source,neighbor,depths[1],effect);
    const auto wrong_depth=ForegroundAt(source,destination,final_native.depth[destination],effect);
    bool neighbor_wrong=false,depth_wrong=false;
    for(int c=0;c<3;++c){neighbor_wrong=neighbor_wrong || std::abs(wrong_neighbor[c]*255-reference[1][c])>4;
        depth_wrong=depth_wrong || std::abs(wrong_depth[c]*255-reference[0][c])>4;}
    Check(neighbor_wrong,"sampling native transmission at the neighboring mask texel is incorrect");
    Check(depth_wrong,"destination final background depth cannot replace retained cue tap depth");
    std::printf("tap witness near rgb=%u,%u,%u far rgb=%u,%u,%u; neighbor/depth substitution rejected\n",
        unsigned(reference[0][0]),unsigned(reference[0][1]),unsigned(reference[0][2]),
        unsigned(reference[1][0]),unsigned(reference[1][1]),unsigned(reference[1][2]));
}
int Run() {
    GLint depth=0,stencil=0,alpha=0,samples=0;
    glGetIntegerv(GL_DEPTH_BITS,&depth);glGetIntegerv(GL_STENCIL_BITS,&stencil);
    glGetIntegerv(GL_ALPHA_BITS,&alpha);glGetIntegerv(0x80A9,&samples);
    if(depth!=24 || stencil!=8 || alpha!=8 || samples!=0){
        std::fprintf(stderr,"SKIP source feasibility requires native depth24 stencil8 alpha8 samples0; actual %d %d %d %d\n",depth,stencil,alpha,samples);return 77;
    }
    VisibilityWitness();
    glViewport(0,0,width,height);Scratch scratch;
    const auto cold=std::chrono::steady_clock::now();
    if(!scratch.Create()){std::fprintf(stderr,"source scratch unavailable\n");scratch.Release();return 77;}
    glFinish();const double cold_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-cold).count();
    const std::array<unsigned char,4> backgrounds[]{{51,102,153,77},{204,26,64,230}};
    int cases=0;
    for(const auto& background:backgrounds)for(const GLenum function:{GL_LESS,GL_LEQUAL,GL_EQUAL})
    for(const bool write:{false,true})for(const bool alpha_write:{false,true})
    for(const float z:{-.5F,0.0F,.5F})for(int variant=0;variant<4;++variant){
        Packet p;p.function=function;p.depth_write=write;p.alpha_write=alpha_write;p.z=z;
        if(variant==1){p.alpha_ref=0;p.flip=true;p.color={.35F,.8F,.6F,.5F};}
        if(variant==2){p.x0=-1.4F;p.flip=true;}
        if(variant==3)p.x1=p.x0;
        Background(background);scratch.Apply(p);
        const Image before=Read();const auto state=Observe();Image source;
        Check(Capture(scratch,p,&source),"shared guard admitted bounded source experiment");
        SameNative(state,Observe());const Image unchanged=Read();
        Check(before.rgba==unchanged.rgba && before.depth==unchanged.depth && before.stencil==unchanged.stencil,
            "scratch does not alter native color/depth/stencil");
        Quad(p);Compare(p,before,source,Read());++cases;
    }
    // Native order is a separate dimension from depth. Retain two per-submission
    // results in this test oracle only; never claim nearest-only suffices.
    std::array<std::array<unsigned char,4>,2> ordered{};
    for(int order=0;order<2;++order){
        Background(backgrounds[0]);Image previous=Read();float first_depth=0;
        for(int n=0;n<2;++n){
            Packet p;p.z=(n==order)?-.5F:-.25F;p.alpha_ref=0;p.color=(n==order)
                ?std::array<float,4>{1,.25F,.25F,.5F}:std::array<float,4>{.25F,1,.25F,.5F};
            scratch.Apply(p);Image source;Check(Capture(scratch,p,&source),"successive source capture");
            Quad(p);const Image native=Read();Compare(p,previous,source,native);previous=native;
            const int center=width*height/2+width/2;
            if(n==0)first_depth=source.depth[center];
            else Check(std::abs(first_depth-source.depth[center])>.1F,"successive overlapping depths stay distinct");
        }
        const int sample=(height/2+4)*width+width/2+12;
        for(int c=0;c<4;++c)ordered[order][c]=previous.rgba[sample*4+c];
    }
    Check(ordered[0]!=ordered[1],"reversing native overlapping draws exposes order dependence");
    TapWitness(scratch);
    Packet p;p.z=-.5F;p.alpha_ref=0;Background(backgrounds[0]);scratch.Apply(p);
    using BeginQuery=void(APIENTRY*)(GLenum,GLuint);
    using EndQuery=void(APIENTRY*)(GLenum);
    using Result=void(APIENTRY*)(GLuint,GLenum,GLuint*);
    const auto gen_query=reinterpret_cast<Gen>(Procedure("glGenQueries"));
    const auto del_query=reinterpret_cast<Del>(Procedure("glDeleteQueries"));
    const auto begin_query=reinterpret_cast<BeginQuery>(Procedure("glBeginQuery"));
    const auto end_query=reinterpret_cast<EndQuery>(Procedure("glEndQuery"));
    const auto query_result=reinterpret_cast<Result>(Procedure("glGetQueryObjectuiv"));
    if(!gen_query || !del_query || !begin_query || !end_query || !query_result){scratch.Release();return 77;}
    GLuint query=0,samples_passed=1;gen_query(1,&query);begin_query(0x8914,query);
    Check(!Capture(scratch,p,nullptr),"active native samples query rejects supplemental geometry");
    end_query(0x8914);query_result(query,0x8866,&samples_passed);del_query(1,&query);
    Check(samples_passed==0,"rejected scratch never changes native query sample count");
    std::array<double,16> elapsed{},native_elapsed{};
    for(int n=-3;n<16;++n){const auto start=std::chrono::steady_clock::now();
        Check(Capture(scratch,p,nullptr),"timed scratch pass");glFinish();
        if(n>=0)elapsed[n]=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
        const auto native_start=std::chrono::steady_clock::now();Quad(p);glFinish();
        if(n>=0)native_elapsed[n]=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-native_start).count();}
    std::sort(elapsed.begin(),elapsed.end());std::sort(native_elapsed.begin(),native_elapsed.end());
    std::printf("source feasibility cases=%d scratch_bytes=%d size=%dx%d cold_ms=%.3f steady_median_ms=%.3f native_quad_median_ms=%.3f (glFinish, no readback; local test only)\n",
        cases,width*height*8,width,height,cold_ms,(elapsed[7]+elapsed[8])*.5,(native_elapsed[7]+native_elapsed[8])*.5);
    Check(glGetError()==GL_NO_ERROR,"source experiment GL errors");scratch.Release();
    return failures?1:0;
}
} // namespace source_experiment
