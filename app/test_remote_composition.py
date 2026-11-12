"""Real Java state transitions for local IME composition, no Windows text reads."""
import pathlib, shutil, subprocess, tempfile, unittest
SRC = pathlib.Path(__file__).parent / 'src/ru/alexv/pcmote'
class RemoteCompositionTests(unittest.TestCase):
 def test_composition_commit_finish_and_local_delete(self):
  source=SRC/'RemoteComposition.java'
  self.assertTrue(source.exists())
  with tempfile.TemporaryDirectory() as directory:
   probe=pathlib.Path(directory)/'Probe.java'
   probe.write_text('''package ru.alexv.pcmote;
public class Probe {
 static void eq(String expected,String actual){if(!expected.equals(actual))throw new AssertionError(expected+" != "+actual);}
 public static void main(String[] args){
  RemoteComposition c=new RemoteComposition();
  c.set("hel");c.set("hello");eq("hello",c.commit("hello"));eq("",c.finish());
  c.set("world");eq("world",c.finish());eq("",c.finish());
  c.set("abc");if(!c.delete(1,0))throw new AssertionError();eq("ab",c.finish());
  c.set("a\\uD83D\\uDE03");c.delete(1,0);eq("a",c.finish());
  if(c.delete(1,0))throw new AssertionError("remote deletion swallowed");
  c.set("discard");c.clear();eq("",c.finish());
  eq("x",c.commit("x"));eq("",c.finish());
 }
}''',encoding='utf-8')
   javac=shutil.which('javac');self.assertTrue(javac)
   result=subprocess.run([javac,'-d',directory,str(source),str(probe)],capture_output=True,text=True)
   self.assertEqual(0,result.returncode,result.stderr)
   result=subprocess.run([str(pathlib.Path(javac).with_name('java.exe')),'-cp',directory,'ru.alexv.pcmote.Probe'],capture_output=True,text=True)
   self.assertEqual(0,result.returncode,result.stderr)
