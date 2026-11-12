"""Offline navigation behavior and resource contracts; no device/UI claim."""
import pathlib, subprocess, tempfile, shutil, unittest, xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).parent
SRC=ROOT/'src/ru/alexv/pcmote'
A='{http://schemas.android.com/apk/res/android}'
class NavigationTests(unittest.TestCase):
 def test_drawer_motion_geometry_reversal_and_stale_completion(self):
  source=SRC/'DrawerMotion.java';self.assertTrue(source.exists(),'drawer motion missing')
  with tempfile.TemporaryDirectory() as d:
   probe=pathlib.Path(d)/'MotionProbe.java'
   probe.write_text('''import ru.alexv.pcmote.DrawerMotion;
public class MotionProbe { public static void main(String[] a) {
 DrawerMotion m=new DrawerMotion(); int old=m.begin(true); m.move(.4f);
 if(Math.abs(m.translation(300)+180)>0.01 || Math.abs(m.dimAlpha()-.4f)>0.01)throw new AssertionError("geometry");
 int next=m.begin(false); if(m.finish(old)||m.progress()!=.4f)throw new AssertionError("stale end");
 if(!m.finish(next)||m.progress()!=0)throw new AssertionError("reverse finish");
 m.move(2);if(m.progress()!=1)throw new AssertionError("upper clamp");m.move(-1);if(m.progress()!=0)throw new AssertionError("lower clamp");
 if(!DrawerMotion.settle(.6f,0,500)||DrawerMotion.settle(.4f,0,500))throw new AssertionError("threshold");
 if(DrawerMotion.settle(.9f,-600,500)||!DrawerMotion.settle(.1f,600,500))throw new AssertionError("velocity");
 if(DrawerMotion.duration(0,1,0)!=0||DrawerMotion.duration(0,1,1)!=240||DrawerMotion.duration(.5f,1,1)!=120)throw new AssertionError("duration/reduced motion");
 old=m.begin(true);m.cancel();if(m.finish(old))throw new AssertionError("cancel stale end");
 }}''',encoding='utf-8')
   r=subprocess.run([shutil.which('javac'),'-d',d,str(source),str(probe)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
   java=str(pathlib.Path(shutil.which('javac')).with_name('java.exe'))
   r=subprocess.run([java,'-cp',d,'MotionProbe'],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
 def test_native_drawer_animation_gesture_and_close_icon_contract(self):
  host=SRC/'DrawerHost.java';self.assertTrue(host.exists(),'gesture host missing')
  text=host.read_text(encoding='utf-8')
  for token in ['ValueAnimator','onInterceptTouchEvent','VelocityTracker','ACTION_CANCEL','ANIMATOR_DURATION_SCALE','areAnimatorsEnabled','DecelerateInterpolator','setTranslationX','setAlpha','onDetachedFromWindow']:
   self.assertIn(token,text)
  self.assertIn('downProgress = motion.progress(); downX = event.getX(index);',text,'intercept must rebase at the currently visible animation position')
  root=ET.parse(ROOT/'res/layout/main.xml').getroot();self.assertEqual(root.tag,'ru.alexv.pcmote.DrawerHost')
  close=next(e for e in root.iter() if e.get(A+'id')=='@+id/drawer_close')
  self.assertEqual(close.tag,'ImageButton');self.assertEqual(close.get(A+'contentDescription'),'@string/nav_close')
  self.assertEqual(close.get(A+'layout_width'),'48dp');self.assertEqual(close.get(A+'src'),'@drawable/ic_close')
 def test_section_state(self):
  source=SRC/'NavigationState.java'
  self.assertTrue(source.exists(),'section state missing')
  with tempfile.TemporaryDirectory() as d:
   probe=pathlib.Path(d)/'NavProbe.java'
   probe.write_text('''import ru.alexv.pcmote.NavigationState;
public class NavProbe { public static void main(String[] args) {
 NavigationState n=new NavigationState();
 if(n.section()!=0 || n.isDrawerOpen()) throw new AssertionError("default");
 n.openDrawer(); if(!n.back() || n.isDrawerOpen() || n.back()) throw new AssertionError("back");
 n.select(1,120); n.select(4,300); if(n.select(0,40)!=120) throw new AssertionError("scroll");
 if(n.select(1,75)!=300) throw new AssertionError("independent scroll");
 n.openDrawer(); n.rememberScroll(222); if(!n.isDrawerOpen() || n.positions()[1]!=222)throw new AssertionError("save keeps drawer state");
 n.select(1,320); if(n.isDrawerOpen() || n.section()!=1)throw new AssertionError("selection");
 n.restore(99,new int[]{1}); if(n.section()!=0) throw new AssertionError("invalid restore");
 n.restore(4,new int[]{1,2,3,4,5}); if(n.section()!=4 || n.positions()[4]!=5)throw new AssertionError("restore");
 }}''',encoding='utf-8')
   r=subprocess.run([shutil.which('javac'),'-d',d,str(source),str(probe)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
   java=str(pathlib.Path(shutil.which('javac')).with_name('java.exe'))
   r=subprocess.run([java,'-cp',d,'NavProbe'],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
 def test_sections_and_accessible_scrollable_drawer(self):
  root=ET.parse(ROOT/'res/layout/main.xml').getroot(); ids={e.get(A+'id'):e for e in root.iter() if e.get(A+'id')}
  all_ids=[e.get(A+'id') for e in root.iter() if e.get(A+'id')];self.assertEqual(len(all_ids),len(set(all_ids)))
  for section in ['control','programs','files','broadcast','settings']:
   self.assertIn('@+id/section_'+section,ids); self.assertIn('@+id/nav_'+section,ids)
  self.assertEqual(ids['@+id/drawer_scroll'].tag,'ScrollView')
  for key in ['btn_menu','drawer_close','nav_control','nav_programs','nav_files','nav_broadcast','nav_settings']:
   self.assertEqual(ids['@+id/'+key].get(A+'minHeight'),'48dp')
   self.assertEqual(ids['@+id/'+key].get(A+'layout_height'),'wrap_content')
  self.assertIn('@+id/drawer_version',ids);self.assertIn('@+id/btn_check_updates',ids)
  main=(SRC/'MainActivity.java').read_text(encoding='utf-8')
  for token in ['onBackPressed()', 'onSaveInstanceState(Bundle', 'getPackageInfo(getPackageName(), 0).versionName', 'startupUpdate.checkManually()', 'IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS']:
   self.assertIn(token,main)
 def test_version_footer_is_reserved_outside_weighted_scroll(self):
  root=ET.parse(ROOT/'res/layout/main.xml').getroot()
  panel=next(e for e in root.iter() if e.get(A+'id')=='@+id/drawer_panel')
  children=list(panel); footer=children[-1]
  self.assertEqual(footer.get(A+'id'),'@+id/drawer_version','footer needs its own measured bottom slot, not weighted ScrollView child')
  self.assertEqual(footer.get(A+'layout_height'),'wrap_content')
  self.assertEqual(footer.get(A+'minHeight'),'48dp')
  self.assertEqual(footer.get(A+'includeFontPadding'),'true')
  self.assertEqual(footer.get(A+'paddingBottom'),'16dp')
  self.assertEqual(children[-2].get(A+'id'),'@+id/drawer_scroll')
  self.assertFalse(any(e.tag=='Space' and e.get(A+'layout_weight') for e in panel.iter()))
 def test_manual_update_does_not_bypass_validation(self):
  text=(SRC/'StartupUpdate.java').read_text(encoding='utf-8')
  for token in ['public void checkManually()', 'checkForUpdates(final boolean manual)', 'update_latest', 'update_check_failed', 'update_busy']:
   self.assertIn(token,text)
 def test_pause_clears_prestart_download_flag(self):
  text=(SRC/'StartupUpdate.java').read_text(encoding='utf-8')
  pause=text[text.index('    public void onPause(){'):text.index('    public void dispose()')]
  harness='''public class PauseProbe {
 static class Dialog {void dismiss(){}} static class Connection {void disconnect(){}}
 static class Prefs {Prefs edit(){return this;} Prefs remove(String key){return this;} boolean commit(){return true;}}
 static class Activity {Prefs getSharedPreferences(String s,int n){return new Prefs();}}
 static class HttpsURLConnection extends Connection {}
 boolean active=true,cancelled,downloading=true; Activity activity=new Activity(); HttpsURLConnection connection; Thread worker; Dialog dialog,progress;
 static String PREFS="prefs"; static java.util.concurrent.atomic.AtomicInteger EPOCH=new java.util.concurrent.atomic.AtomicInteger();
 '''+pause+'''
 public static void main(String[] args){PauseProbe p=new PauseProbe(); p.onPause(); if(p.downloading||p.active||!p.cancelled)throw new AssertionError("cancelled prestart download remains busy");}
 }'''
  with tempfile.TemporaryDirectory() as d:
   source=pathlib.Path(d)/'PauseProbe.java'; source.write_text(harness,encoding='utf-8')
   result=subprocess.run([shutil.which('javac'),'-d',d,str(source)],capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr)
   java=str(pathlib.Path(shutil.which('javac')).with_name('java.exe'))
   result=subprocess.run([java,'-cp',d,'PauseProbe'],capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr)
 def test_async_program_scroll_restore_contract(self):
  text=(SRC/'MainActivity.java').read_text(encoding='utf-8')
  for token in ['pendingProgramScroll', 'currentSectionScroll()', 'restoreSectionScroll(final int y)', 'scrollRestoreRevision', 'MotionEvent.ACTION_DOWN', 'restoreSectionScroll(pendingProgramScroll)']:
   self.assertIn(token,text)
  loader=text[text.index('    private void loadApps()'):text.index('    private void cancelAppIcons()')]
  self.assertLess(loader.index('currentSectionScroll()'),loader.index('remoteApps.clear()'))
  self.assertGreater(loader.index('restoreSectionScroll(pendingProgramScroll)'),loader.index('final boolean loaded'))
 def test_permission_dialog_allows_manual_retry_after_dismiss(self):
  text=(SRC/'StartupUpdate.java').read_text(encoding='utf-8')
  method=text[text.index('    private void requestInstall(){'):text.index('    private void installVerified(){')]
  harness='''public class PermissionProbe {
 interface DialogInterface { interface OnClickListener {void onClick(DialogInterface d,int which);} interface OnDismissListener {void onDismiss(DialogInterface d);} }
 static class AlertDialog implements DialogInterface {
  DialogInterface.OnDismissListener dismiss;
  void show(){} void dismiss(){if(dismiss!=null)dismiss.onDismiss(this);}
  void setOnDismissListener(DialogInterface.OnDismissListener l){dismiss=l;}
  static class Builder {Builder(Object a){} Builder setMessage(int x){return this;} Builder setPositiveButton(int x,DialogInterface.OnClickListener l){return this;} Builder setNegativeButton(int x,DialogInterface.OnClickListener l){return this;} AlertDialog create(){return new AlertDialog();}}
 }
 static class Build {static class VERSION {static int SDK_INT=34;}}
 static class R {static class string {static int update_permission=1,update_now=2,update_later=3;}}
 static class Settings {static String ACTION_MANAGE_UNKNOWN_APP_SOURCES="permission";}
 static class Uri {static Uri parse(String x){return new Uri();}}
 static class Intent {Intent(String a,Uri b){}}
 static class Prefs {Prefs edit(){return this;} Prefs putBoolean(String k,boolean v){return this;} boolean commit(){return true;}}
 static class Activity {Activity getPackageManager(){return this;} boolean canRequestPackageInstalls(){return false;} Prefs getSharedPreferences(String s,int n){return new Prefs();} String getPackageName(){return "app";} void startActivity(Intent i){}}
 static String PREFS="prefs"; Activity activity=new Activity(); AlertDialog dialog; void installVerified(){throw new AssertionError("must keep permission consent");}
 '''+method+'''
 public static void main(String[] args){PermissionProbe p=new PermissionProbe(); p.requestInstall(); AlertDialog first=p.dialog; first.dismiss(); if(p.dialog!=null)throw new AssertionError("dismissed permission dialog blocks manual retry"); p.requestInstall(); if(p.dialog==null||p.dialog==first)throw new AssertionError("retry");}
 }'''
  with tempfile.TemporaryDirectory() as d:
   source=pathlib.Path(d)/'PermissionProbe.java'; source.write_text(harness,encoding='utf-8')
   result=subprocess.run([shutil.which('javac'),'-d',d,str(source)],capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr)
   java=str(pathlib.Path(shutil.which('javac')).with_name('java.exe'))
   result=subprocess.run([java,'-cp',d,'PermissionProbe'],capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr)
 def test_device_system_fonts(self):
  for path in (ROOT/'res').rglob('*.xml'):
   self.assertNotIn('fontFamily',path.read_text(encoding='utf-8'),str(path))
  self.assertFalse(list(ROOT.rglob('*.ttf'))+list(ROOT.rglob('*.otf')))
  for path in SRC.glob('*.java'):
   text=path.read_text(encoding='utf-8')
   self.assertNotIn('Typeface.createFromAsset',text); self.assertNotIn('fontScale =',text)
if __name__=='__main__':unittest.main(verbosity=2)
