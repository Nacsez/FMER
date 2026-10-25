"""Original VA catalog fits current native storage without project mutations."""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import companion_bank as bank
import fm1_native_state_v12 as native
import sound_collection_va as collection
from tests.test_companion import fixture


def instrument(recipe):
    state = bank.decode_record(fixture()["native"])
    for identifier, value in recipe["controls"].items():
        state["controls"][identifier] = value
        if identifier < 145:
            state["vced"][identifier] = value
    state["vced"][145:] = list(recipe["name"].ljust(10).encode("ascii"))
    state["modulation_profiles"] = recipe["modulation_profiles"][:]
    return dict(name=recipe["name"], category=recipe["category"], favorite=False,
                audition_note=recipe["audition_note"], native=bank.pack(state))


class VaCollectionTests(unittest.TestCase):
    def test_all_candidates_roundtrip_through_current_native_contract(self):
        before = bank.decode_record(fixture()["native"])
        for recipe in collection.recipes():
            with self.subTest(recipe=recipe["id"]):
                entry = instrument(recipe)
                bank.BankLibrary.validate_entry(entry)
                state = bank.decode_record(entry["native"])
                self.assertEqual(native.decode(native.encode(state)), state)
                for key in ("patterns", "tracks", "song"):
                    if key in before:
                        self.assertEqual(state[key], before[key])
                for identifier in (150, 151, 152, 153, 154, 155, 156,
                                   178, 179, 180, 181, 191, 195):
                    self.assertEqual(state["controls"][identifier], before["controls"][identifier])
                settings = bank.render_settings(entry)
                self.assertEqual(settings["engine"], "va")
                self.assertEqual(settings["cutoff"], recipe["controls"][177])
                self.assertEqual(settings["lfo_enabled"], bool(recipe["controls"][147]))
                self.assertEqual(settings["vced"][144], recipe["controls"][144])

    def test_collection_has_real_sound_variants_and_intended_coverage(self):
        recipes = collection.recipes()
        self.assertEqual(Counter(r["group"] for r in recipes),
                         {"percussion": 16, "bass": 12, "leads": 12, "keys": 8, "pads": 16})
        self.assertEqual(len({r["id"] for r in recipes}), 64)
        self.assertEqual(len({r["name"] for r in recipes}), 64)
        self.assertEqual(len({tuple(sorted(r["controls"].items())) for r in recipes}), 64)
        self.assertEqual({r["controls"][161] for r in recipes}, {0, 1, 2, 3, 4})
        self.assertEqual({r["controls"][145] for r in recipes}, {0, 1, 2})
        for recipe in recipes:
            self.assertGreater(recipe["controls"][176], 0)  # Defined toggle state; noise remains unpitched.
            self.assertLessEqual(recipe["controls"][177], 18000)  # Audition contract.
            self.assertNotIn(191, recipe["controls"])  # Never change playing mode.
            self.assertTrue(recipe["description"] and recipe["technique"])

    def test_calls_and_nested_recipe_data_are_independent(self):
        original = collection.recipes()
        expected = deepcopy(original)
        original[0]["controls"][164] = 999
        original[0]["tags"].append("edited")
        original[0]["modulation_profiles"][0] = 3
        self.assertEqual(collection.recipes(), expected)


if __name__ == "__main__":
    unittest.main()
