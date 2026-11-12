"""Offline signed-update protocol execution and Android integration contracts (no APK/network)."""
import pathlib, subprocess, tempfile, shutil, os, unittest
ROOT=pathlib.Path(__file__).parent
SRC=ROOT/'src/ru/alexv/pcmote'
WORK=ROOT
class UpdateTests(unittest.TestCase):
 def test_protocol(self):
  source=SRC/'UpdateManifest.java'
  self.assertTrue(source.exists(), 'signed update verifier missing')
  javac=shutil.which('javac'); self.assertTrue(javac)
  java=str(pathlib.Path(javac).with_name('java.exe' if os.name=='nt' else 'java'))
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d); h=p/'Probe.java'
   h.write_text(r'''import ru.alexv.pcmote.UpdateManifest;import java.nio.file.*;import java.util.*;
public class Probe {
 static void bad(byte[] b,long now,long seq)throws Exception {try{UpdateManifest.verify(b,now,seq);throw new AssertionError("accepted bad manifest");}catch(IllegalArgumentException expected){}}
 public static void main(String[] a)throws Exception {
 byte[] b=Files.readAllBytes(Paths.get(a[0]));long now=1794481200000L;
 UpdateManifest m=UpdateManifest.verify(b,now,0);
 if(m.versionCode!=25||m.sequence!=1||!m.packageName.equals("ru.alexv.pcmote"))throw new AssertionError();
 if(m.isNewer(25)||!m.isNewer(24)||m.isNewer(26))throw new AssertionError("version loop");
 bad(b,1893456000000L,0);bad(b,now,2);
 String s=new String(b,"UTF-8");bad(s.replace("\"payload\":","\"payload\":\"AA==\",\"payload\":").getBytes("UTF-8"),now,0);
 bad(s.replace("m2XB","n2XB").getBytes("UTF-8"),now,0);bad(new byte[65537],now,0);
 for(String url:new String[]{"http://github.com/a","https://evil.com/a","https://github.com:444/a","https://u@github.com/a","https://127.0.0.1/a","https://github.com/a#x"}){try{UpdateManifest.redirectUrl(url);throw new AssertionError(url);}catch(IllegalArgumentException expected){}}
 UpdateManifest.redirectUrl("https://release-assets.githubusercontent.com/a?x=y");
 for(String j:new String[]{"{\"x\":1,\"x\":2}","{\"x\":1,\"\\u0078\":2}","[1,]","{\"x\":01}","{\"x\":1.0}","{\"x\":\"\\ud800\"}","{} trailing"}){try{UpdateManifest.parseJson(j);throw new AssertionError(j);}catch(IllegalArgumentException expected){}}
 System.out.println("SIGNED_FIXTURE_AND_REJECTION_OK");}}
''',encoding='utf-8')
   r=subprocess.run([javac,'-encoding','UTF-8','-d',d,str(source),str(h)],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   r=subprocess.run([java,'-cp',d,'Probe',str(WORK/'test-update-positive.json')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr); self.assertIn('SIGNED_FIXTURE',r.stdout)
 def test_signed_rejection_vectors(self):
  import json
  vectors=json.loads((ROOT/'test-update-vectors.json').read_text(encoding='utf-8'))
  self.assertGreaterEqual(len(vectors),24)
  javac=shutil.which('javac'); java=str(pathlib.Path(javac).with_name('java.exe' if os.name=='nt' else 'java'))
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d); paths=[]
   for i,v in enumerate(vectors):
    f=p/(str(i)+'.json'); f.write_text(json.dumps(v['envelope']),encoding='utf-8'); paths.append(str(f))
   h=p/'RejectProbe.java'; h.write_text('import ru.alexv.pcmote.UpdateManifest;import java.nio.file.*;public class RejectProbe {public static void main(String[] args)throws Exception {for(String a:args){try{UpdateManifest.verify(Files.readAllBytes(Paths.get(a)),1794478200000L,0);throw new AssertionError("Accepted vector: "+a);}catch(IllegalArgumentException expected){}}}}',encoding='utf-8')
   result=subprocess.run([javac,'-d',d,str(SRC/'UpdateManifest.java'),str(h)],capture_output=True,text=True); self.assertEqual(result.returncode,0,result.stderr)
   result=subprocess.run([java,'-cp',d,'RejectProbe']+paths,capture_output=True,text=True); self.assertEqual(result.returncode,0,result.stderr)
 def test_binary_manifest_min_sdk_reader(self):
  import struct
  strings=['uses-sdk','minSdkVersion','http://schemas.android.com/apk/res/android']
  encoded=[]
  for value in strings:
   raw=value.encode('utf-8'); encoded.append(bytes([len(value),len(raw)])+raw+b'\0')
  data=b''.join(encoded); offsets=[]; cursor=0
  for item in encoded: offsets.append(cursor); cursor+=len(item)
  pool=struct.pack('<HHIIIIII',1,28,28+4*len(strings)+len(data),len(strings),0,256,28+4*len(strings),0)+struct.pack('<III',*offsets)+data
  node=struct.pack('<HHIII',0x102,16,56,1,0xffffffff)+struct.pack('<IIHHHHHH',0xffffffff,0,20,20,1,0,0,0)+struct.pack('<IIIHBBI',2,1,0xffffffff,8,0,0x10,21)
  xml=struct.pack('<HHI',3,8,8+len(pool)+len(node))+pool+node
  javac=shutil.which('javac'); java=str(pathlib.Path(javac).with_name('java.exe' if os.name=='nt' else 'java'))
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d); (p/'manifest.bin').write_bytes(xml)
   h=p/'SdkProbe.java'; h.write_text('package ru.alexv.pcmote; import java.nio.file.*; public class SdkProbe {public static void main(String[] a)throws Exception {byte[] b=Files.readAllBytes(Paths.get(a[0]));if(ApkMinSdk.parse(b)!=21)throw new AssertionError();b[4]=0;try{ApkMinSdk.parse(b);throw new AssertionError();}catch(java.io.IOException expected){}System.out.println("MIN_SDK_OK");}}',encoding='utf-8')
   result=subprocess.run([javac,'-d',d,str(SRC/'ApkMinSdk.java'),str(h)],capture_output=True,text=True); self.assertEqual(result.returncode,0,result.stderr)
   result=subprocess.run([java,'-cp',d,'ru.alexv.pcmote.SdkProbe',str(p/'manifest.bin')],capture_output=True,text=True); self.assertEqual(result.returncode,0,result.stderr)
 def test_android_bootclasspath_compiles(self):
  import re
  default_sdk=(pathlib.Path(os.environ['LOCALAPPDATA'])/'Android/Sdk') if os.environ.get('LOCALAPPDATA') else pathlib.Path.home()/'Android/Sdk'
  sdk=pathlib.Path(os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT') or default_sdk)
  jar=sdk/'platforms/android-34/android.jar'
  self.assertTrue(jar.exists(),'Android 34 SDK is required for offline compile')
  sources=list(SRC.glob('*.java')); refs={}
  for source in sources:
   for kind,name in re.findall(r'(?<!android\.)\bR\.(\w+)\.(\w+)',source.read_text(encoding='utf-8')):
    refs.setdefault(kind,set()).add(name)
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d); r=p/'R.java'
   r.write_text('package ru.alexv.pcmote; public final class R {'+''.join('public static final class '+kind+' {'+''.join('public static final int '+name+'='+str(i+1)+';' for i,name in enumerate(sorted(names)))+'}' for kind,names in refs.items())+'}',encoding='utf-8')
   result=subprocess.run([shutil.which('javac'),'-encoding','UTF-8','-nowarn','-parameters','-source','8','-target','8','-bootclasspath',str(jar),'-classpath',str(ROOT/'zxing-core-3.3.3.jar'),'-d',d,str(r)]+[str(x) for x in sources],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   for source in [SRC/'StartupUpdate.java',SRC/'UpdateManifest.java',SRC/'UpdateProvider.java',SRC/'UpdateReplacedReceiver.java']:
    self.assertNotIn('->',source.read_text(encoding='utf-8'),'No lambdas: direct D8 build has no desugaring')
 def test_android_contract(self):
  self.assertTrue((SRC/'StartupUpdate.java').exists(),'startup controller missing')
  u=(SRC/'StartupUpdate.java').read_text(encoding='utf-8'); p=(SRC/'UpdateProvider.java').read_text(encoding='utf-8')
  for s in ['AtomicBoolean','setInstanceFollowRedirects(false)','setConnectTimeout(10000)','setReadTimeout(20000)','ACTION_MANAGE_UNKNOWN_APP_SOURCES','canRequestPackageInstalls','ACTION_INSTALL_PACKAGE','FLAG_GRANT_READ_URI_PERMISSION','GET_SIGNING_CERTIFICATES','GET_SIGNATURES','getPackageArchiveInfo','onPause','disconnect()','max_sequence']:
   self.assertIn(s,u)
  for s in ['MODE_READ_ONLY','"r".equals(mode)','update.apk','verifyCached','UnsupportedOperationException']:
   self.assertIn(s,p)
  self.assertNotIn('setDefaultSSLSocketFactory',u); self.assertNotIn('setHostnameVerifier',u)
  manifest=(ROOT/'AndroidManifest.xml').read_text(encoding='utf-8')
  for s in ['versionCode="30"','versionName="1.20"','REQUEST_INSTALL_PACKAGES','MY_PACKAGE_REPLACED','android:grantUriPermissions="true"']:
   self.assertIn(s,manifest)
  main=(SRC/'MainActivity.java').read_text(encoding='utf-8')
  for s in ['startupUpdate.onResume()','startupUpdate.onPause()','startupUpdate.dispose()']:
   self.assertIn(s,main)
  for lang in ['values','values-en']:
   text=(ROOT/'res'/lang/'strings.xml').read_text(encoding='utf-8')
   for key in ['update_title','update_now','update_later','update_progress','update_cancel','update_failed','update_permission','update_reopen']:
    self.assertIn('name="'+key+'"',text)
if __name__=='__main__':unittest.main(verbosity=2)
