// Bounded startup arena. Musical processing never allocates. No target frees
// are expected because the two audio-owner objects live for the entire boot.
#include <stddef.h>
#include <stdint.h>
#include <new>
#include "memory_layout.h"
alignas(16) static unsigned char arena[FMER_STARTUP_ARENA_BYTES] __attribute__((section(".pool")));
static size_t used;
extern "C" void* malloc(size_t size) {
    if (size > sizeof(arena) - 15) return nullptr;
    size = (size + 15) & ~size_t(15);
    if (size > sizeof(arena) - used) return nullptr;
    void* result = arena + used; used += size; return result;
}
extern "C" void free(void*) {}
void* operator new(size_t size) {
    void* result = malloc(size);
    if (!result) for (;;) {} // watchdog resets before the audio path is enabled
    return result;
}
void* operator new[](size_t size) { return ::operator new(size); }
void operator delete(void* p) noexcept { free(p); }
void operator delete[](void* p) noexcept { free(p); }
void operator delete(void* p, size_t) noexcept { free(p); }
void operator delete[](void* p, size_t) noexcept { free(p); }
extern "C" uint32_t fmer_heap_used(void) { return static_cast<uint32_t>(used); }
extern "C" void __cxa_pure_virtual(void) { for (;;) {} }
