"""Admission evidence must not be inferred from voices at the slowest block."""
import sys
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import fm1_710_bench as bench

class AdmissionTests(TestCase):
    def exercise(self,active):
        class Device:
            program=0
            session=journal=None
            def set(self,*args):pass
            def transport(self,*args):pass
            def status(self):return dict(preset_id=self.program,sound_dirty=0)
            def snapshot(self):return self.program,None
            def check(self,*args):return dict(active_voices=active,maximum_render_voices=2)
        d=Device();result=dict(cases=[])
        def send(_session,_journal,status,value,velocity=0):
            if status==0xcf:d.program=value
        def decode(program):
            return dict(preset_id=program,vced=[0]*145+list(bench.NAMES[program].ljust(10).encode()),
                        controls=[0]*160+[bench.program_engine(program)])
        with patch.object(bench,'short_message',side_effect=send),patch.object(bench.native,'decode',side_effect=decode),patch.object(bench.legacy,'reset_peaks'),patch.object(bench.legacy,'query',return_value=dict(active_voices=0)),patch.object(bench.time,'sleep'):
            bench.run_presets(d,d,result,{})
        return result
    def test_four_active_voices_pass_even_when_setup_block_was_slower(self):
        self.assertEqual(len(self.exercise(4)['cases']),64)
    def test_missing_voice_still_fails(self):
        with self.assertRaisesRegex(RuntimeError,'did not admit all four'):
            self.exercise(3)

if __name__=='__main__':main()
