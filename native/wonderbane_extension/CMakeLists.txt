cmake_minimum_required(VERSION 3.24)

project(wonderbane_extension VERSION 1.6.13 LANGUAGES CXX RC)

set(WONDERBANE_EXTENSION_PROFILE "full" CACHE STRING "Extension runtime profile")
set_property(
  CACHE WONDERBANE_EXTENSION_PROFILE
  PROPERTY STRINGS full diagnostics-only
)
if(NOT WONDERBANE_EXTENSION_PROFILE STREQUAL "full"
   AND NOT WONDERBANE_EXTENSION_PROFILE STREQUAL "diagnostics-only")
  message(FATAL_ERROR "Unsupported WonderBane extension profile")
endif()

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
  banded_lighting.cpp
  camera_observation.cpp
  movement_boundary_trace.cpp
  movement_controls.cpp
  movement_native_image.cpp
  movement_lifetime.cpp
  movement_native_stop.cpp
  cel_shading.cpp
  depth_edges.cpp
  event_channel.cpp
  extension.cpp
  fixed_function_state.cpp
  graphics_control.cpp
  graphics_status.cpp
  terrain_trace.cpp
  terrain_mask_refresh.cpp
  import_hook.cpp
  performance_telemetry.cpp
  scene_frame.cpp
  extension.def
  extension.rc
  world_map_capture.cpp
  world_map_projection.cpp
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
if(WONDERBANE_EXTENSION_PROFILE STREQUAL "full")
  target_sources(wonderbane_extension PRIVATE
    navigation_protocol.cpp navigation_channel.cpp navigation_draw.cpp navigation_viewer.cpp
    selected_cue.cpp selected_cue_gpu.cpp selected_cue_runtime.cpp scene_context.cpp
    scene_draw.cpp effects.cpp effects_attachment.cpp effects_runtime.cpp effects_draw.cpp
    sky.cpp sky_draw.cpp sky_runtime.cpp sky_asset.rc)
  target_link_libraries(wonderbane_extension PRIVATE opengl32)
endif()
if(WONDERBANE_EXTENSION_PROFILE STREQUAL "diagnostics-only")
  target_compile_definitions(
    wonderbane_extension
    PRIVATE
    WONDERBANE_EXTENSION_DIAGNOSTICS_ONLY=1
  )
endif()
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
target_link_libraries(wonderbane_extension PRIVATE bcrypt shell32 ole32 user32 uuid)

