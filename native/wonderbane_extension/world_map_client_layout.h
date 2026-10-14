#pragma once
#include <Windows.h>
#include <cstring>
#include "movement_native_image.h"

namespace wonderbane::extension {
// The added read-only table is accepted only with the authenticated file/loaded
// header proof. Matching a larger size or a seventh section alone is insufficient.
inline bool ReviewedWorldMapLayout(const IMAGE_NT_HEADERS32& nt,
    const IMAGE_SECTION_HEADER* added,
    const movement::NativeMovementImageLayout* authenticated) noexcept {
    if (nt.FileHeader.NumberOfSections == 6U
        && nt.OptionalHeader.SizeOfImage == 0x1766000U) { return true; }
    return nt.FileHeader.NumberOfSections == 7U
        && nt.OptionalHeader.SizeOfImage == 0x178F000U
        && authenticated && authenticated->section_count == 7U
        && authenticated->image_size == nt.OptionalHeader.SizeOfImage
        && added && std::memcmp(added->Name, ".wbfp\0\0", IMAGE_SIZEOF_SHORT_NAME) == 0
        && added->VirtualAddress == 0x1766000U
        && added->Misc.VirtualSize == 164008U
        && added->PointerToRawData == 21147648U && added->SizeOfRawData == 167936U
        && added->Characteristics == IMAGE_SCN_CNT_INITIALIZED_DATA + IMAGE_SCN_MEM_READ;
}
}
