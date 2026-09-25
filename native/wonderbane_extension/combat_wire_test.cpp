#include "combat_wire.h"
#include <fstream>
#include <string>
using namespace wonderbane::extension::combat;
int main(int argc, char** argv) {
    if (argc != 2) { return 1; }
    std::ifstream file(argv[1]); std::string hex; wire::Command c{};
    if (!std::getline(file, hex) || hex.size() != sizeof(c) * 2) { return 2; }
    auto* bytes = reinterpret_cast<unsigned char*>(&c);
    for (std::size_t i = 0; i < sizeof(c); ++i) {
        bytes[i] = static_cast<unsigned char>(std::stoul(hex.substr(i * 2, 2), nullptr, 16));
    }
    fence::Binding b{};
    constexpr std::uint64_t creation = 0x1020304050607080ULL;
    if (!wire::BindingFor(c, 1234, creation, b) || b.revision != 19 || b.target_key[0] != 92) { return 3; }
    if (wire::BindingFor(c, 1235, creation, b) || wire::BindingFor(c, 1234, creation + 1, b)) { return 4; }
    for (std::size_t offset : {0U, 8U, 24U, 32U, 48U, 240U, 256U, 352U, 384U, 400U, 408U, 440U, 472U, 504U, 575U}) {
        auto changed = c;
        reinterpret_cast<unsigned char*>(&changed)[offset] ^= 1;
        if (wire::BindingFor(changed, 1234, creation, b)) { return 5; }
    }
    wire::Digest digest{};
    const std::uint16_t name[]{'L','o','c','a','l',0xd83d,0xde42};
    if (!wire::IdentityDigest(name, std::size(name), digest) || digest != c.local_name) { return 6; }
    const std::uint16_t target[]{'E','n','e','m','y',0xe9};
    if (!wire::IdentityDigest(target, std::size(target), digest) || digest != c.target_name) { return 7; }
    const std::uint16_t server[]{'S','e','r','v','e','r'};
    const wire::Text n{name, std::size(name)}, t{target, std::size(target)}, shard{server, std::size(server)};
    if (!wire::IdentitiesMatch(c, n, shard, t, shard)) { return 11; }
    auto wrong_owner = c; wrong_owner.owner[0] ^= 1;
    if (wire::IdentitiesMatch(wrong_owner, n, shard, t, shard)) { return 12; }
    auto wrong_entry = c; wrong_entry.entry[0] ^= 1;
    if (wire::IdentitiesMatch(wrong_entry, n, shard, t, shard)
        || wire::IdentitiesMatch(c, n, shard, t, t)) { return 13; }
    const std::uint16_t invalids[][2]{{0xd800,0}, {0xdc00,'a'}, {'a',0}, {0xd800,'b'}};
    for (const auto& invalid : invalids) {
        if (wire::IdentityDigest(invalid, 2, digest)) { return 8; }
    }
    std::uint16_t many[65]{}; for (auto& v : many) { v = 'a'; }
    if (!wire::IdentityDigest(many, 64, digest) || wire::IdentityDigest(many, 65, digest)
        || wire::IdentityDigest(many, 0, digest) || wire::IdentityDigest(nullptr, 1, digest)) { return 9; }
    auto changed = c; changed.grant.owner = 2;
    if (wire::BindingFor(changed, 1234, creation, b)) { return 10; }
    return 0;
}
