#pragma once

// Original FMER placement hints. No arithmetic, sample-rate or scheduling
// changes. The existing startup copies .ram_text before enabling interrupts;
// app.ld bounds the entire region to 24KiB, outside heap/display/stack storage.
// These DSP routines run only while flash is readable. Unlike flash-programming
// HAL routines, they may call XIP helpers and are not flash-busy-safe entrypoints.
#if defined(FMER_DEVICE) && !defined(_MSC_VER)
#define FMER_DSP_HOT __attribute__((section(".ram_text.dsp")))
#define FMER_SAMPLE_INLINE inline __attribute__((always_inline))
#elif defined(FMER_DEVICE)
#define FMER_DSP_HOT
#define FMER_SAMPLE_INLINE __forceinline
#else
#define FMER_DSP_HOT
#define FMER_SAMPLE_INLINE inline
#endif

// Supported by the pinned pi32v2 Clang compiler. Other host compilers retain
// ordinary loops; no vectorization or floating-point reassociation is enabled.
#if defined(FMER_DEVICE) && defined(__clang__)
#define FMER_FIXED_UNROLL _Pragma("clang loop unroll(full)")
#else
#define FMER_FIXED_UNROLL
#endif
