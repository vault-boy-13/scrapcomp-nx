# Real GP/EP execution for the game, using separately fetched GPL sources.
set(DSP_DEPS "${CMAKE_CURRENT_SOURCE_DIR}/.deps/xemu-dsp/dsp")
if(NOT EXISTS "${DSP_DEPS}/interp/dsp_cpu.c")
    message(FATAL_ERROR "Run tools/fetch_xemu_dsp.py before configuring the game")
endif()
get_target_property(APU_SOURCES xbox_apu SOURCES)
list(FILTER APU_SOURCES EXCLUDE REGEX "(^|/)apu_dsp[.]c$")
set_property(TARGET xbox_apu PROPERTY SOURCES "${APU_SOURCES}")
target_sources(xbox_apu PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/src/audio/apu_dsp_real.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/audio/dsp_runtime.c"
    "${DSP_DEPS}/interp/dsp_cpu.c" "${DSP_DEPS}/dsp_dma.c")
target_include_directories(xbox_apu PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/src/audio" "${DSP_DEPS}"
    PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src/audio/shim")
target_compile_definitions(xbox_apu PUBLIC XBOXRECOMP_REAL_DSP=1)
if(MSVC)
    target_compile_options(xbox_apu PRIVATE /UNDEBUG /O2)
else()
    target_compile_options(xbox_apu PRIVATE -UNDEBUG -O2)
endif()
if(NOT NINTENDO_SWITCH)
    add_executable(host_dsp_probe "${CMAKE_CURRENT_SOURCE_DIR}/probes/host_dsp.c"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/audio/dsp_runtime.c"
        "${DSP_DEPS}/interp/dsp_cpu.c" "${DSP_DEPS}/dsp_dma.c")
    target_include_directories(host_dsp_probe PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src/audio"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/audio/shim" "${DSP_DEPS}")
    if(MSVC)
        target_compile_options(host_dsp_probe PRIVATE /UNDEBUG /O2 /D_CRT_SECURE_NO_WARNINGS)
    else()
        target_compile_options(host_dsp_probe PRIVATE -UNDEBUG -O2)
    endif()
endif()
