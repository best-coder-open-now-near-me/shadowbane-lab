// Exercise the actual observer without injecting a game or creating a GL context.
#include "terrain_trace.cpp"

#include <limits>
#include <string>
#include <vector>

using namespace wonderbane::extension;
namespace {
int calls = 0, active_unit = static_cast<int>(kTexture0 + 1U), maximum_units = 2;
int active_changes = 0;
HGLRC context = reinterpret_cast<HGLRC>(0x1234U);
const char* version = "1.3 test";
bool proc_available = true, program_proc_available = true;
int program_calls = 0, profile_mask = 2;
void APIENTRY Program(unsigned int target,unsigned int name,int* output) {
    ++program_calls;
    if (name != 0x8677U || (target != 0x8620U && target != 0x8804U)) std::abort();
    *output = target == 0x8620U ? 71 : 72;
}
void APIENTRY EnvironmentReal(unsigned int target,unsigned int name,float* output) {
    if(target != 0x2300U || name != 0x2201U) std::abort();
    std::fill_n(output,4U,0.25F);
}
const char* extensions = "";
std::vector<unsigned int> integer_queries;
void APIENTRY Integer(const unsigned int name, int* output) {
    ++calls;
    integer_queries.push_back(name);
    if (name == 0x84E0U) { *output = active_unit; }
    else if (name == 0x84E2U) { *output = maximum_units; }
    else if (name == 0x0BA2U) { output[0] = output[1] = 0; output[2] = 800; output[3] = 600; }
    else if (name == 0x9126U) { *output=profile_mask; }
    else if (name == 0x0B40U) { output[0]=output[1]=0x1B02; }
    else if (name == 0x0C10U) { output[0]=output[1]=0;output[2]=800;output[3]=600; }
    else if (name == 0x0D32U) { *output=6; }
    else if (name == 0x0C23U) { output[0]=1;output[1]=0;output[2]=1;output[3]=0; }
    else if (name == 0x8069U) { *output = 100 + active_unit - static_cast<int>(kTexture0); }
    else { *output = static_cast<int>(name); }
}
void APIENTRY Real(const unsigned int name, float* output) {
    ++calls;
    if (name == 0x0B70U) { output[0]=0.0F;output[1]=1.0F;return; }
    if (name == 0x0BC2U) { *output = 0.5F; return; }
    if (name == 0x0B00U) { std::fill_n(output, 4U, 1.0F); return; }
    std::fill_n(output, 16U, 0.0F);
    output[0] = output[5] = output[10] = output[15] = 1.0F;
    if (name == 0x0BA8U) { output[0] = static_cast<float>(active_unit - static_cast<int>(kTexture0) + 1); }
}
void APIENTRY Parameter(unsigned int, unsigned int, int* output) { ++calls; *output = 33071; }
void APIENTRY Level(unsigned int, int, unsigned int, int* output) { ++calls; *output = 64; }
void APIENTRY Environment(unsigned int, unsigned int, int* output) { ++calls; *output = 8448; }
const unsigned char* APIENTRY String(unsigned int name) {
    return reinterpret_cast<const unsigned char*>(name == 0x1F02U ? version : extensions);
}
void APIENTRY Active(unsigned int unit) { ++active_changes; active_unit = static_cast<int>(unit); }
HGLRC WINAPI Context() { return context; }
PROC WINAPI Proc(LPCSTR name) {
    if(std::strcmp(name,"glGetProgramivARB")==0)
        return program_proc_available ? reinterpret_cast<PROC>(&Program) : nullptr;
    return proc_available ? reinterpret_cast<PROC>(&Active) : nullptr;
}
int Fail(const char* reason) { std::fprintf(stderr, "%s\n", reason); return 1; }
void FakeStart() {
    g_frame = new TraceFrame{};
    g_request = CreateEventW(nullptr, FALSE, FALSE, nullptr);
    g_idle = CreateEventW(nullptr, TRUE, TRUE, nullptr);
    g_gl = {Integer, Real, Parameter, Level, Environment, String, nullptr, Context, Proc, nullptr, EnvironmentReal};
    g_frequency = 1000000000U; // overriden for timing-limit test
    g_image_base = 0x400000U; g_image_size = 0x100000U;
    g_phase.store(Phase::idle);
}
void Arm() { SetEvent(g_request); TerrainTracePresent(); }
void Draw(bool safe = true) {
    TerrainTraceDraw(TerrainSubmission::arrays, 0x400123U, 4U, 2, 6, 0U, 0U, true, safe);
}
bool MaterialQueryAudit() {
    version="2.1 test";extensions="GL_ARB_vertex_program GL_ARB_fragment_program";
    proc_available=true;program_proc_available=true;maximum_units=2;
    DetectCapabilities(*g_frame);
    DrawRecord captured{};program_calls=0;integer_queries.clear();
    const int previous_unit=active_unit;
    ReadState(captured,*g_frame);
    if(program_calls!=2 || captured.arb_programs[1]!=71 || captured.arb_programs[3]!=72
        || captured.textures[0].env_color[0]!=0.25F || active_unit!=previous_unit
        || !captured.active_unit_restored || captured.depth_range[1]!=1.0F) return false;
    program_proc_available=false;DetectCapabilities(*g_frame);
    captured={};ReadState(captured,*g_frame);
    if(captured.arb_programs[1]!=-1 || captured.arb_programs[3]!=-1 || program_calls!=2) return false;
    version="1.1 test";extensions="";DetectCapabilities(*g_frame);
    integer_queries.clear();captured={};ReadState(captured,*g_frame);
    for(const unsigned int illegal:{0x8620U,0x8804U,0x806FU,0x8513U,0x84F5U,0x80A8U,0x80A9U,0x8458U})
        if(std::find(integer_queries.begin(),integer_queries.end(),illegal)!=integer_queries.end())return false;
    if(captured.arb_programs[0]!=0 || captured.arb_programs[1]!=-1 || captured.raster[1]!=0)return false;
    extensions="GL_ARB_fragment_program";program_proc_available=true;DetectCapabilities(*g_frame);
    captured={};program_calls=0;ReadState(captured,*g_frame);
    if(program_calls!=1 || captured.arb_programs[0]!=0 || captured.arb_programs[1]!=-1
        || captured.arb_programs[3]!=72)return false;
    extensions=nullptr;DetectCapabilities(*g_frame);captured={};ReadState(captured,*g_frame);
    if(captured.arb_programs[0]!=-1 || captured.textures[0].alternate_targets[1]!=-1)return false;
    extensions="GL_ARB_vertex_program2 GL_ARB_fragment_program2";DetectCapabilities(*g_frame);
    if(g_frame->arb_vertex || g_frame->arb_fragment)return false;
    version="1.3 test";extensions="";program_proc_available=true;
    return true;
}
bool MaterialGateAudit() {
    version="2.1 test";extensions="GL_ARB_vertex_program GL_ARB_fragment_program";
    DetectCapabilities(*g_frame);
    DrawRecord base{};ReadState(base,*g_frame);
    base.submission=TerrainSubmission::immediate;base.mode=7U;base.caller_rva=0x538ED0U;
    base.program=0;base.arb_programs={0,71,0,72};base.state[8]=base.state[9]=base.raster[3]=0;
    for(auto& t:base.textures){t.enabled=0;t.alternate_targets.fill(0);t.texgen.fill(0);}
    base.textures[0].enabled=1;base.textures[0].env_mode=0x2100;
    auto candidate=[&](const DrawRecord& d){return std::strcmp(QuadMaterialGate(d,*g_frame),
        "fixed_function_material_candidate")==0;};
    if(!candidate(base))return false;
    DrawRecord changed=base;changed.caller_rva=0xD8F13U;if(!candidate(changed))return false;
    changed=base;changed.program=7;if(candidate(changed))return false;
    changed=base;changed.arb_programs[0]=1;if(candidate(changed))return false;
    changed=base;changed.arb_programs[2]=1;if(candidate(changed))return false;
    changed=base;changed.arb_programs[1]=-1;if(candidate(changed))return false;
    changed=base;changed.state[8]=1;if(candidate(changed))return false;
    changed=base;changed.state[9]=1;if(candidate(changed))return false;
    changed=base;changed.raster[3]=1;if(candidate(changed))return false;
    changed=base;changed.textures[0].env_mode=0x8570;if(candidate(changed))return false;
    changed=base;changed.textures[0].texgen[0]=1;if(candidate(changed))return false;
    changed=base;changed.textures[0].alternate_targets[2]=1;if(candidate(changed))return false;
    changed=base;changed.textures[1].enabled=1;if(candidate(changed))return false;
    changed=base;changed.active_unit_restored=false;if(candidate(changed))return false;
    changed=base;changed.submission=TerrainSubmission::list;if(candidate(changed))return false;
    changed=base;changed.caller_rva=0x123U;if(candidate(changed))return false;
    g_frame->omitted_units=1;if(candidate(base))return false;g_frame->omitted_units=0;
    extensions="GL_NV_fragment_program";DetectCapabilities(*g_frame);if(candidate(base))return false;
    extensions=nullptr;DetectCapabilities(*g_frame);if(candidate(base))return false;
    version="3.0 test";extensions="";DetectCapabilities(*g_frame);if(candidate(base))return false;
    version="3.2 test";profile_mask=2;DetectCapabilities(*g_frame);if(!candidate(base))return false;
    profile_mask=1;DetectCapabilities(*g_frame);if(candidate(base))return false;profile_mask=2;
    version="4.1 test";DetectCapabilities(*g_frame);if(candidate(base))return false;
    version="2.1 test";extensions="GL_ARB_separate_shader_objects";
    DetectCapabilities(*g_frame);if(candidate(base))return false;
    version="1.3 test";extensions="";return true;
}
bool TransmissionQueryAudit() {
    struct Case { const char* version; const char* extensions; bool separate, modern, fbo; };
    const Case cases[]{
        {"1.1 test","",false,false,false}, {"1.3 test","",false,false,false},
        {"1.4 test","",true,false,false}, {"2.0 test","",true,true,false},
        {"1.1 test","GL_EXT_framebuffer_object",false,false,true},
        {"1.3 test","GL_EXT_blend_func_separate GL_ARB_shader_objects",false,false,false},
        {"3.0 test","",true,true,true}};
    for (const auto& test:cases) {
        version=test.version;extensions=test.extensions;proc_available=true;
        DetectCapabilities(*g_frame);
        // Isolate state queries; existing tests exercise all texture-unit queries.
        g_frame->unit_count=0;g_frame->multitexture=false;g_gl.active=nullptr;
        DrawRecord value{};integer_queries.clear();ReadState(value,*g_frame);
        std::vector<unsigned int> expected{0xB71,0xB72,0xB74,0xBC0,0xBC1,0xBE2,
            0xBE1,0xBE0,0xB50,0xB60,0xB44,0xB90,0xB92,0xB93,0xB97,0xB98,
            0xB94,0xB95,0xB96,0xC23,0xBA2};
        if(test.separate)expected.insert(expected.end(),{0x80CB,0x80CA,0x8009});
        if(test.modern)expected.insert(expected.end(),{0x883D,0x8B8D,0x8800,
            0x8CA4,0x8CA3,0x8CA5,0x8801,0x8802,0x8803});
        if(test.fbo)expected.push_back(0x8CA6);
        expected.insert(expected.end(),{0xC40,0xC11,0x8037,0xBF2,0xD32,0xB40,0xC10,
            0x3000,0x3001,0x3002,0x3003,0x3004,0x3005});
        if(Version13(test.version))expected.insert(expected.end(),{0x80A8,0x80A9});
        if(test.separate)expected.push_back(0x8458);
        std::sort(expected.begin(),expected.end());
        std::sort(integer_queries.begin(),integer_queries.end());
        if(integer_queries!=expected)return false; // rejects every unsupported or unexpected query
        const std::array<int,6> blend{0xBE1,0xBE0,test.separate?0x80CB:-1,
            test.separate?0x80CA:-1,test.separate?0x8009:-1,test.modern?0x883D:-1};
        const std::array<int,15> stencil{0xB90,0xB92,0xB93,0xB97,0xB98,0xB94,0xB95,0xB96,
            test.modern?0x8800:-1,test.modern?0x8CA4:-1,test.modern?0x8CA3:-1,
            test.modern?0x8CA5:-1,test.modern?0x8801:-1,test.modern?0x8802:-1,test.modern?0x8803:-1};
        if(value.blend_detail!=blend || value.stencil_detail!=stencil
            || value.program!=(test.modern?0x8B8D:-1) || value.framebuffer!=(test.fbo?0x8CA6:-1)
            || value.color_mask!=std::array<int,4>{1,0,1,0})return false;
    }
    return true;
}

}

