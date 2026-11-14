"""Public build uses only server-provided applications."""
import pathlib, re, unittest
ROOT=pathlib.Path(__file__).parent
class AppsTests(unittest.TestCase):
 def test_no_lambda_requires_desugaring_and_visible_brand(self):
  for source in (ROOT/'src').rglob('*.java'):
   for line in source.read_text(encoding='utf-8').splitlines():
    # Ignore documentation arrows and string literals such as WOL log output.
    code=re.sub(r'"(?:[^"\\\\]|\\\\.)*"','""',line).strip()
    if code.startswith(('*','//')):continue
    self.assertNotIn('->',code, str(source.name)+' requires unsupported lambda desugaring')
    self.assertNotIn('::',code, str(source.name)+' requires unsupported method-reference desugaring')
  for folder in ('values','values-en'):
   text=(ROOT/'res'/folder/'strings.xml').read_text(encoding='utf-8')
   self.assertIn('<string name="app_name">PConDistance</string>',text)
   self.assertNotIn('VzaimoPult',text)
   self.assertNotIn('ВзаимоПульт',text)

 def test_dynamic_catalog_privacy_and_limits(self):
  text=(ROOT/'src/ru/alexv/pcmote/MainActivity.java').read_text(encoding='utf-8')
  self.assertNotIn('APP_IDS',text,'Static personal applications remain')
  for item in ('/apps?key=', '65536', 'can_close', 'apps_empty', 'appsGeneration'):
   self.assertIn(item,text)
  for folder in ('values','values-en'):
   resources=(ROOT/'res'/folder/'strings.xml').read_text(encoding='utf-8')
   self.assertNotIn('name="app_zapret"',resources)
  self.assertFalse(list((ROOT/'res').rglob('ic_app_*.png')))
if __name__=='__main__':unittest.main()
