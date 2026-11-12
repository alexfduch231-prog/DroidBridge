"""Offline executable transport/bounds tests and Android lifecycle wiring checks."""
import os, pathlib, shutil, subprocess, tempfile, unittest
ROOT=pathlib.Path(__file__).parent
SRC=ROOT/'src/ru/alexv/pcmote'
class AppIconTests(unittest.TestCase):
 def test_executable_transport_and_png_bounds(self):
  source=SRC/'AppIconClient.java'
  self.assertTrue(source.exists(), 'bounded icon transport missing')
  javac=shutil.which('javac'); self.assertTrue(javac)
  java=str(pathlib.Path(javac).with_name('java.exe' if os.name=='nt' else 'java'))
  with tempfile.TemporaryDirectory() as temp:
   probe=pathlib.Path(temp)/'IconProbe.java'
   probe.write_text('''import ru.alexv.pcmote.AppIconClient;
import java.net.*;import java.io.*;import java.util.*;
public class IconProbe {
 static byte[] data;static int status=200;static Fake last;static boolean disconnected;
 static class Fake extends HttpURLConnection {
  Fake(URL u){super(u);}public void connect(){}public boolean usingProxy(){return false;}
  public void disconnect(){disconnected=true;}
  public int getResponseCode(){return status;}
  public InputStream getInputStream(){return new ByteArrayInputStream(data);}
 }
 static byte[] png(int w,int h){byte[] b=new byte[33];int[] sig={137,80,78,71,13,10,26,10,0,0,0,13,73,72,68,82};for(int i=0;i<sig.length;i++)b[i]=(byte)sig[i];for(int i=0;i<4;i++){b[19-i]=(byte)(w>>>(8*i));b[23-i]=(byte)(h>>>(8*i));}return b;}
 static void check(boolean b){if(!b)throw new AssertionError();}
 public static void main(String[] args)throws Exception {
  URL.setURLStreamHandlerFactory(new URLStreamHandlerFactory(){public URLStreamHandler createURLStreamHandler(String p){return new URLStreamHandler(){protected URLConnection openConnection(URL u){return last=new Fake(u);}};}});
  data=png(64,64);AppIconClient c=new AppIconClient();
  check(Arrays.equals(data,c.fetch("192.168.1.8","secret","a b&c")));
  check(last.getURL().toString().equals("http://192.168.1.8:8765/app-icon?id=a+b%26c"));
  check("Bearer secret".equals(last.getRequestProperty("Authorization")));check(!last.getInstanceFollowRedirects());check(!last.getUseCaches());
  check(last.getConnectTimeout()>0 && last.getReadTimeout()>0 && disconnected);
  for(int code:new int[]{404,302,401,500}){status=code;check(c.fetch("host","secret","id")==null);}status=200;
  for(byte[] bad:new byte[][]{png(129,64),png(64,129),png(0,64),png(-1,64),new byte[12],new byte[65537]}){data=bad;check(c.fetch("host","secret","id")==null);}
  data=png(128,128);check(c.fetch("host","secret","id")!=null);
  data=Arrays.copyOf(png(64,64),65536);check(c.fetch("host","secret","id")!=null);
  c.cancel();check(c.fetch("host","secret","id")==null);
  System.out.println("ICON_TRANSPORT_BOUNDS_OK");
 }
}''',encoding='utf-8')
   subprocess.run([javac,'-encoding','UTF-8','-d',temp,str(source),str(probe)],check=True,capture_output=True)
   result=subprocess.run([java,'-cp',temp,'IconProbe'],check=True,capture_output=True,text=True)
   self.assertIn('ICON_TRANSPORT_BOUNDS_OK',result.stdout)
 def test_executable_decode_rejects_before_pixel_allocation(self):
  javac=shutil.which('javac'); java=str(pathlib.Path(javac).with_name('java.exe' if os.name=='nt' else 'java'))
  with tempfile.TemporaryDirectory() as temp:
   p=pathlib.Path(temp); package=p/'android/graphics'; package.mkdir(parents=True)
   bitmap=package/'Bitmap.java'; bitmap.write_text('''package android.graphics; public class Bitmap {public static class Config {public static final Config ARGB_8888=new Config();}public int getWidth(){return 64;}public int getHeight(){return 64;}public void recycle(){}}''',encoding='utf-8')
   factory=package/'BitmapFactory.java'; factory.write_text('''package android.graphics; public class BitmapFactory {public static int calls,pixels,width=64,height=64;public static String mime="image/png";public static class Options {public boolean inJustDecodeBounds,inScaled=true;public int outWidth,outHeight;public String outMimeType;public Bitmap.Config inPreferredConfig;}public static Bitmap decodeByteArray(byte[] b,int offset,int length,Options o){calls++;if(o.inScaled)throw new AssertionError("scaled");if(o.inJustDecodeBounds){o.outWidth=width;o.outHeight=height;o.outMimeType=mime;return null;}pixels++;return new Bitmap();}}''',encoding='utf-8')
   probe=p/'DecodeProbe.java'; probe.write_text('''package ru.alexv.pcmote; import android.graphics.*;public class DecodeProbe {static void check(boolean v){if(!v)throw new AssertionError();}public static void main(String[] args){byte[] b=new byte[33];int[] sig={137,80,78,71,13,10,26,10,0,0,0,13,73,72,68,82};for(int i=0;i<sig.length;i++)b[i]=(byte)sig[i];b[19]=64;b[23]=64;check(AppIconBitmap.decode(new byte[33])==null);check(BitmapFactory.calls==0);b[18]=1;check(AppIconBitmap.decode(b)==null);check(BitmapFactory.calls==0);b[18]=0;BitmapFactory.width=129;check(AppIconBitmap.decode(b)==null);check(BitmapFactory.pixels==0);BitmapFactory.width=64;BitmapFactory.mime="image/jpeg";check(AppIconBitmap.decode(b)==null);check(BitmapFactory.pixels==0);BitmapFactory.mime="image/png";check(AppIconBitmap.decode(b)!=null);check(BitmapFactory.pixels==1);System.out.println("DECODE_ALLOCATION_ORDER_OK");}}''',encoding='utf-8')
   subprocess.run([javac,'-d',temp,str(bitmap),str(factory),str(SRC/'AppIconClient.java'),str(SRC/'AppIconBitmap.java'),str(probe)],check=True,capture_output=True)
   result=subprocess.run([java,'-cp',temp,'ru.alexv.pcmote.DecodeProbe'],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr); self.assertIn('DECODE_ALLOCATION_ORDER_OK',result.stdout)
 def test_bitmap_validation_before_allocation(self):
  path=SRC/'AppIconBitmap.java'; self.assertTrue(path.exists(),'bounded bitmap decode missing')
  text=path.read_text(encoding='utf-8')
  self.assertLess(text.index('AppIconClient.validPng'),text.index('BitmapFactory.decodeByteArray'))
  self.assertIn('inJustDecodeBounds = true',text)
  self.assertIn('bounds.outWidth > 128',text)
  self.assertIn('bounds.outHeight > 128',text)
  self.assertIn('inScaled = false',text)
 def test_lifecycle_and_render_contract(self):
  text=(SRC/'MainActivity.java').read_text(encoding='utf-8')
  pause=text[text.index('protected void onPause()'):text.index('protected void onDestroy()')]
  catalog=text[text.index('private void loadApps()'):text.index('private void buildAppTiles()')]
  self.assertIn('cancelAppIcons()',pause); self.assertIn('cancelAppIcons()',catalog)
  self.assertIn('buildAppTiles();',catalog); self.assertIn('startAppIcons(',catalog)
  self.assertLess(catalog.index('buildAppTiles();',catalog.index('final boolean loaded')),catalog.index('startAppIcons('))
  for part in ('clearColorFilter()', 'ImageView.ScaleType.FIT_CENTER', 'appIcons.get(app.id)', 'generation!=appsGeneration', 'iconViews.get(app.id)', 'appIconClient!=client'):
   self.assertIn(part,text)
  self.assertIn('host.equals(prefs.getString(K_HOST',text); self.assertIn('key.equals(prefs.getString(K_KEY',text)
  manifest=(ROOT/'AndroidManifest.xml').read_text(encoding='utf-8')
  self.assertIn('android:versionCode="27"',manifest); self.assertIn('android:versionName="1.17"',manifest)
if __name__=='__main__':unittest.main(verbosity=2)
