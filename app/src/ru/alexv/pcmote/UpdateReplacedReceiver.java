package ru.alexv.pcmote;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.os.Build;

/** Best effort only: never start mirroring or accessibility after replacement. */
public final class UpdateReplacedReceiver extends BroadcastReceiver {
    public void onReceive(Context context,Intent intent){
        if(!Intent.ACTION_MY_PACKAGE_REPLACED.equals(intent.getAction()))return;
        Intent open=new Intent(context,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP);
        // Android 10+ disallows unsolicited background activity launches. Notification is the fallback.
        if(Build.VERSION.SDK_INT<29){try{context.startActivity(open);return;}catch(Exception ignored){}}
        if(Build.VERSION.SDK_INT>=33&&context.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)return;
        try{
            NotificationManager nm=(NotificationManager)context.getSystemService(Context.NOTIFICATION_SERVICE);
            if(nm==null||(Build.VERSION.SDK_INT>=24&&!nm.areNotificationsEnabled()))return;
            if(Build.VERSION.SDK_INT>=26)nm.createNotificationChannel(new NotificationChannel("updates",context.getString(R.string.update_title),NotificationManager.IMPORTANCE_DEFAULT));
            PendingIntent pi=PendingIntent.getActivity(context,250,open,PendingIntent.FLAG_UPDATE_CURRENT|(Build.VERSION.SDK_INT>=23?PendingIntent.FLAG_IMMUTABLE:0));
            Notification.Builder n=Build.VERSION.SDK_INT>=26?new Notification.Builder(context,"updates"):new Notification.Builder(context);
            nm.notify(250,n.setSmallIcon(R.drawable.ic_refresh).setContentTitle(context.getString(R.string.app_name)).setContentText(context.getString(R.string.update_reopen)).setContentIntent(pi).setAutoCancel(true).build());
        }catch(Exception ignored){}
    }
}
