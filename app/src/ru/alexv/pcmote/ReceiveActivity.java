package ru.alexv.pcmote;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
import android.os.StatFs;
import android.provider.DocumentsContract;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.RandomAccessFile;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;

/** Foreground, user-selected receives. Raw PC paths are never part of the protocol. */
public final class ReceiveActivity extends Activity {
    private static final int PICK_FOLDER=2101;
    private static final java.util.concurrent.Semaphore TRANSFER=new java.util.concurrent.Semaphore(1);
    private SharedPreferences settings,pair;
    private TextView status;
    private ProgressBar progress;
    private Button refresh,folder,resume,pause,discard;
    private volatile boolean stopped,dead,busy;
    private volatile HttpURLConnection connection;
    private Thread worker;
    private boolean english;
    private String host,key;
    @Override protected void attachBaseContext(Context base){super.attachBaseContext(AppAppearance.wrap(AppLocale.wrap(base)));}
    @Override public void onCreate(Bundle state){
        super.onCreate(state);AppAppearance.apply(this);
        english=!getResources().getConfiguration().locale.getLanguage().equals("ru");
        settings=getSharedPreferences("receive_files",MODE_PRIVATE);pair=getSharedPreferences("pcmote",MODE_PRIVATE);
        LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);
        int pad=(int)(16*getResources().getDisplayMetrics().density);box.setPadding(pad,pad,pad,pad);
        box.setBackgroundColor(AppAppearance.color(this,R.attr.db_bg_screen));
        status=new TextView(this);status.setTextColor(AppAppearance.color(this,R.attr.db_text_primary));status.setTextSize(16);
        box.addView(status,new LinearLayout.LayoutParams(-1,-2));
        progress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);progress.setMax(1000);box.addView(progress,new LinearLayout.LayoutParams(-1,-2));
        folder=button(box,"Папка получения…","Receive folder…",new View.OnClickListener(){public void onClick(View v){pickFolder();}});
        refresh=button(box,"Файлы с ПК","Files from PC",new View.OnClickListener(){public void onClick(View v){listFiles();}});
        resume=button(box,"Продолжить загрузку","Continue download",new View.OnClickListener(){public void onClick(View v){startReceive(null);}});
        pause=button(box,"Пауза","Pause",new View.OnClickListener(){public void onClick(View v){stopWorker();}});
        discard=button(box,"Отменить загрузку","Cancel download",new View.OnClickListener(){public void onClick(View v){confirmDiscard();}});
        button(box,"Назад","Back",new View.OnClickListener(){public void onClick(View v){finish();}});
        android.widget.ScrollView scroll=new android.widget.ScrollView(this);scroll.setFillViewport(true);scroll.addView(box);setContentView(scroll);render(text("Выбери папку и файл, подготовленный на ПК. Для докачки нужна свободная память телефона.","Choose a folder and a file prepared on the PC. Resuming requires free phone storage."));
    }
    private String text(String ru,String en){return english?en:ru;}
    private Button button(LinearLayout box,String ru,String en,View.OnClickListener click){
        Button b=new Button(this);b.setText(text(ru,en));b.setOnClickListener(click);box.addView(b,new LinearLayout.LayoutParams(-1,-2));return b;
    }
    private void render(String message){
        if(dead)return;
        status.setText(message);folder.setEnabled(!busy);refresh.setEnabled(!busy);
        resume.setEnabled(!busy&&settings.contains("pending"));discard.setEnabled(!busy&&settings.contains("pending"));pause.setEnabled(busy);
    }
    private void ui(final String message){runOnUiThread(new Runnable(){public void run(){render(message);}});}
    private void stopWorker(){stopped=true;HttpURLConnection c=connection;if(c!=null)c.disconnect();}
    @Override protected void onStop(){stopWorker();super.onStop();}
    @Override protected void onDestroy(){dead=true;stopWorker();super.onDestroy();}
    private void pickFolder(){
        if(settings.contains("pending")){ui(text("Сначала заверши или отмени текущую загрузку.","Finish or cancel the current download first."));return;}
        Intent intent=new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION|Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        try{startActivityForResult(intent,PICK_FOLDER);}catch(Exception e){ui(text("Системный выбор папки недоступен.","System folder picker is unavailable."));}
    }
    @Override protected void onActivityResult(int request,int result,Intent data){
        super.onActivityResult(request,result,data);
        if(request!=PICK_FOLDER||result!=RESULT_OK||data==null||data.getData()==null)return;
        try{
            int flags=data.getFlags()&(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
            if((flags&Intent.FLAG_GRANT_WRITE_URI_PERMISSION)==0)throw new SecurityException();
            getContentResolver().takePersistableUriPermission(data.getData(),flags);
            if(!settings.edit().putString("tree",data.getData().toString()).commit())throw new Exception();
            ui(text("Папка выбрана. Нажми «Файлы с ПК».","Folder selected. Tap Files from PC."));
        }catch(Exception e){ui(text("Не удалось сохранить доступ к папке.","Could not persist folder access."));}
    }
    private boolean begin(){
        if(busy||worker!=null&&worker.isAlive())return false;
        host=pair.getString("host","");key=pair.getString("key","");
        if(host.length()==0||key.length()==0){ui(text("Сначала подключись к ПК.","Pair a PC first."));return false;}
        stopped=false;busy=true;render(text("Подключение…","Connecting…"));return true;
    }
    private String binding() throws Exception{return ReceiveProtocol.hex(MessageDigest.getInstance("SHA-256").digest((host+"\n"+key).getBytes("UTF-8")));}
    private void check() throws Exception{if(stopped||dead)throw new InterruptedException();}
    private HttpURLConnection open(String route,JSONObject request) throws Exception{
        check();
        HttpURLConnection c=(HttpURLConnection)new URL("http",host,8765,"/outbox/"+route).openConnection();
        connection=c;c.setInstanceFollowRedirects(false);c.setConnectTimeout(10000);c.setReadTimeout(20000);
        c.setRequestMethod("POST");c.setDoOutput(true);c.setRequestProperty("Authorization","Bearer "+key);
        c.setRequestProperty("Content-Type","application/json");byte[] bytes=request.toString().getBytes("UTF-8");c.setFixedLengthStreamingMode(bytes.length);
        try(OutputStream out=c.getOutputStream()){out.write(bytes);}
        if(c.getResponseCode()!=200){c.disconnect();throw new java.io.IOException("Server unavailable");}
        return c;
    }
    private byte[] readBounded(InputStream input,int max) throws Exception{
        ByteArrayOutputStream bytes=new ByteArrayOutputStream();byte[] buffer=new byte[65536];int n;
        while((n=input.read(buffer))!=-1){check();if(bytes.size()+n>max)throw new java.io.IOException("Response too large");bytes.write(buffer,0,n);}
        return bytes.toByteArray();
    }
    private JSONObject json(String route,JSONObject request) throws Exception{
        HttpURLConnection c=open(route,request);
        try(InputStream input=c.getInputStream()){return new JSONObject(new String(readBounded(input,65536),"UTF-8"));}
        finally{c.disconnect();if(connection==c)connection=null;}
    }
    private void listFiles(){
        if(!begin())return;
        worker=new Thread(new Runnable(){public void run(){
            try{
                final JSONArray items=json("list",new JSONObject()).getJSONArray("files");
                if(items.length()>32)throw new Exception();
                final String[] names=new String[items.length()];
                for(int i=0;i<names.length;i++){JSONObject m=items.getJSONObject(i);validate(m);names[i]=m.getString("name")+" ("+m.getLong("size")+" B)";}
                runOnUiThread(new Runnable(){public void run(){
                    busy=false;if(dead)return;
                    render(names.length==0?text("На ПК нет подготовленных файлов.","No files prepared on PC."):text("Выбери файл.","Choose a file."));
                    if(names.length>0)new AlertDialog.Builder(ReceiveActivity.this).setTitle(text("Файлы с ПК","Files from PC")).setItems(names,new android.content.DialogInterface.OnClickListener(){public void onClick(android.content.DialogInterface d,int index){try{startReceive(items.getJSONObject(index));}catch(Exception e){ui(text("Некорректный файл.","Invalid file."));}}}).setNegativeButton(android.R.string.cancel,null).show();
                }});
            }catch(Exception e){busy=false;ui(text("Не удалось получить список. Проверь соединение с ПК.","Could not list files. Check PC connection."));}
        }},"receive-list");worker.start();
    }
    private void validate(JSONObject m) throws Exception{ReceiveProtocol.validate(m.getString("id"),m.getString("name"),m.getLong("size"),m.getString("sha256"));}
    private File partial(JSONObject m) throws Exception{return new File(getFilesDir(),"receive-"+m.getString("id")+".part");}
    private void save(JSONObject m) throws Exception{if(!settings.edit().putString("pending",m.toString()).commit())throw new java.io.IOException("Cannot save progress");}
    private void startReceive(final JSONObject chosen){
        if(settings.getString("tree","").length()==0){pickFolder();return;}
        if(chosen!=null&&settings.contains("pending")){ui(text("Сначала продолжи или отмени текущую загрузку.","Continue or cancel the current download first."));return;}
        if(!begin())return;
        worker=new Thread(new Runnable(){public void run(){
            boolean acquired=false;
            try{
                acquired=TRANSFER.tryAcquire();if(!acquired)throw new java.io.IOException("Previous transfer is stopping");
                JSONObject meta=chosen==null?new JSONObject(settings.getString("pending","")):new JSONObject(chosen.toString());
                validate(meta);
                if(chosen!=null){meta.put("binding",binding());meta.put("tree",settings.getString("tree",""));save(meta);}
                if(!binding().equals(meta.getString("binding")))throw new java.io.IOException("Different PC");
                receive(meta);
                busy=false;ui(text("Файл получен и проверен.","File received and verified."));
            }catch(Exception e){busy=false;ui(stopped?text("Пауза. Продолжить можно позже.","Paused. Continue later."):
                    text("Передача не завершена. Проверь сеть, свободное место и доступ к папке, затем продолжи.","Transfer incomplete. Check network, free space and folder access, then continue."));}
            finally{if(acquired)TRANSFER.release();}
        }},"receive-file");worker.start();
    }
    private void receive(JSONObject meta) throws Exception{
        File file=partial(meta);long size=meta.getLong("size");String id=meta.getString("id");
        if(!meta.has("output")){
            try(RandomAccessFile out=new RandomAccessFile(file,"rw")){
                long offset=ReceiveProtocol.durableOffset(out.length(),size);out.setLength(offset);out.seek(offset);
                if(new StatFs(getFilesDir().getAbsolutePath()).getAvailableBytes()<size-offset+16L*1024*1024)throw new java.io.IOException("Storage full");
                while(offset<size){
                    check();byte[] block=null;Exception last=null;
                    for(int retry=0;retry<3;retry++){
                        try{
                            HttpURLConnection c=open("chunk",new JSONObject().put("id",id).put("offset",offset));
                            try(InputStream input=c.getInputStream()){
                                block=readBounded(input,ReceiveProtocol.CHUNK);
                                if(block.length!=Math.min((long)ReceiveProtocol.CHUNK,size-offset)
                                        ||!ReceiveProtocol.hex(MessageDigest.getInstance("SHA-256").digest(block)).equals(c.getHeaderField("X-Chunk-SHA256")))throw new java.io.IOException("Chunk mismatch");
                            }finally{c.disconnect();if(connection==c)connection=null;}
                            last=null;break;
                        }catch(Exception e){last=e;check();if(retry<2)Thread.sleep(500L*(retry+1));}
                    }
                    if(last!=null)throw last;
                    out.write(block);out.getFD().sync();offset+=block.length;
                    final int fraction=size==0?1000:(int)(offset*1000/size);
                    runOnUiThread(new Runnable(){public void run(){if(!dead)progress.setProgress(fraction);}});
                }
            }
            ui(text("Проверка SHA-256…","Verifying SHA-256…"));
            try(InputStream input=new FileInputStream(file)){if(!hash(input).equals(meta.getString("sha256"))) {new RandomAccessFile(file,"rw").close();if(!file.delete())throw new java.io.IOException();throw new java.io.IOException("Digest mismatch");}}
            check();
            Uri tree=Uri.parse(meta.getString("tree"));Uri parent=DocumentsContract.buildDocumentUriUsingTree(tree,DocumentsContract.getTreeDocumentId(tree));
            String name=meta.getString("name");int dot=name.lastIndexOf('.');String suffix=" ("+id.substring(0,8)+")";
            String unique=dot>0?name.substring(0,dot)+suffix+name.substring(dot):name+suffix;
            Uri output=DocumentsContract.createDocument(getContentResolver(),parent,"application/octet-stream",unique);
            if(output==null)throw new java.io.IOException("Cannot create file");
            meta.put("output",output.toString());meta.put("copied",false);save(meta);
        }
        Uri output=Uri.parse(meta.getString("output"));
        if(!meta.optBoolean("copied",false)){
            if(!file.exists()||file.length()!=size)throw new java.io.IOException("Missing verified cache");
            ui(text("Сохранение в выбранную папку…","Saving to selected folder…"));
            try(InputStream input=new FileInputStream(file);OutputStream out=getContentResolver().openOutputStream(output,"wt")){
                if(out==null)throw new java.io.IOException();byte[] buffer=new byte[262144];int n;
                while((n=input.read(buffer))!=-1){check();out.write(buffer,0,n);}out.flush();
            }
            try(InputStream input=getContentResolver().openInputStream(output)){
                if(input==null||!hash(input).equals(meta.getString("sha256")))throw new java.io.IOException("Saved file mismatch");
            }
            meta.put("copied",true);save(meta);
        }
        // Recheck even after a restart between saving and ACK; never consume a missing destination.
        try(InputStream input=getContentResolver().openInputStream(output)){
            if(input==null||!hash(input).equals(meta.getString("sha256")))throw new java.io.IOException("Destination changed");
        }
        check();json("ack",new JSONObject().put("id",id).put("sha256",meta.getString("sha256")));
        if(!settings.edit().remove("pending").commit())throw new java.io.IOException();
        file.delete();
    }
    private String hash(InputStream input) throws Exception{
        MessageDigest digest=MessageDigest.getInstance("SHA-256");byte[] bytes=new byte[262144];int n;
        while((n=input.read(bytes))!=-1){check();digest.update(bytes,0,n);}return ReceiveProtocol.hex(digest.digest());
    }
    private void confirmDiscard(){
        new AlertDialog.Builder(this).setMessage(text("Удалить незавершённую загрузку с телефона? Копия на ПК останется.","Delete the unfinished phone download? The PC copy remains."))
            .setPositiveButton(android.R.string.ok,new android.content.DialogInterface.OnClickListener(){public void onClick(android.content.DialogInterface d,int which){
                if(!TRANSFER.tryAcquire()){ui(text("Дождись остановки передачи.","Wait for transfer to stop."));return;}
                try{JSONObject m=new JSONObject(settings.getString("pending",""));validate(m);
                    if(m.has("output")&&!m.optBoolean("copied",false))DocumentsContract.deleteDocument(getContentResolver(),Uri.parse(m.getString("output")));
                    if(!settings.edit().remove("pending").commit())throw new Exception();partial(m).delete();render(text("Загрузка отменена.","Download canceled."));
                }catch(Exception e){ui(text("Не удалось очистить загрузку.","Could not discard download."));}finally{TRANSFER.release();}
            }}).setNegativeButton(android.R.string.cancel,null).show();
    }
}
