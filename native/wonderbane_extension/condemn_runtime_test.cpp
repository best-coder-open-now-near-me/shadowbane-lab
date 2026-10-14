#include <Windows.h>
#include <iostream>
static HWND test_window = reinterpret_cast<HWND>(123);
static bool foreground = true, owner_thread = true, lease_alive = true;
static std::uint64_t runtime_tick = 100;
static HWND Foreground() { return foreground ? test_window : nullptr; }
static BOOL Iconic(HWND) { return FALSE; }
static DWORD OwnerThread(HWND, LPDWORD pid) { *pid = GetCurrentProcessId(); return owner_thread ? GetCurrentThreadId() : 0; }
static ULONGLONG Clock() { return runtime_tick; }
#define GetForegroundWindow Foreground
#define IsIconic Iconic
#define GetWindowThreadProcessId OwnerThread
#define GetTickCount64 Clock
#include "vendor_runtime.cpp"
#undef GetForegroundWindow
#undef IsIconic
#undef GetWindowThreadProcessId
#undef GetTickCount64
namespace ex = wonderbane::extension;
namespace ko = ex::condemn;
namespace v = ex::vendor;
static ko::native::Snapshot state;
static ko::Cursor cursor{12,34,0,0,0};
static unsigned opens = 0, adds = 0, enables = 0, other_reads = 0, other_writes = 0;
static unsigned order = 0, drained_order = 0, captured_order = 0;
static bool reply = false, readable = true;
static bool vendor_active = false, production_readable = true;
static v::wire::Snapshot vendor_state;
static ex::vendor_production::Cursor production_cursor{12,34,0,0,0};
static std::unique_ptr<ex::vendor_production::Batch> production_input;
static unsigned vendor_creates = 0, production_reads = 0;
static std::uint32_t funding_minimum = 0;
static int failures = 0;
static void Check(bool b, const char* why) { if (!b) { ++failures; std::cerr << why << '\n'; } }
namespace wonderbane::extension {
namespace movement {
bool VerifyNativeMovementImage(std::uintptr_t& out) noexcept { out = 1; return true; }
bool ReadNativeMovementLifetime(NativeScene& out) noexcept { out = {}; out.window = state.root; out.epoch = state.scene; out.identity = state.local; return true; }
bool NativeMovementLifetimeCurrent(const NativeScene& s) noexcept { return s.epoch == state.scene && s.identity == state.local; }
}
namespace condemn {
bool ReadCursor(Cursor& out) noexcept { out = cursor; return readable; }
bool ReadAfter(const Cursor& before, Batch& out) noexcept {
    drained_order = ++order; out.count = 0; out.after = cursor;
    if (!readable) { return false; }
    if (reply) {
        out.count = 3; out.after.sequence = before.sequence + 3;
        for (unsigned i = 0; i < 3; ++i) {
            auto& r = out.records[i]; r = {}; r.sequence = static_cast<LONG64>(before.sequence + i + 1);
            r.decode_sequence = before.sequence + 1; r.stage = i + 1; r.flags = i ? 7 : 3;
            r.tick_ms = runtime_tick; r.thread_id = 1; r.scene_epoch = state.scene; r.local = state.local;
            r.caller_rva = i ? 0x1234 : 0x3625bc; r.payload.operation = 17; r.payload.fields = 1;
            r.payload.building = state.building; r.payload.entry = state.entry_key; r.payload.state = 1;
        }
        cursor = out.after; reply = false;
    }
    return true;
}
namespace native {
bool Capture(std::uintptr_t, const movement::NativeScene&, const Target&, Snapshot& out) noexcept { captured_order = ++order; out = state; return true; }
Result Invoke(std::uintptr_t, const movement::NativeScene&, const Target&, Action a,
    const Snapshot&, Admission admit, void* ctx) noexcept {
    if (!admit(ctx)) { return Result::unavailable; }
    if (a == Action::open) { ++opens; } else if (a == Action::add) { ++adds; } else { ++enables; }
    return Result::submitted;
}
}
}
namespace vendor {
bool Capture(std::uintptr_t, const movement::NativeScene&, wire::Snapshot& out, std::uint32_t,
    bool& present, bool& top, wire::RemainingCounts* counts) noexcept {
    ++other_reads;
    if (!vendor_active) { return false; }
    out=vendor_state; present=false; top=true;
    if(counts) { counts->fill(1); }
    return true;
}
bool InvokeNative(std::uintptr_t, wire::Verb, const wire::Snapshot&, std::uint32_t) noexcept { ++other_writes; return false; }
}
namespace vendor_menu {
bool OrderCostMatches(std::uintptr_t, const vendor::wire::Snapshot&,
    const vendor::wire::OrderBudget& budget, std::uint32_t minimum) noexcept {
    ++other_reads; funding_minimum=minimum; return vendor_active && minimum==budget.total;
}
vendor::wire::Outcome InvokeRandomCreate(std::uintptr_t, const movement::NativeScene&,
    const vendor::wire::Snapshot& expected, Admission admit, void* context, bool orders) noexcept {
    ++other_writes;
    if(!vendor_active || !orders || !admit(context)) { return vendor::wire::Outcome::unavailable; }
    ++vendor_creates;
    auto& r=production_input->records[production_input->count++]; r={};
    r.sequence=static_cast<LONG64>(++production_cursor.sequence); r.stage=4; r.flags=3;
    r.thread_id=GetCurrentThreadId(); r.scene_epoch=expected.scene; r.local=state.local;
    r.payload.action=1; r.payload.fields=8; r.payload.building={expected.building,8};
    r.payload.vendor={expected.vendor,42}; r.payload.reference={expected.item_template,0};
    r.payload.quantity=expected.quantity; r.payload.multiple=1; r.payload.marker=expected.table;
    production_input->after=production_cursor;
    return vendor::wire::Outcome::submitted;
}
bool Capture(std::uintptr_t, const movement::NativeScene&, wire::Snapshot&) noexcept { ++other_reads; return false; }
wire::Outcome Invoke(std::uintptr_t, const movement::NativeScene&, wire::Verb,
    const wire::Command&, Admission, void*) noexcept { ++other_writes; return wire::Outcome::unavailable; }
}
namespace vendor_production {
bool ReadCursor(Cursor& out) noexcept {
    ++other_reads; out=production_cursor; return vendor_active && production_readable;
}
bool ReadAfter(const Cursor& before, Batch& out) noexcept {
    ++other_reads; ++production_reads;
    if(!vendor_active || !production_readable || !production_input
        || before.sequence+production_input->count!=production_cursor.sequence) { return false; }
    out=*production_input; out.after=production_cursor; production_input->count=0;
    return true;
}
}
namespace city_window {
bool Capture(std::uintptr_t, const movement::NativeScene&, wire::Snapshot&) noexcept { ++other_reads; return false; }
bool InvokeOpen(std::uintptr_t, const wire::Snapshot&) noexcept { ++other_writes; return false; }
}
namespace guard_upgrade {
bool Capture(std::uintptr_t, const movement::NativeScene&, wire::Snapshot&, bool&) noexcept { ++other_reads; return false; }
bool CaptureReturn(std::uintptr_t, const movement::NativeScene&, const wire::Snapshot&, ReturnSnapshot&) noexcept { ++other_reads; return false; }
bool Invoke(std::uintptr_t, const wire::Snapshot&) noexcept { ++other_writes; return false; }
}
namespace guard_funding {
bool Capture(std::uintptr_t, const movement::NativeScene&, std::uint32_t, wire::Snapshot&, bool&) noexcept { ++other_reads; return false; }
bool InvokeOpen(std::uintptr_t, const movement::NativeScene&, const wire::Command&, Admission, void*) noexcept { ++other_writes; return false; }
bool Invoke(std::uintptr_t, const movement::NativeScene&, const wire::Command&, Admission, void*) noexcept { ++other_writes; return false; }
}
namespace vendor_navigation {
bool Capture(std::uintptr_t, const movement::NativeScene&, wire::Snapshot&) noexcept { ++other_reads; return false; }
bool FindVendorControl(std::uintptr_t, const wire::Snapshot&, wire::Key, std::uint32_t&) noexcept { ++other_reads; return false; }
bool FindGuardControl(std::uintptr_t, const wire::Snapshot&, wire::Key, std::uint32_t&) noexcept { ++other_reads; return false; }
bool InvokeGuard(std::uintptr_t, const wire::Snapshot&, wire::Key, Admission, void*) noexcept { ++other_writes; return false; }
bool InvokeVendor(std::uintptr_t, const wire::Snapshot&, wire::Key, Admission, void*) noexcept { ++other_writes; return false; }
bool BuildingTarget::Bind(HWND) noexcept { return true; }
vendor::wire::Outcome BuildingTarget::Open(const movement::NativeScene&, Key, Admission, void*) noexcept { ++other_writes; return vendor::wire::Outcome::unavailable; }
vendor::wire::Outcome BuildingTarget::OpenWarehouse(const movement::NativeScene&, Key, WarehouseSource, Admission, void*) noexcept { ++other_writes; return vendor::wire::Outcome::unavailable; }
}
}
static bool Lease(void*, const ex::movement::wire::Host&, std::uint64_t) noexcept { return lease_alive; }
static std::shared_ptr<ex::movement::CommandLease> Producer() {
    auto p = std::make_shared<ex::movement::CommandLease>();
    p->process = CreateEventW(nullptr, TRUE, FALSE, nullptr); p->validate = &Lease; return p;
}
template<class T> static void Allow(const std::shared_ptr<T>& q) {
    q->lease = Producer(); q->deadline = runtime_tick + 500; q->command.window = 123;
}
static void Frame() { ++runtime_tick; v::Update(reinterpret_cast<void*>(state.root), test_window); }
static ko::wire::Receipt Run(const ko::wire::Command& c, ko::wire::Verb verb) {
    auto q = std::make_shared<ko::QueuedCommand>(); q->command = c; q->verb = verb;
    q->lease = Producer(); q->deadline = runtime_tick + 500;
    Check(ko::Queue(q), "queue accepted"); Frame();
    Check(q->state.load() == 2 && q->execution_thread == GetCurrentThreadId(), "receipt belongs to owner thread");
    ko::Release(q); return q->receipt;
}
static v::wire::Receipt VendorCommand(v::wire::Command command, v::wire::Verb verb) {
    auto q=std::make_shared<v::QueuedCommand>(); q->command=command; q->verb=verb; Allow(q);
    Check(v::Queue(q), "vendor command queued"); Frame();
    Check(q->state.load()==2 && q->execution_thread==GetCurrentThreadId(), "vendor receipt on native owner");
    v::Release(q); return q->receipt;
}
static void VendorReply(std::uint32_t item, unsigned first, unsigned last) {
    namespace p=ex::vendor_production;
    const auto decode=production_cursor.sequence+1-(first-1);
    for(unsigned stage=first;stage<=last;++stage) {
        auto& r=production_input->records[production_input->count++]; r={};
        r.sequence=static_cast<LONG64>(++production_cursor.sequence); r.stage=stage;
        r.flags=stage==1?3:7; r.decode_sequence=decode; r.thread_id=GetCurrentThreadId();
        r.scene_epoch=vendor_state.scene; r.local=state.local;
        r.payload.action=8; r.payload.fields=5; r.payload.building={vendor_state.building,8};
        r.payload.vendor={vendor_state.vendor,42}; r.payload.item={item,40};
        r.payload.item_template=vendor_state.item_template; r.payload.queue_count_raw=1;
    }
    production_input->after=production_cursor;
}
static void VerifyVendorOrders() {
    namespace w=v::wire;
    v::controller={}; v::menu_controller={}; v::order_admission.Reset();
    vendor_active=true; production_input=std::make_unique<ex::vendor_production::Batch>();
    vendor_state={}; vendor_state.scene=state.scene; vendor_state.root=state.root;
    vendor_state.manager=200; vendor_state.menu=300; vendor_state.recipe=400; vendor_state.hireling=500;
    vendor_state.building=20; vendor_state.vendor=777; vendor_state.item_template=26990;
    vendor_state.prefix=vendor_state.suffix=3362971591U; vendor_state.mode=1;
    vendor_state.table=12; vendor_state.quantity=10; vendor_state.multiple=1; vendor_state.count=2;
    vendor_state.slots[0].entry=600; vendor_state.slots[1].entry=700;
    Frame();
    w::Command create{}; create.host={10,1,456}; create.window=123; create.request[0]=20;
    create.reserved[0]=42; create.expected=v::controller.Current();
    const w::OrderBudget budget{1,2,10,555,1660,3320};
    std::memcpy(create.reserved+16,&budget,sizeof(budget));
    const auto sent=VendorCommand(create,w::Verb::create_orders);
    Check(sent.outcome==1 && sent.flags==w::in_flight && vendor_creates==1 && funding_minimum==3320,
        "native owner sends one fully funded request");
    vendor_state.slots[0]={600,1001,1}; vendor_state.slots[1]={700,1002,1};
    VendorReply(1001,1,2); Frame();
    Check(v::controller.PendingOrders(), "visible rows and incomplete callbacks cannot admit batch");
    VendorReply(1001,3,3); VendorReply(1002,1,3); Frame();
    w::Command inspect{}; inspect.host=create.host; inspect.window=123; inspect.request[0]=21;
    const auto admitted=VendorCommand(inspect,w::Verb::inspect_orders);
    Check(admitted.flags==w::ready && admitted.transition_request==create.request
        && admitted.reserved[0]==1 && production_reads>=2 && vendor_creates==1,
        "owner service reconciles split receive intervals without quota-count assumptions");
    vendor_state.slots[0]={600,0,0}; vendor_state.slots[1]={700,0,0}; ++vendor_state.menu; Frame();
    create.request[0]=22; create.expected=v::controller.Current();
    Check(VendorCommand(create,w::Verb::create_orders).outcome==3 && vendor_creates==1,
        "reopened menu cannot dispatch same batch again");
    create.request[0]=23; create.reserved[0]=43; create.expected=v::controller.Current();
    Check(VendorCommand(create,w::Verb::create_orders).outcome==1 && vendor_creates==2,
        "new independently funded batch retains separate identity");
    production_readable=false; Frame();
    inspect.request[0]=24;
    Check(VendorCommand(inspect,w::Verb::inspect_orders).flags&w::unresolved,
        "lost production cursor makes native admission permanently unresolved");
}
int main() {
    state.scene = 7; state.local = {99,53}; state.root = 100; state.manager = 200;
    state.building_hud = state.front = 300; state.open_button = 400; state.building = {20,8};
    Check(v::Start(), "owner service starts with bounded response buffer");
    ko::wire::Command inspect{}; inspect.host = {10,1,456}; inspect.window = 123; inspect.request[0] = 1;
    inspect.target = {{20,8},{30,23},5};
    auto first = Run(inspect, ko::wire::Verb::inspect);
    Check(first.flags & ko::wire::ready, "scoped inspection ready on native owner");
    ko::wire::Command command = inspect; command.request[0] = 2; command.expected = first.snapshot;
    foreground = false;
    Check(Run(command, ko::wire::Verb::ensure).outcome == static_cast<unsigned>(ko::wire::Outcome::unavailable)
        && !opens, "background cannot start action");
    foreground = true;
    auto started = Run(command, ko::wire::Verb::ensure);
    Check(opens == 1 && v::condemn_controller.Busy() && started.flags & ko::wire::in_flight, "owner queue invokes one open");
    // Existing native invokers must refuse before capturing/invoking any other workflow.
    ex::movement::NativeScene scene{}; ex::movement::ReadNativeMovementLifetime(scene);
    other_reads = other_writes = 0;
    auto vq = std::make_shared<v::QueuedCommand>(); Allow(vq); v::NativeInvoker vi(vq, scene, test_window);
    vi.Invoke(v::wire::Verb::create, {}, 0);
    auto cq = std::make_shared<ex::city_window::QueuedCommand>(); Allow(cq); v::CityInvoker ci(cq, scene, test_window); ci.Open({});
    auto nq = std::make_shared<ex::vendor_navigation::QueuedCommand>(); Allow(nq); v::NavigationInvoker ni(nq, scene, test_window);
    ni.Open(ex::vendor_navigation::wire::Verb::building, {});
    auto gq = std::make_shared<ex::guard_upgrade::QueuedCommand>(); Allow(gq); v::GuardInvoker gi(gq, scene, test_window);
    gi.Upgrade({}); gq->verb = ex::guard_upgrade::wire::Verb::inspect; gi.Reopen({}, {});
    auto fq = std::make_shared<ex::guard_funding::QueuedCommand>(); Allow(fq); v::FundingInvoker fi(fq, scene, test_window);
    fi.Transfer(ex::guard_funding::wire::Verb::open_quote, {});
    auto mq = std::make_shared<ex::vendor_menu::QueuedCommand>(); Allow(mq); v::MenuInvoker mi(mq, scene, test_window);
    mi.Invoke(ex::vendor_menu::wire::Verb::open_recipe, {});
    Check(!other_reads && !other_writes, "Condemn barrier excludes every conflicting native invoker");
    state.kos = state.front = 500; state.list = 600; state.context = state.building;
    Frame(); Check(drained_order && drained_order < captured_order && !adds, "frame drains before row capture but cannot auto-advance");
    inspect.transition_request = command.request;
    ++inspect.host.generation; Run(inspect, ko::wire::Verb::inspect);
    Check(!adds, "replacement producer cannot continue original transaction"); --inspect.host.generation;
    lease_alive = false; Run(inspect, ko::wire::Verb::inspect); Check(!adds, "dead lease cannot advance"); lease_alive = true;
    Run(inspect, ko::wire::Verb::inspect); Check(adds == 1, "original owner advances to add");
    state.entry = 700; state.row = 800; state.entry_key = {30,23}; state.count = 1;
    Run(inspect, ko::wire::Verb::inspect); Check(enables == 1 && v::condemn_controller.Busy(), "same job advances to enable");
    state.enabled = 1; reply = true;
    auto other_scope = inspect; other_scope.target.scope = 4;
    const auto mixed = Run(other_scope, ko::wire::Verb::inspect);
    Check(!v::condemn_controller.Busy() && !(mixed.flags & ko::wire::ready)
        && mixed.target.scope == 5 && mixed.transition_target.scope == 5,
        "completion frame cannot relabel nation observation as guild state");
    const auto done = Run(inspect, ko::wire::Verb::inspect);
    Check(!v::condemn_controller.Busy() && done.phase == static_cast<unsigned>(ko::wire::Phase::verified)
        && done.completion_sequence == 3, "native owner confirms keyed response plus later row");
    const auto replay = Run(command, ko::wire::Verb::ensure);
    Check(replay.phase == started.phase && replay.response_floor == started.response_floor
        && opens == 1 && adds == 1 && enables == 1, "transport replay cannot invoke composite twice");
    auto queued = std::make_shared<ko::QueuedCommand>(); queued->command = inspect;
    queued->verb = ko::wire::Verb::inspect; queued->deadline = runtime_tick + 500; queued->lease = Producer();
    Check(ko::Queue(queued), "queue for owner-thread isolation"); owner_thread = false; Frame();
    Check(queued->state.load() == 0, "wrong thread cannot consume command"); owner_thread = true; Frame();
    Check(queued->state.load() == 2, "original owner consumes it"); ko::Release(queued);
    struct GuardCall final : ex::guard_upgrade::Invoker {
        ex::guard_upgrade::wire::Outcome Upgrade(const ex::guard_upgrade::wire::Snapshot&) noexcept override { return ex::guard_upgrade::wire::Outcome::submitted; }
        ex::guard_upgrade::wire::Outcome Reopen(const ex::guard_upgrade::wire::Snapshot&, const ex::guard_upgrade::ReturnSnapshot&) noexcept override { return ex::guard_upgrade::wire::Outcome::uncertain; }
    } guard_call;
    ex::guard_upgrade::wire::Snapshot guard{};
    auto& nav = guard.navigation; nav.scene = nav.revision = 1; nav.root = 100; nav.manager = 200; nav.mode = 6;
    nav.building_hud = 300; nav.vendor_hud = 400; nav.selected_entry = 500;
    nav.visible = 3; nav.initialized = 1; nav.building = {20,8}; nav.vendor = {777,37};
    guard.rank = 1; guard.cost = 100; guard.funds = 150; guard.can_upgrade = 1; guard.control_flags = 3;
    guard.upgrade_control = 600; guard.progress_control = 700;
    v::guard_controller.Observe(guard, true, runtime_tick);
    ex::guard_upgrade::wire::Command gc{}; gc.host = {10,1,456}; gc.window = 123; gc.request[0] = 9;
    gc.expected = v::guard_controller.Current();
    v::guard_controller.Execute(ex::guard_upgrade::wire::Verb::upgrade, gc, true, true, runtime_tick, guard_call);
    Check(v::guard_controller.Busy(), "guard transaction owns the UI");
    auto blocked = std::make_shared<ko::QueuedCommand>(); Allow(blocked);
    v::CondemnInvoker bi(blocked, scene, test_window); ko::Cursor observed{};
    Check(!bi.Baseline(observed) && bi.Invoke(ko::native::Action::enable, {}, state) == ko::native::Result::unavailable
        && enables == 1, "guard ownership blocks Condemn admission in the opposite direction");
    v::guard_controller = {};
    struct MenuCall final : ex::vendor_menu::Invoker {
        ex::vendor_menu::wire::Outcome Invoke(ex::vendor_menu::wire::Verb,
            const ex::vendor_menu::wire::Command&) noexcept override { return ex::vendor_menu::wire::Outcome::submitted; }
    } menu_call;
    ex::vendor_menu::wire::Snapshot menu{};
    menu.scene = menu.revision = 1; menu.root = 100; menu.manager = 200;
    menu.menu = menu.front_hud = 300; menu.hireling = 400; menu.building = 20; menu.vendor = 777;
    v::menu_controller.Observe(menu, true, runtime_tick);
    ex::vendor_menu::wire::Command mc{}; mc.host = {10,1,456}; mc.window = 123; mc.request[0] = 10;
    mc.expected = v::menu_controller.Current();
    v::menu_controller.Execute(ex::vendor_menu::wire::Verb::open_recipe, mc, true, true, runtime_tick, menu_call);
    Check(v::menu_controller.Busy(), "menu transaction owns the UI");
    other_reads = other_writes = 0;
    vi.Invoke(v::wire::Verb::create, {}, 0); vi.Invoke(v::wire::Verb::create_random, {}, 0); ci.Open({});
    ni.Open(ex::vendor_navigation::wire::Verb::building, {});
    gi.Upgrade({}); gi.Reopen({}, {});
    fi.Transfer(ex::guard_funding::wire::Verb::open_quote, {});
    Check(!bi.Baseline(observed) && !other_reads && !other_writes,
        "menu barrier excludes spending, navigation, guards, funding and Condemn");
    VerifyVendorOrders();
    return failures;
}
