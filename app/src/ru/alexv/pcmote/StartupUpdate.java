package ru.alexv.pcmote;

import android.app.*;
import android.content.*;
import android.content.pm.*;
import android.net.Uri;
import android.os.*;
import android.provider.Settings;
import android.util.Base64;
import java.io.*;
import java.net.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;
import javax.net.ssl.HttpsURLConnection;

/** Voluntary foreground-only update flow. Network failures never affect local control. */
public final class StartupUpdate {
    static final String PREFS="startup_update";
    private static final String INSTALLED_CERT="6e1f9c7b0ece3723d929a5f4d3bfeb502393c85199dea6e7c82d18a7dd5377a0";
    private static final AtomicBoolean CHECKED=new AtomicBoolean();
    private static final Object WORK_LOCK=new Object();
    private static final java.util.concurrent.atomic.AtomicInteger EPOCH=new java.util.concurrent.atomic.AtomicInteger();
    private final ThreadLocal<Integer> taskEpoch=new ThreadLocal<Integer>();
    private int epoch;
    private static volatile byte[] pendingEnvelope;
    private final Activity activity;
    private final Handler ui=new Handler(Looper.getMainLooper());
    private volatile boolean cancelled,active,disposed;
    private volatile HttpsURLConnection connection;
    private volatile Thread worker;
    private AlertDialog dialog;
    private ProgressDialog progress;
    private boolean downloading;
    private long deadline;
    public StartupUpdate(Activity activity){this.activity=activity;}
    public void onResume(){
        active=true;cancelled=false;
        if(activity.getSharedPreferences(PREFS,0).getBoolean("awaiting_permission",false)){
            activity.getSharedPreferences(PREFS,0).edit().putBoolean("awaiting_permission",false).commit();
            if(Build.VERSION.SDK_INT<26||activity.getPackageManager().canRequestPackageInstalls())installVerified();
            return;
        }
        if(pendingEnvelope!=null){offer(pendingEnvelope);return;}
        if(CHECKED.compareAndSet(false,true))checkForUpdates(false);
    }
    /** Explicit user action uses the same signed feed, validation and installer consent. */
    public void checkManually(){
        if(!active||disposed)return;
        // Never reset cancellation or epoch while an older task is still unwinding.
        if(downloading||progress!=null||dialog!=null||worker!=null&&worker.isAlive()){
            message(R.string.update_busy);return;
        }
        CHECKED.set(true);
        if(pendingEnvelope!=null){offer(pendingEnvelope);return;}
        message(R.string.update_checking);
        checkForUpdates(true);
    }
    private void message(int resource){android.widget.Toast.makeText(activity,resource,android.widget.Toast.LENGTH_LONG).show();}
    private void checkForUpdates(final boolean manual){
        start(new Runnable(){public void run(){
            try{
                cleanup(activity);
                final byte[] envelope=fetchManifest();final UpdateManifest m=checkedManifest(activity,envelope);
                check();
                // Persist rollback floor only after complete signed schema and installed-identity checks.
                if(!activity.getSharedPreferences(PREFS,0).edit().putLong("max_sequence",m.sequence).commit())throw new IOException("Metadata unavailable");
                PackageInfo installed=activity.getPackageManager().getPackageInfo(activity.getPackageName(),0);
                if(m.isNewer(version(installed))&&m.minSdk<=Build.VERSION.SDK_INT){
                    post(new Runnable(){public void run(){pendingEnvelope=envelope;offer(envelope);}});
                }else if(manual){
                    final int result=m.isNewer(version(installed))?R.string.update_incompatible:R.string.update_latest;
                    post(new Runnable(){public void run(){message(result);}});
                }
            }catch(Exception ignored){
                if(manual)post(new Runnable(){public void run(){message(R.string.update_check_failed);}});
                // Automatic startup failures remain silent.
            }
        }});
    }
    public void onPause(){
        active=false;cancelled=true;EPOCH.incrementAndGet();HttpsURLConnection c=connection;if(c!=null)c.disconnect();Thread t=worker;if(t!=null)t.interrupt();
        if(dialog!=null){dialog.dismiss();dialog=null;}if(progress!=null){progress.dismiss();progress=null;}
        // An APK being handed to system UI must remain available through its URI grant.
        if(downloading){activity.getSharedPreferences(PREFS,0).edit().remove("verified_envelope").commit();}
        // The worker may have been cancelled before entering download's try/finally.
        // Keep worker.isAlive() as the retry gate while it unwinds, not this UI flag.
        downloading=false;
    }
    public void dispose(){disposed=true;onPause();ui.removeCallbacksAndMessages(null);}
    private void start(final Runnable work){
        cancelled=false;final int generation=EPOCH.incrementAndGet();epoch=generation;
        worker=new Thread(new Runnable(){public void run(){synchronized(WORK_LOCK){
            if(EPOCH.get()!=generation||disposed||!active)return;
            taskEpoch.set(Integer.valueOf(generation));deadline=SystemClock.elapsedRealtime()+600000L;
            try{work.run();}finally{taskEpoch.remove();}
        }}},"startup-update");worker.start();
    }
    private void post(final Runnable r){Integer task=taskEpoch.get();final int generation=task==null?epoch:task.intValue();ui.post(new Runnable(){public void run(){if(EPOCH.get()==generation&&active&&!disposed&&!cancelled&&!activity.isFinishing()&&!activity.isDestroyed())r.run();}});}
    private void check()throws IOException{Integer task=taskEpoch.get();if(cancelled||task==null||EPOCH.get()!=task.intValue()||Thread.currentThread().isInterrupted()||SystemClock.elapsedRealtime()>deadline)throw new IOException("Update cancelled");}
    private void offer(final byte[] envelope){
        if(envelope==null||dialog!=null||downloading||!active)return;
        try{
            final UpdateManifest m=checkedManifest(activity,envelope);
            if(!m.isNewer(version(activity.getPackageManager().getPackageInfo(activity.getPackageName(),0)))){pendingEnvelope=null;return;}
            dialog=new AlertDialog.Builder(activity).setTitle(R.string.update_title).setMessage(activity.getString(R.string.update_available,m.versionName))
                .setPositiveButton(R.string.update_now,new DialogInterface.OnClickListener(){public void onClick(DialogInterface d,int which){dialog=null;pendingEnvelope=null;download(envelope,m);}})
                .setNegativeButton(R.string.update_later,new DialogInterface.OnClickListener(){public void onClick(DialogInterface d,int which){pendingEnvelope=null;dialog=null;}})
                .setOnCancelListener(new DialogInterface.OnCancelListener(){public void onCancel(DialogInterface d){pendingEnvelope=null;dialog=null;}}).create();dialog.show();
        }catch(Exception ignored){pendingEnvelope=null;}
    }
    private HttpsURLConnection open(String initial)throws Exception{
        URI u=UpdateManifest.redirectUrl(initial);
        for(int redirects=0;;redirects++){
            check();HttpsURLConnection c=(HttpsURLConnection)u.toURL().openConnection();connection=c;
            c.setInstanceFollowRedirects(false);c.setConnectTimeout(10000);c.setReadTimeout(20000);c.setRequestProperty("Accept-Encoding","identity");
            int code=c.getResponseCode();check();
            if(code==301||code==302||code==303||code==307||code==308){String location=c.getHeaderField("Location");c.disconnect();if(redirects>=5||location==null)throw new IOException("Redirect rejected");u=UpdateManifest.redirectUrl(u.resolve(location).toString());continue;}
            if(code!=200){c.disconnect();throw new IOException("Update unavailable");}
            String encoding=c.getHeaderField("Content-Encoding");if(encoding!=null&&!encoding.equalsIgnoreCase("identity")){c.disconnect();throw new IOException("Encoding rejected");}return c;
        }
    }
    private static long contentLength(HttpsURLConnection c)throws IOException{String s=c.getHeaderField("Content-Length");if(s==null)return -1;try{long n=Long.parseLong(s);if(n<0)throw new NumberFormatException();return n;}catch(NumberFormatException e){throw new IOException("Invalid length");}}
    private byte[] fetchManifest()throws Exception{
        HttpsURLConnection c=open(UpdateManifest.FEED);try{
            long length=contentLength(c);if(length>65536)throw new IOException("Manifest too large");
            ByteArrayOutputStream out=new ByteArrayOutputStream();InputStream in=c.getInputStream();try{byte[] b=new byte[4096];int n;while((n=in.read(b))!=-1){check();if(out.size()+n>65536)throw new IOException("Manifest too large");out.write(b,0,n);}}finally{in.close();}
            if(length>=0&&length!=out.size())throw new IOException("Truncated manifest");return out.toByteArray();
        }finally{c.disconnect();connection=null;}
    }
    private void download(final byte[] envelope,final UpdateManifest m){
        downloading=true;progress=new ProgressDialog(activity);progress.setTitle(R.string.update_progress);progress.setProgressStyle(ProgressDialog.STYLE_HORIZONTAL);progress.setMax(100);progress.setCancelable(true);
        progress.setButton(DialogInterface.BUTTON_NEGATIVE,activity.getString(R.string.update_cancel),new DialogInterface.OnClickListener(){public void onClick(DialogInterface d,int which){cancelDownload();}});
        progress.setOnCancelListener(new DialogInterface.OnCancelListener(){public void onCancel(DialogInterface d){cancelDownload();}});progress.show();
        start(new Runnable(){public void run(){File part=new File(directory(activity),"update.part");boolean success=false;try{
            cleanup(activity);File dir=directory(activity);if(!dir.isDirectory()&&!dir.mkdirs())throw new IOException("Cache unavailable");
            HttpsURLConnection c=open(m.url);try{
                long declared=contentLength(c);if(declared>=0&&declared!=m.size)throw new IOException("Size mismatch");
                MessageDigest hash=MessageDigest.getInstance("SHA-256");long total=0;InputStream in=c.getInputStream();FileOutputStream out=new FileOutputStream(part);
                try{byte[] b=new byte[32768];int n;while((n=in.read(b))!=-1){check();total+=n;if(total>m.size)throw new IOException("Oversized update");out.write(b,0,n);hash.update(b,0,n);final int pct=(int)(total*100/m.size);post(new Runnable(){public void run(){if(progress!=null)progress.setProgress(pct);}});}out.getFD().sync();}finally{try{in.close();}finally{out.close();}}
                check();if(total!=m.size||!hex(hash.digest()).equals(m.sha256))throw new IOException("Update hash mismatch");
            }finally{c.disconnect();connection=null;}
            validateApk(activity,part,m);check();File apk=apk(activity);if(!part.renameTo(apk))throw new IOException("Cache rename failed");
            if(!apk.setReadOnly())throw new IOException("Cannot protect cached APK");
            if(!activity.getSharedPreferences(PREFS,0).edit().putString("verified_envelope",Base64.encodeToString(envelope,Base64.NO_WRAP)).commit())throw new IOException("Metadata unavailable");
            check();success=true;post(new Runnable(){public void run(){downloading=false;dismissProgress();requestInstall();}});
        }catch(Exception ignored){post(new Runnable(){public void run(){downloading=false;dismissProgress();new AlertDialog.Builder(activity).setMessage(R.string.update_failed).setPositiveButton(android.R.string.ok,null).show();}});
        }finally{part.delete();if(!success)cleanup(activity);downloading=false;}}});
    }
    private void cancelDownload(){cancelled=true;HttpsURLConnection c=connection;if(c!=null)c.disconnect();Thread t=worker;if(t!=null)t.interrupt();dismissProgress();}
    private void dismissProgress(){if(progress!=null){progress.dismiss();progress=null;}}
    private void requestInstall(){
        if(Build.VERSION.SDK_INT>=26&&!activity.getPackageManager().canRequestPackageInstalls()){
            dialog=new AlertDialog.Builder(activity).setMessage(R.string.update_permission).setPositiveButton(R.string.update_now,new DialogInterface.OnClickListener(){public void onClick(DialogInterface d,int which){
                dialog=null;activity.getSharedPreferences(PREFS,0).edit().putBoolean("awaiting_permission",true).commit();
                try{activity.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,Uri.parse("package:"+activity.getPackageName())));}catch(Exception ignored){activity.getSharedPreferences(PREFS,0).edit().putBoolean("awaiting_permission",false).commit();}
            }}).setNegativeButton(R.string.update_later,null).create();
            dialog.setOnDismissListener(new DialogInterface.OnDismissListener(){public void onDismiss(DialogInterface dismissed){
                if(dialog==dismissed)dialog=null;
            }});
            dialog.show();return;
        }installVerified();
    }
    private void installVerified(){start(new Runnable(){public void run(){try{
        verifyCached(activity);post(new Runnable(){public void run(){try{
            Intent i=new Intent(Intent.ACTION_INSTALL_PACKAGE);i.setDataAndType(Uri.parse("content://"+activity.getPackageName()+".updates/update.apk"),"application/vnd.android.package-archive");
            i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);i.setClipData(ClipData.newRawUri("Verified update",i.getData()));activity.startActivity(i);
        }catch(Exception ignored){cleanup(activity);}}});
    }catch(Exception ignored){cleanup(activity);}}});}
    static File directory(Context c){return new File(c.getCacheDir(),"startup-update");}
    static File apk(Context c){return new File(directory(c),"update.apk");}
    static void cleanup(Context c){c.getSharedPreferences(PREFS,0).edit().remove("verified_envelope").commit();apk(c).delete();new File(directory(c),"update.part").delete();}
    static long version(PackageInfo p){return Build.VERSION.SDK_INT>=28?p.getLongVersionCode():p.versionCode;}
    static Set<String> certs(PackageInfo p)throws Exception{
        android.content.pm.Signature[] signatures;
        if(Build.VERSION.SDK_INT>=28){if(p.signingInfo==null)throw new SecurityException();signatures=p.signingInfo.getApkContentsSigners();}else signatures=p.signatures;
        if(signatures==null||signatures.length==0)throw new SecurityException();Set<String> result=new HashSet<String>();for(android.content.pm.Signature s:signatures)result.add(hex(MessageDigest.getInstance("SHA-256").digest(s.toByteArray())));return result;
    }
    static int signatureFlags(){return Build.VERSION.SDK_INT>=28?PackageManager.GET_SIGNING_CERTIFICATES:PackageManager.GET_SIGNATURES;}
    static UpdateManifest checkedManifest(Context c,byte[] envelope)throws Exception{
        UpdateManifest m=UpdateManifest.verify(envelope,System.currentTimeMillis(),c.getSharedPreferences(PREFS,0).getLong("max_sequence",0));
        PackageInfo installed=c.getPackageManager().getPackageInfo(c.getPackageName(),signatureFlags());
        Set<String> current=certs(installed);
        if(!current.equals(Collections.singleton(INSTALLED_CERT))||!current.equals(m.signerCertSha256))throw new SecurityException();return m;
    }
    static void validateApk(Context c,File file,UpdateManifest m)throws Exception{
        PackageManager pm=c.getPackageManager();PackageInfo p=pm.getPackageArchiveInfo(file.getAbsolutePath(),signatureFlags());PackageInfo installed=pm.getPackageInfo(c.getPackageName(),signatureFlags());
        if(p==null||!c.getPackageName().equals(p.packageName)||!m.packageName.equals(p.packageName)||version(p)!=m.versionCode||!m.isNewer(version(installed))||!m.versionName.equals(p.versionName)||!certs(p).equals(certs(installed))||!certs(p).equals(m.signerCertSha256))throw new SecurityException();
        if(Build.VERSION.SDK_INT>=24&&(p.applicationInfo==null||p.applicationInfo.minSdkVersion!=m.minSdk||p.applicationInfo.minSdkVersion>Build.VERSION.SDK_INT))throw new SecurityException();
        // API 21-23 PackageManager does not expose minSdkVersion. Parse the binary XML manifest instead.
        if(Build.VERSION.SDK_INT<24&&ApkMinSdk.read(file)!=m.minSdk)throw new SecurityException();
    }
    static File verifyCached(Context c)throws Exception{
        String encoded=c.getSharedPreferences(PREFS,0).getString("verified_envelope",null);if(encoded==null||encoded.length()>90000)throw new SecurityException();
        UpdateManifest m=checkedManifest(c,Base64.decode(encoded,Base64.NO_WRAP));File f=apk(c);
        if(!f.getCanonicalFile().equals(new File(c.getCacheDir().getCanonicalFile(),"startup-update/update.apk"))||!f.isFile()||f.length()!=m.size)throw new SecurityException();
        MessageDigest hash=MessageDigest.getInstance("SHA-256");InputStream in=new FileInputStream(f);try{byte[] b=new byte[32768];int n;long total=0;while((n=in.read(b))!=-1){total+=n;if(total>m.size)throw new SecurityException();hash.update(b,0,n);}if(total!=m.size)throw new SecurityException();}finally{in.close();}
        if(!hex(hash.digest()).equals(m.sha256))throw new SecurityException();validateApk(c,f,m);return f;
    }
    static String hex(byte[] bytes){StringBuilder s=new StringBuilder();for(byte b:bytes){int n=b&255;s.append("0123456789abcdef".charAt(n>>4));s.append("0123456789abcdef".charAt(n&15));}return s.toString();}
}
