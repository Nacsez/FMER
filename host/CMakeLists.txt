add_executable(fmer_host main.cpp render.cpp patch_tool.cpp)
target_link_libraries(fmer_host PRIVATE fmer_core)
target_compile_definitions(fmer_host PRIVATE
    FMER_VERSION="${PROJECT_VERSION}"
    FMER_BUILD_ID="${FMER_BUILD_ID}"
    FMER_COMPILER_ID="${CMAKE_CXX_COMPILER_ID}"
    FMER_COMPILER_VERSION="${CMAKE_CXX_COMPILER_VERSION}"
    FMER_BUILD_CONFIG="$<CONFIG>"
)
if(MSVC)
    target_compile_options(fmer_host PRIVATE /W4 /permissive-)
else()
    target_compile_options(fmer_host PRIVATE -Wall -Wextra -Wpedantic)
endif()

if(BUILD_TESTING)
    add_test(NAME host.diagnostics
        COMMAND "${Python3_EXECUTABLE}" -B "${PROJECT_SOURCE_DIR}/tools/dev.py"
            verify-host "$<TARGET_FILE:fmer_host>")
    set_tests_properties(host.diagnostics PROPERTIES TIMEOUT 15)
    add_test(NAME host.integration
        COMMAND "${Python3_EXECUTABLE}" -B "${PROJECT_SOURCE_DIR}/tests/host_integration.py"
            "$<TARGET_FILE:fmer_host>")
    set_tests_properties(host.integration PROPERTIES TIMEOUT 90)
    add_test(NAME host.library
        COMMAND "${CMAKE_COMMAND}" -E env "FMER_HOST_EXE=$<TARGET_FILE:fmer_host>"
            "${Python3_EXECUTABLE}" -B -m unittest discover
            -s "${PROJECT_SOURCE_DIR}/tests" -p test_library.py -v)
    set_tests_properties(host.library PROPERTIES TIMEOUT 90)
    add_test(NAME host.companion
        COMMAND "${CMAKE_COMMAND}" -E env "FMER_HOST_EXE=$<TARGET_FILE:fmer_host>"
            "${Python3_EXECUTABLE}" -B -m unittest discover
            -s "${PROJECT_SOURCE_DIR}/tests" -p test_companion.py -v)
    # Includes full128-slot native10 migration, resets and actual renderer probes.
    set_tests_properties(host.companion PROPERTIES TIMEOUT 180)
endif()
