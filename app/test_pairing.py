"""Offline bootstrap parser, certificate and Android contract tests."""
import pathlib, shutil, subprocess, tempfile, unittest, os
ROOT=pathlib.Path(__file__).parent
SRC=ROOT/'src/ru/alexv/pcmote'
class PairingTests(unittest.TestCase):
 def test_strict_link_parser(self):
  source=SRC/'PairingLink.java'
  self.assertTrue(source.exists(), 'PairingLink implementation missing')
  javac=shutil.which('javac'); self.assertTrue(javac)
  java=str(pathlib.Path(javac).with_name('java.exe' if os.name=='nt' else 'java'))
  with tempfile.TemporaryDirectory() as temp:
   p=pathlib.Path(temp); harness=p/'Probe.java'
   harness.write_text('''import ru.alexv.pcmote.PairingLink;
public class Probe {
 static void bad(String s) throws Exception {try {PairingLink.parse(s);throw new AssertionError("accepted invalid link");}catch(IllegalArgumentException expected){}}
 public static void main(String[] args)throws Exception {
 String valid="pcmote://pair?v=1&host=192.168.2.7&port=8767&fp="+new String(new char[64]).replace('\\0','a')+"&ticket="+new String(new char[43]).replace('\\0','A');
 if(!PairingLink.parse(valid).host.equals("192.168.2.7"))throw new AssertionError();
 for(String host:new String[]{"127.0.0.1","8.8.8.8","0.0.0.0","172.32.1.2","10.01.1.2","localhost","192.168.2.999"})bad(valid.replace("192.168.2.7",host));
 for(String suffix:new String[]{"&v=1","&x=y","#fragment"})bad(valid+suffix);
 bad(valid.replace("8767","8765"));bad(valid.replace("pcmote:","https:"));bad(valid.replace("//pair?","//user@pair?"));bad(valid.replace("//pair?","//pair/?"));
 bad(valid.substring(0,valid.length()-1));bad(valid.substring(0,valid.length()-1)+"B");
 bad(valid.replace("host=","%68ost="));
 System.out.println("PAIRING_LINK_OK");}}
''',encoding='utf-8')
   subprocess.run([javac,'-encoding','UTF-8','-d',temp,str(source),str(harness)],check=True,capture_output=True)
   result=subprocess.run([java,'-cp',temp,'Probe'],check=True,capture_output=True,text=True)
   self.assertIn('PAIRING_LINK_OK',result.stdout)
 def test_executed_approved_broadcast_regex(self):
  import re
  source=(SRC/'PairingActivity.java').read_text(encoding='utf-8')
  pattern=re.search(r'result\.broadcast\.matches\(("[^"\n]+")\)',source).group(1)
  split=re.search(r'result\.broadcast\.split\(("[^"\n]+")\)',source).group(1)
  javac=shutil.which('javac'); java=str(pathlib.Path(javac).with_name('java.exe' if os.name=='nt' else 'java'))
  with tempfile.TemporaryDirectory() as temp:
   harness=pathlib.Path(temp)/'BroadcastProbe.java'
   harness.write_text('public class BroadcastProbe {public static void main(String[] args){String valid="192.168.7.255";if(!valid.matches('+pattern+'))throw new AssertionError("valid broadcast rejected");if(valid.split('+split+').length!=4)throw new AssertionError("IPv4 split failed");if("192x168x7x255".matches('+pattern+'))throw new AssertionError("invalid broadcast accepted");System.out.println("BROADCAST_OK");}}',encoding='utf-8')
   subprocess.run([javac,'-d',temp,str(harness)],check=True,capture_output=True)
   subprocess.run([java,'-cp',temp,'BroadcastProbe'],check=True,capture_output=True)
 def test_executed_certificate_pin(self):
  javac=shutil.which('javac'); self.assertTrue(javac)
  home=pathlib.Path(javac).parent; ext='.exe' if os.name=='nt' else ''
  with tempfile.TemporaryDirectory() as temp:
   p=pathlib.Path(temp)
   subprocess.run([str(home/('keytool'+ext)),'-genkeypair','-alias','pair','-keyalg','RSA','-keysize','2048','-validity','2','-dname','CN=pair','-keystore',str(p/'test.p12'),'-storepass','test-password','-noprompt'],check=True,capture_output=True)
   subprocess.run([str(home/('keytool'+ext)),'-exportcert','-alias','pair','-keystore',str(p/'test.p12'),'-storepass','test-password','-file',str(p/'cert.der')],check=True,capture_output=True)
   harness=p/'CertProbe.java'
   harness.write_text('''import ru.alexv.pcmote.PairingClient;import java.security.cert.*;import java.security.*;import java.nio.file.*;
public class CertProbe {public static void main(String[] a)throws Exception{
 X509Certificate c=(X509Certificate)CertificateFactory.getInstance("X.509").generateCertificate(Files.newInputStream(Paths.get(a[0])));
 StringBuilder fp=new StringBuilder();for(byte b:MessageDigest.getInstance("SHA-256").digest(c.getEncoded()))fp.append(String.format("%02x",b));
 PairingClient.verifyCertificate(c,fp.toString());
 try{PairingClient.verifyCertificate(c,new String(new char[64]).replace('\\0','0'));throw new AssertionError();}catch(CertificateException expected){}
 System.out.println("PIN_EXECUTED_OK");}}
''',encoding='utf-8')
   subprocess.run([javac,'-d',temp,str(SRC/'PairingLink.java'),str(SRC/'PairingClient.java'),str(harness)],check=True,capture_output=True)
   result=subprocess.run([str(home/('java'+ext)),'-cp',temp,'CertProbe',str(p/'cert.der')],check=True,capture_output=True,text=True)
   self.assertIn('PIN_EXECUTED_OK',result.stdout)
 def test_transport_and_activity_contract(self):
  p=SRC/'PairingClient.java'; self.assertTrue(p.exists(),'Pinned transport missing')
  text=p.read_text(encoding='utf-8')
  for required in ('setSSLSocketFactory','setHostnameVerifier','setInstanceFollowRedirects(false)','checkValidity','RSAPublicKey','MessageDigest.isEqual','8192'):
   self.assertIn(required,text)
  self.assertNotIn('setDefaultSSLSocketFactory',text)
  self.assertNotIn('setDefaultHostnameVerifier',text)
  activity=(SRC/'PairingActivity.java').read_text(encoding='utf-8')
  for required in ('FLAG_SECURE','setSaveEnabled(false)','setData(null)','shutdownNow','commit()','/pair/v1/claim','/pair/v1/status','/pair/v1/ack'):
   self.assertIn(required,activity)
  self.assertNotIn('getMessage()',activity)
  self.assertIn('edit.putLong("pair_revision"',activity)
  main=(SRC/'MainActivity.java').read_text(encoding='utf-8')
  resume=main[main.index('protected void onResume()'):main.index('protected void onPause()')]
  self.assertIn('loadedPairRevision != currentPairRevision',resume)
  self.assertIn('editKey.setText(currentPairKey)',resume)
  self.assertIn('loadedPairRevision = currentPairRevision',resume)
  self.assertIn('Thread.sleep(3000)',activity, 'Poll cadence exceeds server rate budget')
if __name__=='__main__':unittest.main(verbosity=2)
