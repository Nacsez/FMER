# Selected audited MSFA engine; no upstream build scripts are executed.
set(MSFA_ROOT ${PROJECT_SOURCE_DIR}/third_party/msfa/src)
add_library(fmer_msfa STATIC
    ${MSFA_ROOT}/dx7note.cc ${MSFA_ROOT}/env.cc ${MSFA_ROOT}/exp2.cc
    ${MSFA_ROOT}/fm_core.cc ${MSFA_ROOT}/fm_op_kernel.cc ${MSFA_ROOT}/freqlut.cc
    ${MSFA_ROOT}/lfo.cc ${MSFA_ROOT}/pitchenv.cc ${MSFA_ROOT}/sin.cc
    ${MSFA_ROOT}/patch.cc)
target_include_directories(fmer_msfa PUBLIC ${MSFA_ROOT})
target_compile_definitions(fmer_msfa PRIVATE _USE_MATH_DEFINES)
target_compile_features(fmer_msfa PUBLIC cxx_std_17)

add_library(fmer_core STATIC patch.cpp performance.cpp multitrack.cpp pattern_edit.cpp synth.cpp storage.cpp effects.cpp factory_presets.cpp ble_midi.cpp)
target_include_directories(fmer_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(fmer_core PRIVATE fmer_msfa)
target_compile_features(fmer_core PUBLIC cxx_std_17)
if(MSVC)
    target_compile_options(fmer_core PRIVATE /W4 /permissive-)
else()
    target_compile_options(fmer_core PRIVATE -Wall -Wextra -Wpedantic)
endif()
