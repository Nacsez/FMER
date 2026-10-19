#pragma once

#include <cstdint>
#include <cstring>
#include <limits>

namespace fmer {
// IEEE binary32 has a finite value exactly when its exponent is not all ones.
// Preserve subnormals and both zero signs; reject every NaN payload and infinity.
// Explicit bit copy avoids the target libc's general classification call in
// per-sample guards, without aliasing assumptions or weakening fault recovery.
inline bool finite_float(float value) noexcept {
    static_assert(sizeof(float) == sizeof(std::uint32_t) &&
                  std::numeric_limits<float>::is_iec559, "requires IEEE binary32");
    std::uint32_t bits;
#if defined(FMER_DEVICE)
    __builtin_memcpy(&bits, &value, sizeof(bits));
#else
    std::memcpy(&bits, &value, sizeof(bits));
#endif
    return (bits & 0x7f800000u) != 0x7f800000u;
}
} // namespace fmer
