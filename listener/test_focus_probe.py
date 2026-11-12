import pathlib,sys,unittest,subprocess
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).parent))
class FocusProbeTests(unittest.TestCase):
 def test_busy_probe_does_not_launch_another_process(self):
  import focus_probe, threading
  entered=threading.Event(); release=threading.Event()
  def run(*args,**kwargs):
   entered.set(); release.wait(3)
   return subprocess.CompletedProcess([],0,'false','')
  with patch.object(focus_probe.subprocess,'run',side_effect=run) as mocked:
   worker=threading.Thread(target=focus_probe.editable_focus)
   worker.start()
   try:
    self.assertTrue(entered.wait(1))
    self.assertIsNone(focus_probe.editable_focus())
    self.assertEqual(1,mocked.call_count)
   finally:
    release.set(); worker.join(4)

 def test_probe_is_bounded_and_returns_only_boolean_metadata(self):
  import focus_probe
  with patch.object(focus_probe.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'true','')) as run:
   self.assertIs(True,focus_probe.editable_focus())
   self.assertLessEqual(run.call_args.kwargs['timeout'],2)
   script=run.call_args.args[0][-1]
   self.assertNotIn('.Current.Value',script)
   self.assertNotIn('.Current.Name',script)
 def test_unavailable_or_malformed_is_unknown(self):
  import focus_probe
  for result in [subprocess.CompletedProcess([],1,'true',''),subprocess.CompletedProcess([],0,'garbage','')]:
   with patch.object(focus_probe.subprocess,'run',return_value=result):self.assertIsNone(focus_probe.editable_focus())
  with patch.object(focus_probe.subprocess,'run',side_effect=subprocess.TimeoutExpired('probe',1)):
   self.assertIsNone(focus_probe.editable_focus())
