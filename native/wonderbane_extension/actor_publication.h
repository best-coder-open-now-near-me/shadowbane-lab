#pragma once
#include "actor_buff_observation.h"
#include "actor_application_journal.h"
#include "actor_selector_manifest.h"
#include <Windows.h>

namespace wonderbane::extension::actor::publication {
using Id=fence::Id;using Digest=fence::Digest;
constexpr std::uint32_t slot_size=32768,mapping_size=256+2*slot_size;
#pragma pack(push,8)
struct Header {
    char magic[8]{'W','B','A','P','U','B','1',0};
    std::uint32_t version=1,bytes=mapping_size,client_pid{},slot_bytes=slot_size,slots=2,reserved{};
    std::uint64_t client_creation{};Id actor_lifetime{};Digest manifest{};
    std::uint32_t actor_key[2]{},actor_address{},reserved2{};std::uint64_t scene{};
    volatile LONG active=-1;std::uint8_t padding[140]{};
};
struct Effect {
    std::uint32_t descriptor{},action{},rank{},native_class{},source_tag{},source[3]{},action_class{},suppression{};
};
struct Readiness {
    selectors::Record selector{};
    std::uint32_t rank{},category{},target_mode{},delivery{},required_mode{},coverage{},readiness{};
    std::uint32_t descriptor_offset{},descriptor_count{};
    std::uint32_t item_key[2]{},template_key[2]{},item_hint{},template_hint{},quantity{},type{},flags{};
    std::uint8_t reserved[24]{};
};
struct Application {
    Digest intent{},command{};std::uint64_t submitted_revision{},observed_revision{};
    std::uint32_t entry{},state{},local_settled{},queued{};std::uint8_t reserved[32]{};
};
struct Descriptor {
    std::uint32_t id{},action{},action_class{};std::uint8_t suppression{},present{},reserved[2]{};
};
struct alignas(8) Frame {
    volatile LONG64 sequence{};std::uint64_t revision{};Id snapshot{};
    std::uint64_t sampled_tick{},effect_epoch{};
    std::uint32_t unknown=1,complete{},effect_count{},readiness_count{},application_count{},descriptor_count{},actor_mode{},initiation_clear{};
    std::uint8_t reserved[176]{};
    std::array<Effect,256> effects{};std::array<Readiness,32> readiness{};
    std::array<Application,32> applications{};std::array<Descriptor,256> descriptors{};
    std::uint8_t padding[9984]{};
};
struct Mapping {Header header{};std::array<Frame,2> frames{};};
#pragma pack(pop)
static_assert(sizeof(Header)==256 && offsetof(Header,active)==112);
static_assert(sizeof(Effect)==40 && sizeof(Readiness)==128 && sizeof(Application)==128 && sizeof(Descriptor)==16);
static_assert(sizeof(Frame)==slot_size && offsetof(Frame,effects)==256 && offsetof(Frame,descriptors)==18688);
static_assert(sizeof(Mapping)==mapping_size);
bool Valid(const Header&) noexcept;
bool Valid(const Frame&) noexcept;
std::wstring Name(std::uint32_t pid,std::uint64_t creation,const Digest& manifest);
// Encoding never resolves or invokes native objects. The owner must revalidate
// the retained resolver Publication before publishing/using its copied facts.
bool Encode(const selectors::Manifest&,const actor_buffs::Publication&,
    const actor_actions::ApplicationJournal&,Frame&) noexcept;
class Writer final {
public:
    Writer() noexcept=default;~Writer(){Close();}
    Writer(const Writer&)=delete;Writer& operator=(const Writer&)=delete;
    // The retained actor supplies its revision high-water when a new manifest
    // replaces a writer. Journal submitted/observed revisions outlive mappings.
    bool Open(const Header&,std::uint64_t revision_floor=0) noexcept;
    bool Publish(const Frame&) noexcept;
    bool Unknown(std::uint32_t reason) noexcept;
    void Close() noexcept;
    bool Current(Frame&) const noexcept;
    std::uint64_t Revision() const noexcept{return revision_;}
private:
    HANDLE handle_{};Mapping* mapping_{};std::uint64_t revision_{},write_sequence_{};
    Frame last_{};bool has_last_{},faulted_{};
};
}
