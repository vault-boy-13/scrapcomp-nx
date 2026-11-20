cmake_minimum_required(VERSION 3.22)
project(scrapcomp-nx LANGUAGES C CXX)
if(MSVC AND CMAKE_GENERATOR MATCHES "Ninja")
    # CMake's compiler-ID detection can misdecode UTF-8 localized MSVC output.
    # Probe actual /showIncludes bytes with an explicit encoding; otherwise
    # Ninja accepts object files with zero header dependencies.
    set(include_probe "${CMAKE_BINARY_DIR}/msvc-include-probe.c")
    file(WRITE "${include_probe}" "#include <stddef.h>\n")
    execute_process(COMMAND "${CMAKE_C_COMPILER}" /nologo /Zs /showIncludes "${include_probe}"
        OUTPUT_VARIABLE include_output ERROR_VARIABLE include_error
        RESULT_VARIABLE include_status ENCODING UTF-8)
    string(REGEX MATCH "[\r\n]([^\r\n]+:)[ \t]+[A-Za-z]:[/\\\\]" include_match "${include_output}")
    if(NOT include_status EQUAL 0 OR NOT include_match)
        message(FATAL_ERROR "Cannot determine MSVC include dependency prefix: ${include_output}${include_error}")
    endif()
    set(CMAKE_CL_SHOWINCLUDES_PREFIX "${CMAKE_MATCH_1}")
endif()
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(XR "${CMAKE_CURRENT_SOURCE_DIR}/runtime/xboxrecomp")
if(NOT EXISTS "${XR}/CMakeLists.txt")
    message(FATAL_ERROR "Run tools/workspace.ps1 prepare first")
endif()

# Compile the actual pinned runtime, not substitute implementations. This is
# build validation only; it does not pretend to boot the Scrapland executable.
add_subdirectory("${XR}" "${CMAKE_BINARY_DIR}/xboxrecomp" EXCLUDE_FROM_ALL)
add_custom_target(runtime_check ALL DEPENDS xbox_kernel xbox_apu xbox_usb xbox_d3d8 xbox_nv2a)

if(NINTENDO_SWITCH)
    add_dependencies(runtime_check xbox_nv2a_gl)
    foreach(probe runtime_probe deko_probe gl_probe)
        add_executable(${probe} "probes/${probe}.c")
        target_compile_options(${probe} PRIVATE -Wall -Wextra -g -O2)
        target_link_options(${probe} PRIVATE "-Wl,-Map,${CMAKE_BINARY_DIR}/${probe}.map")
        nx_generate_nacp(OUTPUT "${CMAKE_BINARY_DIR}/${probe}.nacp"
            NAME "scrapcomp-nx: ${probe}" AUTHOR "scrapcomp-nx contributors" VERSION "0.1.0")
    endforeach()
    target_link_libraries(runtime_probe PRIVATE nx pthread m)
    target_link_libraries(deko_probe PRIVATE deko3dd nx m)
    target_link_libraries(gl_probe PRIVATE glad EGL glapi drm_nouveau stdc++ nx m)
    target_include_directories(gl_probe PRIVATE "${DEVKITPRO}/portlibs/switch/include")
    set(PROBE_ROMFS "${CMAKE_BINARY_DIR}/probe-romfs")
    file(MAKE_DIRECTORY "${PROBE_ROMFS}/shaders")
    foreach(stage vert frag)
        set(shader "${PROBE_ROMFS}/shaders/triangle.${stage}.dksh")
        add_custom_command(OUTPUT "${shader}"
            COMMAND "${NX_UAM_EXE}" -s ${stage} -o "${shader}" "${CMAKE_CURRENT_SOURCE_DIR}/probes/shaders/triangle.${stage}"
            DEPENDS "probes/shaders/triangle.${stage}" VERBATIM)
        list(APPEND PROBE_SHADERS "${shader}")
    endforeach()
    add_custom_target(probe_shaders DEPENDS ${PROBE_SHADERS})
    add_dependencies(deko_probe probe_shaders)
    nx_create_nro(runtime_probe NACP "${CMAKE_BINARY_DIR}/runtime_probe.nacp")
    nx_create_nro(gl_probe NACP "${CMAKE_BINARY_DIR}/gl_probe.nacp")
    nx_create_nro(deko_probe NACP "${CMAKE_BINARY_DIR}/deko_probe.nacp" ROMFS "${PROBE_ROMFS}")
