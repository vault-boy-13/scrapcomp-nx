# Keep the CLI path relative when crossing Windows RTK -> MSYS2 CMake.
# The official devkitPro toolchain remains unchanged.
execute_process(COMMAND cygpath -u "$ENV{DEVKITPRO}"
    OUTPUT_VARIABLE _dkp_posix OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
set(ENV{DEVKITPRO} "${_dkp_posix}")
include("${_dkp_posix}/cmake/Switch.cmake")
# GCC is a native Windows executable. Its switch.specs expands DEVKITPRO
# internally, after MSYS argument conversion, and therefore needs a native path.
execute_process(COMMAND cygpath -m "${_dkp_posix}"
    OUTPUT_VARIABLE _dkp_native OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
set(ENV{DEVKITPRO} "${_dkp_native}")
