package ru.alexv.pcmote;

import android.app.Activity;
import android.os.Handler;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewConfiguration;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.Toast;
import org.json.JSONObject;
import java.net.HttpURLConnection;
import java.net.URL;
import java.io.OutputStream;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.RejectedExecutionException;

/** Explicit opt-in, absolute-image input. No held keys cross the network. */
final class DesktopControl implements View.OnTouchListener {
    private final Activity activity;
    private final Handler ui = new Handler();
    private final String base, key;
    private final ThreadPoolExecutor worker = new ThreadPoolExecutor(1,1,0,TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<Runnable>(12));
    private final ThreadPoolExecutor focusWorker = new ThreadPoolExecutor(1,1,0,TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<Runnable>(1));
    private volatile int touchRevision;
    private volatile boolean enabled, live, disposed;
    private volatile long lastFrame;
    private boolean fresh(){return live && android.os.SystemClock.elapsedRealtime()-lastFrame<1500;}
    void frame(){lastFrame=android.os.SystemClock.elapsedRealtime();live=true;}
    private volatile int generation;
    private volatile HttpURLConnection connection, focusConnection;
    private final HybridGesture motion;
    private final View video;
    private final RemoteImeView ime;
    private long lastMove, lastFocus;
    private float pendingDx, pendingDy;

