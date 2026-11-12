package ru.alexv.pcmote;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.ProgressDialog;
import android.content.DialogInterface;
import android.content.Intent;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.net.Uri;
import android.provider.OpenableColumns;
import java.io.*;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.util.UUID;
import org.json.JSONObject;

/** Explicit foreground-only upload. One atomic pending record; never persists the bearer key. */
final class FileUpload {
    interface Result { void done(String message); }
    private static final Object LOCK = new Object();
    private static boolean working;
    private final Activity activity;
    private final Result result;
    private final ProgressDialog dialog;
    private AlertDialog choice;
    private volatile boolean cancelled, disposed;
    private boolean resultDelivered;
    private volatile HttpURLConnection connection;
    private volatile InputStream activeInput;
    private volatile Thread worker;
    private final android.os.CancellationSignal providerCancel = new android.os.CancellationSignal();
    private JSONObject pending;
    private String host, key;
    private long lastProgress;

    FileUpload(Activity activity, Result result) {
        this.activity = activity; this.result = result;
        dialog = new ProgressDialog(activity);
        dialog.setTitle(R.string.upload_title);
        dialog.setMessage(activity.getString(R.string.upload_preparing));
        dialog.setProgressStyle(ProgressDialog.STYLE_HORIZONTAL); dialog.setMax(100);
        dialog.setIndeterminate(true); dialog.setCanceledOnTouchOutside(false);
        dialog.setButton(DialogInterface.BUTTON_NEGATIVE, activity.getString(R.string.upload_pause), new DialogInterface.OnClickListener() {
            public void onClick(DialogInterface d, int which) { cancel(); }
        });
        dialog.setOnCancelListener(new DialogInterface.OnCancelListener() { public void onCancel(DialogInterface d) { cancel(); } });
    }
    private SharedPreferences store() { return activity.getSharedPreferences("resume_upload", Activity.MODE_PRIVATE); }
    static boolean hasPending(Activity a) { return a.getSharedPreferences("resume_upload", Activity.MODE_PRIVATE).contains("pending"); }
    private JSONObject load() throws Exception {
        String text = store().getString("pending", "");
        if (text.length() == 0 || text.length() > 16384) throw new IOException(activity.getString(R.string.upload_pending_invalid));
        JSONObject p = new JSONObject(text);
        String id=p.getString("id"), uri=p.getString("uri"), owner=p.getString("host"), hash=p.getString("keyHash");
        if (!id.matches("[0-9a-f]{32}") || uri.length()>4096 || owner.length()>255 || !hash.matches("[0-9a-f]{64}")
                || p.getString("name").length()>1024 || p.getLong("size") < -1 || p.getLong("size") > ResumeProtocol.MAX
                || !p.getString("sha256").matches("([0-9a-f]{64})?")) throw new IOException(activity.getString(R.string.upload_pending_invalid));
        return p;
    }
    private void save() throws Exception {
        String text=pending.toString();
        if(text.length()>16384 || !store().edit().putString("pending",text).commit()) throw new IOException(activity.getString(R.string.upload_persist_failed));
    }
    private File cache() { return new File(activity.getFilesDir(), "resume-upload-"+pending.optString("id")+".tmp"); }
    void dispose() { disposed=true; resultDelivered=true; cancel(); if(choice!=null)choice.dismiss(); }
    void cancel() {
        cancelled=true; dialog.dismiss();
        final Thread t=worker; if(t!=null)t.interrupt();
        new Thread(new Runnable(){public void run(){
            providerCancel.cancel();
            InputStream in=activeInput; if(in!=null)try{in.close();}catch(IOException ignored){}
            HttpURLConnection c=connection;if(c!=null)c.disconnect();
        }},"upload-close").start();
    }
    void start(final Uri uri, final String host, final String key) { begin(uri,host,key,false); }
    void resume(String host,String key) { begin(null,host,key,false); }
    void discard(String host,String key) { begin(null,host,key,true); }
    void discardLocal() { localOnly=true;begin(null,"","",true); }
    private boolean localOnly;
    private void begin(final Uri uri, final String owner, final String token, final boolean discard) {
        this.host=owner;this.key=token;
        synchronized(LOCK){if(working){
            new android.os.Handler(android.os.Looper.getMainLooper()).post(new Runnable(){public void run(){finish(activity.getString(R.string.upload_wait));}});
            return;
        }working=true;}
        dialog.show();
        worker=new Thread(new Runnable(){public void run(){
            String message;
            try {
                if(hasPending(activity)) {
                    pending=load();
                    if(uri!=null)throw new IOException(activity.getString(R.string.upload_pending));
                    if(!localOnly && !ResumeProtocol.bound(owner,token,pending.getString("host"),pending.getString("keyHash")))throw new IOException(activity.getString(R.string.upload_owner_changed));
                } else {
                    if(uri==null)throw new IOException(activity.getString(R.string.upload_pending_invalid));
                    if(uri.toString().length()>4096 || owner.length()>255)throw new IOException(activity.getString(R.string.upload_pending_invalid));
                    pending=new JSONObject().put("id",UUID.randomUUID().toString().replace("-",""))
                            .put("uri",uri.toString()).put("host",owner).put("keyHash",ResumeProtocol.fingerprint(token))
                            .put("name","file").put("size",-1).put("sha256","").put("cached",false).put("discard",false);
                    save(); // Persist ownership before provider IO or a server request.
                }
                if(discard || pending.optBoolean("discard")) {
                    pending.put("discard",true);save();
                    if(ResumeProtocol.needsRemoteAbort(localOnly)) {
                        try { request("abort",new JSONObject().put("id",pending.getString("id")),null,0); }
                        catch(HttpFailure e){if(e.code!=404)throw e;}
                    }
                    cleanup();message=activity.getString(localOnly?R.string.upload_discard_local_done:R.string.upload_discarded);
                } else {
                    JSONObject reply=completedStatus();
                    boolean prepared=pending.getString("sha256").length()!=0;
                    if(ResumeProtocol.needsSource(prepared,reply!=null)) {
                        phase(R.string.upload_verifying);try(InputStream in=source()){if(!ResumeProtocol.hash(in,pending.getLong("size"),checks()).equals(pending.getString("sha256")))throw new IOException(activity.getString(R.string.upload_source_changed));}
                    }
                    if(reply==null) {
                        if(!prepared)prepare();
                        reply=transfer();
                    }
                    message=activity.getString(R.string.upload_saved_fmt,reply.getString("path"));
                    cleanup();
                }
            } catch(Exception e) {
                message=cancelled?activity.getString(R.string.upload_paused):activity.getString(R.string.upload_failed_fmt,e.getMessage()==null?e.getClass().getSimpleName():e.getMessage());
            } finally {
                HttpURLConnection c=connection;if(c!=null)c.disconnect();connection=null;activeInput=null;
                synchronized(LOCK){working=false;}
            }
            final String text=message;
            activity.runOnUiThread(new Runnable(){public void run(){finish(text);}});
        }},"pc-resumable-upload");worker.start();
    }
    private ResumeProtocol.Check checks(){return new ResumeProtocol.Check(){public void check()throws IOException{checkCancelled();}};}
    private void prepare() throws Exception {
        phase(R.string.upload_preparing);
        Uri uri=Uri.parse(pending.getString("uri"));String name="file";long size=-1;
        try(Cursor cursor=activity.getContentResolver().query(uri,new String[]{OpenableColumns.DISPLAY_NAME,OpenableColumns.SIZE},null,null,null,providerCancel)){
            if(cursor!=null&&cursor.moveToFirst()){
                int n=cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME),s=cursor.getColumnIndex(OpenableColumns.SIZE);
                if(n>=0&&!cursor.isNull(n))name=cursor.getString(n);
                if(s>=0&&!cursor.isNull(s))size=cursor.getLong(s);
            }
        }
        if(name==null || name.length()>1024)throw new IOException(activity.getString(R.string.upload_pending_invalid));
        if(size>ResumeProtocol.MAX)throw new IOException(activity.getString(R.string.upload_max_size));
        pending.put("name",name).put("size",size).put("cached",size<0);save();
        String sha;
        if(size<0){
            // Kept in filesDir, not evictable cacheDir. Bound every write by size and free-space reserve.
            MessageDigest md=ResumeProtocol.digest();size=0;
            try(InputStream in=open(uri);FileOutputStream out=new FileOutputStream(cache())){
                byte[] b=new byte[65536];int n;
                while((n=in.read(b))!=-1){checkCancelled();size+=n;
                    if(size>ResumeProtocol.MAX)throw new IOException(activity.getString(R.string.upload_max_size));
                    if(cache().getUsableSpace()<n+16L*1024*1024)throw new IOException(activity.getString(R.string.upload_cache_budget));
                    out.write(b,0,n);md.update(b,0,n);
                }
                out.getFD().sync();
            }
            sha=ResumeProtocol.hex(md.digest());
        }else try(InputStream in=open(uri)){sha=ResumeProtocol.hash(in,size,checks());}
        checkCancelled();pending.put("size",size).put("sha256",sha);save();
    }
    private JSONObject completedStatus() throws Exception {
        if(pending.getString("sha256").length()==0)return null;
        try {
            JSONObject reply=request("status",new JSONObject().put("id",pending.getString("id")),null,0);
            validate(reply);return reply.getBoolean("complete")?reply:null;
        }catch(HttpFailure e){if(e.code!=404)throw e;return null;}
        catch(IOException e){checkCancelled();return null;} // Transfer performs bounded status retries.
    }
    private JSONObject transfer() throws Exception {
        int failures=0;
        while(true){
            checkCancelled();
            try {
                JSONObject reply;
                try{reply=request("status",new JSONObject().put("id",pending.getString("id")),null,0);}
                catch(HttpFailure e){
                    if(e.code!=404)throw e;
                    if(!ResumeProtocol.mayCreate(pending.optBoolean("createAttempted")))throw new HttpFailure(404,activity.getString(R.string.upload_session_missing));
                    // Persist before sending: even an ambiguous create cannot silently retarget after a restart.
                    pending.put("createAttempted",true);save();
                    reply=request("create",new JSONObject().put("id",pending.getString("id")).put("name",pending.getString("name")).put("size",pending.getLong("size")).put("sha256",pending.getString("sha256")),null,0);
                }
                validate(reply);
                if(reply.getBoolean("complete"))return reply;
                long offset=reply.getLong("offset"),size=pending.getLong("size");
                try(InputStream in=source()){
                    ResumeProtocol.skipFully(in,offset,checks());progress(offset,size);
                    byte[] chunk=new byte[ResumeProtocol.CHUNK];
                    while(offset<size){
                        checkCancelled();int count=(int)Math.min(chunk.length,size-offset),got=0;
                        while(got<count){checkCancelled();int n=in.read(chunk,got,count-got);if(n<0)throw new IOException(activity.getString(R.string.upload_source_changed));got+=n;}
                        reply=request("chunk",null,chunk,count,offset);validate(reply);
                        if(reply.getLong("offset")!=offset+count)throw new IOException(activity.getString(R.string.invalid_reply));
                        offset+=count;failures=0;progress(offset,size);
                    }
                }
                phase(R.string.upload_finalizing);
                reply=request("finish",new JSONObject().put("id",pending.getString("id")),null,0);validate(reply);
                if(!reply.getBoolean("complete"))throw new IOException(activity.getString(R.string.invalid_reply));
                return reply;
            }catch(IOException e){
                checkCancelled();
                if(e instanceof HttpFailure && !((HttpFailure)e).retryable())throw e;
                long delay=ResumeProtocol.retryDelay(failures++);if(delay<0)throw e;
                phase(R.string.upload_retrying);Thread.sleep(delay);
                // Always re-query committed status after any ambiguous response, never blindly replay bytes.
            }
        }
    }
    private void validate(JSONObject r)throws Exception{
        if(!pending.getString("id").equals(r.getString("id")) || r.getLong("size")!=pending.getLong("size"))throw new IOException(activity.getString(R.string.invalid_reply));
        ResumeProtocol.checkOffset(r.getLong("offset"),pending.getLong("size"));
        if(r.getBoolean("complete") && (r.getLong("offset")!=pending.getLong("size") || r.getString("path").length()>4096))throw new IOException(activity.getString(R.string.invalid_reply));
    }
    private JSONObject request(String action,JSONObject body,byte[] chunk,int count)throws Exception{return request(action,body,chunk,count,0);}
    private JSONObject request(String action,JSONObject body,byte[] chunk,int count,long offset)throws Exception{
        checkCancelled();
        HttpURLConnection c=(HttpURLConnection)new URL("http://"+host+":8765/upload/resume/"+action).openConnection();connection=c;
        try{
            c.setRequestMethod("POST");c.setConnectTimeout(10000);c.setReadTimeout("finish".equals(action)?30*60*1000:60000);
            c.setInstanceFollowRedirects(false);c.setDoOutput(true);c.setRequestProperty("Authorization","Bearer "+key);
            byte[] data=chunk==null?body.toString().getBytes("UTF-8"):chunk;int length=chunk==null?data.length:count;
            if(chunk==null && length>8192)throw new IOException(activity.getString(R.string.upload_pending_invalid));
            c.setFixedLengthStreamingMode(length);c.setRequestProperty("Content-Type",chunk==null?"application/json":"application/octet-stream");
            if(chunk!=null){
                MessageDigest md=ResumeProtocol.digest();md.update(chunk,0,count);
                c.setRequestProperty("X-Upload-Id",pending.getString("id"));c.setRequestProperty("X-Upload-Offset",Long.toString(offset));c.setRequestProperty("X-Chunk-SHA256",ResumeProtocol.hex(md.digest()));
            }
            checkCancelled();try(OutputStream out=c.getOutputStream()){out.write(data,0,length);}
            int code=c.getResponseCode();String text=readReply(code<400?c.getInputStream():c.getErrorStream());
            if(code!=200&&code!=201)throw new HttpFailure(code,activity.getString(R.string.upload_http_fmt,code));
            JSONObject reply=new JSONObject(text);if(!Boolean.TRUE.equals(reply.get("ok")))throw new IOException(activity.getString(R.string.invalid_reply));return reply;
        }finally{c.disconnect();if(connection==c)connection=null;}
    }
    private static final class HttpFailure extends IOException {
        final int code;HttpFailure(int code,String text){super(text);this.code=code;}
        boolean retryable(){return code==408||code==429||code>=500;}
    }
    private InputStream source()throws Exception{return pending.optBoolean("cached")?track(new FileInputStream(cache())):open(Uri.parse(pending.getString("uri")));}
    private InputStream track(InputStream in)throws IOException{activeInput=in;if(cancelled){in.close();checkCancelled();}return in;}
    private InputStream open(Uri uri)throws IOException{
        checkCancelled();android.content.res.AssetFileDescriptor fd=activity.getContentResolver().openAssetFileDescriptor(uri,"r",providerCancel);
        if(fd==null)throw new IOException(activity.getString(R.string.upload_open_failed));
        try{return track(fd.createInputStream());}catch(IOException e){fd.close();throw e;}
    }
    private void cleanup()throws Exception{
        // Retain a cleanup tombstone until private bytes and grant have been released; restart retries safely.
        pending.put("discard",true);save();
        if(cache().exists()&&!cache().delete())throw new IOException(activity.getString(R.string.upload_persist_failed));
        try{activity.getContentResolver().releasePersistableUriPermission(Uri.parse(pending.getString("uri")),Intent.FLAG_GRANT_READ_URI_PERMISSION);}catch(SecurityException ignored){}
        if(!store().edit().remove("pending").commit())throw new IOException(activity.getString(R.string.upload_persist_failed));
    }
    private void checkCancelled()throws IOException{
        if(cancelled||disposed||Thread.currentThread().isInterrupted())throw new IOException(activity.getString(R.string.upload_paused));
        if(!localOnly && host!=null) {
            SharedPreferences current=activity.getSharedPreferences("pcmote",Activity.MODE_PRIVATE);
            if(!host.equals(current.getString("host", "")) || !key.equals(current.getString("key", "")))
                throw new IOException(activity.getString(R.string.upload_owner_changed));
        }
    }
    private String readReply(InputStream in)throws IOException{
        if(in==null)return "";try(InputStream s=in;ByteArrayOutputStream b=new ByteArrayOutputStream()){
            byte[] bytes=new byte[1024];int n;while((n=s.read(bytes))!=-1){checkCancelled();if(b.size()+n>16384)throw new IOException(activity.getString(R.string.invalid_reply));b.write(bytes,0,n);}return b.toString("UTF-8");
        }
    }
    private void phase(final int text){activity.runOnUiThread(new Runnable(){public void run(){if(!disposed&&!cancelled&&!activity.isDestroyed()){dialog.setIndeterminate(true);dialog.setMessage(activity.getString(text));}}});}
    private void progress(final long sent,final long total){
        long now=android.os.SystemClock.elapsedRealtime();if(sent!=total&&now-lastProgress<150)return;lastProgress=now;
        activity.runOnUiThread(new Runnable(){public void run(){if(!disposed&&!cancelled&&!activity.isDestroyed()){dialog.setIndeterminate(false);dialog.setMessage(activity.getString(R.string.upload_progress_fmt,pending.optString("name")));dialog.setProgress(total==0?100:(int)(sent*100/total));}}});
    }
    private void finish(String message){if(disposed||resultDelivered||activity.isFinishing()||activity.isDestroyed())return;resultDelivered=true;dialog.dismiss();result.done(message);}
}
