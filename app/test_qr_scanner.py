from pathlib import Path
import unittest

APP=Path(__file__).resolve().parent
class QrScannerTests(unittest.TestCase):
    def test_scanner_is_local_and_releases_camera(self):
        path=APP/'src/ru/alexv/pcmote/QrScannerActivity.java'
        self.assertTrue(path.exists(), 'in-app scanner missing')
        src=path.read_text(encoding='utf-8')
        for required in ['PairingLink.parse','old.release()','onPause','requestPermissions','BarcodeFormat.QR_CODE','setPreviewCallbackWithBuffer(null)']:
            self.assertIn(required,src)
        for forbidden in ['http://','https://','Log.','FileOutputStream','setResult(RESULT_OK']:
            self.assertNotIn(forbidden,src)
    def test_preview_callback_uses_cached_dimensions_not_camera_parameters(self):
        src=(APP/'src/ru/alexv/pcmote/QrScannerActivity.java').read_text(encoding='utf-8')
        callback=src.split('public void onPreviewFrame',1)[1].split('private void closeCamera',1)[0]
        self.assertNotIn('getParameters()',callback)
        self.assertIn('final int width=frameWidth,height=frameHeight;',callback)
    def test_surface_callback_does_not_open_camera_before_permission(self):
        src=(APP/'src/ru/alexv/pcmote/QrScannerActivity.java').read_text(encoding='utf-8')
        opening=src.split('private void openCamera(){',1)[1]
        self.assertLess(opening.index('checkSelfPermission'),opening.index('Camera.open('))
    def test_new_camera_session_is_not_blocked_by_stale_decode(self):
        src=(APP/'src/ru/alexv/pcmote/QrScannerActivity.java').read_text(encoding='utf-8')
        close=src.split('private void closeCamera(){',1)[1]
        self.assertIn('decoding=false;',close)
        callback=src.split('final String result=found;',1)[1]
        self.assertLess(callback.index('session!=generation'),callback.index('decoding=false;'))
    def test_real_decoder_roundtrip_in_all_rotations(self):
        import shutil, subprocess, tempfile
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); source=p/'QrProbe.java'
            source.write_text('''import com.google.zxing.*;import com.google.zxing.qrcode.*;import com.google.zxing.common.*;
public class QrProbe{public static void main(String[] a)throws Exception{
String text="pcmote://pair?v=1&host=192.168.7.1&port=8767";
BitMatrix qr=new QRCodeWriter().encode(text,BarcodeFormat.QR_CODE,400,400);
for(int rotation=0;rotation<4;rotation++){byte[] frame=new byte[400*400];
for(int y=0;y<400;y++)for(int x=0;x<400;x++){int px=x,py=y;for(int r=0;r<rotation;r++){int old=px;px=399-py;py=old;}frame[y*400+x]=(byte)(qr.get(px,py)?0:255);}
String decoded=new QRCodeReader().decode(new BinaryBitmap(new HybridBinarizer(new PlanarYUVLuminanceSource(frame,400,400,0,0,400,400,false)))).getText();
if(!text.equals(decoded))throw new AssertionError();}System.out.println("QR_OK");}}''',encoding='utf-8')
            jar=str(APP/'zxing-core-3.3.3.jar')
            result=subprocess.run([shutil.which('javac'),'-cp',jar,'-d',d,str(source)],capture_output=True,text=True)
            self.assertEqual(0,result.returncode,result.stderr)
            import os
            result=subprocess.run([str(Path(shutil.which('javac')).with_name('java.exe')),'-cp',d+os.pathsep+jar,'QrProbe'],capture_output=True,text=True)
            self.assertEqual(0,result.returncode,result.stderr)
    def test_camera_optional_and_activity_private(self):
        import xml.etree.ElementTree as ET
        root=ET.parse(APP/'AndroidManifest.xml').getroot();ns='{http://schemas.android.com/apk/res/android}'
        self.assertTrue(any(x.get(ns+'name')=='android.permission.CAMERA' for x in root.findall('uses-permission')))
        scanner=[x for x in root.find('application').findall('activity') if x.get(ns+'name')=='.QrScannerActivity']
        self.assertEqual(1,len(scanner))
        self.assertEqual('false',scanner[0].get(ns+'exported'))
if __name__=='__main__':unittest.main()
