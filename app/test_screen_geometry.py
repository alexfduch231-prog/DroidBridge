"""Execute fit/fill geometry on the real Java helper without Android stubs."""
import pathlib, shutil, subprocess, tempfile, unittest
SRC = pathlib.Path(__file__).parent / 'src/ru/alexv/pcmote'
class ScreenGeometryTests(unittest.TestCase):
    def test_fullscreen_modes_are_integrated_without_replacing_decoder(self):
        source = (SRC / 'ScreenActivity.java').read_text(encoding='utf-8')
        self.assertIn('ScreenGeometry.calculate', source)
        self.assertIn('SYSTEM_UI_FLAG_IMMERSIVE_STICKY', source)
        self.assertIn('if (fullscreen)', source)
        self.assertIn('screen_fill', source)
        layout = (SRC.parents[3] / 'res/layout/screen_view.xml').read_text(encoding='utf-8')
        self.assertIn('@+id/screen_fullscreen', layout)

    def test_fit_fill_and_cropped_input_coordinates(self):
        source = SRC / 'ScreenGeometry.java'
        self.assertTrue(source.exists(), 'fit/fill geometry missing')
        with tempfile.TemporaryDirectory() as d:
            probe = pathlib.Path(d) / 'Probe.java'
            probe.write_text('''package ru.alexv.pcmote;
public class Probe {
 static void near(double a,double b){if(Math.abs(a-b)>0.002)throw new AssertionError(a+" != "+b);}
 public static void main(String[] args){
 ScreenGeometry fit=ScreenGeometry.calculate(1920,1080,1080,2400,false);
 if(fit.width!=1080||fit.height!=608)throw new AssertionError("fit");
 ScreenGeometry fill=ScreenGeometry.calculate(1920,1080,1080,2400,true);
 if(fill.width!=4267||fill.height!=2400||fill.left>=0)throw new AssertionError("fill");
 near(fill.normalizedX(540),0.5); near(fill.normalizedY(1200),0.5);
 if(fill.normalizedX(0)<0.3||fill.normalizedX(1080)>0.7)throw new AssertionError("crop mapping");
 if(!Double.isNaN(fit.normalizedY(0)))throw new AssertionError("letterbox touch");
 ScreenGeometry tall=ScreenGeometry.calculate(720,1600,1920,1080,false);
 if(tall.height!=1080||tall.width!=486)throw new AssertionError("rotation");
 try {ScreenGeometry.calculate(0,1080,100,100,false);throw new AssertionError("invalid");}catch(IllegalArgumentException expected){}
 System.out.println("OK");}}
''', encoding='utf-8')
            javac = shutil.which('javac')
            self.assertTrue(javac)
            result = subprocess.run([javac, '-d', d, str(source), str(probe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            java = str(pathlib.Path(javac).with_name('java.exe'))
            result = subprocess.run([java, '-cp', d, 'ru.alexv.pcmote.Probe'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
