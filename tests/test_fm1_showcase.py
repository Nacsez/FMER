import sys,json,tempfile,unittest,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import fm1_session as session
import generate_fm1_visuals as visuals
class ShowcaseTests(unittest.TestCase):
 def test_generated_assets_exact(self):
  subprocess.run([sys.executable,str(ROOT/'tools/generate_fm1_visuals.py'),'--check'],check=True,capture_output=True)
  d=json.loads((ROOT/'host/fm_algorithms.json').read_text());self.assertEqual(len(d['algorithms']),32)
  for a in d['algorithms']:
   self.assertGreater(a['carriers'],0)
   for i,mask in enumerate(a['incoming']):self.assertLess(mask,1<<i)
  self.assertEqual(d['algorithms'][31]['carriers'],63)
  self.assertEqual(d['algorithms'][31]['incoming'],[0]*6)
  self.assertEqual(d['algorithms'][4]['incoming'],[0,1,0,4,0,16])
  self.assertEqual([a['algorithm'] for a in d['algorithms'] if a['unsupported_feedback']],[3,5])
 def test_output_metrics_strict(self):
  frame=lambda s:session.PREFIX+bytes([27])+s.encode()+bytes([247])
  self.assertEqual(session.parse_output_metrics(frame('1 2 3 4 5 65535 32111'))['guarded_samples'],2)
  for s in ('2 0 0 0 0 0 0','1 0 0 0 0 0 32112','1 -1 0 0 0 0 0','1 0 0','1 0 0 0 0 65536 0'):
   with self.assertRaises(ValueError):session.parse_output_metrics(frame(s))
 def test_compact_capture_retains_events_and_failure_context(self):
  with tempfile.TemporaryDirectory() as tmp:
   j=session.DurableJournal(Path(tmp)/'capture',wire_log=False,identity=session.SHOWCASE_IDENTITY)
   for n in range(20):j.record('send_intent',number=n)
   j.record('target_event_batch',events=[]);j.record('target_event_batch',events=[{'kind':'encoder'}]);j.record('connection_gap_start',error='test disconnect');j.close()
   rows=[json.loads(x) for x in j.paths[0].read_text().splitlines()]
   self.assertEqual(len(rows),2);self.assertEqual(rows[0]['events'][0]['kind'],'encoder')
   self.assertEqual(len(rows[1]['recent_wire']),8);self.assertEqual(rows[1]['recent_wire'][0]['number'],12);self.assertEqual(j.suppressed,21)
if __name__=='__main__':unittest.main()
