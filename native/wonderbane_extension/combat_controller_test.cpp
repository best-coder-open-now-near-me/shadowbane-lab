#include "combat_controller.h"
#include <fstream>
#include <string>
using namespace wonderbane::extension::combat;
namespace {
struct Backend final : Invoker {
    Controller* controller = nullptr;
    unsigned starts = 0, cancels = 0;
    bool retire_inside_start = false, bad_reply = false, allow_cancel = true;
    bool missing_cleanup = false, unavailable = false;
    wire::Receipt Start(const wire::Command& command) noexcept override {
        ++starts;
        if (retire_inside_start) { controller->Retire(command.grant.scene); }
        auto receipt = wire::Reply(command, wire::Outcome::client_outbound_queued);
        receipt.flags = wire::cleanup_required | wire::outbound_queued;
        receipt.phase = wire::Phase::engaged;
        if (bad_reply) { receipt.target_key[0] ^= 1; }
        if (missing_cleanup) { receipt.flags &= ~wire::cleanup_required; }
        if (unavailable) { receipt = wire::Reply(command, wire::Outcome::unavailable); }
        return receipt;
    }
    wire::Receipt Cancel(const wire::Command& command) noexcept override {
        ++cancels;
        auto receipt = wire::Reply(command,
            allow_cancel ? wire::Outcome::local_cancelled : wire::Outcome::pending);
        receipt.flags = allow_cancel ? wire::local_cancelled : wire::cleanup_required;
        receipt.phase = allow_cancel ? wire::Phase::idle : wire::Phase::cancelling;
        return receipt;
    }
};
}
int main(int argc, char** argv) {
    if (argc != 2) { return 1; }
    std::ifstream file(argv[1]); std::string hex; wire::Command command{};
    if (!std::getline(file, hex) || hex.size() != sizeof(command) * 2) { return 2; }
    auto* bytes = reinterpret_cast<unsigned char*>(&command);
    for (std::size_t i = 0; i < sizeof(command); ++i) {
        bytes[i] = static_cast<unsigned char>(std::stoul(hex.substr(i * 2, 2), nullptr, 16));
    }
    Controller controller; Backend backend; backend.controller = &controller;
    using V = wire::Verb; using O = wire::Outcome; using P = wire::Phase;
    auto receipt = controller.Execute(V::status, command, true, true, backend);
    if (receipt.outcome != O::unavailable || backend.starts || controller.Busy()) { return 3; }
    receipt = controller.Execute(V::start, command, true, true, backend);
    if (receipt.outcome != O::client_outbound_queued || backend.starts != 1 || !controller.Busy()) { return 4; }
    receipt = controller.Execute(V::start, command, true, true, backend);
    if (receipt.outcome != O::client_outbound_queued || backend.starts != 1) { return 5; }
    auto changed = command; changed.target_key[0] ^= 1;
    if (controller.Execute(V::cancel, changed, true, true, backend).outcome != O::invalid
        || backend.cancels) { return 6; }
    auto other = command; other.request[0] ^= 1;
    if (controller.Execute(V::start, other, true, true, backend).outcome != O::pending
        || backend.starts != 1) { return 7; }
    auto never_entered = other; never_entered.request[2] ^= 1;
    receipt = controller.Execute(V::cancel, never_entered, true, false, backend);
    if (receipt.outcome != O::local_cancelled || !controller.Busy()
        || backend.cancels || controller.Active()->request != command.request) { return 16; }
    receipt = controller.Execute(V::start, never_entered, true, true, backend);
    if (receipt.outcome != O::local_cancelled || backend.starts != 1) { return 17; }
    auto forged = never_entered; forged.local_key[0] ^= 1;
    if (controller.Execute(V::start, forged, true, true, backend).outcome != O::invalid
        || backend.starts != 1 || backend.cancels) { return 18; }
    backend.allow_cancel = false;
    receipt = controller.Execute(V::cancel, command, true, false, backend);
    if (receipt.phase != P::cancelling || !controller.Busy() || backend.cancels != 1) { return 8; }
    backend.allow_cancel = true;
    receipt = controller.Execute(V::cancel, command, true, false, backend);
    if (receipt.outcome != O::local_cancelled || controller.Busy() || backend.cancels != 2) { return 9; }
    receipt = controller.Execute(V::start, command, true, true, backend);
    if (receipt.outcome != O::local_cancelled || backend.starts != 1) { return 10; }

    // Retirement inside a native callback must win over its eventual old reply.
    backend.retire_inside_start = true;
    receipt = controller.Execute(V::start, other, true, true, backend);
    if (receipt.phase != P::retired || controller.Busy()
        || receipt.flags & wire::cleanup_required || !(receipt.flags & wire::outbound_queued)
        || backend.starts != 2) { return 11; }
    auto late = wire::Reply(other, O::client_outbound_queued);
    late.flags = wire::cleanup_required | wire::outbound_queued; late.phase = P::engaged;
    if (controller.Update(late) || controller.Busy()) { return 12; }

    // A malformed backend receipt cannot release an admitted native obligation.
    backend.retire_inside_start = false; backend.bad_reply = true;
    other.request[1] ^= 1;
    receipt = controller.Execute(V::start, other, true, true, backend);
    if (receipt.outcome != O::uncertain || receipt.phase != P::blocked
        || !(receipt.flags & wire::cleanup_required) || !controller.Busy()) { return 13; }
    controller.Retire(command.grant.scene + 1);
    if (!controller.Busy()) { return 14; }
    controller.Retire(command.grant.scene);
    if (controller.Busy()) { return 15; }
    backend.bad_reply = false;
    for (bool unavailable : {false, true}) {
        other.request[3]++;
        backend.missing_cleanup = true; backend.unavailable = unavailable;
        receipt = controller.Execute(V::start, other, true, true, backend);
        if (!controller.Busy() || receipt.outcome != O::uncertain
            || !(receipt.flags & wire::cleanup_required)) { return 19; }
        const auto before = backend.cancels;
        receipt = controller.Execute(V::cancel, other, true, false, backend);
        if (controller.Busy() || receipt.outcome != O::local_cancelled
            || backend.cancels != before + 1) { return 20; }
    }
    return 0;
}
