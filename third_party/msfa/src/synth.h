/*
 * Copyright 2012 Google Inc.
 * 
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 * 
 *      http://www.apache.org/licenses/LICENSE-2.0
 * 
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#ifndef __SYNTH_H
#define __SYNTH_H

// This may not be present on MSVC.
// See http://stackoverflow.com/questions/126279/c99-stdint-h-header-and-ms-visual-studio
#include <stdint.h>
#include <stddef.h>
// FMER 2026-10-05: the selected MSFA translation units never use this macro.
// FMER_DEVICE has one musical-core owner and no C++ thread library. This branch
// provides compiler ordering only; the target HAL owns device/DMA bus barriers.
#if defined(FMER_DEVICE)
#define SynthMemoryBarrier() __asm__ __volatile__("" ::: "memory")
#else
// Standard portable host fence; no platform framework dependency.
#include <atomic>
#define SynthMemoryBarrier() std::atomic_thread_fence(std::memory_order_seq_cst)
#endif

// TODO(raph): move from fixed to variable N
#define LG_N 6
#define N (1 << LG_N)

#if 0 && defined(__APPLE__)
#include <libkern/OSAtomic.h>
#define SynthMemoryBarrier() OSMemoryBarrier()
#elif 0 && defined(__GNUC__)
#if (__GNUC__ > 4) || (__GNUC__ == 4 && __GNUC_MINOR__ >= 1)
#define SynthMemoryBarrier() __sync_synchronize()
#endif
#endif

// #undef SynthMemoryBarrier()

#ifndef SynthMemoryBarrier
#warning Memory barrier is not enabled
#define SynthMemoryBarrier()
#endif

template<typename T>
inline static T min(const T& a, const T& b) {
    return a < b ? a : b;
}

template<typename T>
inline static T max(const T& a, const T& b) {
    return a > b ? a : b;
}

// FMER: scalar reference path selected on every host for comparable renders.
#if defined(FMER_MSFA_ENABLE_NEON) && defined(__aarch64__)
#define HAVE_NEON_INTRINSICS
#include <arm_neon.h>
static inline bool hasNeon() {
  return true;
}
#elif defined(FMER_MSFA_ENABLE_NEON) && defined(__ARM_NEON__)
#define HAVE_NEON_INTRINSICS
#include <arm_neon.h>
// TODO: get this working (although maybe we don't even care about non-NEON ARM any more)
//#include <cpu-features.h>

static inline bool hasNeon() {
  return true;
  //return (android_getCpuFeatures() & ANDROID_CPU_ARM_FEATURE_NEON) != 0;
}
#else
static inline bool hasNeon() {
  return false;
}
#endif

#endif  // __SYNTH_H
