cmake_minimum_required(VERSION 3.20)
project(FMER VERSION 0.4.0 LANGUAGES CXX)

# Portable Windows host: keep the C/C++ runtime inside the executable.
if(MSVC)
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
endif()

if(CMAKE_CONFIGURATION_TYPES)
    message(STATUS "FMER multi-config generator: use --config when building; single-config hint is ${CMAKE_BUILD_TYPE}")
else()
    message(STATUS "FMER host build configuration: ${CMAKE_BUILD_TYPE}")
endif()

# Shared musical prototype: no board HAL, updater or hardware access.
set(CMAKE_CXX_EXTENSIONS OFF)
set(FMER_BUILD_ID "host-prototype-${PROJECT_VERSION}" CACHE STRING "Build identity")
if(FMER_BUILD_ID STREQUAL "workspace-scaffold-0.1.0" OR FMER_BUILD_ID STREQUAL "host-prototype-0.2.0" OR FMER_BUILD_ID STREQUAL "host-prototype-0.3.0")
    set(FMER_BUILD_ID "host-prototype-${PROJECT_VERSION}" CACHE STRING "Build identity" FORCE)
endif()
if(NOT FMER_BUILD_ID MATCHES "^[A-Za-z0-9._+-]+$")
    message(FATAL_ERROR "FMER_BUILD_ID must contain only letters, numbers, ., _, +, or -")
endif()

include(CTest)
if(BUILD_TESTING)
    enable_language(C)
    add_subdirectory(tests/runtime)
    add_executable(fx_audit tools/fx_audit.cpp)
    target_link_libraries(fx_audit PRIVATE fmer_core)
    find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
endif()

add_subdirectory(core)
add_subdirectory(host)

