#include "storage.hpp"
#include <iostream>
#include <stdexcept>

void check(bool value, const char* description) {
    if (!value) throw std::runtime_error(description);
}
int main() {
    try {
        fmer::PresetStore store;
        const auto original = store.backup();
        auto patch = fmer::make_init_patch(); patch.vced[134] = 31;
        check(store.edit(patch), "valid audition");
        check(store.backup() == original, "audition must not alter any saved preset");
        check(store.undo() && store.audition().vced[134] == 0, "undo is complete");
        check(!store.undo(), "no phantom undo");
        check(store.edit(patch) && store.commit(127), "last preset slot saves");
        check(store.saved(127)->vced == patch.vced && store.generation() == 1, "saved generation");
        const auto committed = store.backup();
        check(!store.commit(128) && store.backup() == committed, "capacity refusal preserves data");
        patch.vced[0] = 127;
        check(!store.edit(patch), "reject invalid audition");
        fmer::PresetStore restored;
        std::string error;
        check(restored.restore(committed.data(), committed.size(), error), "native preset readback");
        check(restored.backup() == committed, "all 128 presets round trip");
        for (std::size_t offset : {std::size_t(0), std::size_t(8), std::size_t(12), std::size_t(20), committed.size()-1}) {
            auto corrupt = committed; corrupt[offset] ^= 1;
            check(!restored.restore(corrupt.data(), corrupt.size(), error), "reject corrupt header/payload/CRC");
            check(restored.backup() == committed, "failed restore must be atomic");
        }
        for (std::size_t n : {std::size_t(0), std::size_t(15), committed.size()-1})
            check(!restored.restore(committed.data(), n, error), "reject truncated save");
        std::cout << "Preset storage: audition/undo/128 slots/generation/CRC/atomic validation passed\n";
        return 0;
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