else()
    option(SCRAP_BUILD_GAME_HOST "Build the diagnostic Windows game host" OFF)
    if(SCRAP_BUILD_GAME_HOST)
        include(cmake/RealDsp.cmake)
    endif()
    if(EXISTS "${CMAKE_BINARY_DIR}/cpu-tests/interrupt_functions.c")
        add_executable(host_interrupt_probe probes/host_interrupt.c src/platform/host/thread_hooks.c
            "${CMAKE_BINARY_DIR}/cpu-tests/interrupt_functions.c")
        target_include_directories(host_interrupt_probe PRIVATE "${XR}/templates/runtime")
        target_link_libraries(host_interrupt_probe PRIVATE xboxrecomp)
    endif()
    add_executable(host_numeric_probe probes/host_numeric.c)
    if(WIN32)
        add_executable(host_pvideo_probe probes/host_pvideo.c src/runtime/pvideo.c)
    endif()
    add_executable(host_d3d_hooks_probe probes/host_d3d_hooks.c src/runtime/d3d_hooks.c
        src/platform/host/thread_hooks.c)
    target_include_directories(host_d3d_hooks_probe PRIVATE "${XR}/templates/runtime")
    target_link_libraries(host_d3d_hooks_probe PRIVATE xboxrecomp)
    target_include_directories(host_numeric_probe PRIVATE "${XR}/templates/runtime")
    if(MSVC)
        target_compile_options(host_numeric_probe PRIVATE /O2 /we4013)
    endif()
    if(SCRAP_BUILD_GAME_HOST)
        add_executable(host_sampler probes/host_sampler.c)
        target_link_libraries(host_sampler PRIVATE dbghelp)
        find_package(SDL2 CONFIG REQUIRED)
        if(NOT WIN32)
            message(FATAL_ERROR "The initial game harness currently targets Windows")
        endif()
        set(SCRAP_GENERATED_DIR "" CACHE PATH "Generated image directory with c/ and host-strict/")
        if(NOT EXISTS "${SCRAP_GENERATED_DIR}/host-strict/manifest.json")
            message(FATAL_ERROR "Run tools/game_host.py prepare first")
        endif()
        file(GLOB SCRAP_GAME_SOURCES CONFIGURE_DEPENDS "${SCRAP_GENERATED_DIR}/c/recomp_*.c")
        list(FILTER SCRAP_GAME_SOURCES EXCLUDE REGEX "recomp_stubs_unresolved[.]c$")
        add_executable(scrapcomp_host src/platform/host/main.c src/platform/host/diagnostics.c
            src/platform/host/thread_hooks.c src/platform/host/graphics.c
            src/platform/host/audio.c src/platform/host/audio_capture.c
            src/platform/host/renderdoc_capture.c
            src/runtime/io_ports.c
            src/runtime/cache.c
            src/runtime/cpu_identity.c
            src/runtime/d3d_hooks.c
            src/runtime/pvideo.c
            "${SCRAP_GENERATED_DIR}/host-strict/unresolved.c" ${SCRAP_GAME_SOURCES})
        target_include_directories(scrapcomp_host PRIVATE
            "${SCRAP_GENERATED_DIR}/host-strict" "${SCRAP_GENERATED_DIR}/c")
        set(SCRAP_RENDERDOC_INCLUDE_DIR "" CACHE PATH "Optional installed RenderDoc application API header directory")
        if(EXISTS "${SCRAP_RENDERDOC_INCLUDE_DIR}/renderdoc_app.h")
            set_property(SOURCE src/platform/host/renderdoc_capture.c APPEND PROPERTY
                INCLUDE_DIRECTORIES "${SCRAP_RENDERDOC_INCLUDE_DIR}")
            set_property(SOURCE src/platform/host/renderdoc_capture.c APPEND PROPERTY
                COMPILE_DEFINITIONS SCRAP_HOST_RENDERDOC=1)
        endif()
        target_link_libraries(scrapcomp_host PRIVATE xboxrecomp dbghelp)
        add_custom_command(TARGET scrapcomp_host POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different "$<TARGET_FILE:SDL2::SDL2>"
                "$<TARGET_FILE_DIR:scrapcomp_host>" VERBATIM)
        if(MSVC)
            target_compile_options(scrapcomp_host PRIVATE /bigobj /Od /Z7 /wd4244 /wd4309
                /we4013 /we4133)
            # The lifted XMV decoder cannot feed its next audio packet in time
            # at /Od. Locate its translation unit by a stable guest function,
            # rather than a generated chunk number. Keep precise FP semantics.
            set(SCRAP_XMV_UNITS 0)
            foreach(source IN LISTS SCRAP_GAME_SOURCES)
                file(STRINGS "${source}" SCRAP_XMV_ENTRY
                    REGEX "^void sub_0030EDC7_gen\\(void\\)")
                if(SCRAP_XMV_ENTRY)
                    set_property(SOURCE "${source}" APPEND PROPERTY COMPILE_OPTIONS /O2 /fp:strict)
                    math(EXPR SCRAP_XMV_UNITS "${SCRAP_XMV_UNITS} + 1")
                    message(STATUS "Optimized guest XMV translation unit: ${source}")
                endif()
            endforeach()
            if(NOT SCRAP_XMV_UNITS EQUAL 1)
                message(FATAL_ERROR "Expected exactly one generated XMV decoder translation unit")
            endif()
            target_compile_definitions(scrapcomp_host PRIVATE _CRT_SECURE_NO_WARNINGS)
            target_link_options(scrapcomp_host PRIVATE /DEBUG /INCREMENTAL:NO /STACK:16777216)
        endif()
    endif()
    add_executable(workspace_probe probes/host_probe.c)
    target_include_directories(workspace_probe PRIVATE "${XR}/src/d3d")
    target_link_libraries(workspace_probe PRIVATE xbox_d3d8)
    # Build the BLACK lineage's tools without its game hooks or runtime.
    set(ZYDIS_BUILD_TOOLS OFF CACHE BOOL "" FORCE)
    set(ZYDIS_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
    set(ZYDIS_BUILD_DOXYGEN OFF CACHE BOOL "" FORCE)
    add_subdirectory(.deps/zydis "${CMAKE_BINARY_DIR}/zydis" EXCLUDE_FROM_ALL)
    add_subdirectory(.deps/tomlplusplus "${CMAKE_BINARY_DIR}/tomlplusplus" EXCLUDE_FROM_ALL)
    set(HLE_SDK "${CMAKE_CURRENT_SOURCE_DIR}/.deps/XboxXBE-Recomp")
    file(GLOB RECOMP_TOOL_SOURCES CONFIGURE_DEPENDS "${HLE_SDK}/tools/recomp/*.cpp")
    add_executable(xbe_recomp ${RECOMP_TOOL_SOURCES})
    add_executable(xbe_symbols "${HLE_SDK}/tools/symbols/main.cpp")
    foreach(tool xbe_recomp xbe_symbols)
        target_include_directories(${tool} PRIVATE "${HLE_SDK}/runtime" "${HLE_SDK}/tools/recomp")
        target_compile_definitions(${tool} PRIVATE _CRT_SECURE_NO_WARNINGS)
        target_link_libraries(${tool} PRIVATE Zydis tomlplusplus::tomlplusplus)
    endforeach()
endif()