if(BUILD_TESTING)
    add_executable(synth_pcm_probe tests/synth_pcm_probe.cpp)
    target_link_libraries(synth_pcm_probe PRIVATE fmer_core)
    foreach(suite codec performance multitrack pattern_edit synth storage effects factory_presets ble_midi)
        add_executable(${suite}_tests tests/${suite}_tests.cpp)
        target_link_libraries(${suite}_tests PRIVATE fmer_core)
        add_test(NAME core.${suite} COMMAND ${suite}_tests)
        set_tests_properties(core.${suite} PROPERTIES TIMEOUT 60)
    endforeach()
    target_compile_definitions(codec_tests PRIVATE FMER_CODEC_MSFA_REFERENCE=1)
    target_link_libraries(codec_tests PRIVATE fmer_msfa)
    # Exercise the actual 8-pattern target representation against the same
    # behavior suite; desktop 16-pattern capacity remains independently tested.
    add_executable(fm1_performance_tests tests/performance_tests.cpp core/performance.cpp)
    target_compile_definitions(fm1_performance_tests PRIVATE FMER_DEVICE)
    target_compile_features(fm1_performance_tests PRIVATE cxx_std_17)
    add_test(NAME target.performance_capacity COMMAND fm1_performance_tests)
    add_executable(board_adapter_tests tests/board_adapter_tests.cpp firmware/fm1/dsp_adapter.cpp)
    add_executable(fm1_multitrack_adapter_tests tests/fm1_multitrack_adapter_tests.cpp firmware/fm1/dsp_adapter.cpp)
    target_link_libraries(fm1_multitrack_adapter_tests PRIVATE fmer_core)
    add_test(NAME target.multitrack_adapter_host COMMAND fm1_multitrack_adapter_tests)
    set_tests_properties(target.multitrack_adapter_host PROPERTIES TIMEOUT 60)
    add_executable(fm1_midi_tests tests/fm1_midi_tests.cpp firmware/fm1/dsp_adapter.cpp)
    target_link_libraries(fm1_midi_tests PRIVATE fmer_core)
    add_test(NAME target.midi_host COMMAND fm1_midi_tests)
    set_tests_properties(target.midi_host PROPERTIES TIMEOUT 60)
    set(FMER_MIDI_IO_DIR "${CMAKE_CURRENT_BINARY_DIR}/midi-io-probe")
    add_custom_command(OUTPUT "${FMER_MIDI_IO_DIR}/midi_io.inc"
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/extract_fm1_midi.py"
                "${CMAKE_CURRENT_SOURCE_DIR}" "${FMER_MIDI_IO_DIR}/midi_io.inc"
        DEPENDS firmware/fm1/board.c tools/build_fm1_candidate.py tests/extract_fm1_midi.py VERBATIM)
    add_executable(fm1_midi_io_tests tests/fm1_midi_io_tests.cpp "${FMER_MIDI_IO_DIR}/midi_io.inc")
    target_include_directories(fm1_midi_io_tests PRIVATE "${FMER_MIDI_IO_DIR}")
    target_compile_features(fm1_midi_io_tests PRIVATE cxx_std_17)
    add_test(NAME target.midi_io_host COMMAND fm1_midi_io_tests)
    target_link_libraries(board_adapter_tests PRIVATE fmer_core)
    add_test(NAME target.adapter_host COMMAND board_adapter_tests)
    set_tests_properties(target.adapter_host PROPERTIES TIMEOUT 60)
    add_executable(fm1_ui_tests tests/fm1_ui_tests.cpp)
    target_compile_features(fm1_ui_tests PRIVATE cxx_std_17)
    # Documentation uses the production LCD renderer and the existing offline HAL mock.
    add_executable(fmer_feature_capture tools/feature_capture.cpp)
    target_compile_features(fmer_feature_capture PRIVATE cxx_std_17)
    add_test(NAME target.ui_host COMMAND fm1_ui_tests)
    set_tests_properties(target.ui_host PROPERTIES TIMEOUT 60)
    add_executable(fm1_dispatch_tests tests/fm1_dispatch_tests.cpp)
    target_compile_features(fm1_dispatch_tests PRIVATE cxx_std_17)
    add_test(NAME target.dispatch_host COMMAND fm1_dispatch_tests)
    set_tests_properties(target.dispatch_host PROPERTIES TIMEOUT 60)
    add_executable(fm1_trace_tests tests/fm1_trace_tests.cpp)
    target_compile_features(fm1_trace_tests PRIVATE cxx_std_17)
    add_test(NAME target.trace_host COMMAND fm1_trace_tests)
    set_tests_properties(target.trace_host PROPERTIES TIMEOUT 60)
    add_executable(fm1_panel_tests tests/fm1_panel_tests.cpp)
    target_compile_features(fm1_panel_tests PRIVATE cxx_std_17)
    add_test(NAME target.panel_host COMMAND fm1_panel_tests)
    set_tests_properties(target.panel_host PROPERTIES TIMEOUT 60)
    add_executable(fm1_gesture_tests tests/fm1_gesture_tests.cpp)
    add_executable(fm1_encoder_tests tests/fm1_encoder_tests.cpp)
    target_compile_features(fm1_encoder_tests PRIVATE cxx_std_17)
    add_test(NAME target.encoder_host COMMAND fm1_encoder_tests)
    target_compile_features(fm1_gesture_tests PRIVATE cxx_std_17)
    add_test(NAME target.gesture_host COMMAND fm1_gesture_tests)
    set_tests_properties(target.gesture_host PROPERTIES TIMEOUT 60)
    add_executable(fm1_led_tests tests/fm1_led_tests.cpp)
    add_executable(fm1_battery_tests tests/fm1_battery_tests.cpp)
    add_executable(fm1_usb_link_tests tests/fm1_usb_link_tests.cpp)
    target_compile_features(fm1_usb_link_tests PRIVATE cxx_std_17)
    add_test(NAME target.usb_link_host COMMAND fm1_usb_link_tests)
    target_compile_features(fm1_battery_tests PRIVATE cxx_std_17)
    add_test(NAME target.battery_host COMMAND fm1_battery_tests)
    target_compile_features(fm1_led_tests PRIVATE cxx_std_17)
    add_test(NAME target.led_host COMMAND fm1_led_tests)
    set_tests_properties(target.led_host PROPERTIES TIMEOUT 60)
    add_executable(fm1_control_mailbox_tests tests/fm1_control_mailbox_tests.cpp firmware/fm1/dsp_adapter.cpp)
    target_link_libraries(fm1_control_mailbox_tests PRIVATE fmer_core)
    add_test(NAME target.control_mailbox_host COMMAND fm1_control_mailbox_tests)
    set_tests_properties(target.control_mailbox_host PROPERTIES TIMEOUT 60)
    add_executable(fm1_native_state_tests tests/fm1_native_state_tests.cpp)
    add_executable(fm1_preset_store_tests tests/fm1_preset_store_tests.cpp)
    add_executable(fm1_bank_store_tests tests/fm1_bank_store_tests.cpp firmware/fm1/dsp_adapter.cpp)
    target_link_libraries(fm1_bank_store_tests PRIVATE fmer_core)
    add_test(NAME target.bank_store_host COMMAND fm1_bank_store_tests)
    set_tests_properties(target.bank_store_host PROPERTIES TIMEOUT 120)
    target_compile_features(fm1_preset_store_tests PRIVATE cxx_std_17)
    add_test(NAME target.preset_store_host COMMAND fm1_preset_store_tests)
    set_tests_properties(target.preset_store_host PROPERTIES TIMEOUT 120)
    target_compile_features(fm1_native_state_tests PRIVATE cxx_std_17)
    add_test(NAME target.native_state_host COMMAND fm1_native_state_tests)
    set_tests_properties(target.native_state_host PROPERTIES TIMEOUT 60)
    set(FMER_NATIVE_BOARD_PROBE_DIR "${CMAKE_CURRENT_BINARY_DIR}/native-board-probe")
    add_custom_command(
        OUTPUT "${FMER_NATIVE_BOARD_PROBE_DIR}/fm1_native_board_block.inc"
               "${FMER_NATIVE_BOARD_PROBE_DIR}/fm1_native_pause.inc"
               "${FMER_NATIVE_BOARD_PROBE_DIR}/fm1_native_commit_guard.inc"
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/extract_fm1_native_board.py"
                "${CMAKE_CURRENT_SOURCE_DIR}/firmware/fm1/board.c"
                "${FMER_NATIVE_BOARD_PROBE_DIR}/fm1_native_board_block.inc"
        DEPENDS firmware/fm1/board.c tests/extract_fm1_native_board.py tests/extract_fm1_storage_board.py
        VERBATIM)
    add_executable(fm1_native_board_tests tests/fm1_native_board_tests.cpp firmware/fm1/dsp_adapter.cpp
                   "${FMER_NATIVE_BOARD_PROBE_DIR}/fm1_native_board_block.inc"
                   "${FMER_NATIVE_BOARD_PROBE_DIR}/fm1_native_pause.inc"
                   "${FMER_NATIVE_BOARD_PROBE_DIR}/fm1_native_commit_guard.inc")
    target_include_directories(fm1_native_board_tests PRIVATE "${FMER_NATIVE_BOARD_PROBE_DIR}")
    target_link_libraries(fm1_native_board_tests PRIVATE fmer_core)
    add_test(NAME target.native_board_host COMMAND fm1_native_board_tests)
    set_tests_properties(target.native_board_host PROPERTIES TIMEOUT 60)
    set(FMER_STORAGE_BOARD_DIR "${CMAKE_CURRENT_BINARY_DIR}/storage-board-probe")
    set(FMER_STORAGE_BOARD_PARTS
        "${FMER_STORAGE_BOARD_DIR}/storage_board_globals.inc"
        "${FMER_STORAGE_BOARD_DIR}/storage_board_pause.inc"
        "${FMER_STORAGE_BOARD_DIR}/storage_board_capture.inc"
        "${FMER_STORAGE_BOARD_DIR}/storage_board_import.inc")
    add_custom_command(OUTPUT ${FMER_STORAGE_BOARD_PARTS}
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/extract_fm1_storage_board.py"
                "${CMAKE_CURRENT_SOURCE_DIR}" "${FMER_STORAGE_BOARD_DIR}"
        DEPENDS firmware/fm1/board.c tests/extract_fm1_storage_board.py VERBATIM)
    add_executable(fm1_storage_board_tests tests/fm1_storage_board_tests.cpp
        firmware/fm1/dsp_adapter.cpp ${FMER_STORAGE_BOARD_PARTS})
    target_include_directories(fm1_storage_board_tests PRIVATE "${FMER_STORAGE_BOARD_DIR}")
    target_link_libraries(fm1_storage_board_tests PRIVATE fmer_core)
    add_test(NAME target.storage_board_host COMMAND fm1_storage_board_tests)
    set_tests_properties(target.storage_board_host PROPERTIES TIMEOUT 60)
endif()