    DesktopControl(Activity a, View videoView, String baseUrl, String token) {
        activity=a; base=baseUrl; key=token;video=videoView;
        motion=new HybridGesture(ViewConfiguration.get(a).getScaledTouchSlop());
        enabled=true;
        FrameLayout root=(FrameLayout)video.getParent();
        ime=new RemoteImeView(a,new RemoteImeView.Sink(){
            public void text(String value){DesktopControl.this.text(value);}
            public void key(String value){DesktopControl.this.key(value);}
        });
        root.addView(ime,new FrameLayout.LayoutParams(1,1));
        video.setOnTouchListener(this);
    }
    void setToolbarVisible(boolean visible) { /* No command strip. */ }
    void live(boolean value){live=value;if(!value){generation++;worker.getQueue().clear();motion.cancel();ime.hideKeyboard();}}
    void pause(){enabled=false;live(false);}
    void resume(){enabled=true;}
    void close(){disposed=true;pause();ui.removeCallbacksAndMessages(null);worker.shutdownNow();focusWorker.shutdownNow();HttpURLConnection c=connection;if(c!=null)c.disconnect();c=focusConnection;if(c!=null)c.disconnect();}
    void keyboard(){if(enabled&&fresh()&&!disposed)ime.showKeyboard();}
    private void toast(final String text){ui.post(new Runnable(){public void run(){if(!disposed&&!activity.isFinishing())Toast.makeText(activity,text,Toast.LENGTH_SHORT).show();}});}
    void key(String name){try{send(new JSONObject().put("action","key").put("name",name));}catch(Exception ignored){}}
    void text(String text){try{send(new JSONObject().put("action","text").put("text",text));}catch(Exception ignored){}}
    private void scroll(int d){try{send(new JSONObject().put("action","scroll").put("x",.5).put("y",.5).put("delta",d));}catch(Exception ignored){}}
    private float norm(float v,int size){return Math.max(0,Math.min(1,v/Math.max(1,size-1)));}
    public boolean onTouch(View v,MotionEvent e){
        if(!enabled||!fresh()||disposed){motion.cancel();return false;}
        int action=e.getActionMasked();
        if(action==MotionEvent.ACTION_DOWN){
            touchRevision++;motion.down(e.getX(),e.getY(),e.getEventTime());pendingDx=pendingDy=0;
        }else if(action==MotionEvent.ACTION_POINTER_DOWN){
            if(e.getPointerCount()==2)motion.twoFingers((e.getY(0)+e.getY(1))/2);
            else motion.cancel();
        }else if(action==MotionEvent.ACTION_POINTER_UP){motion.pointerLift();}
        else if(action==MotionEvent.ACTION_CANCEL){motion.cancel();pendingDx=pendingDy=0;}
        else {
            HybridGesture.Event event=null;
            if(action==MotionEvent.ACTION_MOVE){
                event=e.getPointerCount()==2?motion.scroll((e.getY(0)+e.getY(1))/2):motion.move(e.getX(),e.getY());
            }else if(action==MotionEvent.ACTION_UP)event=motion.up(e.getX(),e.getY(),e.getEventTime());
            if(event!=null)try{
                if(event.kind==HybridGesture.MOVE){
                    pendingDx+=event.dx;pendingDy+=event.dy;
                    if(e.getEventTime()-lastMove>=40){flushMove(v);lastMove=e.getEventTime();}
                }else if(event.kind==HybridGesture.SCROLL){
                    int delta=motion.scrollSteps(event.dy,24*activity.getResources().getDisplayMetrics().density);
                    if(delta!=0)send(new JSONObject().put("action","scroll").put("x",.5).put("y",.5).put("delta",delta));
                }else if(event.x>=0&&event.y>=0&&event.x<v.getWidth()&&event.y<v.getHeight()){
                    send(new JSONObject().put("action","click").put("x",norm(event.x,v.getWidth()))
                            .put("y",norm(event.y,v.getHeight())).put("button",event.right?"right":"left").put("count",1));
                    // Focus is queried only after this click is acknowledged by the PC.
                }
            }catch(Exception ignored){}
            if(action==MotionEvent.ACTION_UP)flushMove(v);
        }
        return true;
    }
    private void flushMove(View v){
        if(pendingDx==0&&pendingDy==0)return;
        try{send(new JSONObject().put("action","move_relative")
                .put("dx",Math.max(-1,Math.min(1,pendingDx/Math.max(1,v.getWidth()))))
                .put("dy",Math.max(-1,Math.min(1,pendingDy/Math.max(1,v.getHeight())))));}catch(Exception ignored){}
        pendingDx=pendingDy=0;
    }
    private void probeFocus(){
        if(!enabled||!fresh()||disposed)return;
        long now=android.os.SystemClock.elapsedRealtime();if(now-lastFocus<500)return;lastFocus=now;
        try{send(new JSONObject().put("action","focus"));}catch(Exception ignored){}
    }
    private void send(final JSONObject event){
        if(!enabled||!fresh()||disposed){toast(activity.getString(R.string.control_required));return;}
        final int epoch=generation;
        final long queuedAt=android.os.SystemClock.elapsedRealtime();
        final boolean focus="focus".equals(event.optString("action"));
        final int revision=touchRevision;
        try{(focus?focusWorker:worker).execute(new Runnable(){public void run(){
            if(disposed||!enabled||!fresh()||epoch!=generation
                    ||android.os.SystemClock.elapsedRealtime()-queuedAt>750)return;
            HttpURLConnection c=null;
            try{
                byte[] body=event.toString().getBytes("UTF-8");
                if(body.length>8192)throw new Exception(activity.getString(R.string.text_too_long));
                c=(HttpURLConnection)new URL(base+"/input").openConnection(); if(focus)focusConnection=c;else connection=c;
                c.setConnectTimeout(2500); c.setReadTimeout(4000); c.setInstanceFollowRedirects(false);
                c.setRequestMethod("POST");c.setDoOutput(true);c.setFixedLengthStreamingMode(body.length);
                c.setRequestProperty("Authorization","Bearer "+key);c.setRequestProperty("Content-Type","application/json");
                if(disposed||!enabled||epoch!=generation)return;
                try(OutputStream out=c.getOutputStream()){out.write(body);}
                int status=c.getResponseCode();
                if(status!=200)throw new Exception(activity.getString(R.string.control_http_fmt,status));
                if("click".equals(event.optString("action"))&&!"right".equals(event.optString("button"))){
                    ui.postDelayed(new Runnable(){public void run(){if(epoch==generation&&revision==touchRevision)probeFocus();}},150);
                }
                if(focus){
                    java.io.InputStream in=c.getInputStream();java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream();
                    byte[] buffer=new byte[256];int n;while((n=in.read(buffer))!=-1){if(out.size()+n>1024)throw new java.io.IOException("response too large");out.write(buffer,0,n);}in.close();
                    final Object editable=new JSONObject(out.toString("UTF-8")).opt("editable");
                    ui.post(new Runnable(){public void run(){if(!disposed&&enabled&&fresh()&&epoch==generation&&revision==touchRevision){
                        if(Boolean.TRUE.equals(editable))ime.showKeyboard();else if(Boolean.FALSE.equals(editable))ime.hideKeyboard();
                    }}});
                }
            }catch(Exception ex){
                if(epoch==generation&&!disposed){generation++;worker.getQueue().clear();toast(activity.getString(R.string.control_error_fmt,ex.getMessage()));}
            }finally{if(c!=null)c.disconnect();if(focus)focusConnection=null;else connection=null;}
        }});}catch(RejectedExecutionException ex){toast(activity.getString(R.string.control_wait));}
    }
}
