package ru.alexv.pcmote;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.content.DialogInterface;
import android.view.View;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.WindowManager;
import android.widget.*;
import org.json.JSONObject;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Foreground-only pairing. Rotation/cancellation intentionally destroys bootstrap secrets. */
public final class PairingActivity extends Activity {
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private volatile PairingClient client;
    private volatile boolean cancelled;
    private EditText input;
    private TextView status;
    private Button connect;
    private String requestId, sessionSecret;
    private long deadline;
    @Override protected void attachBaseContext(Context base){super.attachBaseContext(AppLocale.wrap(base));}
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        setTitle(R.string.pair_title);
        LinearLayout content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);
        int padding=(int)(20*getResources().getDisplayMetrics().density);content.setPadding(padding,padding,padding,padding);
        TextView explanation=new TextView(this);explanation.setText(R.string.pair_instructions);content.addView(explanation);
        input=new EditText(this);input.setSingleLine(false);input.setHint(R.string.pair_link_hint);
        input.setSaveEnabled(false);input.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD);
        if(android.os.Build.VERSION.SDK_INT>=26)input.setImportantForAutofill(android.view.View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS);
        content.addView(input,new LinearLayout.LayoutParams(-1,-2));
        connect=new Button(this);connect.setText(R.string.pair_connect);content.addView(connect);
        status=new TextView(this);status.setSaveEnabled(false);content.addView(status);
        Button cancel=new Button(this);cancel.setText(android.R.string.cancel);content.addView(cancel);cancel.setOnClickListener(new View.OnClickListener(){public void onClick(View v){finish();}});
        setContentView(content);
        Intent launch=getIntent();String incoming=launch.getDataString();launch.setData(null);
        if(state==null && incoming!=null)input.setText(incoming);
        if(state!=null)status.setText(R.string.pair_restart);
        connect.setOnClickListener(new View.OnClickListener(){public void onClick(View v){begin();}});
    }
    private void begin() {
        final PairingLink link;
        try{link=PairingLink.parse(input.getText().toString().trim());}
        catch(Exception ignored){status.setText(R.string.pair_invalid);return;}
        new AlertDialog.Builder(this).setTitle(R.string.pair_title).setMessage(R.string.pair_replace_warning)
            .setNegativeButton(android.R.string.cancel,null).setPositiveButton(R.string.pair_connect,new DialogInterface.OnClickListener(){public void onClick(DialogInterface d,int w){
                input.setText("");input.setEnabled(false);connect.setEnabled(false);status.setText(R.string.pair_connecting);
                worker.execute(new Runnable(){public void run(){claim(link);}});
            }}).show();
    }
    private static String string(JSONObject object,String key)throws Exception {
        Object value=object.get(key);if(!(value instanceof String))throw new Exception();return (String)value;
    }
    private static int integer(JSONObject object,String key)throws Exception {
        Object value=object.get(key);if(!(value instanceof Integer))throw new Exception();return (Integer)value;
    }
    private JSONObject post(String path,JSONObject json)throws Exception {
        if(cancelled || SystemClock.elapsedRealtime()>=deadline && deadline!=0)throw new Exception();
        JSONObject reply=new JSONObject(client.post(path,json.toString(),false));
        if(integer(reply,"v")!=1)throw new Exception();return reply;
    }
    private JSONObject credentials()throws Exception {
        return new JSONObject().put("request_id",requestId).put("session_secret",sessionSecret);
    }
    private void claim(PairingLink link) {
        try {
            client=new PairingClient(link);
            if(cancelled){client.close();return;}
            JSONObject reply=post("/pair/v1/claim",new JSONObject().put("ticket",link.ticket).put("device_name","Android"));
            if(!"pending".equals(string(reply,"state")))throw new Exception();
            requestId=string(reply,"request_id");sessionSecret=string(reply,"session_secret");
            String code=string(reply,"confirm_code");int ttl=integer(reply,"expires_in");
            if(!requestId.matches("[A-Za-z0-9_-]{21}[AQgw]") || !PairingLink.secret(sessionSecret) || !code.matches("[0-9]{6}") || ttl<1 || ttl>120)throw new Exception();
            deadline=SystemClock.elapsedRealtime()+ttl*1000L;
            runOnUiThread(new Runnable(){public void run(){if(!cancelled)status.setText(getString(R.string.pair_compare_code,code));}});
            while(!cancelled && SystemClock.elapsedRealtime()<deadline) {
                Thread.sleep(3000);
                reply=post("/pair/v1/status",credentials());
                String phase=string(reply,"state");
                if("pending".equals(phase))continue;
                if(!"approved".equals(phase))throw new Exception();
                final Approved approved=validate(reply,link.host);
                runOnUiThread(new Runnable(){public void run(){confirm(approved);}});return;
            }
            throw new Exception();
        }catch(Exception ignored){fail();}
    }
    private static final class Approved {
        String host,key,mac,broadcast;
    }
    private static Approved validate(JSONObject json,String expectedHost)throws Exception {
        Approved result=new Approved();result.host=string(json,"host");result.key=string(json,"key");
        if(!expectedHost.equals(result.host) || !PairingLink.privateIPv4(result.host) || integer(json,"http_port")!=8765
                || !result.key.matches("[A-Za-z0-9_-]{22,256}") || !"VzaimoPult".equals(string(json,"pc_name")))throw new Exception();
        if(json.has("mac")) {result.mac=string(json,"mac");if(!result.mac.matches("(?i)[0-9a-f]{2}(?:[:-][0-9a-f]{2}){5}"))throw new Exception();}
        if(json.has("broadcast")) {
            result.broadcast=string(json,"broadcast");
            if(!result.broadcast.matches("(?:[0-9]{1,3}\\.){3}[0-9]{1,3}"))throw new Exception();
            for(String part:result.broadcast.split("\\."))if(Integer.parseInt(part)>255)throw new Exception();
        }
        return result;
    }
    private void confirm(final Approved result) {
        if(cancelled)return;
        status.setText(R.string.pair_approved);
        new AlertDialog.Builder(this).setTitle(R.string.pair_title).setMessage(R.string.pair_save_warning)
            .setNegativeButton(android.R.string.cancel,new DialogInterface.OnClickListener(){public void onClick(DialogInterface d,int w){finish();}}).setOnCancelListener(new DialogInterface.OnCancelListener(){public void onCancel(DialogInterface d){finish();}})
            .setPositiveButton(R.string.pair_save,new DialogInterface.OnClickListener(){public void onClick(DialogInterface d,int w){worker.execute(new Runnable(){public void run(){save(result);}});}}).show();
    }
    private void save(Approved result) {
        try {
            if(cancelled || SystemClock.elapsedRealtime()>=deadline)throw new Exception();
            android.content.SharedPreferences.Editor edit=getSharedPreferences("pcmote",MODE_PRIVATE).edit();
            edit.putString("host",result.host).putString("key",result.key);
            edit.putLong("pair_revision",getSharedPreferences("pcmote",MODE_PRIVATE).getLong("pair_revision",0)+1);
            if(result.mac==null)edit.remove("mac");else edit.putString("mac",result.mac);
            if(result.broadcast==null)edit.remove("bcast");else edit.putString("bcast",result.broadcast);
            if(!edit.commit())throw new Exception();
            // Local commit is definitive. A lost acknowledgement must never undo pairing.
            try{client.post("/pair/v1/ack",credentials().toString(),true);}catch(Exception ignored){}
            runOnUiThread(new Runnable(){public void run(){if(!cancelled){setResult(RESULT_OK);Toast.makeText(PairingActivity.this,R.string.pair_saved,Toast.LENGTH_LONG).show();finish();}}});
        }catch(Exception ignored){fail();}
    }
    private void fail() {
        PairingClient current=client;if(current!=null)current.close();
        runOnUiThread(new Runnable(){public void run(){if(!cancelled){status.setText(R.string.pair_failed);input.setEnabled(true);connect.setEnabled(true);deadline=0;requestId=null;sessionSecret=null;}}});
    }
    @Override protected void onStop() {
        super.onStop();
        // Pairing is deliberately foreground-only, including Home/app switches.
        cancelled=true;PairingClient current=client;if(current!=null)current.close();worker.shutdownNow();
        if(!isFinishing())finish();
    }
    @Override protected void onDestroy() {
        cancelled=true;PairingClient current=client;if(current!=null)current.close();worker.shutdownNow();
        requestId=null;sessionSecret=null;if(input!=null)input.setText("");super.onDestroy();
    }
}
