"""Offline resume helpers plus Android integration/bootclasspath contracts."""
import pathlib, subprocess, tempfile, shutil, os, unittest
ROOT=pathlib.Path(__file__).parent
SRC=ROOT/'src/ru/alexv/pcmote'
class ResumeTests(unittest.TestCase):
 def test_stream_identity_offsets_and_binding(self):
  source=SRC/'ResumeProtocol.java'
  self.assertTrue(source.exists(), 'resume protocol helper missing')
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d); probe=p/'Probe.java'
   probe.write_text('''package ru.alexv.pcmote;
import java.io.*;
public class Probe {
 static void bad(long offset,long size)throws Exception {try{ResumeProtocol.checkOffset(offset,size);throw new AssertionError("bad offset");}catch(IOException expected){}}
 public static void main(String[] a)throws Exception {
 if(!ResumeProtocol.hash(new ByteArrayInputStream("abc".getBytes("UTF-8")),3,null).equals("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"))throw new AssertionError("hash");
 try{ResumeProtocol.hash(new ByteArrayInputStream(new byte[4]),3,null);throw new AssertionError("growth");}catch(IOException expected){}
 try{ResumeProtocol.hash(new ByteArrayInputStream(new byte[2]),3,null);throw new AssertionError("shrink");}catch(IOException expected){}
 bad(-1,10);bad(11,10);bad(1,10);ResumeProtocol.checkOffset(10,10);ResumeProtocol.checkOffset(4194304,4194305);
 if(ResumeProtocol.bound("pc","key","other",ResumeProtocol.fingerprint("key")))throw new AssertionError("host binding");
 if(ResumeProtocol.bound("pc","new","pc",ResumeProtocol.fingerprint("key")))throw new AssertionError("key binding");
 if(!ResumeProtocol.bound("pc","key","pc",ResumeProtocol.fingerprint("key")))throw new AssertionError("same owner");
 InputStream shortReads=new ByteArrayInputStream(new byte[13]){public synchronized long skip(long n){return 0;}};
 ResumeProtocol.skipFully(shortReads,12);if(shortReads.read()!=0||shortReads.read()!=-1)throw new AssertionError("skip fallback");
 try{ResumeProtocol.skipFully(new ByteArrayInputStream(new byte[2]),3);throw new AssertionError("short skip");}catch(IOException expected){}
 final int[] calls={0};try{ResumeProtocol.hash(new ByteArrayInputStream(new byte[100000]),100000,new ResumeProtocol.Check(){public void check()throws IOException{if(++calls[0]==2)throw new IOException("cancel");}});throw new AssertionError("cancel ignored");}catch(IOException expected){}
 if(!ResumeProtocol.mayCreate(false)||ResumeProtocol.mayCreate(true))throw new AssertionError("missing session recreated");
 if(ResumeProtocol.needsSource(true,true)||ResumeProtocol.needsSource(false,false)||!ResumeProtocol.needsSource(true,false))throw new AssertionError("completed ack needs source");
 if(ResumeProtocol.needsRemoteAbort(true)||!ResumeProtocol.needsRemoteAbort(false))throw new AssertionError("local discard contacted remote");
 if(ResumeProtocol.retryDelay(0)!=1000||ResumeProtocol.retryDelay(1)!=2000||ResumeProtocol.retryDelay(2)!=4000||ResumeProtocol.retryDelay(3)!=-1)throw new AssertionError("retry bounds");
 System.out.println("RESUME_HELPERS_OK"); }}''',encoding='utf-8')
   javac=shutil.which('javac'); self.assertTrue(javac)
   java=str(pathlib.Path(javac).with_name('java.exe' if os.name=='nt' else 'java'))
   r=subprocess.run([javac,'-encoding','UTF-8','-source','8','-target','8','-d',d,str(source),str(probe)],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   r=subprocess.run([java,'-cp',d,'ru.alexv.pcmote.Probe'],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr);self.assertIn('RESUME_HELPERS_OK',r.stdout)
 def test_large_stream_is_bounded_and_cancellable_skip(self):
  source=SRC/'ResumeProtocol.java'
  self.assertTrue(source.exists())
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d); probe=p/'Bounded.java'
   probe.write_text('''package ru.alexv.pcmote;import java.io.*;
public class Bounded {public static void main(String[] a)throws Exception {
 final long[] left={32L*1024*1024};
 InputStream generated=new InputStream(){public int read(){throw new AssertionError("single-byte read");}public int read(byte[] b,int o,int n){if(n>65536)throw new AssertionError("unbounded allocation");if(left[0]==0)return -1;int take=(int)Math.min(n,left[0]);java.util.Arrays.fill(b,o,o+take,(byte)0);left[0]-=take;return take;}};
 String digest=ResumeProtocol.hash(generated,32L*1024*1024,null);if(!digest.equals("83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302"))throw new AssertionError(digest);
 final int[] checks={0};try{ResumeProtocol.skipFully(new ByteArrayInputStream(new byte[200000]),200000,new ResumeProtocol.Check(){public void check()throws IOException{if(++checks[0]==2)throw new IOException("stop");}});throw new AssertionError("skip ignored cancellation");}catch(IOException expected){}
 }}''',encoding='utf-8')
   javac=shutil.which('javac');java=str(pathlib.Path(javac).with_name('java.exe' if os.name=='nt' else 'java'))
   r=subprocess.run([javac,'-d',d,str(source),str(probe)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
   r=subprocess.run([java,'-Xmx16m','-cp',d,'ru.alexv.pcmote.Bounded'],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
 def test_android_resume_contract(self):
  u=(SRC/'FileUpload.java').read_text(encoding='utf-8');m=(SRC/'MainActivity.java').read_text(encoding='utf-8')
  for marker in ['takePersistableUriPermission','FLAG_GRANT_PERSISTABLE_URI_PERMISSION','offerPendingUpload']:
   self.assertIn(marker,m)
  for marker in ['/upload/resume/','X-Upload-Offset','X-Chunk-SHA256','releasePersistableUriPermission','commit()','ResumeProtocol.hash','"discard"','setInstanceFollowRedirects(false)']:
   self.assertIn(marker,u)
  self.assertNotIn('->',u);self.assertNotIn('/upload"',u)
  self.assertIn('current.getString("host", "")',u)
  self.assertIn('current.getString("key", "")',u)
  self.assertIn('getFilesDir()',u)
  self.assertNotIn('getCacheDir()',u)
  self.assertIn('getFD().sync()',u)
  self.assertIn('discardLocal()',u)
  self.assertLess(u.index('completedStatus()'),u.index('phase(R.string.upload_verifying)'))
  self.assertIn('upload_discard_local_confirm',m)
  for lang in ['values','values-en']:
   text=(ROOT/'res'/lang/'strings.xml').read_text(encoding='utf-8')
   for key in ['upload_resume','upload_pause','upload_discard','upload_pending','upload_owner_changed','upload_cache_budget']:
    self.assertIn('name="'+key+'"',text)
if __name__=='__main__':unittest.main(verbosity=2)
