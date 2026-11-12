import pathlib,shutil,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).parent
class ReceiveTests(unittest.TestCase):
 def test_real_protocol_validation(self):
  source=ROOT/'src/ru/alexv/pcmote/ReceiveProtocol.java'
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'Probe.java'
   p.write_text('''package ru.alexv.pcmote;
public class Probe {static void check(boolean v){if(!v)throw new AssertionError();}
public static void main(String[] x){String id="0123456789abcdef0123456789abcdef",sha=new String(new char[64]).replace('\\0','a');
ReceiveProtocol.validate(id,"hello.txt",ReceiveProtocol.MAX,sha);
check(ReceiveProtocol.durableOffset(5000000,9000000)==4194304);
check(ReceiveProtocol.durableOffset(9,9)==9);
for(String name:new String[]{"../x",".","..","/x","x\\\\y","x\\n"}){boolean bad=false;try{ReceiveProtocol.validate(id,name,1,sha);}catch(IllegalArgumentException e){bad=true;}check(bad);}
boolean bad=false;try{ReceiveProtocol.durableOffset(11,10);}catch(IllegalArgumentException e){bad=true;}check(bad);
}}''')
   javac=shutil.which('javac');self.assertTrue(javac)
   r=subprocess.run([javac,'-d',d,str(source),str(p)],capture_output=True,text=True);self.assertEqual(0,r.returncode,r.stderr)
   r=subprocess.run([str(pathlib.Path(javac).with_name('java.exe')),'-cp',d,'ru.alexv.pcmote.Probe'],capture_output=True,text=True);self.assertEqual(0,r.returncode,r.stderr)
 def test_activity_declared_private_and_uses_existing_pair(self):
  import xml.etree.ElementTree as ET
  ns='{http://schemas.android.com/apk/res/android}'
  manifest=ET.parse(ROOT/'AndroidManifest.xml').getroot()
  activity=next((a for a in manifest.findall('application/activity') if a.get(ns+'name')=='.ReceiveActivity'),None)
  self.assertIsNotNone(activity)
  self.assertEqual('false',activity.get(ns+'exported'))
  code=(ROOT/'src/ru/alexv/pcmote/ReceiveActivity.java').read_text()
  for marker in ('ACTION_OPEN_DOCUMENT_TREE','takePersistableUriPermission','open("chunk"','X-Chunk-SHA256','MessageDigest','getFilesDir','FLAG_GRANT_WRITE_URI_PERMISSION'):
   self.assertIn(marker,code)
if __name__=='__main__':unittest.main()