int main() {
    Draw(); TerrainTraceClear(true, 0x4100U); TerrainTraceDone3d(); TerrainTracePresent();
    if (IsTerrainTraceCapturing() || calls != 0 || g_phase.load() != Phase::disabled) { return Fail("disabled observer queried GL"); }
    if (LocalOrdinaryDirectory(L"\\\\server\\share")
        || LocalOrdinaryDirectory(L"relative") || LocalOrdinaryDirectory(L"\\\\?\\C:\\")) {
        return Fail("non-local destination accepted");
    }
    if (!Version13("1.3 Mesa") || Version13("1.2 Mesa") || Version13(nullptr)
        || Token("GL_ARB_multitexture2", "GL_ARB_multitexture")
        || !Token("X GL_ARB_multitexture Y", "GL_ARB_multitexture")) {
        return Fail("capability parsing");
    }
#ifdef WONDERBANE_EXTENSION_DIAGNOSTICS_ONLY
    SetEnvironmentVariableW(L"WONDERBANE_TERRAIN_TRACE", L"1");
    StartTerrainTrace(L"C:\\test\\status.json", 1U, 1U,
        "55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc");
    if (g_phase.load() != Phase::disabled) { return Fail("diagnostics profile enabled renderer trace"); }
    SetEnvironmentVariableW(L"WONDERBANE_TERRAIN_TRACE", nullptr);
#endif
    FakeStart();
    if(!MaterialQueryAudit() || !MaterialGateAudit())return Fail("bounded material evidence eligibility");
    calls=0;active_changes=0;
    Draw();
    if (calls != 0) { return Fail("idle observer queried GL"); }
    Arm();
    if (WaitForSingleObject(g_idle, 0) != WAIT_TIMEOUT) { return Fail("busy channel stayed idle"); }
    TerrainTraceClear(false, 0x4100U); Draw();
    if (calls != 0 || g_phase.load() != Phase::armed) { return Fail("unreviewed clear armed capture"); }
    TerrainTraceClear(true, 0x4100U);
    if (!IsTerrainTraceCapturing() || !g_frame->helpers_available || g_frame->unit_count != 2U) { return Fail("capability detection"); }
    const int before_unsafe = calls;
    Draw(false);
    if (calls != before_unsafe || g_frame->unsafe != 1U) { return Fail("unsafe GL query"); }
    TerrainTraceDraw(TerrainSubmission::multi_elements, 0x400123U, 4U, 0, 2, 0x1403U, 0U, true, true);
    const auto& draw = g_frame->draws[0];
    if (g_frame->retained != 1U || draw.caller_rva != 0x123U
        || draw.submission != TerrainSubmission::multi_elements || draw.count != 2
        || draw.textures[0].binding != 100 || draw.textures[1].binding != 101
        || draw.textures[1].matrix[0] != 2.0F || !draw.active_unit_restored
        || active_unit != static_cast<int>(kTexture0 + 1U) || active_changes != 3) {
        return Fail("per-unit capture or active unit restoration");
    }
    if (draw.program!=-1 || draw.framebuffer!=-1 || draw.blend_detail[2]!=-1
        || draw.stencil_detail[8]!=-1 || draw.color_mask!=std::array<int,4>{1,0,1,0})
        return Fail("legacy optional state availability");
    g_frame->query_ticks = g_frequency;
    Draw();
    if (g_frame->budget_skipped != 1U || g_frame->retained != 1U) { return Fail("time bound"); }
    g_frame->query_ticks = 0;
    g_frame->retained = kMaxDraws;
    Draw();
    if (g_frame->overflow != 1U) { return Fail("record bound"); }
    g_frame->retained = 1;
    TerrainTraceDone3d();
    const int before_ui = calls;
    Draw();
    if (calls != before_ui || !TerrainTracePresent() || !g_frame->done3d) { return Fail("UI boundary"); }
    // Serialize the real record, including nonfinite input, to a disposable test file.
    wchar_t directory[MAX_PATH]{}, temporary[MAX_PATH]{};
    if (!GetTempPathW(MAX_PATH, directory) || !GetTempFileNameW(directory, L"wtt", 0, temporary)) {
        return Fail("temporary test path");
    }
    HANDLE file = CreateFileW(temporary, GENERIC_WRITE | GENERIC_READ, 0, nullptr,
        OPEN_EXISTING, FILE_ATTRIBUTE_TEMPORARY | FILE_FLAG_DELETE_ON_CLOSE, nullptr);
    if (file == INVALID_HANDLE_VALUE) { return Fail("temporary test file"); }
    g_frame->draws[0].model_view[0] = std::numeric_limits<float>::quiet_NaN();
    Json json; json.file = file; WriteFrame(json, *g_frame); json.Flush();
    SetFilePointer(file, 0, nullptr, FILE_BEGIN);
    char contents[16384U]{}; DWORD read = 0;
    ReadFile(file, contents, sizeof(contents) - 1U, &read, nullptr);
    CloseHandle(file);
    if (!json.ok || std::strstr(contents,"\"replay_eligible\":false")==nullptr
        || std::strstr(contents,"\"arb_enable_binding\":")==nullptr
        || std::strstr(contents,"\"env_color\":[0.25,0.25,0.25,0.25]")==nullptr
        || std::strstr(contents, "\"transmission_state\":{\"unavailable\":-1,\"program\":-1") == nullptr
        || std::strstr(contents, "\"submission_label\":\"multi_elements\",\"count_unit\":\"subdraws\"") == nullptr
        || std::strstr(contents, "\"model_view\":[null,") == nullptr
        || std::strstr(contents, "\"display_lists\":\"entry-state-only-not-internal-draws\"") == nullptr
        || std::strstr(contents, "\"reviewed_interval_complete\":true") == nullptr) {
        return Fail("JSON fidelity and scope");
    }
    g_phase.store(Phase::idle);
    Arm();
    if (!TerrainTracePresent() || g_frame->main_clear || g_frame->done3d) { return Fail("missing clear failure"); }
    g_phase.store(Phase::idle); Arm(); TerrainTraceClear(true, 0x4100U);
    TerrainTraceClear(false, 0x100U);
    if (!g_frame->extra_depth_clear || !TerrainTracePresent() || g_frame->done3d) {
        return Fail("interrupted or missing done3d failure");
    }
    g_phase.store(Phase::idle); Arm(); TerrainTraceClear(true, 0x4100U);
    context = reinterpret_cast<HGLRC>(0x5678U);
    const int before_mismatch = calls; Draw();
    if (!g_frame->context_mismatch || calls != before_mismatch) { return Fail("context guard"); }
    context = reinterpret_cast<HGLRC>(0x1234U);
    g_frame->thread = GetCurrentThreadId() + 1U; Draw();
    if (calls != before_mismatch || g_frame->unsafe != 2U) { return Fail("thread guard"); }
    g_phase.store(Phase::idle); maximum_units = 8; Arm(); TerrainTraceClear(true, 0x4100U);
    if (g_frame->unit_count != 4U || g_frame->omitted_units != 4U) { return Fail("unit cap"); }
    g_phase.store(Phase::idle); proc_available = false; Arm(); TerrainTraceClear(true, 0x4100U);
    const int before_missing = calls; Draw();
    if (g_frame->helpers_available || calls != before_missing) { return Fail("missing multitexture function"); }
    g_phase.store(Phase::idle); version = "1.1 test"; Arm(); TerrainTraceClear(true, 0x4100U);
    if (!g_frame->helpers_available || g_frame->unit_count != 1U || g_frame->combine_supported) {
        return Fail("legacy capability fallback");
    }
    if(!TransmissionQueryAudit())return Fail("exact transmission pnames, capability gates or field order");
    StopTerrainTrace();
    if (g_frame != nullptr || g_request != nullptr || g_idle != nullptr
        || g_phase.load() != Phase::disabled) {
        return Fail("shutdown");
    }
    return 0;
}
