#include "world_map_client_layout.h"
#include <iostream>

int main() {
    using namespace wonderbane::extension;
    unsigned failures = 0;
    const auto check = [&failures](bool ok, const char* reason) {
        if (!ok) { ++failures; std::cerr << reason << '\n'; }
    };
    IMAGE_NT_HEADERS32 nt{};
    nt.FileHeader.NumberOfSections = 6;
    nt.OptionalHeader.SizeOfImage = 0x1766000U;
    check(ReviewedWorldMapLayout(nt, nullptr, nullptr), "legacy layout remains supported");
    nt.FileHeader.NumberOfSections = 7;
    check(!ReviewedWorldMapLayout(nt, nullptr, nullptr), "mixed old size/new sections rejected");
    nt.OptionalHeader.SizeOfImage = 0x178F000U;
    IMAGE_SECTION_HEADER added{};
    std::memcpy(added.Name, ".wbfp\0\0", IMAGE_SIZEOF_SHORT_NAME);
    added.VirtualAddress = 0x1766000U; added.Misc.VirtualSize = 164008;
    added.PointerToRawData = 21147648; added.SizeOfRawData = 167936;
    added.Characteristics = IMAGE_SCN_CNT_INITIALIZED_DATA | IMAGE_SCN_MEM_READ;
    movement::NativeMovementImageLayout proof{0x178F000U, 7};
    check(ReviewedWorldMapLayout(nt, &added, &proof), "authenticated expanded layout supported");
    check(!ReviewedWorldMapLayout(nt, &added, nullptr), "shape alone grants no expanded identity");
    proof.image_size = 0x1766000U;
    check(!ReviewedWorldMapLayout(nt, &added, &proof), "wrong authenticated image rejected");
    proof.image_size = 0x178F000U; proof.section_count = 6;
    check(!ReviewedWorldMapLayout(nt, &added, &proof), "wrong authenticated sections rejected");
    proof.section_count = 7;
    const auto exact = added;
    added.Characteristics |= IMAGE_SCN_MEM_WRITE;
    check(!ReviewedWorldMapLayout(nt, &added, &proof), "writable table rejected");
    added = exact; added.VirtualAddress += 0x1000;
    check(!ReviewedWorldMapLayout(nt, &added, &proof), "relocated table rejected");
    added = exact; added.Name[1] = 'x';
    check(!ReviewedWorldMapLayout(nt, &added, &proof), "unknown section rejected");
    added = exact; ++added.SizeOfRawData;
    check(!ReviewedWorldMapLayout(nt, &added, &proof), "changed section extent rejected");
    added = exact; nt.FileHeader.NumberOfSections = 9;
    nt.OptionalHeader.SizeOfImage = 0x1791000U;
    proof = {0x1791000U, 9, true};
    check(ReviewedWorldMapLayout(nt, &added, &proof), "authenticated .22 patch sections supported");
    proof.added_patch_sections_verified = false;
    check(!ReviewedWorldMapLayout(nt, &added, &proof), "unsealed added dispatcher code rejected");
    proof.added_patch_sections_verified = true; proof.section_count = 7;
    check(!ReviewedWorldMapLayout(nt, &added, &proof), "older table proof cannot authorize .22");
    return failures ? 1 : 0;
}
