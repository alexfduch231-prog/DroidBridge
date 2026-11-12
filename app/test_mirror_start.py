"""Offline socket tests and Android wiring contracts for phone-initiated casting."""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).parent
SRC = ROOT / 'src/ru/alexv/pcmote'


class MirrorStartTests(unittest.TestCase):
    def test_activity_hands_granted_projection_and_pair_to_service_without_http(self):
        text = (SRC / 'MainActivity.java').read_text(encoding='utf-8')
        start = text.index('if (requestCode != REQ_PROJECTION) return;')
        end = text.index('// ---------- состояние ПК', start)
        mirror = text[start:end]
        self.assertNotIn('/mirror?', mirror)
        self.assertNotIn('httpGet(', mirror)
        self.assertIn('startMirrorService(code, grant, key, host)', mirror)
        self.assertIn('.putExtra(MirrorService.EXTRA_HOST, host)', mirror)
        self.assertLess(mirror.index('resultCode != RESULT_OK'), mirror.index('startMirrorService(code'))

    def test_service_notifies_only_after_projection_and_listener_ready(self):
        text = (SRC / 'MirrorService.java').read_text(encoding='utf-8')
        self.assertIn('EXTRA_HOST', text)
        self.assertLess(text.index('if (projection == null)'), text.index('netThread.start()'))
        serve = text[text.index('private void serve('):text.index('private void readControls(')]
        self.assertLess(serve.index('listener.bind('), serve.index('startPcNotifier('))
        self.assertLess(serve.index('startPcNotifier('), serve.index('listener.accept()'))
        self.assertIn('pcNotifyThread.interrupt()', text)
        self.assertLess(text.index('if (running || stopped.get())'), text.index('if (intent == null)'))
        self.assertIn('notifier.notifyPc(', text)
        self.assertIn('mirror_view_only', (SRC / 'MainActivity.java').read_text(encoding='utf-8'))

    def test_service_closes_locally_owned_sockets_even_when_stop_precedes_bind(self):
        text = (SRC / 'MirrorService.java').read_text(encoding='utf-8')
        serve = text[text.index('private void serve('):text.index('private void readControls(')]
        self.assertIn('finally {', serve)
        self.assertIn('listener.close()', serve)
        self.assertIn('accepted.close()', serve)
        self.assertIn('server = listener', serve)
        self.assertIn('accepted = listener.accept()', serve)

    def test_real_http_request_authentication_status_and_cancellation(self):
        source = SRC / 'MirrorPcNotifier.java'
        self.assertTrue(source.exists(), 'service-owned PC notifier is missing')
        with tempfile.TemporaryDirectory() as d:
            probe = pathlib.Path(d) / 'Probe.java'
            probe.write_text('''package ru.alexv.pcmote;
import java.net.*;import java.io.*;import java.util.concurrent.atomic.*;
public class Probe {
 public static void main(String[] args)throws Exception {
  if(MirrorPcNotifier.retryDelay(0)!=1000||MirrorPcNotifier.retryDelay(1)!=2000||MirrorPcNotifier.retryDelay(2)!=4000||MirrorPcNotifier.retryDelay(3)!=-1)throw new AssertionError("retry bounds");
  MirrorPcNotifier notifier=new MirrorPcNotifier();
  final AtomicBoolean alive=new AtomicBoolean(true);
  MirrorPcNotifier.Alive active=new MirrorPcNotifier.Alive(){public boolean isAlive(){return alive.get();}};
  ServerSocket server=new ServerSocket(0,1,InetAddress.getByName("127.0.0.1"));
  final AtomicReference<Throwable> error=new AtomicReference<Throwable>();
  Thread peer=new Thread(new Runnable(){public void run(){try{
   Socket socket=server.accept();socket.setSoTimeout(4000);
   BufferedReader in=new BufferedReader(new InputStreamReader(socket.getInputStream(),"UTF-8"));
   String line=in.readLine();
   if(!line.equals("GET /mirror?port=8768&key=a%2Bb%26c HTTP/1.1"))throw new AssertionError(line);
   while(!(line=in.readLine()).isEmpty()){}
   socket.getOutputStream().write("HTTP/1.1 200 OK\\r\\nContent-Length: 2\\r\\nConnection: close\\r\\n\\r\\nOK".getBytes("UTF-8"));socket.close();
  }catch(Throwable e){error.set(e);}}});peer.start();
  if(!notifier.notifyPc("127.0.0.1",server.getLocalPort(),"a+b&c",8768,active))throw new AssertionError("not accepted");
  peer.join(5000);server.close();if(peer.isAlive())throw new AssertionError("worker stuck");if(error.get()!=null)throw new AssertionError(error.get());
  alive.set(false);long began=System.currentTimeMillis();
  if(notifier.notifyPc("127.0.0.1",1,"secret",8768,active))throw new AssertionError("cancel success");
  if(System.currentTimeMillis()-began>500)throw new AssertionError("cancel not immediate");
  if(notifier.request("127.0.0.1",1,"secret",8768))throw new AssertionError("closed port success");
  notifier.cancel();if(notifier.request("127.0.0.1",1,"secret",8768))throw new AssertionError("cancelled request");
  for(final int status:new int[]{302,403,500}) {
   final ServerSocket rejected=new ServerSocket(0,1,InetAddress.getByName("127.0.0.1"));
   Thread reject=new Thread(new Runnable(){public void run(){try{Socket s=rejected.accept();s.setSoTimeout(3000);BufferedReader r=new BufferedReader(new InputStreamReader(s.getInputStream()));while(!r.readLine().isEmpty()){}s.getOutputStream().write(("HTTP/1.1 "+status+" Rejected\\r\\nLocation: http://127.0.0.1:1/leak\\r\\nContent-Length: 0\\r\\nConnection: close\\r\\n\\r\\n").getBytes("UTF-8"));s.close();}catch(Exception e){error.set(e);}}});reject.start();
   if(new MirrorPcNotifier().request("127.0.0.1",rejected.getLocalPort(),"secret",8768))throw new AssertionError("accepted "+status);
   reject.join(5000);rejected.close();if(reject.isAlive())throw new AssertionError("reject stuck");if(error.get()!=null)throw new AssertionError(error.get());
  }
  System.out.println("MIRROR_NOTIFY_OK");
 }
}''', encoding='utf-8')
            javac = shutil.which('javac')
            self.assertIsNotNone(javac)
            java = str(pathlib.Path(javac).with_name('java.exe' if os.name == 'nt' else 'java'))
            result = subprocess.run([javac, '-encoding', 'UTF-8', '-d', d, str(source), str(probe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([java, '-cp', d, 'ru.alexv.pcmote.Probe'], capture_output=True, text=True, timeout=25)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('MIRROR_NOTIFY_OK', result.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
