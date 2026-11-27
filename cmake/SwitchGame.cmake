include("${CMAKE_CURRENT_LIST_DIR}/RealDsp.cmake")

set(SCRAP_GENERATED_DIR "" CACHE STRING "Generated image directory with c/ and switch-strict/")
cmake_path(ABSOLUTE_PATH SCRAP_GENERATED_DIR BASE_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}" NORMALIZE)
if(NOT EXISTS "${SCRAP_GENERATED_DIR}/switch-strict/manifest.json")
    message(FATAL_ERROR "Run tools/workspace.ps1 build-game-switch")
endif()
set(SCRAP_SWITCH_C "${SCRAP_GENERATED_DIR}/switch-strict/c")
file(READ "${SCRAP_GENERATED_DIR}/codegen-manifest.json" SCRAP_CODEGEN_MANIFEST)
string(JSON SCRAP_FILE_COUNT LENGTH "${SCRAP_CODEGEN_MANIFEST}" files)
math(EXPR SCRAP_LAST_FILE "${SCRAP_FILE_COUNT} - 1")
foreach(index RANGE ${SCRAP_LAST_FILE})
    string(JSON source MEMBER "${SCRAP_CODEGEN_MANIFEST}" files ${index})
    if(source MATCHES "^recomp_.*[.]c$" AND NOT source STREQUAL "recomp_stubs_unresolved.c")
        list(APPEND SCRAP_SWITCH_GAME_SOURCES "${SCRAP_SWITCH_C}/${source}")
    endif()
endforeach()
if(NOT SCRAP_SWITCH_GAME_SOURCES)
    message(FATAL_ERROR "No generated Scrapland sources")
endif()

add_executable(scrapcomp_switch
    src/platform/switch/main.c
    src/platform/switch/diagnostics.c
    src/runtime/io_ports.c
    src/runtime/cache.c
    src/runtime/cpu_identity.c
    src/runtime/d3d_hooks.c
    src/runtime/pvideo.c
    "${SCRAP_GENERATED_DIR}/switch-strict/unresolved.c"
    ${SCRAP_SWITCH_GAME_SOURCES})
set_property(SOURCE ${SCRAP_SWITCH_GAME_SOURCES} APPEND PROPERTY
    COMPILE_OPTIONS -fno-strict-aliasing -fwrapv -ffp-contract=off)
option(SCRAP_SWITCH_TRACE_XPP "Trace the Scrapland USB completion and error paths" OFF)
if(SCRAP_SWITCH_TRACE_XPP)
    set_property(SOURCE "${SCRAP_SWITCH_C}/recomp_0083.c" "${SCRAP_SWITCH_C}/recomp_0084.c"
        APPEND PROPERTY COMPILE_OPTIONS -finstrument-functions
            -finstrument-functions-exclude-file-list=recomp_types.h,recomp_funcs.h)
    set_property(SOURCE src/platform/switch/diagnostics.c APPEND PROPERTY
        COMPILE_DEFINITIONS SCRAP_SWITCH_TRACE_XPP)
endif()
target_include_directories(scrapcomp_switch PRIVATE
    "${SCRAP_GENERATED_DIR}/switch-strict" "${SCRAP_SWITCH_C}")
set_property(SOURCE src/platform/switch/main.c APPEND PROPERTY INCLUDE_DIRECTORIES "${XR}/src/apu")
target_link_options(scrapcomp_switch PRIVATE "-Wl,-Map,${CMAKE_BINARY_DIR}/scrapcomp_switch.map")
target_link_libraries(scrapcomp_switch PRIVATE xboxrecomp EGL glapi drm_nouveau nx m)
nx_generate_nacp(OUTPUT "${CMAKE_BINARY_DIR}/scrapcomp_switch.nacp"
    NAME "Scrapland (Xbox recomp)" AUTHOR "scrapcomp-nx contributors" VERSION "0.1.0")
nx_create_nro(scrapcomp_switch NACP "${CMAKE_BINARY_DIR}/scrapcomp_switch.nacp")
