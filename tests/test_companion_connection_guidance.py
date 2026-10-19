import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import companion_errors

class Guidance(unittest.TestCase):
    def test_multiple_devices_explain_one_at_a_time(self):
        result=companion_errors.explain('Multiple candidate instruments; refusing ambiguous updater connection')
        self.assertIn('More than one',result['title'])
        self.assertIn('each unit separately',result['next_step'])

    def test_busy_input_and_output_have_actionable_guidance(self):
        for operation in ('midiInOpen','midiOutOpen'):
            result=companion_errors.explain(operation+' returned MMRESULT 7')
            self.assertEqual(result['title'],'The MIDI port is already in use')
            self.assertIn('Ableton',result['next_step'])
        self.assertNotEqual(companion_errors.explain('midiInOpen returned MMRESULT 2')['title'],'The MIDI port is already in use')
