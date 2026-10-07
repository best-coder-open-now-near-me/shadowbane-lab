#pragma once

#include <algorithm>
#include <cwctype>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace shadowbane::desktop {

struct Mode {
    unsigned width{}, height{}, refresh{}, bits{}, orientation{};
    bool operator==(const Mode&) const = default;
};

struct Display {
    std::wstring device;
    long left{}, top{};
    bool primary{};
    Mode current, desktop;
};

inline bool EqualName(std::wstring_view left, std::wstring_view right) {
    return left.size() == right.size() && std::equal(left.begin(), left.end(), right.begin(),
        [](wchar_t a, wchar_t b) { return std::towupper(a) == std::towupper(b); });
}

inline const Display& SelectDisplay(const std::vector<Display>& displays,
                                    const std::wstring& requested) {
    const Display* match = nullptr;
    for (const auto& display : displays) {
        if ((requested.empty() && display.primary) || EqualName(display.device, requested)) {
            if (match != nullptr) throw std::runtime_error("Display selection is ambiguous.");
            match = &display;
        }
    }
    if (match == nullptr) throw std::runtime_error("The selected display is not connected.");
    return *match;
}

inline void ValidateDesktop(const Display& display) {
    if (display.current != display.desktop) {
        throw std::runtime_error(
            "Another fullscreen application has changed this display's mode. "
            "Close it before launching Shadowbane.");
    }
    if (display.current.width < 640 || display.current.height < 480 ||
        display.current.width > 16384 || display.current.height > 16384) {
        throw std::runtime_error("The desktop dimensions are outside the supported range.");
    }
}

// Quote one argument using the Windows CommandLineToArgvW/CRT escaping rules.
inline std::wstring Quote(std::wstring_view value) {
    std::wstring result = L"\"";
    std::size_t slashes = 0;
    for (wchar_t c : value) {
        if (c == L'\\') { ++slashes; continue; }
        result.append(c == L'\"' ? slashes * 2 + 1 : slashes, L'\\');
        slashes = 0;
        result += c;
    }
    result.append(slashes * 2, L'\\');
    return result + L'\"';
}

inline std::wstring Arguments(const std::wstring& executable, const Display& display) {
    ValidateDesktop(display);
    return Quote(executable) + L" -windowed -resolution " +
        std::to_wstring(display.current.width) + L"x" +
        std::to_wstring(display.current.height);
}

// The display policy owns only DPI flags. Keep unrelated compatibility flags.
inline std::wstring DpiLayer(std::wstring_view existing) {
    std::wstring result;
    std::size_t offset = 0;
    while (offset < existing.size()) {
        while (offset < existing.size() && std::iswspace(existing[offset])) ++offset;
        const auto start = offset;
        while (offset < existing.size() && !std::iswspace(existing[offset])) ++offset;
        const auto token = existing.substr(start, offset - start);
        if (token.empty() || EqualName(token, L"HIGHDPIAWARE") ||
            EqualName(token, L"DPIUNAWARE") || EqualName(token, L"GDIDPISCALING")) continue;
        if (!result.empty()) result += L' ';
        result += token;
    }
    if (!result.empty()) result += L' ';
    return result + L"HIGHDPIAWARE";
}

}  // namespace shadowbane::desktop
