#pragma once
#include "multitrack.hpp"

namespace fmer {
// Small pure editing operations. Failure leaves every byte untouched. Moving
// a note preserves its ties and rejects occupied destinations; copying a range
// makes a leading tie a rest so it cannot attach to an unrelated destination.
bool move_note(MonoPattern&, unsigned step, int distance) noexcept;
bool resize_note(MonoPattern&, unsigned step, unsigned length) noexcept;
bool erase_note(MonoPattern&, unsigned step) noexcept;
unsigned note_start(const MonoPattern&, unsigned step) noexcept;
unsigned note_length(const MonoPattern&, unsigned step) noexcept;
bool copy_steps(const MonoPattern&, unsigned start, unsigned count, MonoPattern& clipboard) noexcept;
bool paste_steps(MonoPattern&, unsigned start, const MonoPattern& clipboard) noexcept;
}