set_property(TARGET wonderbane_extension PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
set_target_properties(
  wonderbane_extension
  PROPERTIES
  OUTPUT_NAME "wonderbane-extension"
  PREFIX ""
)
add_custom_command(
  TARGET wonderbane_extension
  POST_BUILD
  COMMAND
    "${CMAKE_COMMAND}" -E copy_if_different
    "$<TARGET_FILE:wonderbane_extension>"
    "$<TARGET_FILE_DIR:wonderbane_extension>/wonderbane-extension-${PROJECT_VERSION}.dll"
  VERBATIM
)

if(BUILD_TESTING)
  add_executable(wonderbane_extension_startup_test extension_startup_test.cpp)
  target_compile_features(wonderbane_extension_startup_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_startup_test PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_startup_test PRIVATE /W4 /WX /permissive- /utf-8)
  target_link_libraries(wonderbane_extension_startup_test PRIVATE shell32 ole32)
  set_property(TARGET wonderbane_extension_startup_test PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
  add_test(NAME wonderbane_extension_startup COMMAND wonderbane_extension_startup_test)
  add_executable(wonderbane_extension_scene_context_test scene_context_test.cpp)
  target_compile_features(wonderbane_extension_scene_context_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_scene_context_test PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_scene_context_test PRIVATE /W4 /WX /permissive- /utf-8)
  target_link_libraries(wonderbane_extension_scene_context_test PRIVATE opengl32)
  set_property(TARGET wonderbane_extension_scene_context_test PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
  add_test(NAME wonderbane_extension_scene_context COMMAND wonderbane_extension_scene_context_test)
  add_executable(wonderbane_extension_selected_cue_runtime_test
    selected_cue.cpp effects_attachment.cpp import_hook.cpp selected_cue_runtime_test.cpp)
  target_compile_features(wonderbane_extension_selected_cue_runtime_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_selected_cue_runtime_test PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_selected_cue_runtime_test PRIVATE /W4 /WX /permissive- /utf-8)
  target_link_libraries(wonderbane_extension_selected_cue_runtime_test PRIVATE bcrypt opengl32)
  set_property(TARGET wonderbane_extension_selected_cue_runtime_test PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
  add_test(NAME wonderbane_extension_selected_cue_runtime COMMAND wonderbane_extension_selected_cue_runtime_test)
  add_executable(wonderbane_extension_selected_cue_binding_test selected_cue_binding_test.cpp)
  target_compile_features(wonderbane_extension_selected_cue_binding_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_selected_cue_binding_test PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_selected_cue_binding_test PRIVATE /W4 /WX /permissive- /utf-8)
  target_link_libraries(wonderbane_extension_selected_cue_binding_test PRIVATE bcrypt)
  set_property(TARGET wonderbane_extension_selected_cue_binding_test PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
  add_test(NAME wonderbane_extension_selected_cue_binding COMMAND wonderbane_extension_selected_cue_binding_test)
  set_tests_properties(wonderbane_extension_selected_cue_binding PROPERTIES SKIP_RETURN_CODE 77)
  add_executable(wonderbane_extension_selected_cue_gpu_test
    selected_cue.cpp selected_cue_gpu.cpp scene_draw.cpp selected_cue_gpu_test.cpp)
  target_compile_features(wonderbane_extension_selected_cue_gpu_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_selected_cue_gpu_test PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_selected_cue_gpu_test PRIVATE /W4 /WX /permissive- /utf-8)
  target_link_libraries(wonderbane_extension_selected_cue_gpu_test PRIVATE opengl32 gdi32 user32)
  set_property(TARGET wonderbane_extension_selected_cue_gpu_test PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
  add_test(NAME wonderbane_extension_selected_cue_gpu COMMAND wonderbane_extension_selected_cue_gpu_test)
  set_tests_properties(wonderbane_extension_selected_cue_gpu PROPERTIES SKIP_RETURN_CODE 77)
  add_test(NAME wonderbane_extension_selected_cue_source_feasibility
    COMMAND wonderbane_extension_selected_cue_gpu_test --source-feasibility)
  set_tests_properties(wonderbane_extension_selected_cue_source_feasibility PROPERTIES SKIP_RETURN_CODE 77)
  add_test(NAME wonderbane_extension_selected_cue_native_transparency
    COMMAND wonderbane_extension_selected_cue_gpu_test --native-transparency)
  set_tests_properties(wonderbane_extension_selected_cue_native_transparency PROPERTIES SKIP_RETURN_CODE 77)
  add_executable(wonderbane_extension_selected_cue_test selected_cue.cpp selected_cue_test.cpp)
  target_compile_features(wonderbane_extension_selected_cue_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_selected_cue_test PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_selected_cue_test PRIVATE
    /W4 /WX /permissive- /sdl /GS /guard:cf /utf-8)
  set_property(TARGET wonderbane_extension_selected_cue_test PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
  add_test(NAME wonderbane_extension_selected_cue COMMAND wonderbane_extension_selected_cue_test)
  add_executable(wonderbane_extension_navigation_draw_test navigation_draw.cpp scene_draw.cpp effects.cpp effects_attachment.cpp effects_draw.cpp selected_cue.cpp selected_cue_gpu.cpp sky.cpp sky_draw.cpp sky_asset.rc navigation_draw_test.cpp)
  target_compile_features(wonderbane_extension_navigation_draw_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_navigation_draw_test PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_navigation_draw_test PRIVATE
    /W4 /WX /permissive- /sdl /GS /guard:cf /utf-8)
  target_link_libraries(wonderbane_extension_navigation_draw_test PRIVATE opengl32 gdi32 user32 bcrypt)
  set_property(TARGET wonderbane_extension_navigation_draw_test PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
  add_test(NAME wonderbane_extension_navigation_draw COMMAND wonderbane_extension_navigation_draw_test)
  add_test(NAME wonderbane_extension_ordered_operators
    COMMAND wonderbane_extension_navigation_draw_test --ordered-operators)
  set_tests_properties(wonderbane_extension_ordered_operators PROPERTIES SKIP_RETURN_CODE 77)
  add_test(NAME wonderbane_extension_combined_render
    COMMAND wonderbane_extension_navigation_draw_test --combined-render)
  set_tests_properties(wonderbane_extension_combined_render PROPERTIES SKIP_RETURN_CODE 77)
  add_test(NAME wonderbane_extension_effects_native_transparency
    COMMAND wonderbane_extension_navigation_draw_test --verify-native-transparency)

  add_executable(wonderbane_extension_navigation_test
    navigation_protocol.cpp navigation_channel.cpp navigation_protocol_test.cpp)
  target_compile_features(wonderbane_extension_navigation_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_navigation_test PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_navigation_test PRIVATE
    /W4 /WX /permissive- /sdl /GS /guard:cf /utf-8)
  target_link_options(wonderbane_extension_navigation_test PRIVATE /DYNAMICBASE /NXCOMPAT)
  set_property(TARGET wonderbane_extension_navigation_test PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
  add_test(NAME wonderbane_extension_navigation
    COMMAND wonderbane_extension_navigation_test
      "${CMAKE_CURRENT_SOURCE_DIR}/../../tests/fixtures/navigation-inspector-v1.hex"
      "${CMAKE_CURRENT_SOURCE_DIR}/../../tests/fixtures/navigation-inspector-controls-v1.hex")
  foreach(repair_profile full disabled)
    add_executable(wonderbane_extension_terrain_refresh_${repair_profile}_test terrain_mask_refresh_test.cpp)
    target_compile_features(wonderbane_extension_terrain_refresh_${repair_profile}_test PRIVATE cxx_std_20)
    target_compile_definitions(wonderbane_extension_terrain_refresh_${repair_profile}_test PRIVATE
      UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
    if(repair_profile STREQUAL "disabled")
      target_compile_definitions(wonderbane_extension_terrain_refresh_${repair_profile}_test PRIVATE
        WONDERBANE_EXTENSION_DIAGNOSTICS_ONLY=1)
    endif()
    target_compile_options(wonderbane_extension_terrain_refresh_${repair_profile}_test PRIVATE
      /W4 /WX /permissive- /sdl /GS /guard:cf /utf-8)
    target_link_libraries(wonderbane_extension_terrain_refresh_${repair_profile}_test PRIVATE bcrypt)
    target_link_options(wonderbane_extension_terrain_refresh_${repair_profile}_test PRIVATE /DYNAMICBASE /NXCOMPAT)
    set_property(TARGET wonderbane_extension_terrain_refresh_${repair_profile}_test
      PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
    add_test(NAME wonderbane_extension_terrain_refresh_${repair_profile}
      COMMAND wonderbane_extension_terrain_refresh_${repair_profile}_test)
  endforeach()
  foreach(trace_profile full disabled)
    add_executable(wonderbane_extension_terrain_trace_${trace_profile}_test terrain_trace_test.cpp)
    target_compile_features(wonderbane_extension_terrain_trace_${trace_profile}_test PRIVATE cxx_std_20)
    target_compile_definitions(wonderbane_extension_terrain_trace_${trace_profile}_test PRIVATE
      UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
    if(trace_profile STREQUAL "disabled")
      target_compile_definitions(wonderbane_extension_terrain_trace_${trace_profile}_test PRIVATE
        WONDERBANE_EXTENSION_DIAGNOSTICS_ONLY=1)
    endif()
    target_compile_options(wonderbane_extension_terrain_trace_${trace_profile}_test PRIVATE
      /W4 /WX /permissive- /sdl /GS /guard:cf /utf-8)
    target_link_options(wonderbane_extension_terrain_trace_${trace_profile}_test PRIVATE /DYNAMICBASE /NXCOMPAT)
    set_property(TARGET wonderbane_extension_terrain_trace_${trace_profile}_test
      PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
    add_test(NAME wonderbane_extension_terrain_trace_${trace_profile}
      COMMAND wonderbane_extension_terrain_trace_${trace_profile}_test)
  endforeach()
  add_executable(wonderbane_extension_scene_boundary_test reviewed_scene_boundary_test.cpp)
  target_compile_features(wonderbane_extension_scene_boundary_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_scene_boundary_test PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_scene_boundary_test PRIVATE
    /W4 /WX /permissive- /sdl /GS /guard:cf /utf-8)
  target_link_libraries(wonderbane_extension_scene_boundary_test PRIVATE bcrypt)
  target_link_options(wonderbane_extension_scene_boundary_test PRIVATE /DYNAMICBASE /NXCOMPAT)
  set_property(TARGET wonderbane_extension_scene_boundary_test
    PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
  add_test(NAME wonderbane_extension_scene_boundary COMMAND wonderbane_extension_scene_boundary_test)

  add_executable(
    wonderbane_extension_scene_frame_test
    scene_frame.cpp
    scene_frame_test.cpp
  )
  target_compile_features(
    wonderbane_extension_scene_frame_test
    PRIVATE
    cxx_std_20
  )
  target_compile_definitions(
    wonderbane_extension_scene_frame_test
    PRIVATE
    UNICODE
    _UNICODE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    STRICT
  )
  target_compile_options(
    wonderbane_extension_scene_frame_test
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
    wonderbane_extension_scene_frame_test
    PRIVATE
    /DYNAMICBASE
    /NXCOMPAT
    /guard:cf
    /INCREMENTAL:NO
  )
  set_property(
    TARGET wonderbane_extension_scene_frame_test
    PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded"
  )
  add_test(
    NAME wonderbane_extension_scene_frame
    COMMAND wonderbane_extension_scene_frame_test
  )

  add_executable(
    wonderbane_extension_fixed_function_state_test
    fixed_function_state.cpp
    fixed_function_state_test.cpp
  )
  target_compile_features(
    wonderbane_extension_fixed_function_state_test
    PRIVATE
    cxx_std_20
  )
  target_compile_definitions(
    wonderbane_extension_fixed_function_state_test
    PRIVATE
    UNICODE
    _UNICODE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    STRICT
  )
  target_compile_options(
    wonderbane_extension_fixed_function_state_test
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
    wonderbane_extension_fixed_function_state_test
    PRIVATE
    /DYNAMICBASE
    /NXCOMPAT
    /guard:cf
    /INCREMENTAL:NO
  )
  set_property(
    TARGET wonderbane_extension_fixed_function_state_test
    PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded"
  )
  add_test(
    NAME wonderbane_extension_fixed_function_state
    COMMAND wonderbane_extension_fixed_function_state_test
  )

  add_executable(
    wonderbane_extension_cel_shading_test
    banded_lighting.cpp
    cel_shading_test.cpp
    depth_edges.cpp
    fixed_function_state.cpp
    graphics_control.cpp
    graphics_status.cpp
    terrain_trace.cpp
    terrain_mask_refresh.cpp
    import_hook.cpp
    performance_telemetry.cpp
    scene_frame.cpp
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

  add_executable(
    wonderbane_extension_banded_lighting_test
    banded_lighting.cpp
    banded_lighting_test.cpp
    graphics_control.cpp
  )
  target_compile_features(
    wonderbane_extension_banded_lighting_test
    PRIVATE
    cxx_std_20
  )
  target_compile_definitions(
    wonderbane_extension_banded_lighting_test
    PRIVATE
    UNICODE
    _UNICODE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    STRICT
  )
  target_compile_options(
    wonderbane_extension_banded_lighting_test
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
    wonderbane_extension_banded_lighting_test
    PRIVATE
    /DYNAMICBASE
    /NXCOMPAT
    /guard:cf
    /INCREMENTAL:NO
  )
  set_property(
    TARGET wonderbane_extension_banded_lighting_test
    PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded"
  )
  target_link_libraries(
    wonderbane_extension_cel_shading_test
    PRIVATE
    bcrypt
    shell32
    ole32
    uuid
  )
  add_test(
    NAME wonderbane_extension_banded_lighting
    COMMAND wonderbane_extension_banded_lighting_test
  )

  add_executable(
    wonderbane_extension_depth_edges_test
    depth_edges.cpp
    depth_edges_test.cpp
    graphics_control.cpp
    graphics_status.cpp
    terrain_trace.cpp
    terrain_mask_refresh.cpp
  )
  target_compile_features(wonderbane_extension_depth_edges_test PRIVATE cxx_std_20)
  target_compile_definitions(
    wonderbane_extension_depth_edges_test
    PRIVATE
    UNICODE
    _UNICODE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    STRICT
  )
  target_compile_options(
    wonderbane_extension_depth_edges_test
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
    wonderbane_extension_depth_edges_test
    PRIVATE
    /DYNAMICBASE
    /NXCOMPAT
    /guard:cf
    /INCREMENTAL:NO
  )
  target_link_libraries(
    wonderbane_extension_depth_edges_test
    PRIVATE
    bcrypt
    shell32
    ole32
    uuid
  )
  set_property(
    TARGET wonderbane_extension_depth_edges_test
    PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded"
  )
  add_test(
    NAME wonderbane_extension_depth_edges
    COMMAND wonderbane_extension_depth_edges_test
  )

  add_executable(
    wonderbane_extension_graphics_control_test
    graphics_control.cpp
    graphics_control_test.cpp
  )
  target_compile_features(
    wonderbane_extension_graphics_control_test
    PRIVATE
    cxx_std_20
  )
  target_compile_definitions(
    wonderbane_extension_graphics_control_test
    PRIVATE
    UNICODE
    _UNICODE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    STRICT
  )
  target_compile_options(
    wonderbane_extension_graphics_control_test
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
    wonderbane_extension_graphics_control_test
    PRIVATE
    /DYNAMICBASE
    /NXCOMPAT
    /guard:cf
    /INCREMENTAL:NO
  )
  set_property(
    TARGET wonderbane_extension_graphics_control_test
    PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded"
  )
  add_test(
    NAME wonderbane_extension_graphics_control
    COMMAND wonderbane_extension_graphics_control_test
  )

  add_executable(
    wonderbane_extension_graphics_status_test
    graphics_control.cpp
    terrain_trace.cpp
    terrain_mask_refresh.cpp
    graphics_status_test.cpp
  )
  target_compile_features(
    wonderbane_extension_graphics_status_test
    PRIVATE
    cxx_std_20
  )
  target_compile_definitions(
    wonderbane_extension_graphics_status_test
    PRIVATE
    UNICODE
    _UNICODE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    STRICT
  )
  target_compile_options(
    wonderbane_extension_graphics_status_test
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
    wonderbane_extension_graphics_status_test
    PRIVATE
    /DYNAMICBASE
    /NXCOMPAT
    /guard:cf
    /INCREMENTAL:NO
  )
  target_link_libraries(
    wonderbane_extension_graphics_status_test
    PRIVATE
    bcrypt
    shell32
    ole32
    uuid
  )
  set_property(
    TARGET wonderbane_extension_graphics_status_test
    PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded"
  )
  add_test(
    NAME wonderbane_extension_graphics_status
    COMMAND wonderbane_extension_graphics_status_test
  )

  add_executable(
    wonderbane_extension_world_map_projection_test
    world_map_projection.cpp
    world_map_projection_test.cpp
  )
  target_compile_features(
    wonderbane_extension_world_map_projection_test
    PRIVATE
    cxx_std_20
  )
  target_compile_definitions(
    wonderbane_extension_world_map_projection_test
    PRIVATE
    UNICODE
    _UNICODE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    STRICT
  )
  target_compile_options(
    wonderbane_extension_world_map_projection_test
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
    wonderbane_extension_world_map_projection_test
    PRIVATE
    /DYNAMICBASE
    /NXCOMPAT
    /guard:cf
    /INCREMENTAL:NO
  )
  set_property(
    TARGET wonderbane_extension_world_map_projection_test
    PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded"
  )
  add_test(
    NAME wonderbane_extension_world_map_projection
    COMMAND wonderbane_extension_world_map_projection_test
  )

  add_executable(
    wonderbane_extension_event_channel_test
    event_channel.cpp
    event_channel_test.cpp
  )
  target_compile_features(wonderbane_extension_event_channel_test PRIVATE cxx_std_20)
  target_compile_definitions(
    wonderbane_extension_event_channel_test
    PRIVATE
    UNICODE
    _UNICODE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    STRICT
  )
  target_compile_options(
    wonderbane_extension_event_channel_test
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
    wonderbane_extension_event_channel_test
    PRIVATE
    /DYNAMICBASE
    /NXCOMPAT
    /guard:cf
    /INCREMENTAL:NO
  )
  set_property(
    TARGET wonderbane_extension_event_channel_test
    PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded"
  )
  add_test(
    NAME wonderbane_extension_event_channel
    COMMAND wonderbane_extension_event_channel_test
  )

  add_executable(
    wonderbane_extension_performance_telemetry_test
    banded_lighting.cpp
    cel_shading.cpp
    depth_edges.cpp
    fixed_function_state.cpp
    graphics_control.cpp
    graphics_status.cpp
    terrain_trace.cpp
    terrain_mask_refresh.cpp
    import_hook.cpp
    performance_telemetry_test.cpp
    scene_frame.cpp
  )
  target_compile_features(
    wonderbane_extension_performance_telemetry_test
    PRIVATE
    cxx_std_20
  )
  target_compile_definitions(
    wonderbane_extension_performance_telemetry_test
    PRIVATE
    UNICODE
    _UNICODE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    STRICT
  )
  target_compile_options(
    wonderbane_extension_performance_telemetry_test
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
    wonderbane_extension_performance_telemetry_test
    PRIVATE
    /DYNAMICBASE
    /NXCOMPAT
    /guard:cf
    /INCREMENTAL:NO
  )
  target_link_libraries(
    wonderbane_extension_performance_telemetry_test
    PRIVATE
    bcrypt
    shell32
    ole32
    user32
    uuid
  )
  set_property(
    TARGET wonderbane_extension_performance_telemetry_test
    PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded"
  )
  add_test(
    NAME wonderbane_extension_performance_telemetry
    COMMAND wonderbane_extension_performance_telemetry_test
  )

  add_executable(wonderbane_extension_probe event_channel.cpp probe.cpp)
  if(WONDERBANE_EXTENSION_PROFILE STREQUAL "diagnostics-only")
    target_compile_definitions(
      wonderbane_extension_probe
      PRIVATE
      WONDERBANE_EXTENSION_DIAGNOSTICS_ONLY=1
    )
  endif()
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

if(BUILD_TESTING)
  foreach(renderer_test wonderbane_extension_cel_shading_test wonderbane_extension_performance_telemetry_test)
    target_sources(${renderer_test} PRIVATE
      navigation_protocol.cpp navigation_channel.cpp navigation_draw.cpp navigation_viewer.cpp
    selected_cue.cpp selected_cue_gpu.cpp selected_cue_runtime.cpp scene_context.cpp
    scene_draw.cpp effects.cpp effects_attachment.cpp effects_runtime.cpp effects_draw.cpp
    sky.cpp sky_draw.cpp sky_runtime.cpp sky_asset.rc)
    target_link_libraries(${renderer_test} PRIVATE opengl32)
  endforeach()
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_effects_test effects.cpp effects_attachment.cpp effects_test.cpp)
  target_compile_features(wonderbane_extension_effects_test PRIVATE cxx_std_20)
  target_compile_options(wonderbane_extension_effects_test PRIVATE /W4 /WX /permissive- /utf-8)
  set_property(TARGET wonderbane_extension_effects_test PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
  add_test(NAME wonderbane_extension_effects COMMAND wonderbane_extension_effects_test)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_effects_runtime_test
    effects.cpp effects_attachment.cpp effects_runtime_test.cpp)
  target_compile_features(wonderbane_extension_effects_runtime_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_effects_runtime_test PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_effects_runtime_test PRIVATE /W4 /WX /permissive- /utf-8)
  target_link_libraries(wonderbane_extension_effects_runtime_test PRIVATE opengl32)
  set_property(TARGET wonderbane_extension_effects_runtime_test PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
  add_test(NAME wonderbane_extension_effects_runtime COMMAND wonderbane_extension_effects_runtime_test)
endif()

if(BUILD_TESTING)
  foreach(sky_test sky sky_binding)
    add_executable(wonderbane_extension_${sky_test}_test ${sky_test}_test.cpp)
    target_compile_features(wonderbane_extension_${sky_test}_test PRIVATE cxx_std_20)
    target_compile_definitions(wonderbane_extension_${sky_test}_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
    target_compile_options(wonderbane_extension_${sky_test}_test PRIVATE /W4 /WX /permissive- /utf-8)
    target_link_libraries(wonderbane_extension_${sky_test}_test PRIVATE bcrypt)
    set_property(TARGET wonderbane_extension_${sky_test}_test PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
    add_test(NAME wonderbane_extension_${sky_test} COMMAND wonderbane_extension_${sky_test}_test)
  endforeach()
  target_sources(wonderbane_extension_sky_test PRIVATE sky.cpp sky_asset.rc)
  set_tests_properties(wonderbane_extension_sky_binding PROPERTIES SKIP_RETURN_CODE 77)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_sky_render_test sky_render_test.cpp sky.cpp sky_draw.cpp scene_draw.cpp import_hook.cpp sky_asset.rc)
  target_compile_features(wonderbane_extension_sky_render_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_sky_render_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_sky_render_test PRIVATE /W4 /WX /permissive- /utf-8)
  target_link_libraries(wonderbane_extension_sky_render_test PRIVATE bcrypt opengl32 gdi32 user32)
  set_property(TARGET wonderbane_extension_sky_render_test PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
  add_test(NAME wonderbane_extension_sky_render COMMAND wonderbane_extension_sky_render_test)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_movement_controls_test
    movement_controls.cpp movement_controls_test.cpp)
  target_compile_features(wonderbane_extension_movement_controls_test PRIVATE cxx_std_20)
  target_compile_options(wonderbane_extension_movement_controls_test PRIVATE
    /W4 /WX /permissive- /sdl /utf-8)
  set_property(TARGET wonderbane_extension_movement_controls_test
    PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
  add_test(NAME wonderbane_extension_movement_controls
    COMMAND wonderbane_extension_movement_controls_test)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_movement_boundary_test
    movement_boundary_trace.cpp movement_boundary_trace_test.cpp)
  target_compile_features(wonderbane_extension_movement_boundary_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_movement_boundary_test PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT WONDERBANE_MOVEMENT_TRACE_TESTING=1)
  target_compile_options(wonderbane_extension_movement_boundary_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_movement_boundary_test PRIVATE bcrypt user32)
  set_property(TARGET wonderbane_extension_movement_boundary_test PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  add_test(NAME wonderbane_extension_movement_boundary_stop
    COMMAND wonderbane_extension_movement_boundary_test)
  add_test(NAME wonderbane_extension_movement_boundary_startup_failure
    COMMAND wonderbane_extension_movement_boundary_test startup-failure)
endif()

if(BUILD_TESTING)
  add_test(NAME wonderbane_extension_movement_boundary_concurrent_stop
    COMMAND wonderbane_extension_movement_boundary_test concurrent-stop)
endif()

# Explicit developer investigation target; never linked into or installed with DLL.
# Requires a separately supplied reviewed client executable and is not a CI mock.
if(BUILD_TESTING)
  add_executable(wonderbane_extension_movement_tree_probe EXCLUDE_FROM_ALL movement_tree_probe.cpp)
  target_compile_features(wonderbane_extension_movement_tree_probe PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_movement_tree_probe PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_movement_tree_probe PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_movement_tree_probe PRIVATE bcrypt)
  set_property(TARGET wonderbane_extension_movement_tree_probe PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_movement_native_stop_test
    movement_controls.cpp movement_native_image.cpp movement_native_stop.cpp movement_lifetime.cpp import_hook.cpp movement_native_stop_test.cpp)
  target_compile_features(wonderbane_extension_movement_native_stop_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_movement_native_stop_test PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_movement_native_stop_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_movement_native_stop_test PRIVATE bcrypt user32)
  set_property(TARGET wonderbane_extension_movement_native_stop_test PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  add_test(NAME wonderbane_extension_movement_native_stop COMMAND wonderbane_extension_movement_native_stop_test)
endif()

if(BUILD_TESTING)
  add_test(NAME wonderbane_extension_movement_shared_trace_first
    COMMAND wonderbane_extension_movement_boundary_test shared-trace-first)
  add_test(NAME wonderbane_extension_movement_shared_controls_first
    COMMAND wonderbane_extension_movement_boundary_test shared-controls-first)
  add_test(NAME wonderbane_extension_movement_shared_held_control
    COMMAND wonderbane_extension_movement_boundary_test shared-held-control)
  add_test(NAME wonderbane_extension_movement_update_startup_failure
    COMMAND wonderbane_extension_movement_boundary_test movement-startup-failure)
  add_test(NAME wonderbane_extension_movement_shared_slot_replaced
    COMMAND wonderbane_extension_movement_boundary_test shared-slot-replaced)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_movement_lifetime_test
    movement_lifetime_test.cpp movement_native_stop.cpp movement_controls.cpp)
  target_compile_features(wonderbane_extension_movement_lifetime_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_movement_lifetime_test PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_movement_lifetime_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_movement_lifetime_test PRIVATE user32)
  set_property(TARGET wonderbane_extension_movement_lifetime_test PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  foreach(mode normal held held-free rollback foreign foreign-free actuator unsupported unsupported-reference)
    add_test(NAME wonderbane_extension_movement_lifetime_${mode}
      COMMAND wonderbane_extension_movement_lifetime_test ${mode})
  endforeach()
endif()
