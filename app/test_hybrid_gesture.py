import pathlib,shutil,subprocess,tempfile,unittest
SRC=pathlib.Path(__file__).parent/'src/ru/alexv/pcmote'
class HybridGestureTests(unittest.TestCase):
 def test_android_integration_has_no_command_strip_and_preserves_guards(self):
  desktop=(SRC/'DesktopControl.java').read_text(encoding='utf-8')
  ime=(SRC/'RemoteImeView.java').read_text(encoding='utf-8')
  layout=(SRC.parents[3]/'res/layout/screen_view.xml').read_text(encoding='utf-8')
  self.assertNotIn('screen_input_bar',layout)
  self.assertNotIn('new Button',desktop)
  self.assertIn('fresh()',desktop)
  self.assertIn('revision==touchRevision',desktop)
  self.assertIn('focus?focusWorker:worker',desktop)
  self.assertIn('.put("count",1)',desktop) # Two physical taps are two clicks, not three.
  self.assertIn('onCreateInputConnection',ime)
  self.assertIn('IME_FLAG_NO_EXTRACT_UI',ime)
  self.assertIn('setComposingText',ime)
  self.assertNotIn('getSharedPreferences',ime)

 def test_real_gesture_sequences(self):
  source=SRC/'HybridGesture.java'
  self.assertTrue(source.exists(),'hybrid gesture classifier missing')
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'Probe.java'
   p.write_text('''package ru.alexv.pcmote;
public class Probe {
 static void check(boolean b){if(!b)throw new AssertionError();}
 public static void main(String[] args){
 HybridGesture g=new HybridGesture(10);
 g.down(20,30,0); check(g.move(25,35)==null);
 HybridGesture.Event e=g.up(25,35,100);check(e.kind==HybridGesture.CLICK&&e.count==1&&!e.right);
 g.down(25,35,200);e=g.up(25,35,250);check(e.kind==HybridGesture.CLICK&&e.count==2);
 g.down(40,50,1000);e=g.move(70,80);check(e.kind==HybridGesture.MOVE&&e.dx==30&&e.dy==30);check(g.up(70,80,1100)==null);
 g.down(1,2,2000);e=g.up(1,2,2700);check(e.right&&e.count==1);
 g.down(1,2,3000);g.twoFingers(100);check(g.scroll(105)==null);e=g.scroll(160);check(e.kind==HybridGesture.SCROLL&&e.dy==60);check(g.up(1,2,3100)==null);
 g.down(1,2,4000);g.cancel();check(g.up(1,2,4050)==null);
 g.down(1,2,6000);check(g.scrollSteps(15,72)==0);check(g.scrollSteps(15,72)==0);check(g.scrollSteps(15,72)==0);check(g.scrollSteps(30,72)==1);check(g.scrollSteps(-75,72)==-1);
  g.down(1,2,7000);check(g.scrollSteps(10,72)==0);
  g.down(1,2,5000);g.twoFingers(100);g.pointerLift();check(g.move(200,200)==null);check(g.up(200,200,5100)==null);
 System.out.println("OK");}}
''')
   javac=shutil.which('javac');self.assertTrue(javac)
   r=subprocess.run([javac,'-d',d,str(source),str(p)],capture_output=True,text=True);self.assertEqual(0,r.returncode,r.stderr)
   r=subprocess.run([str(pathlib.Path(javac).with_name('java.exe')),'-cp',d,'ru.alexv.pcmote.Probe'],capture_output=True,text=True);self.assertEqual(0,r.returncode,r.stderr)
