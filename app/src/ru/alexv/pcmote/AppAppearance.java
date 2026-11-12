package ru.alexv.pcmote;

import android.app.Activity;
import android.content.Context;
import android.content.res.Configuration;

/** Saved IDs 0/1/2 retain compatibility with existing installations. */
public final class AppAppearance {
    private AppAppearance() {}
    public static int mode(Context context) {
        int value=context.getSharedPreferences("pcmote",Context.MODE_PRIVATE).getInt("theme",0);
        return value>=0 && value<=5 ? value : 0;
    }
    public static Context wrap(Context context) {
        int mode=mode(context);
        if(mode==0)return context;
        Configuration config=new Configuration(context.getResources().getConfiguration());
        config.uiMode=(config.uiMode & ~Configuration.UI_MODE_NIGHT_MASK)
            | (mode==1 ? Configuration.UI_MODE_NIGHT_NO : Configuration.UI_MODE_NIGHT_YES);
        return context.createConfigurationContext(config);
    }
    public static int color(Context context,int attribute) {
        android.util.TypedValue value=new android.util.TypedValue();
        context.getTheme().resolveAttribute(attribute,value,true);
        return value.data;
    }
    public static void apply(Activity activity) {
        int value=mode(activity);
        if(value==0)value=(activity.getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK)
            ==Configuration.UI_MODE_NIGHT_YES ? 2 : 1;
        int[] styles={0,R.style.Appearance_Light,R.style.Appearance_Dark,R.style.Appearance_Ocean,
            R.style.Appearance_Forest,R.style.Appearance_Plum};
        activity.getTheme().applyStyle(styles[value],true);
    }
}
