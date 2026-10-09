cmake_minimum_required(VERSION 3.24)

project(wonderbane_extension VERSION 1.8.55 LANGUAGES CXX RC)

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
  targeted_action_trace.cpp
  condemn_responses.cpp
  item_application_trace.cpp
  condemn_native.cpp
  movement_controls.cpp
  movement_windows_input.cpp
  movement_runtime.cpp
  vendor_runtime.cpp
  vendor_menu_native.cpp
  vendor_native.cpp
  guard_upgrade_native.cpp
  guard_funding_native.cpp
  city_window_native.cpp
  building_native_target.cpp
  actor_effects_native.cpp
  combat_item_entry.cpp
  combat_submission.cpp
  actor_inventory_native.cpp
  actor_buff_observation.cpp
  actor_action_native.cpp
  actor_publication.cpp
  combat_melee_entry.cpp
  combat_target_policy.cpp
  combat_power_entry.cpp
  combat_power_observer.cpp
  combat_activation_observer.cpp
  actor_action_runtime.cpp
  vendor_navigation_native.cpp
  movement_settings.cpp
  movement_native_image.cpp
  movement_lifetime.cpp
  door_native_collection.cpp
  movement_native_ui.cpp
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
    selected_cue.cpp selected_cue_gpu.cpp selected_cue_runtime.cpp weapon_appearance.cpp visual_inspector.cpp moonfire.cpp scene_context.cpp
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
target_link_libraries(wonderbane_extension PRIVATE bcrypt shell32 ole32 user32 uuid comctl32 advapi32 gdi32)

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
    selected_cue.cpp effects_attachment.cpp import_hook.cpp weapon_appearance.cpp visual_inspector.cpp selected_cue_runtime_test.cpp)
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
  add_test(NAME wonderbane_extension_selected_cue_native_material
    COMMAND wonderbane_extension_selected_cue_gpu_test --native-material)
  set_tests_properties(wonderbane_extension_selected_cue_native_material PROPERTIES SKIP_RETURN_CODE 77)
  add_test(NAME wonderbane_extension_scene_pipeline_guard
    COMMAND wonderbane_extension_selected_cue_gpu_test --pipeline-guard)
  set_tests_properties(wonderbane_extension_scene_pipeline_guard PROPERTIES SKIP_RETURN_CODE 77)
  add_test(NAME wonderbane_extension_scene_query_guard
    COMMAND wonderbane_extension_selected_cue_gpu_test --query-guard)
  set_tests_properties(wonderbane_extension_scene_query_guard PROPERTIES SKIP_RETURN_CODE 77)
  add_test(NAME wonderbane_extension_selected_cue_unsupported_formats
    COMMAND wonderbane_extension_selected_cue_gpu_test --unsupported-formats)
  set_tests_properties(wonderbane_extension_selected_cue_unsupported_formats PROPERTIES SKIP_RETURN_CODE 77)
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
  add_test(NAME wonderbane_extension_ordered_operators_legacy
    COMMAND wonderbane_extension_navigation_draw_test --ordered-operators)
  set_tests_properties(wonderbane_extension_ordered_operators_legacy PROPERTIES
    ENVIRONMENT "WONDERBANE_TEST_GDI_GL=1" SKIP_RETURN_CODE 77)
  add_test(NAME wonderbane_extension_combined_render
    COMMAND wonderbane_extension_navigation_draw_test --combined-render)
  set_tests_properties(wonderbane_extension_combined_render PROPERTIES SKIP_RETURN_CODE 77)
  add_test(NAME wonderbane_extension_effects_native_transparency
    COMMAND wonderbane_extension_navigation_draw_test --verify-native-transparency)
  # Deferred ideal composition probes remain executable, separate from required fallback.
  set_tests_properties(wonderbane_extension_selected_cue_native_transparency
    wonderbane_extension_effects_native_transparency PROPERTIES LABELS "stretch-diagnostic")

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
    movement_controls.cpp
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

  add_executable(wonderbane_extension_probe event_channel.cpp probe.cpp movement_controls.cpp)
  target_link_libraries(wonderbane_extension_probe PRIVATE bcrypt)
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
    selected_cue.cpp selected_cue_gpu.cpp selected_cue_runtime.cpp weapon_appearance.cpp visual_inspector.cpp moonfire.cpp scene_context.cpp
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
  add_executable(wonderbane_extension_door_collection_test door_collection_admission_test.cpp)
  target_compile_features(wonderbane_extension_door_collection_test PRIVATE cxx_std_20)
  target_compile_options(wonderbane_extension_door_collection_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  set_property(TARGET wonderbane_extension_door_collection_test PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  add_test(NAME wonderbane_extension_door_collection COMMAND wonderbane_extension_door_collection_test)
  set_tests_properties(wonderbane_extension_door_collection PROPERTIES TIMEOUT 15)

  add_executable(wonderbane_extension_door_targeting_test door_targeting_test.cpp)
  target_compile_features(wonderbane_extension_door_targeting_test PRIVATE cxx_std_20)
  target_compile_options(wonderbane_extension_door_targeting_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  set_property(TARGET wonderbane_extension_door_targeting_test PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  add_test(NAME wonderbane_extension_door_targeting COMMAND wonderbane_extension_door_targeting_test)

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
  add_test(NAME wonderbane_extension_movement_boundary_input_diagnostics
    COMMAND wonderbane_extension_movement_boundary_test input-diagnostics)
  add_test(NAME wonderbane_extension_movement_boundary_lifetime_diagnostics
    COMMAND wonderbane_extension_movement_boundary_test lifetime-diagnostics)
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
    movement_controls.cpp movement_native_image.cpp terrain_mask_refresh.cpp movement_native_stop.cpp movement_lifetime.cpp movement_native_ui.cpp import_hook.cpp movement_native_stop_test.cpp)
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
  add_test(NAME wonderbane_extension_movement_boundary_outermost_service
    COMMAND wonderbane_extension_movement_boundary_test outermost-service)
  add_test(NAME wonderbane_extension_movement_update_startup_failure
    COMMAND wonderbane_extension_movement_boundary_test movement-startup-failure)
  add_test(NAME wonderbane_extension_movement_shared_slot_replaced
    COMMAND wonderbane_extension_movement_boundary_test shared-slot-replaced)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_movement_lifetime_test
    movement_lifetime_test.cpp movement_native_stop.cpp movement_native_ui.cpp movement_controls.cpp door_native_collection.cpp)
  target_compile_features(wonderbane_extension_movement_lifetime_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_movement_lifetime_test PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_movement_lifetime_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_movement_lifetime_test PRIVATE user32)
  set_property(TARGET wonderbane_extension_movement_lifetime_test PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  foreach(mode normal parent-continuity diagnostics established-churn identity-fields capture-gap held held-free rollback rollback-batch foreign foreign-free actuator actuator-foreign actuator-foreign-free unsupported unsupported-reference
      arm-first-ref arm-first-free arm-replacement-ref arm-replacement-free
      arm-first-ref-publish arm-first-free-publish arm-replacement-ref-publish arm-replacement-free-publish
      arm-first-held-ref arm-first-held-free arm-replacement-held-ref arm-replacement-held-free
      arm-before-first-ref arm-before-first-free arm-before-replacement-ref arm-before-replacement-free
      arm-edge-ref arm-edge-free arm-replacement-edge-ref arm-replacement-edge-free)
    add_test(NAME wonderbane_extension_movement_lifetime_${mode}
      COMMAND wonderbane_extension_movement_lifetime_test ${mode})
  endforeach()
  foreach(mode door-normal door-rollback door-foreign door-teardown door-query door-query-fault)
    add_test(NAME wonderbane_extension_movement_lifetime_${mode}
      COMMAND wonderbane_extension_movement_lifetime_test ${mode})
    set_tests_properties(wonderbane_extension_movement_lifetime_${mode} PROPERTIES TIMEOUT 20)
  endforeach()

endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_movement_native_ui_test movement_native_ui.cpp movement_native_ui_test.cpp)
  target_compile_features(wonderbane_extension_movement_native_ui_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_movement_native_ui_test PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_movement_native_ui_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_movement_native_ui_test PRIVATE user32)
  set_property(TARGET wonderbane_extension_movement_native_ui_test PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  add_test(NAME wonderbane_extension_movement_native_ui COMMAND wonderbane_extension_movement_native_ui_test)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_movement_windows_input_test
    movement_windows_input.cpp movement_windows_input_test.cpp movement_controls.cpp import_hook.cpp)
  target_compile_features(wonderbane_extension_movement_windows_input_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_movement_windows_input_test PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_movement_windows_input_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_movement_windows_input_test PRIVATE user32 comctl32)
  set_property(TARGET wonderbane_extension_movement_windows_input_test PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  foreach(mode keyboard mouse controller lifecycle rollback foreign-subclass unsupported settings preparation)
    add_test(NAME wonderbane_extension_movement_windows_input_${mode}
      COMMAND wonderbane_extension_movement_windows_input_test ${mode})
  endforeach()
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_movement_runtime_test movement_runtime_test.cpp
    movement_controls.cpp movement_native_stop.cpp movement_native_ui.cpp movement_windows_input.cpp
    movement_native_image.cpp terrain_mask_refresh.cpp movement_settings.cpp import_hook.cpp)
  target_compile_features(wonderbane_extension_movement_runtime_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_movement_runtime_test PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_movement_runtime_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_movement_runtime_test PRIVATE user32 comctl32 bcrypt advapi32 gdi32)
  set_property(TARGET wonderbane_extension_movement_runtime_test PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  foreach(mode commands owner-service keyboard keyboard-cold-start keyboard-reversal manual-update-gap parent-keyboard parent-controller parent-controller-text parent-drag parent-automation parent-ui parent-focus parent-stop-failure parent-nested-stop parent-notice parent-identity parent-actor parent-unowned parent-disabled input-diagnostics controller controller-modal-rearm controller-text controller-profile controller-cancel-failure controller-cancel-nested drag focus stale destroyed nested-stop nested-camera nested-move startup-unavailable startup-hook-failure settings-stale scene-stale chat)
    add_test(NAME wonderbane_extension_movement_runtime_${mode} COMMAND wonderbane_extension_movement_runtime_test ${mode})
  endforeach()
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_movement_settings_test movement_settings_test.cpp movement_controls.cpp)
  target_compile_features(wonderbane_extension_movement_settings_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_movement_settings_test PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_movement_settings_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_movement_settings_test PRIVATE user32 comctl32 advapi32 gdi32)
  set_property(TARGET wonderbane_extension_movement_settings_test PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  add_test(NAME wonderbane_extension_movement_settings COMMAND wonderbane_extension_movement_settings_test)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_combat_fence_test combat_fence_test.cpp)
  target_compile_features(wonderbane_extension_combat_fence_test PRIVATE cxx_std_20)
  target_link_libraries(wonderbane_extension_combat_fence_test PRIVATE bcrypt)
  target_compile_options(wonderbane_extension_combat_fence_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  set_property(TARGET wonderbane_extension_combat_fence_test PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  add_test(NAME wonderbane_extension_combat_fence COMMAND wonderbane_extension_combat_fence_test
    "${CMAKE_CURRENT_SOURCE_DIR}/../../tests/fixtures/combat_fence_v2.hex")

  add_executable(wonderbane_extension_movement_wire_test movement_wire_test.cpp movement_controls.cpp)
  target_compile_features(wonderbane_extension_movement_wire_test PRIVATE cxx_std_20)
  target_compile_options(wonderbane_extension_movement_wire_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  set_property(TARGET wonderbane_extension_movement_wire_test PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  add_test(NAME wonderbane_extension_movement_wire COMMAND wonderbane_extension_movement_wire_test
    "${CMAKE_CURRENT_SOURCE_DIR}/../../tests/fixtures/native_movement_wire_v3.hex")
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_movement_channel_test movement_channel_test.cpp movement_controls.cpp)
  target_compile_features(wonderbane_extension_movement_channel_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_movement_channel_test PRIVATE NOMINMAX WIN32_LEAN_AND_MEAN)
  target_compile_options(wonderbane_extension_movement_channel_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  set_property(TARGET wonderbane_extension_movement_channel_test PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  add_test(NAME wonderbane_extension_movement_channel COMMAND wonderbane_extension_movement_channel_test)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_movement_image_test
    movement_image_test.cpp movement_lifetime.cpp import_hook.cpp)
  if(WONDERBANE_EXTENSION_PROFILE STREQUAL "diagnostics-only")
    target_compile_definitions(wonderbane_extension_movement_image_test PRIVATE WONDERBANE_EXTENSION_DIAGNOSTICS_ONLY=1)
  endif()
  target_compile_features(wonderbane_extension_movement_image_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_movement_image_test PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_movement_image_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_movement_image_test PRIVATE bcrypt user32)
  set_property(TARGET wonderbane_extension_movement_image_test PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  add_test(NAME wonderbane_extension_movement_image COMMAND wonderbane_extension_movement_image_test)
  set_tests_properties(wonderbane_extension_movement_image PROPERTIES SKIP_RETURN_CODE 77)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_movement_settings_runtime_test movement_settings_runtime_test.cpp
    movement_controls.cpp movement_native_stop.cpp movement_native_ui.cpp movement_windows_input.cpp
    movement_native_image.cpp terrain_mask_refresh.cpp import_hook.cpp)
  target_compile_features(wonderbane_extension_movement_settings_runtime_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_movement_settings_runtime_test PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_movement_settings_runtime_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_movement_settings_runtime_test PRIVATE user32 comctl32 bcrypt advapi32 gdi32)
  set_property(TARGET wonderbane_extension_movement_settings_runtime_test PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  add_test(NAME wonderbane_extension_movement_settings_runtime COMMAND wonderbane_extension_movement_settings_runtime_test)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_targeted_action_trace_test targeted_action_trace_test.cpp)
  target_compile_features(wonderbane_extension_targeted_action_trace_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_targeted_action_trace_test PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_targeted_action_trace_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  set_property(TARGET wonderbane_extension_targeted_action_trace_test PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  add_test(NAME wonderbane_extension_targeted_action_trace COMMAND wonderbane_extension_targeted_action_trace_test)
  add_test(NAME wonderbane_extension_targeted_action_trace_rollback COMMAND wonderbane_extension_targeted_action_trace_test rollback)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_vendor_controller_test vendor_controller_test.cpp)
  target_compile_features(wonderbane_extension_vendor_controller_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_vendor_controller_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_vendor_controller_test PRIVATE /W4 /WX /permissive- /utf-8)
  add_test(NAME wonderbane_extension_vendor_controller COMMAND wonderbane_extension_vendor_controller_test)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_vendor_native_test vendor_native_test.cpp vendor_native.cpp)
  target_compile_features(wonderbane_extension_vendor_native_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_vendor_native_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_vendor_native_test PRIVATE /W4 /WX /permissive- /utf-8)
  add_test(NAME wonderbane_extension_vendor_native COMMAND wonderbane_extension_vendor_native_test)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_vendor_channel_test vendor_channel_test.cpp movement_controls.cpp)
  target_compile_features(wonderbane_extension_vendor_channel_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_vendor_channel_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_vendor_channel_test PRIVATE /W4 /WX /permissive- /utf-8)
  add_test(NAME wonderbane_extension_vendor_channel COMMAND wonderbane_extension_vendor_channel_test)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_city_window_controller_test city_window_controller_test.cpp)
  target_compile_features(wonderbane_extension_city_window_controller_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_city_window_controller_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_city_window_controller_test PRIVATE /W4 /WX /permissive- /utf-8)
  add_test(NAME wonderbane_extension_city_window_controller COMMAND wonderbane_extension_city_window_controller_test)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_city_window_native_test city_window_native_test.cpp city_window_native.cpp)
  target_compile_features(wonderbane_extension_city_window_native_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_city_window_native_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_city_window_native_test PRIVATE /W4 /WX /permissive- /utf-8)
  add_test(NAME wonderbane_extension_city_window_native COMMAND wonderbane_extension_city_window_native_test)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_city_window_channel_test city_window_channel_test.cpp movement_controls.cpp)
  target_compile_features(wonderbane_extension_city_window_channel_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_city_window_channel_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_city_window_channel_test PRIVATE /W4 /WX /permissive- /utf-8)
  add_test(NAME wonderbane_extension_city_window_channel COMMAND wonderbane_extension_city_window_channel_test)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_building_target_test building_native_target_test.cpp building_native_target.cpp)
  target_compile_features(wonderbane_extension_building_target_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_building_target_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_building_target_test PRIVATE /W4 /WX /permissive- /utf-8)
  add_test(NAME wonderbane_extension_building_target COMMAND wonderbane_extension_building_target_test)
  set_tests_properties(wonderbane_extension_building_target PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_vendor_navigation_controller_test vendor_navigation_controller_test.cpp)
  target_compile_features(wonderbane_extension_vendor_navigation_controller_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_vendor_navigation_controller_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_vendor_navigation_controller_test PRIVATE /W4 /WX /permissive- /utf-8)
  add_test(NAME wonderbane_extension_vendor_navigation_controller COMMAND wonderbane_extension_vendor_navigation_controller_test)
  set_tests_properties(wonderbane_extension_vendor_navigation_controller PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_vendor_navigation_native_test vendor_navigation_native_test.cpp vendor_navigation_native.cpp guard_upgrade_native.cpp)
  target_compile_features(wonderbane_extension_vendor_navigation_native_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_vendor_navigation_native_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_vendor_navigation_native_test PRIVATE /W4 /WX /permissive- /utf-8)
  add_test(NAME wonderbane_extension_vendor_navigation_native COMMAND wonderbane_extension_vendor_navigation_native_test)
  set_tests_properties(wonderbane_extension_vendor_navigation_native PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_vendor_navigation_channel_test vendor_navigation_channel_test.cpp movement_controls.cpp)
  target_compile_features(wonderbane_extension_vendor_navigation_channel_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_vendor_navigation_channel_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_vendor_navigation_channel_test PRIVATE /W4 /WX /permissive- /utf-8)
  add_test(NAME wonderbane_extension_vendor_navigation_channel COMMAND wonderbane_extension_vendor_navigation_channel_test)
  set_tests_properties(wonderbane_extension_vendor_navigation_channel PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_guard_upgrade_controller_test guard_upgrade_controller_test.cpp)
  target_compile_features(wonderbane_extension_guard_upgrade_controller_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_guard_upgrade_controller_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_guard_upgrade_controller_test PRIVATE /W4 /WX /permissive- /utf-8)
  add_test(NAME wonderbane_extension_guard_upgrade_controller COMMAND wonderbane_extension_guard_upgrade_controller_test)
  set_tests_properties(wonderbane_extension_guard_upgrade_controller PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_guard_upgrade_channel_test guard_upgrade_channel_test.cpp movement_controls.cpp)
  target_compile_features(wonderbane_extension_guard_upgrade_channel_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_guard_upgrade_channel_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_guard_upgrade_channel_test PRIVATE /W4 /WX /permissive- /utf-8)
  add_test(NAME wonderbane_extension_guard_upgrade_channel COMMAND wonderbane_extension_guard_upgrade_channel_test)
  set_tests_properties(wonderbane_extension_guard_upgrade_channel PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_guard_funding_native_test guard_funding_native_test.cpp guard_funding_native.cpp)
  target_compile_features(wonderbane_extension_guard_funding_native_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_guard_funding_native_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_guard_funding_native_test PRIVATE /W4 /WX /permissive- /utf-8)
  add_test(NAME wonderbane_extension_guard_funding_native COMMAND wonderbane_extension_guard_funding_native_test)
  set_tests_properties(wonderbane_extension_guard_funding_native PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_guard_funding_controller_test guard_funding_controller_test.cpp)
  target_compile_features(wonderbane_extension_guard_funding_controller_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_guard_funding_controller_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_guard_funding_controller_test PRIVATE /W4 /WX /permissive- /utf-8)
  add_test(NAME wonderbane_extension_guard_funding_controller COMMAND wonderbane_extension_guard_funding_controller_test)
  set_tests_properties(wonderbane_extension_guard_funding_controller PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_guard_funding_channel_test guard_funding_channel_test.cpp movement_controls.cpp)
  target_compile_features(wonderbane_extension_guard_funding_channel_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_guard_funding_channel_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_guard_funding_channel_test PRIVATE /W4 /WX /permissive- /utf-8)
  add_test(NAME wonderbane_extension_guard_funding_channel COMMAND wonderbane_extension_guard_funding_channel_test)
  set_tests_properties(wonderbane_extension_guard_funding_channel PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_condemn_responses_test condemn_responses_test.cpp)
  target_compile_features(wonderbane_extension_condemn_responses_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_condemn_responses_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_condemn_responses_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  set_property(TARGET wonderbane_extension_condemn_responses_test PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  add_test(NAME wonderbane_extension_condemn_responses COMMAND wonderbane_extension_condemn_responses_test)
  set_tests_properties(wonderbane_extension_condemn_responses PROPERTIES TIMEOUT 15)
  foreach(step RANGE 1 3)
    add_test(NAME wonderbane_extension_condemn_rollback_${step} COMMAND wonderbane_extension_condemn_responses_test ${step})
    set_tests_properties(wonderbane_extension_condemn_rollback_${step} PROPERTIES TIMEOUT 15)
  endforeach()
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_condemn_native_test condemn_native_test.cpp condemn_native.cpp)
  target_compile_features(wonderbane_extension_condemn_native_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_condemn_native_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_condemn_native_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  add_test(NAME wonderbane_extension_condemn_native COMMAND wonderbane_extension_condemn_native_test)
  set_tests_properties(wonderbane_extension_condemn_native PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_condemn_evidence_test condemn_evidence_test.cpp)
  target_compile_features(wonderbane_extension_condemn_evidence_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_condemn_evidence_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_condemn_evidence_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  add_test(NAME wonderbane_extension_condemn_evidence COMMAND wonderbane_extension_condemn_evidence_test)
  set_tests_properties(wonderbane_extension_condemn_evidence PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_condemn_controller_test condemn_controller_test.cpp)
  target_compile_features(wonderbane_extension_condemn_controller_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_condemn_controller_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_condemn_controller_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  add_test(NAME wonderbane_extension_condemn_controller COMMAND wonderbane_extension_condemn_controller_test)
  set_tests_properties(wonderbane_extension_condemn_controller PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  foreach(kind channel runtime)
    add_executable(wonderbane_extension_condemn_${kind}_test condemn_${kind}_test.cpp movement_controls.cpp)
    target_compile_features(wonderbane_extension_condemn_${kind}_test PRIVATE cxx_std_20)
    target_compile_definitions(wonderbane_extension_condemn_${kind}_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
    target_compile_options(wonderbane_extension_condemn_${kind}_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
    add_test(NAME wonderbane_extension_condemn_${kind} COMMAND wonderbane_extension_condemn_${kind}_test)
    set_tests_properties(wonderbane_extension_condemn_${kind} PROPERTIES TIMEOUT 15)
  endforeach()
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_vendor_menu_controller_test vendor_menu_controller_test.cpp)
  add_executable(wonderbane_extension_vendor_menu_channel_test vendor_menu_channel_test.cpp movement_controls.cpp)
  add_executable(wonderbane_extension_vendor_menu_native_test vendor_menu_native_test.cpp vendor_menu_native.cpp vendor_native.cpp)
  foreach(component controller channel native)
    set(target wonderbane_extension_vendor_menu_${component}_test)
    target_compile_features(${target} PRIVATE cxx_std_20)
    target_compile_definitions(${target} PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
    target_compile_options(${target} PRIVATE /W4 /WX /permissive- /utf-8)
    if(component STREQUAL "controller")
      add_test(NAME wonderbane_extension_vendor_menu_${component} COMMAND ${target}
        "${CMAKE_CURRENT_SOURCE_DIR}/../../tests/fixtures/native_vendor_menu_wire_v1.hex")
    else()
      add_test(NAME wonderbane_extension_vendor_menu_${component} COMMAND ${target})
    endif()
    set_tests_properties(wonderbane_extension_vendor_menu_${component} PROPERTIES TIMEOUT 15)
  endforeach()
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_combat_wire_test combat_wire_test.cpp)
  target_compile_features(wonderbane_extension_combat_wire_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_combat_wire_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_combat_wire_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_combat_wire_test PRIVATE bcrypt)
  add_test(NAME wonderbane_extension_combat_wire COMMAND wonderbane_extension_combat_wire_test "${CMAKE_CURRENT_SOURCE_DIR}/../../tests/fixtures/combat_command_v1.hex")
  set_tests_properties(wonderbane_extension_combat_wire PROPERTIES TIMEOUT 15)

  add_executable(wonderbane_extension_combat_party_test combat_party_test.cpp)
  target_compile_features(wonderbane_extension_combat_party_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_combat_party_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_combat_party_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  add_test(NAME wonderbane_extension_combat_party COMMAND wonderbane_extension_combat_party_test)
  set_tests_properties(wonderbane_extension_combat_party PROPERTIES TIMEOUT 15)

  add_executable(wonderbane_extension_combat_controller_test combat_controller_test.cpp)
  target_compile_features(wonderbane_extension_combat_controller_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_combat_controller_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_combat_controller_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_combat_controller_test PRIVATE bcrypt)
  add_test(NAME wonderbane_extension_combat_controller COMMAND wonderbane_extension_combat_controller_test "${CMAKE_CURRENT_SOURCE_DIR}/../../tests/fixtures/combat_command_v1.hex")
  set_tests_properties(wonderbane_extension_combat_controller PROPERTIES TIMEOUT 15)

  add_executable(wonderbane_extension_combat_submission_test combat_submission_test.cpp)
  target_compile_features(wonderbane_extension_combat_submission_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_combat_submission_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_combat_submission_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  add_test(NAME wonderbane_extension_combat_submission COMMAND wonderbane_extension_combat_submission_test)
  add_test(NAME wonderbane_extension_combat_submission_install_failure COMMAND wonderbane_extension_combat_submission_test install-failure)
  foreach(image_case prepared11 prepared12 original12 prepared13 original13 prepared14 original14 prepared15 original15 unknown)
    if(image_case STREQUAL "prepared11")
      set(digest "7f283cdbeb691d65ef3073d32e4ea7bc0cfcb31e1bb205e460573f23d0a7758f")
      set(admission allow)
    elseif(image_case STREQUAL "prepared12")
      set(digest "2dc0e19c3fcf43bc19508939fb9c63982bc370a868f810208394324a12cdc289")
      set(admission allow)
    elseif(image_case STREQUAL "original12")
      set(digest "3891fcab09dac06d858ac55911046448e75f3519e2f58e1d7c2ccc954aa410b7")
      set(admission deny)
    elseif(image_case STREQUAL "prepared13")
      set(digest "0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d")
      set(admission allow)
    elseif(image_case STREQUAL "prepared14")
      set(digest "78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903")
      set(admission allow)
    elseif(image_case STREQUAL "prepared15")
      set(digest "e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437")
      set(admission allow)
    elseif(image_case STREQUAL "original15")
      set(digest "381e67586b3c36b8ce1dcdb824439010d373d455aa6b460b02cf44f7d58fe9e5")
      set(admission deny)
    elseif(image_case STREQUAL "original14")
      set(digest "e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e")
      set(admission deny)
    elseif(image_case STREQUAL "original13")
      set(digest "e5bb74e159a9acd8529652eb5b0c07766ced7ffd70c03c960ccdbcefca83c6e8")
      set(admission deny)
    else()
      set(digest "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff")
      set(admission deny)
    endif()
    add_test(NAME wonderbane_extension_combat_image_${image_case}
      COMMAND wonderbane_extension_combat_submission_test image-admission ${digest} ${admission})
    set_tests_properties(wonderbane_extension_combat_image_${image_case} PROPERTIES TIMEOUT 15)
  endforeach()
  set_tests_properties(wonderbane_extension_combat_submission PROPERTIES TIMEOUT 15)
  add_executable(wonderbane_extension_combat_native_test combat_native_test.cpp combat_native.cpp)
  target_compile_features(wonderbane_extension_combat_native_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_combat_native_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_combat_native_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_combat_native_test PRIVATE bcrypt user32)
  add_test(NAME wonderbane_extension_combat_native COMMAND wonderbane_extension_combat_native_test)
  set_tests_properties(wonderbane_extension_combat_native PROPERTIES TIMEOUT 15)
  add_executable(wonderbane_extension_combat_runtime_test combat_runtime_test.cpp)
  target_compile_features(wonderbane_extension_combat_runtime_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_combat_runtime_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_combat_runtime_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_combat_runtime_test PRIVATE bcrypt user32)
  add_test(NAME wonderbane_extension_combat_runtime COMMAND wonderbane_extension_combat_runtime_test)
  set_tests_properties(wonderbane_extension_combat_runtime PROPERTIES TIMEOUT 15)
  # Real named-mapping preparation IPC; gameplay callbacks are explicit test substitutions.
  # Executed by mandatory Python actor IPC gates, rather than unattended CTest.
  add_executable(wonderbane_extension_preparation_channel_test preparation_channel_test.cpp movement_controls.cpp)
  target_compile_features(wonderbane_extension_preparation_channel_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_preparation_channel_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_preparation_channel_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_preparation_channel_test PRIVATE bcrypt advapi32)
  add_executable(wonderbane_extension_combat_channel_test combat_channel_test.cpp movement_controls.cpp)
  target_compile_features(wonderbane_extension_combat_channel_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_combat_channel_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_combat_channel_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_combat_channel_test PRIVATE bcrypt)
  add_test(NAME wonderbane_extension_combat_channel COMMAND wonderbane_extension_combat_channel_test "${CMAKE_CURRENT_SOURCE_DIR}/../../tests/fixtures/actor_command_v3.hex")
  set_tests_properties(wonderbane_extension_combat_channel PROPERTIES TIMEOUT 15)
  foreach(kind city_window movement guard_upgrade guard_funding condemn event vendor_navigation vendor vendor_menu)
    target_link_libraries(wonderbane_extension_${kind}_channel_test PRIVATE bcrypt)
  endforeach()
endif()

# Offline native resolver conformance; explicit private executable argument only.
# Not linked into the DLL, distributed package, or the public CTest suite.
if(BUILD_TESTING)
  add_executable(wonderbane_extension_combat_registry_probe EXCLUDE_FROM_ALL combat_registry_probe.cpp)
  target_compile_features(wonderbane_extension_combat_registry_probe PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_combat_registry_probe PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_combat_registry_probe PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_combat_registry_probe PRIVATE bcrypt)
  set_property(TARGET wonderbane_extension_combat_registry_probe PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
endif()

# Compare the explicit-object adapter to the reviewed ordinary attack control flow.
if(BUILD_TESTING)
  add_executable(wonderbane_extension_combat_melee_entry_test combat_melee_entry_test.cpp combat_melee_entry.cpp)
  add_executable(wonderbane_extension_combat_melee_probe EXCLUDE_FROM_ALL combat_melee_entry_test.cpp combat_melee_entry.cpp)
  foreach(target wonderbane_extension_combat_melee_entry_test wonderbane_extension_combat_melee_probe)
    target_compile_features(${target} PRIVATE cxx_std_20)
    target_compile_definitions(${target} PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
    target_compile_options(${target} PRIVATE /W4 /WX /permissive- /sdl /utf-8)
    target_link_libraries(${target} PRIVATE bcrypt)
  endforeach()
  target_compile_definitions(wonderbane_extension_combat_melee_probe PRIVATE MELEE_NATIVE_PROBE)
  set_property(TARGET wonderbane_extension_combat_melee_probe PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  add_test(NAME wonderbane_extension_combat_melee_entry COMMAND wonderbane_extension_combat_melee_entry_test)
  set_tests_properties(wonderbane_extension_combat_melee_entry PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_combat_power_entry_test combat_power_entry_test.cpp combat_activation_observer.cpp)
  target_link_libraries(wonderbane_extension_combat_power_entry_test PRIVATE bcrypt)
  target_compile_features(wonderbane_extension_combat_power_entry_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_combat_power_entry_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_combat_power_entry_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  add_test(NAME wonderbane_extension_combat_power_entry COMMAND wonderbane_extension_combat_power_entry_test)
  add_test(NAME wonderbane_extension_combat_power_partial_install COMMAND wonderbane_extension_combat_power_entry_test partial-install)
  foreach(image_case prepared12 original12 prepared13 original13 prepared14 original14 prepared15 original15 unknown)
    if(image_case STREQUAL "prepared12")
      set(digest "2dc0e19c3fcf43bc19508939fb9c63982bc370a868f810208394324a12cdc289")
      set(admission deny)
    elseif(image_case STREQUAL "original12")
      set(digest "3891fcab09dac06d858ac55911046448e75f3519e2f58e1d7c2ccc954aa410b7")
      set(admission deny)
    elseif(image_case STREQUAL "prepared13")
      set(digest "0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d")
      set(admission allow)
    elseif(image_case STREQUAL "prepared14")
      set(digest "78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903")
      set(admission allow)
    elseif(image_case STREQUAL "prepared15")
      set(digest "e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437")
      set(admission allow)
    elseif(image_case STREQUAL "original15")
      set(digest "381e67586b3c36b8ce1dcdb824439010d373d455aa6b460b02cf44f7d58fe9e5")
      set(admission deny)
    elseif(image_case STREQUAL "original14")
      set(digest "e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e")
      set(admission deny)
    elseif(image_case STREQUAL "original13")
      set(digest "e5bb74e159a9acd8529652eb5b0c07766ced7ffd70c03c960ccdbcefca83c6e8")
      set(admission deny)
    else()
      set(digest "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff")
      set(admission deny)
    endif()
    add_test(NAME wonderbane_extension_combat_power_image_${image_case}
      COMMAND wonderbane_extension_combat_power_entry_test image-admission ${digest} ${admission})
    set_tests_properties(wonderbane_extension_combat_power_image_${image_case} PROPERTIES TIMEOUT 15)
  endforeach()
  set_tests_properties(wonderbane_extension_combat_power_entry wonderbane_extension_combat_power_partial_install PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  foreach(target wonderbane_extension_movement_native_stop_test wonderbane_extension_movement_runtime_test wonderbane_extension_movement_settings_runtime_test wonderbane_extension_movement_image_test)
    target_sources(${target} PRIVATE combat_power_image_test_stub.cpp)
  endforeach()
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_combat_power_probe EXCLUDE_FROM_ALL combat_power_probe.cpp)
  target_compile_features(wonderbane_extension_combat_power_probe PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_combat_power_probe PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_combat_power_probe PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_combat_power_probe PRIVATE bcrypt)
  set_property(TARGET wonderbane_extension_combat_power_probe PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  add_executable(wonderbane_extension_actor_preparation_motion_test actor_preparation_motion_test.cpp)
  target_compile_features(wonderbane_extension_actor_preparation_motion_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_actor_preparation_motion_test PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)
  target_compile_options(wonderbane_extension_actor_preparation_motion_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  add_test(NAME wonderbane_extension_actor_preparation_motion COMMAND wonderbane_extension_actor_preparation_motion_test)
  add_executable(wonderbane_extension_combat_initiation_test combat_initiation_test.cpp)
  target_compile_features(wonderbane_extension_combat_initiation_test PRIVATE cxx_std_20)
  target_compile_options(wonderbane_extension_combat_initiation_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  add_test(NAME wonderbane_extension_combat_initiation COMMAND wonderbane_extension_combat_initiation_test)
  add_executable(wonderbane_extension_combat_power_initiation_probe EXCLUDE_FROM_ALL combat_power_initiation_probe.cpp)
  target_compile_features(wonderbane_extension_combat_power_initiation_probe PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_combat_power_initiation_probe PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_combat_power_initiation_probe PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_combat_power_initiation_probe PRIVATE bcrypt)
  set_property(TARGET wonderbane_extension_combat_power_initiation_probe PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  add_executable(wonderbane_extension_combat_power_movement_probe EXCLUDE_FROM_ALL combat_power_movement_probe.cpp)
  target_compile_features(wonderbane_extension_combat_power_movement_probe PRIVATE cxx_std_20)
  target_compile_options(wonderbane_extension_combat_power_movement_probe PRIVATE /W4 /WX /EHsc)
  target_link_libraries(wonderbane_extension_combat_power_movement_probe PRIVATE bcrypt)
  # Private copied-image SEH search substitute only; never applied to the DLL.
  target_link_options(wonderbane_extension_combat_power_movement_probe PRIVATE /SAFESEH:NO)
  set_property(TARGET wonderbane_extension_combat_power_movement_probe PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  add_executable(wonderbane_extension_combat_power_readiness_test combat_power_readiness_test.cpp)
  target_compile_features(wonderbane_extension_combat_power_readiness_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_combat_power_readiness_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_combat_power_readiness_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  add_test(NAME wonderbane_extension_combat_power_readiness COMMAND wonderbane_extension_combat_power_readiness_test)
  add_executable(wonderbane_extension_combat_power_readiness_probe EXCLUDE_FROM_ALL combat_power_readiness_probe.cpp)
  target_compile_features(wonderbane_extension_combat_power_readiness_probe PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_combat_power_readiness_probe PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_combat_power_readiness_probe PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_combat_power_readiness_probe PRIVATE bcrypt)
  set_property(TARGET wonderbane_extension_combat_power_readiness_probe PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  # Private exact-image conformance; never linked into the runtime DLL.
  add_executable(wonderbane_extension_hostile_health_consumer_probe EXCLUDE_FROM_ALL hostile_health_consumer_probe.cpp)
  target_compile_features(wonderbane_extension_hostile_health_consumer_probe PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_hostile_health_consumer_probe PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_hostile_health_consumer_probe PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_hostile_health_consumer_probe PRIVATE bcrypt)
  set_property(TARGET wonderbane_extension_hostile_health_consumer_probe PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)

  add_executable(wonderbane_extension_combat_power_mode_probe EXCLUDE_FROM_ALL combat_power_mode_probe.cpp)
  target_compile_features(wonderbane_extension_combat_power_mode_probe PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_combat_power_mode_probe PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_combat_power_mode_probe PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_combat_power_mode_probe PRIVATE bcrypt)
  set_property(TARGET wonderbane_extension_combat_power_mode_probe PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_combat_target_policy_test combat_target_policy_test.cpp combat_target_policy.cpp)
  target_compile_features(wonderbane_extension_combat_target_policy_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_combat_target_policy_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_combat_target_policy_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_combat_target_policy_test PRIVATE user32)
  add_test(NAME wonderbane_extension_combat_target_policy COMMAND wonderbane_extension_combat_target_policy_test)
  set_tests_properties(wonderbane_extension_combat_target_policy PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_combat_v2_wire_test combat_v2_wire_test.cpp)
  target_compile_features(wonderbane_extension_combat_v2_wire_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_combat_v2_wire_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_combat_v2_wire_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_combat_v2_wire_test PRIVATE bcrypt)
  add_test(NAME wonderbane_extension_combat_v2_wire COMMAND wonderbane_extension_combat_v2_wire_test
    "${CMAKE_CURRENT_SOURCE_DIR}/../../tests/fixtures/combat_command_v2.hex"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../tests/fixtures/combat_fence_v3.hex"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../tests/fixtures/combat_receipt_v2.hex")
  set_tests_properties(wonderbane_extension_combat_v2_wire PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_combat_v2_controller_test combat_v2_controller_test.cpp)
  target_compile_features(wonderbane_extension_combat_v2_controller_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_combat_v2_controller_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_combat_v2_controller_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_combat_v2_controller_test PRIVATE bcrypt)
  add_test(NAME wonderbane_extension_combat_v2_controller COMMAND wonderbane_extension_combat_v2_controller_test)
  set_tests_properties(wonderbane_extension_combat_v2_controller PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_combat_v3_fence_test combat_v3_fence_test.cpp)
  target_compile_features(wonderbane_extension_combat_v3_fence_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_combat_v3_fence_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_combat_v3_fence_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_combat_v3_fence_test PRIVATE bcrypt)
  add_test(NAME wonderbane_extension_combat_v3_fence COMMAND wonderbane_extension_combat_v3_fence_test
    "${CMAKE_CURRENT_SOURCE_DIR}/../../tests/fixtures/combat_fence_v3.hex")
  set_tests_properties(wonderbane_extension_combat_v3_fence PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_combat_v2_native_test combat_v2_native_test.cpp combat_v2_native.cpp combat_target_policy.cpp)
  target_compile_features(wonderbane_extension_combat_v2_native_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_combat_v2_native_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_combat_v2_native_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_combat_v2_native_test PRIVATE bcrypt user32)
  add_test(NAME wonderbane_extension_combat_v2_native COMMAND wonderbane_extension_combat_v2_native_test)
  set_tests_properties(wonderbane_extension_combat_v2_native PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_combat_v2_runtime_test combat_v2_runtime_test.cpp)
  target_compile_features(wonderbane_extension_combat_v2_runtime_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_combat_v2_runtime_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_combat_v2_runtime_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_combat_v2_runtime_test PRIVATE bcrypt user32)
  add_test(NAME wonderbane_extension_combat_v2_runtime COMMAND wonderbane_extension_combat_v2_runtime_test)
  set_tests_properties(wonderbane_extension_combat_v2_runtime PROPERTIES TIMEOUT 15)
endif()

# Shared native item entry; the test includes its implementation for fault injection.
if(BUILD_TESTING)
  add_executable(wonderbane_extension_combat_item_entry_test combat_item_entry_test.cpp combat_activation_observer.cpp)
  target_link_libraries(wonderbane_extension_combat_item_entry_test PRIVATE bcrypt)
  target_compile_features(wonderbane_extension_combat_item_entry_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_combat_item_entry_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_combat_item_entry_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  add_test(NAME wonderbane_extension_combat_item_entry COMMAND wonderbane_extension_combat_item_entry_test)
  add_executable(wonderbane_extension_combat_activation_lifecycle_test combat_activation_lifecycle_test.cpp)
  target_compile_features(wonderbane_extension_combat_activation_lifecycle_test PRIVATE cxx_std_20)
  target_compile_options(wonderbane_extension_combat_activation_lifecycle_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  add_test(NAME wonderbane_extension_combat_activation_lifecycle COMMAND wonderbane_extension_combat_activation_lifecycle_test)
  add_executable(wonderbane_extension_combat_activation_observer_test combat_activation_observer_test.cpp)
  target_compile_features(wonderbane_extension_combat_activation_observer_test PRIVATE cxx_std_20)
  target_compile_options(wonderbane_extension_combat_activation_observer_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_combat_activation_observer_test PRIVATE bcrypt)
  add_test(NAME wonderbane_extension_combat_activation_observer COMMAND wonderbane_extension_combat_activation_observer_test)
  foreach(boundary incoming completion)
    add_executable(wonderbane_extension_combat_activation_${boundary}_probe EXCLUDE_FROM_ALL combat_activation_${boundary}_probe.cpp)
    target_compile_features(wonderbane_extension_combat_activation_${boundary}_probe PRIVATE cxx_std_20)
    target_compile_options(wonderbane_extension_combat_activation_${boundary}_probe PRIVATE /W4 /WX /EHsc)
    target_link_libraries(wonderbane_extension_combat_activation_${boundary}_probe PRIVATE bcrypt)
    target_link_options(wonderbane_extension_combat_activation_${boundary}_probe PRIVATE /SAFESEH:NO)
    set_property(TARGET wonderbane_extension_combat_activation_${boundary}_probe PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  endforeach()
  set_tests_properties(wonderbane_extension_combat_item_entry PROPERTIES TIMEOUT 15)
  add_executable(wonderbane_extension_combat_power_special_probe EXCLUDE_FROM_ALL combat_power_special_probe.cpp)
  target_compile_features(wonderbane_extension_combat_power_special_probe PRIVATE cxx_std_20)
  target_compile_options(wonderbane_extension_combat_power_special_probe PRIVATE /W4 /WX /EHsc)
  target_link_libraries(wonderbane_extension_combat_power_special_probe PRIVATE bcrypt)
  target_link_options(wonderbane_extension_combat_power_special_probe PRIVATE /SAFESEH:NO)
  set_property(TARGET wonderbane_extension_combat_power_special_probe PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_combat_item_probe EXCLUDE_FROM_ALL combat_item_probe.cpp combat_activation_observer.cpp)
  target_compile_features(wonderbane_extension_combat_item_probe PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_combat_item_probe PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_combat_item_probe PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_combat_item_probe PRIVATE bcrypt)
  set_property(TARGET wonderbane_extension_combat_item_probe PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_actor_effects_native_test actor_effects_native_test.cpp)
  add_executable(wonderbane_extension_actor_effects_native_probe EXCLUDE_FROM_ALL actor_effects_native_probe.cpp)
  foreach(target wonderbane_extension_actor_effects_native_test wonderbane_extension_actor_effects_native_probe)
    target_compile_features(${target} PRIVATE cxx_std_20)
    target_compile_definitions(${target} PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
    target_compile_options(${target} PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  endforeach()
  target_link_libraries(wonderbane_extension_actor_effects_native_probe PRIVATE bcrypt)
  set_property(TARGET wonderbane_extension_actor_effects_native_probe PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  add_test(NAME wonderbane_extension_actor_effects_native COMMAND wonderbane_extension_actor_effects_native_test)
  foreach(mode partial cpp saturation prepared14 prepared15)
    add_test(NAME wonderbane_extension_actor_effects_native_${mode} COMMAND wonderbane_extension_actor_effects_native_test ${mode})
    set_tests_properties(wonderbane_extension_actor_effects_native_${mode} PROPERTIES TIMEOUT 15)
  endforeach()
  set_tests_properties(wonderbane_extension_actor_effects_native PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_actor_application_journal_test actor_application_journal_test.cpp)
  target_compile_features(wonderbane_extension_actor_application_journal_test PRIVATE cxx_std_20)
  target_compile_options(wonderbane_extension_actor_application_journal_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  add_test(NAME wonderbane_extension_actor_application_journal COMMAND wonderbane_extension_actor_application_journal_test)
  set_tests_properties(wonderbane_extension_actor_application_journal PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_actor_inventory_native_test actor_inventory_native_test.cpp)
  add_executable(wonderbane_extension_actor_inventory_native_probe EXCLUDE_FROM_ALL actor_inventory_native_probe.cpp)
  foreach(target wonderbane_extension_actor_inventory_native_test wonderbane_extension_actor_inventory_native_probe)
    target_compile_features(${target} PRIVATE cxx_std_20)
    target_compile_definitions(${target} PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
    target_compile_options(${target} PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  endforeach()
  target_link_libraries(wonderbane_extension_actor_inventory_native_probe PRIVATE bcrypt)
  set_property(TARGET wonderbane_extension_actor_inventory_native_probe PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  add_test(NAME wonderbane_extension_actor_inventory_native COMMAND wonderbane_extension_actor_inventory_native_test)
  set_tests_properties(wonderbane_extension_actor_inventory_native PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_actor_selector_manifest_test actor_selector_manifest_test.cpp)
  target_compile_features(wonderbane_extension_actor_selector_manifest_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_actor_selector_manifest_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_actor_selector_manifest_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_actor_selector_manifest_test PRIVATE bcrypt)
  add_test(NAME wonderbane_extension_actor_selector_manifest COMMAND wonderbane_extension_actor_selector_manifest_test "${CMAKE_CURRENT_SOURCE_DIR}/../../tests/fixtures/actor_selector_manifest_v1.hex")
  set_tests_properties(wonderbane_extension_actor_selector_manifest PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_actor_action_wire_test actor_action_wire_test.cpp)
  target_compile_features(wonderbane_extension_actor_action_wire_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_actor_action_wire_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_actor_action_wire_test PRIVATE /W4 /WX /permissive- /sdl /utf-8 /UNDEBUG)
  target_link_libraries(wonderbane_extension_actor_action_wire_test PRIVATE bcrypt)
  add_test(NAME wonderbane_extension_actor_action_wire COMMAND wonderbane_extension_actor_action_wire_test
    "${CMAKE_CURRENT_SOURCE_DIR}/../../tests/fixtures/actor_owner_v4.hex"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../tests/fixtures/actor_context_v4.hex"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../tests/fixtures/actor_command_v3.hex"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../tests/fixtures/actor_receipt_v3.hex")
  set_tests_properties(wonderbane_extension_actor_action_wire PROPERTIES TIMEOUT 15)

  add_executable(wonderbane_extension_actor_buff_observation_test actor_buff_observation_test.cpp)
  add_executable(wonderbane_extension_actor_buff_observation_probe EXCLUDE_FROM_ALL actor_buff_observation_probe.cpp)
  foreach(target wonderbane_extension_actor_buff_observation_test wonderbane_extension_actor_buff_observation_probe)
    target_compile_features(${target} PRIVATE cxx_std_20)
    target_compile_definitions(${target} PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
    target_compile_options(${target} PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  endforeach()
  target_link_libraries(wonderbane_extension_actor_buff_observation_probe PRIVATE bcrypt)
  set_property(TARGET wonderbane_extension_actor_buff_observation_probe PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  add_test(NAME wonderbane_extension_actor_buff_observation COMMAND wonderbane_extension_actor_buff_observation_test)
  set_tests_properties(wonderbane_extension_actor_buff_observation PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_actor_action_controller_test actor_action_controller_test.cpp)
  target_compile_features(wonderbane_extension_actor_action_controller_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_actor_action_controller_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_actor_action_controller_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_actor_action_controller_test PRIVATE bcrypt)
  add_test(NAME wonderbane_extension_actor_action_controller COMMAND wonderbane_extension_actor_action_controller_test
    "${CMAKE_CURRENT_SOURCE_DIR}/../../tests/fixtures/actor_command_v3.hex"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../tests/fixtures/actor_context_v4.hex")
  set_tests_properties(wonderbane_extension_actor_action_controller PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_actor_action_native_test actor_action_native_test.cpp actor_action_native.cpp combat_target_policy.cpp)
  target_compile_features(wonderbane_extension_actor_action_native_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_actor_action_native_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_actor_action_native_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_actor_action_native_test PRIVATE bcrypt user32)
  add_test(NAME wonderbane_extension_actor_action_native COMMAND wonderbane_extension_actor_action_native_test)
  set_tests_properties(wonderbane_extension_actor_action_native PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_actor_publication_test actor_publication_test.cpp)
  target_compile_features(wonderbane_extension_actor_publication_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_actor_publication_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_actor_publication_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_actor_publication_test PRIVATE bcrypt advapi32)
  add_test(NAME wonderbane_extension_actor_publication COMMAND wonderbane_extension_actor_publication_test)
  set_tests_properties(wonderbane_extension_actor_publication PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_actor_action_runtime_test actor_action_runtime_test.cpp)
  target_compile_features(wonderbane_extension_actor_action_runtime_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_actor_action_runtime_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_actor_action_runtime_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_actor_action_runtime_test PRIVATE bcrypt advapi32)
  add_test(NAME wonderbane_extension_actor_action_runtime COMMAND wonderbane_extension_actor_action_runtime_test)
  set_tests_properties(wonderbane_extension_actor_action_runtime PROPERTIES TIMEOUT 15)
endif()

if(BUILD_TESTING)
  add_executable(wonderbane_extension_item_application_trace_test item_application_trace_test.cpp)
  target_compile_features(wonderbane_extension_item_application_trace_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_item_application_trace_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_item_application_trace_test PRIVATE /W4 /WX /permissive- /sdl /utf-8)
  target_link_libraries(wonderbane_extension_item_application_trace_test PRIVATE advapi32 bcrypt)
  set_property(TARGET wonderbane_extension_item_application_trace_test PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)
  add_test(NAME wonderbane_extension_item_application_trace COMMAND wonderbane_extension_item_application_trace_test)
  foreach(step RANGE 1 6)
    add_test(NAME wonderbane_extension_item_trace_install_${step} COMMAND wonderbane_extension_item_application_trace_test ${step})
  endforeach()
endif()

add_executable(wonderbane_extension_item_application_trace_probe EXCLUDE_FROM_ALL item_application_trace_probe.cpp)
target_compile_features(wonderbane_extension_item_application_trace_probe PRIVATE cxx_std_20)
target_compile_definitions(wonderbane_extension_item_application_trace_probe PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
target_compile_options(wonderbane_extension_item_application_trace_probe PRIVATE /W4 /WX /permissive- /sdl /utf-8)
target_link_libraries(wonderbane_extension_item_application_trace_probe PRIVATE advapi32 bcrypt)
set_property(TARGET wonderbane_extension_item_application_trace_probe PROPERTY MSVC_RUNTIME_LIBRARY MultiThreaded)

if(BUILD_TESTING AND WONDERBANE_EXTENSION_PROFILE STREQUAL "full")
  add_executable(wonderbane_extension_weapon_appearance_test weapon_appearance_test.cpp)
  target_compile_features(wonderbane_extension_weapon_appearance_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_weapon_appearance_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_weapon_appearance_test PRIVATE /W4 /WX /permissive- /utf-8)
  set_property(TARGET wonderbane_extension_weapon_appearance_test PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
  add_test(NAME wonderbane_extension_weapon_appearance COMMAND wonderbane_extension_weapon_appearance_test)
endif()

if(BUILD_TESTING AND WONDERBANE_EXTENSION_PROFILE STREQUAL "full")
  add_executable(wonderbane_extension_moonfire_test moonfire_test.cpp moonfire.cpp scene_draw.cpp)
  target_compile_features(wonderbane_extension_moonfire_test PRIVATE cxx_std_20)
  target_compile_definitions(wonderbane_extension_moonfire_test PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT)
  target_compile_options(wonderbane_extension_moonfire_test PRIVATE /W4 /WX /permissive- /utf-8)
  target_link_libraries(wonderbane_extension_moonfire_test PRIVATE opengl32 gdi32 user32)
  set_property(TARGET wonderbane_extension_moonfire_test PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
  add_test(NAME wonderbane_extension_moonfire COMMAND wonderbane_extension_moonfire_test)
  add_test(NAME wonderbane_extension_moonfire_gdi COMMAND wonderbane_extension_moonfire_test --gdi)
endif()

if(BUILD_TESTING AND WONDERBANE_EXTENSION_PROFILE STREQUAL "full")
  add_executable(wonderbane_extension_visual_inspector_test visual_inspector_test.cpp)
  target_compile_features(wonderbane_extension_visual_inspector_test PRIVATE cxx_std_17)
  target_compile_definitions(wonderbane_extension_visual_inspector_test PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)
  set_property(TARGET wonderbane_extension_visual_inspector_test PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
  add_test(NAME wonderbane_extension_visual_inspector COMMAND wonderbane_extension_visual_inspector_test)
endif()
