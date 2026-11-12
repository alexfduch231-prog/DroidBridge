package ru.alexv.pcmote;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.hardware.Camera;
import android.os.Bundle;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import android.view.View;
import android.view.WindowManager;
import android.widget.*;
import com.google.zxing.*;
import com.google.zxing.common.HybridBinarizer;
import com.google.zxing.qrcode.QRCodeReader;
import java.util.Collections;
import java.util.EnumMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Camera frames are decoded in memory and never logged, saved or uploaded. */
@SuppressWarnings("deprecation")
public final class QrScannerActivity extends Activity implements SurfaceHolder.Callback, Camera.PreviewCallback {
    private SurfaceView preview;
    private android.widget.FrameLayout previewBox;
    private int previewWidth, previewHeight, frameWidth, frameHeight;
    private void fitPreview(){
        if(previewWidth<=0 || previewHeight<=0 || previewBox.getWidth()<=0 || previewBox.getHeight()<=0)return;
        float scale=Math.min(previewBox.getWidth()/(float)previewWidth,previewBox.getHeight()/(float)previewHeight);
        android.widget.FrameLayout.LayoutParams p=new android.widget.FrameLayout.LayoutParams(Math.round(previewWidth*scale),Math.round(previewHeight*scale),android.view.Gravity.CENTER);
        preview.setLayoutParams(p);
    }
    private TextView status;
    private Camera camera;
    private volatile boolean resumed, decoding, delivered;
    private boolean surfaceReady, permissionRequested;
    private int generation;
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    @Override protected void attachBaseContext(Context base){super.attachBaseContext(AppAppearance.wrap(AppLocale.wrap(base)));}
    @Override public void onCreate(Bundle state){
        super.onCreate(state);AppAppearance.apply(this);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE|WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        LinearLayout content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);
        status=new TextView(this);status.setText(R.string.scan_instructions);status.setPadding(16,16,16,16);content.addView(status);
        previewBox=new android.widget.FrameLayout(this);previewBox.setBackgroundColor(android.graphics.Color.BLACK);
        preview=new SurfaceView(this);previewBox.addView(preview,new android.widget.FrameLayout.LayoutParams(-1,-1));
        content.addView(previewBox,new LinearLayout.LayoutParams(-1,0,1));
        previewBox.addOnLayoutChangeListener(new View.OnLayoutChangeListener(){public void onLayoutChange(View v,int l,int t,int r,int b,int ol,int ot,int or,int ob){if(r-l!=or-ol || b-t!=ob-ot)fitPreview();}});
        Button retry=new Button(this);retry.setText(R.string.scan_retry);retry.setOnClickListener(new View.OnClickListener(){public void onClick(View v){permissionRequested=false;permissionOrOpen();}});content.addView(retry);
        Button close=new Button(this);close.setText(android.R.string.cancel);close.setOnClickListener(new View.OnClickListener(){public void onClick(View v){finish();}});content.addView(close);
        setContentView(content);preview.getHolder().addCallback(this);
    }
    @Override protected void onResume(){super.onResume();resumed=true;permissionOrOpen();}
    private void permissionOrOpen(){
        if(android.os.Build.VERSION.SDK_INT>=23 && checkSelfPermission(Manifest.permission.CAMERA)!=PackageManager.PERMISSION_GRANTED){
            if(!permissionRequested){permissionRequested=true;requestPermissions(new String[]{Manifest.permission.CAMERA},71);}
            return;
        }
        openCamera();
    }
    @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] results){
        super.onRequestPermissionsResult(request,permissions,results);
        if(request==71){if(results.length>0 && results[0]==PackageManager.PERMISSION_GRANTED)openCamera();else status.setText(R.string.scan_permission);}
    }
    private void openCamera(){
        if(!resumed || !surfaceReady || camera!=null || delivered)return;
        if(android.os.Build.VERSION.SDK_INT>=23 && checkSelfPermission(Manifest.permission.CAMERA)!=PackageManager.PERMISSION_GRANTED)return;
        try{
            int id=-1;Camera.CameraInfo info=new Camera.CameraInfo();
            for(int i=0;i<Camera.getNumberOfCameras();i++){Camera.getCameraInfo(i,info);if(info.facing==Camera.CameraInfo.CAMERA_FACING_BACK){id=i;break;}}
            if(id<0)throw new IllegalStateException();
            camera=Camera.open(id);Camera.Parameters parameters=camera.getParameters();
            Camera.Size best=null;for(Camera.Size size:parameters.getSupportedPreviewSizes()){
                if(size.width<=1280 && size.height<=960 && (best==null || size.width*size.height>best.width*best.height))best=size;
            }
            if(best!=null)parameters.setPreviewSize(best.width,best.height);
            parameters.setPreviewFormat(android.graphics.ImageFormat.NV21);
            if(parameters.getSupportedFocusModes()!=null && parameters.getSupportedFocusModes().contains(Camera.Parameters.FOCUS_MODE_CONTINUOUS_PICTURE))parameters.setFocusMode(Camera.Parameters.FOCUS_MODE_CONTINUOUS_PICTURE);
            camera.setParameters(parameters);
            Camera.getCameraInfo(id,info);int degrees=getWindowManager().getDefaultDisplay().getRotation()*90;
            int rotation=(info.orientation-degrees+360)%360;
            camera.setDisplayOrientation(rotation);
            Camera.Size dimensions=camera.getParameters().getPreviewSize();
            frameWidth=dimensions.width;frameHeight=dimensions.height;
            previewWidth=rotation%180==0 ? dimensions.width : dimensions.height;
            previewHeight=rotation%180==0 ? dimensions.height : dimensions.width;
            fitPreview();
            camera.setPreviewDisplay(preview.getHolder());camera.setPreviewCallbackWithBuffer(this);
            Camera.Size size=camera.getParameters().getPreviewSize();camera.addCallbackBuffer(new byte[size.width*size.height*3/2]);
            camera.startPreview();status.setText(R.string.scan_instructions);
        }catch(Exception ignored){closeCamera();status.setText(R.string.scan_unavailable);}
    }
    @Override public void onPreviewFrame(final byte[] data,final Camera source){
        if(!resumed || delivered || decoding || camera!=source)return;
        decoding=true;final int session=generation;
        final int width=frameWidth,height=frameHeight;
        worker.execute(new Runnable(){public void run(){
            String found=null;
            try{
                QRCodeReader reader=new QRCodeReader();
                EnumMap<DecodeHintType,Object> hints=new EnumMap<DecodeHintType,Object>(DecodeHintType.class);
                hints.put(DecodeHintType.POSSIBLE_FORMATS,Collections.singletonList(BarcodeFormat.QR_CODE));
                PlanarYUVLuminanceSource pixels=new PlanarYUVLuminanceSource(data,width,height,0,0,width,height,false);
                found=reader.decode(new BinaryBitmap(new HybridBinarizer(pixels)),hints).getText();
            }catch(Exception ignored){}
            final String result=found;
            runOnUiThread(new Runnable(){public void run(){
                if(!resumed || session!=generation || camera!=source || delivered)return;
                decoding=false;
                if(result!=null){
                    try{
                        PairingLink.parse(result);
                        delivered=true;closeCamera();
                        Intent intent=new Intent(QrScannerActivity.this,PairingActivity.class);intent.setData(android.net.Uri.parse(result));
                        startActivity(intent);finish();return;
                    }catch(Exception ignored){status.setText(R.string.scan_invalid);}
                }
                try{source.addCallbackBuffer(data);}catch(Exception ignored){}
            }});
        }});
    }
    private void closeCamera(){
        generation++;decoding=false;
        Camera old=camera;camera=null;
        if(old!=null){
            try{old.setPreviewCallbackWithBuffer(null);old.stopPreview();}catch(Exception ignored){}
            try{old.release();}catch(Exception ignored){}
        }
    }
    @Override protected void onPause(){resumed=false;closeCamera();super.onPause();}
    @Override protected void onDestroy(){worker.shutdownNow();super.onDestroy();}
    public void surfaceCreated(SurfaceHolder holder){surfaceReady=true;openCamera();}
    public void surfaceChanged(SurfaceHolder holder,int format,int width,int height){}
    public void surfaceDestroyed(SurfaceHolder holder){surfaceReady=false;closeCamera();}
}
