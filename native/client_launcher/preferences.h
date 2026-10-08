#pragma once
#include "policy.h"
#include <array>
#include <cctype>

namespace shadowbane::desktop {
// Preserve every non-display line and inline annotation, including its encoding/newlines.
inline std::string DesktopPreferences(const std::string& source, const Display& display) {
    ValidateDesktop(display);
    if (source.size() > 1024 * 1024 || source.find('\0') != std::string::npos)
        throw std::runtime_error("Client preferences are not a supported text file.");
    const auto w = std::to_string(display.current.width), h = std::to_string(display.current.height);
    const auto refresh = std::to_string(display.current.refresh);
    const std::array<std::string, 4> keys{"RESOLUTION=", "FULLSCREEN=", "REFRESH=", "VIDEOSETTINGSVALIDATION="};
    const std::array<std::string, 4> values{w + " " + h, "FALSE", refresh, w + "x" + h + "@" + refresh + "Hz"};
    std::array<unsigned, 4> count{};
    const auto newline = source.find("\r\n") != std::string::npos ? "\r\n" : "\n";
    std::string result;
    std::size_t start = 0;
    while (start < source.size()) {
        const auto next = source.find('\n', start);
        const auto end = next == std::string::npos ? source.size() : next + 1;
        const auto line = source.substr(start, end - start);
        const auto first = line.find_first_not_of(" \t");
        bool replaced = false;
        for (std::size_t i = 0; i < keys.size(); ++i) {
            if (first == std::string::npos || line.compare(first, keys[i].size(), keys[i]) != 0) continue;
            if (++count[i] != 1) throw std::runtime_error("Client preferences contain duplicate display keys.");
            const auto value_start = first + keys[i].size();
            auto content_end = line.find_first_of("\r\n", value_start);
            if (content_end == std::string::npos) content_end = line.size();
            // Configuration annotations are not consumed by the numeric/bool reader.
            auto annotation = line.find_first_of("(#;", value_start);
            const auto slash = line.find("//", value_start);
            if (slash != std::string::npos) annotation = std::min(annotation, slash);
            auto suffix_start = std::min(annotation, content_end);
            while (suffix_start > value_start &&
                   std::isspace(static_cast<unsigned char>(line[suffix_start - 1]))) --suffix_start;
            result += keys[i] + " " + values[i] + line.substr(suffix_start);
            replaced = true; break;
        }
        if (!replaced) result += line;
        start = end;
    }
    for (std::size_t i = 0; i < keys.size(); ++i) {
        if (count[i]) continue;
        if (!result.empty() && result.back() != '\n') result += newline;
        result += keys[i] + " " + values[i] + newline;
    }
    return result;
}
}  // namespace shadowbane::desktop
