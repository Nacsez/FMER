# Host behavioral checks for the upstream units that differ from the vendor
# objects. These do not qualify pi32v2 code generation or target timing.
set(RUNTIME_ROOT "${PROJECT_SOURCE_DIR}/third_party/runtime")
set(NEWLIB "${RUNTIME_ROOT}/newlib/newlib")
set(BUILTINS "${RUNTIME_ROOT}/compiler-rt/lib/builtins")
add_library(runtime_memory OBJECT
    "${NEWLIB}/libc/string/memcmp.c" "${NEWLIB}/libc/string/memcpy.c"
    "${NEWLIB}/libc/string/memmove.c" "${NEWLIB}/libc/string/memset.c")
target_include_directories(runtime_memory PRIVATE shim "${NEWLIB}/libc/string")
target_compile_definitions(runtime_memory PRIVATE memcpy=fmer_test_memcpy
    memcmp=fmer_test_memcmp memmove=fmer_test_memmove memset=fmer_test_memset)
add_library(runtime_math OBJECT
    "${NEWLIB}/libm/math/e_rem_pio2.c" "${NEWLIB}/libm/math/ef_rem_pio2.c"
    "${NEWLIB}/libm/math/k_rem_pio2.c" "${NEWLIB}/libm/math/kf_rem_pio2.c")
target_include_directories(runtime_math PRIVATE shim "${NEWLIB}/libm/common")
target_compile_definitions(runtime_math PRIVATE __STDC__=1)
add_library(runtime_builtins OBJECT "${BUILTINS}/adddf3.c" "${BUILTINS}/subdf3.c"
    "${BUILTINS}/muldf3.c" "${BUILTINS}/divdf3.c" "${BUILTINS}/fixdfsi.c"
    "${BUILTINS}/floatsidf.c" "${BUILTINS}/udivdi3.c" "${BUILTINS}/udivmoddi4.c"
    "${BUILTINS}/umoddi3.c")
if(MSVC)
    target_compile_options(runtime_memory PRIVATE /FI_ansi.h /Oi-)
    target_compile_options(runtime_math PRIVATE /FI_ansi.h /fp:strict)
    target_compile_options(runtime_builtins PRIVATE /fp:strict)
else()
    target_compile_options(runtime_memory PRIVATE -include _ansi.h -fno-builtin)
    target_compile_options(runtime_math PRIVATE -include _ansi.h -fno-strict-aliasing)
endif()
add_executable(runtime_behavior runtime_behavior.cpp
    $<TARGET_OBJECTS:runtime_memory> $<TARGET_OBJECTS:runtime_math>
    $<TARGET_OBJECTS:runtime_builtins>)
target_compile_features(runtime_behavior PRIVATE cxx_std_17)
add_test(NAME runtime.source_behavior COMMAND runtime_behavior)
set_tests_properties(runtime.source_behavior PROPERTIES TIMEOUT 60)
