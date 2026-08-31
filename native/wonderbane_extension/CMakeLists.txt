cmake_minimum_required(VERSION 3.24)

project(wonderbane_extension VERSION 1.4.0 LANGUAGES CXX RC)

include(CTest)

if(NOT MSVC)
  message(FATAL_ERROR "The WonderBane extension requires the reviewed MSVC toolchain")
endif()

if(NOT CMAKE_SIZEOF_VOID_P EQUAL 4)
  message(FATAL_ERROR "The WonderBane extension must be configured for Win32/x86")
endif()

add_library(
  wonderbane_extension
  SHARED
  cel_shading.cpp
  extension.cpp
  extension.def
  extension.rc
)

target_compile_features(wonderbane_extension PRIVATE cxx_std_20)
target_compile_definitions(
  wonderbane_extension
  PRIVATE
  UNICODE
  _UNICODE
  WIN32_LEAN_AND_MEAN
  NOMINMAX
  STRICT
)
target_compile_options(
  wonderbane_extension
  PRIVATE
  /W4
  /WX
  /permissive-
  /sdl
  /GS
  /guard:cf
  /GR-
  /Zc:__cplusplus
  /Zc:inline
  /utf-8
)
target_link_options(
  wonderbane_extension
  PRIVATE
  /DYNAMICBASE
  /NXCOMPAT
  /guard:cf
  /INCREMENTAL:NO
  /OPT:REF
  /OPT:ICF
  /Brepro
)
target_link_libraries(wonderbane_extension PRIVATE shell32 ole32 uuid)

set_property(TARGET wonderbane_extension PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
set_target_properties(
  wonderbane_extension
  PROPERTIES
  OUTPUT_NAME "wonderbane-extension"
  PREFIX ""
)

if(BUILD_TESTING)
  add_executable(
    wonderbane_extension_cel_shading_test
    cel_shading.cpp
    cel_shading_test.cpp
  )
  target_compile_features(
    wonderbane_extension_cel_shading_test
    PRIVATE
    cxx_std_20
  )
  target_compile_definitions(
    wonderbane_extension_cel_shading_test
    PRIVATE
    UNICODE
    _UNICODE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    STRICT
  )
  target_compile_options(
    wonderbane_extension_cel_shading_test
    PRIVATE
    /W4
    /WX
    /permissive-
    /sdl
    /GS
    /guard:cf
    /Zc:__cplusplus
    /utf-8
  )
  target_link_options(
    wonderbane_extension_cel_shading_test
    PRIVATE
    /DYNAMICBASE
    /NXCOMPAT
    /guard:cf
    /INCREMENTAL:NO
  )
  set_property(
    TARGET wonderbane_extension_cel_shading_test
    PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded"
  )
  add_test(
    NAME wonderbane_extension_cel_shading
    COMMAND wonderbane_extension_cel_shading_test
  )

  add_executable(wonderbane_extension_probe probe.cpp)
  target_compile_features(wonderbane_extension_probe PRIVATE cxx_std_20)
  target_compile_definitions(
    wonderbane_extension_probe
    PRIVATE
    UNICODE
    _UNICODE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    STRICT
  )
  target_compile_options(
    wonderbane_extension_probe
    PRIVATE
    /W4
    /WX
    /permissive-
    /sdl
    /GS
    /guard:cf
    /Zc:__cplusplus
    /utf-8
  )
  target_link_options(
    wonderbane_extension_probe
    PRIVATE
    /DYNAMICBASE
    /NXCOMPAT
    /guard:cf
    /INCREMENTAL:NO
  )
  set_property(
    TARGET wonderbane_extension_probe
    PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded"
  )
  add_test(
    NAME wonderbane_extension_heartbeat
    COMMAND wonderbane_extension_probe $<TARGET_FILE:wonderbane_extension>
  )
endif()
