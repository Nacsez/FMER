/* Original FMER fixed-memory placement contract.
 * Mutable display/cache workspaces live after the startup arena and before
 * the stack guard. app.ld bounds them; fm1_cstart clears them before DSP/IRQs.
 * This relocates RAM; it does not turn mutable buffers into flash constants.
 * Never place constructors, initialized data, or audio-time allocations here.
 */
#ifndef FMER_MEMORY_LAYOUT_H
#define FMER_MEMORY_LAYOUT_H
#define FMER_STARTUP_ARENA_BYTES (288u * 1024u)
#if defined(FMER_DEVICE) && !defined(_MSC_VER)
#define FMER_WORKSPACE __attribute__((section(".workspace"), aligned(16)))
#else
#define FMER_WORKSPACE
#endif
#endif
