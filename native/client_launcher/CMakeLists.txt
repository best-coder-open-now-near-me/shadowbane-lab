cmake_minimum_required(VERSION 3.24)
project(shadowbane_client_launcher VERSION 1.0.0 LANGUAGES CXX)
if(NOT MSVC)
  message(FATAL_ERROR "The client launcher requires the reviewed MSVC toolchain")
endif()
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
include(CTest)
add_executable(client-launcher-policy-test policy_test.cpp)
target_compile_features(client-launcher-policy-test PRIVATE cxx_std_20)
target_compile_definitions(client-launcher-policy-test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX)
target_compile_options(client-launcher-policy-test PRIVATE /W4 /WX /permissive- /utf-8)
target_link_libraries(client-launcher-policy-test PRIVATE shell32)
add_test(NAME client-launcher-policy COMMAND client-launcher-policy-test)

add_library(client-launcher-platform STATIC platform.cpp)
target_compile_features(client-launcher-platform PUBLIC cxx_std_20)
target_compile_definitions(client-launcher-platform PUBLIC UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX)
target_compile_options(client-launcher-platform PRIVATE /W4 /WX /permissive- /utf-8)
target_link_libraries(client-launcher-platform PUBLIC bcrypt dwmapi shcore user32)

add_executable(client-launcher-platform-test platform_test.cpp)
target_link_libraries(client-launcher-platform-test PRIVATE client-launcher-platform)
target_compile_options(client-launcher-platform-test PRIVATE /W4 /WX /permissive- /utf-8)
add_test(NAME client-launcher-platform COMMAND client-launcher-platform-test)

find_package(Python3 REQUIRED COMPONENTS Interpreter)
set(PROFILE_GENERATOR "${CMAKE_CURRENT_SOURCE_DIR}/../../scripts/generate-client-launcher-profile.py")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
  "${PROFILE_GENERATOR}"
  "${CMAKE_CURRENT_SOURCE_DIR}/../../src/shadowbane_lab/client_extension/distribution.py")
execute_process(COMMAND "${Python3_EXECUTABLE}" "${PROFILE_GENERATOR}"
  --output "${CMAKE_CURRENT_BINARY_DIR}/generated/profile.h"
  RESULT_VARIABLE PROFILE_RESULT)
if(NOT PROFILE_RESULT EQUAL 0)
  message(FATAL_ERROR "Could not generate reviewed client profile")
endif()
add_executable(ShadowbaneLauncher WIN32 launcher.cpp)
target_include_directories(ShadowbaneLauncher PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated")
target_link_libraries(ShadowbaneLauncher PRIVATE client-launcher-platform shell32)
target_compile_options(ShadowbaneLauncher PRIVATE /W4 /WX /permissive- /utf-8 /guard:cf)
target_link_options(ShadowbaneLauncher PRIVATE /guard:cf /DYNAMICBASE /NXCOMPAT
  "/MANIFESTINPUT:${CMAKE_CURRENT_SOURCE_DIR}/launcher.manifest")

add_test(NAME client-launcher-inspection
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/cli_test.py" "$<TARGET_FILE:ShadowbaneLauncher>")
