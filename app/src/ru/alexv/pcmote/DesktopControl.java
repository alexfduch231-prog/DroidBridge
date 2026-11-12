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
    private volatile boolean enabled, live, disposed;
    private volatile long lastFrame;
    private boolean fresh(){return live && android.os.SystemClock.elapsedRealtime()-lastFrame<1500;}
    void frame(){lastFrame=android.os.SystemClock.elapsedRealtime();live=true;}
    private volatile int generation;
    private volatile HttpURLConnection connection;
    private final Button toggle;
    private float x, y;
    private long downAt;
    private boolean gesture;
    private int slop;
    private FrameLayout root;
    private View bar;

    DesktopControl(Activity a, View video, String baseUrl, String token) {
        activity=a; base=baseUrl; key=token;
        slop=ViewConfiguration.get(a).getScaledTouchSlop();
        root=(FrameLayout)video.getParent();
        HorizontalScrollView scroll=new HorizontalScrollView(a);
        scroll.setFillViewport(false);
        LinearLayout row=new LinearLayout(a);
        row.setBackgroundColor(0xEE17212B);
        scroll.addView(row);
        toggle=button(row,activity.getString(R.string.control_off),new Runnable(){ public void run(){
            enabled=!enabled; generation++; worker.getQueue().clear(); gesture=false;
            toggle.setText(enabled?activity.getString(R.string.control_on):activity.getString(R.string.control_off));
            if(enabled) toast(activity.getString(R.string.control_gestures));
        }});
        keyButton(row,activity.getString(R.string.start_menu),"win"); keyButton(row,"Esc","esc");
        keyButton(row,"Enter","enter"); keyButton(row,"Tab","tab");
        button(row,activity.getString(R.string.scroll_up),new Runnable(){public void run(){scroll(3);}});
        button(row,activity.getString(R.string.scroll_down),new Runnable(){public void run(){scroll(-3);}});
        FrameLayout.LayoutParams lp=new FrameLayout.LayoutParams(-1,dp(48),Gravity.TOP);
        lp.topMargin=dp(30);
        root.addView(scroll,lp); bar=scroll;
        video.setOnTouchListener(this);
    }
    private int dp(int n){return Math.round(n*activity.getResources().getDisplayMetrics().density);}
    private Button button(LinearLayout row,String title,final Runnable r){
        Button b=new Button(activity, null, 0, R.style.BtnToolbar); b.setText(title); b.setTextSize(12);
        row.addView(b,new LinearLayout.LayoutParams(-2,dp(48)));
        b.setOnClickListener(new View.OnClickListener(){public void onClick(View v){r.run();}}); return b;
    }
    private void keyButton(LinearLayout row,String title,final String name){
        button(row,title,new Runnable(){public void run(){key(name);}});
    }
    void live(boolean value){ live=value; if(!value){generation++;worker.getQueue().clear();gesture=false;} }
    void pause(){enabled=false;live(false);toggle.setText(activity.getString(R.string.control_off));}
    void close(){disposed=true; pause(); worker.shutdownNow(); HttpURLConnection c=connection;if(c!=null)c.disconnect();}
    private void toast(final String text){ui.post(new Runnable(){public void run(){if(!disposed&&!activity.isFinishing())Toast.makeText(activity,text,Toast.LENGTH_SHORT).show();}});}
    void key(String name){try{send(new JSONObject().put("action","key").put("name",name));}catch(Exception ignored){}}
    void text(String text){try{send(new JSONObject().put("action","text").put("text",text));}catch(Exception ignored){}}
    private void scroll(int d){try{send(new JSONObject().put("action","scroll").put("x",.5).put("y",.5).put("delta",d));}catch(Exception ignored){}}
    private float norm(float v,int size){return Math.max(0,Math.min(1,v/Math.max(1,size-1)));}
    public boolean onTouch(View v,MotionEvent e){
        if(!enabled||!fresh()||disposed)return false;
        int action=e.getActionMasked();
        if(e.getPointerCount()!=1||action==MotionEvent.ACTION_CANCEL){gesture=false;return true;}
        if(action==MotionEvent.ACTION_DOWN){x=e.getX();y=e.getY();downAt=e.getEventTime();gesture=true;return true;}
        if(action==MotionEvent.ACTION_UP&&gesture){
            gesture=false;
            if(e.getX()<0||e.getY()<0||e.getX()>=v.getWidth()||e.getY()>=v.getHeight())return true;
            try{
                float endX=e.getX(),endY=e.getY();
                long duration=e.getEventTime()-downAt;
                JSONObject event=new JSONObject().put("x",norm(x,v.getWidth())).put("y",norm(y,v.getHeight()));
                if(Math.hypot(endX-x,endY-y)>slop){
                    event.put("action","drag").put("x2",norm(endX,v.getWidth())).put("y2",norm(endY,v.getHeight()))
                            .put("duration",Math.max(100,Math.min(2000,duration)));
                }else event.put("action","click").put("button",duration>=600?"right":"left").put("count",1);
                send(event);
            }catch(Exception ex){toast(activity.getString(R.string.command_failed));}
            return true;
        }
        return true;
    }
    private void send(final JSONObject event){
        if(!enabled||!fresh()||disposed){toast(activity.getString(R.string.control_required));return;}
        final int epoch=generation;
        final long queuedAt=android.os.SystemClock.elapsedRealtime();
        try{worker.execute(new Runnable(){public void run(){
            if(disposed||!enabled||!fresh()||epoch!=generation
                    ||android.os.SystemClock.elapsedRealtime()-queuedAt>750)return;
            HttpURLConnection c=null;
            try{
                byte[] body=event.toString().getBytes("UTF-8");
                if(body.length>8192)throw new Exception(activity.getString(R.string.text_too_long));
                c=(HttpURLConnection)new URL(base+"/input").openConnection(); connection=c;
                c.setConnectTimeout(2500); c.setReadTimeout(4000); c.setInstanceFollowRedirects(false);
                c.setRequestMethod("POST");c.setDoOutput(true);c.setFixedLengthStreamingMode(body.length);
                c.setRequestProperty("Authorization","Bearer "+key);c.setRequestProperty("Content-Type","application/json");
                if(disposed||!enabled||epoch!=generation)return;
                try(OutputStream out=c.getOutputStream()){out.write(body);}
                int status=c.getResponseCode();
                if(status!=200)throw new Exception(activity.getString(R.string.control_http_fmt,status));
            }catch(Exception ex){
                if(epoch==generation&&!disposed){generation++;worker.getQueue().clear();toast(activity.getString(R.string.control_error_fmt,ex.getMessage()));}
            }finally{if(c!=null)c.disconnect();connection=null;}
        }});}catch(RejectedExecutionException ex){toast(activity.getString(R.string.control_wait));}
    }
}
