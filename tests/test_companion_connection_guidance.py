import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import companion_errors

class Guidance(unittest.TestCase):
    def test_discovery_distinguishes_device_from_patches(self):
        for reason, title in [('no_ports','connection not found'),('unrecognized_ports','connection not found'),('incomplete_pair','Only one'),('identity_timeout','no usable firmware reply')]:
            with self.subTest(reason=reason):
                result=companion_errors.explain(f'Timed out waiting for None; [discovery:{reason}]; no automatic reset or rollback sent')
                self.assertIn(title,result['title'])
                self.assertIn('operation record',result['next_step'])
        legacy=companion_errors.explain('Timed out waiting for None; no automatic reset or rollback sent')
        self.assertIn('physical unit',legacy['explanation'])
        self.assertIn('PC/NORMAL',legacy['next_step'])

    def test_transition_failure_never_claims_no_write_or_recommends_blind_reset(self):
        for expected in ('ota-FM-1_935','FM-1_735'):
            result=companion_errors.explain(f'Timed out waiting for {expected}; [discovery:no_ports]; no automatic reset or rollback sent')
            self.assertIn('Keep the unit powered on',result['next_step'])
            self.assertNotIn('application was not written',result['explanation'])
            self.assertNotIn('power the unit off',result['next_step'])

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
