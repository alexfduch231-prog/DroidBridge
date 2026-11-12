package ru.alexv.pcmote;

import android.content.Context;
import android.content.SharedPreferences;
import android.content.res.Configuration;
import java.util.Locale;

/** Per-app language, independent of pairing preferences and the system locale. */
public final class AppLocale {
    private static final String KEY = "language";
    private AppLocale() { }

    public static String language(Context context) {
        SharedPreferences prefs = context.getSharedPreferences("pcmote", Context.MODE_PRIVATE);
        String saved = prefs.getString(KEY, "");
        if ("ru".equals(saved) || "en".equals(saved)) return saved;
        String system = android.content.res.Resources.getSystem().getConfiguration().locale.getLanguage();
        String selected = "ru".equals(system) ? "ru" : "en";
        prefs.edit().putString(KEY, selected).apply();
        return selected;
    }

    public static void select(Context context, String language) {
        if (!"ru".equals(language) && !"en".equals(language)) throw new IllegalArgumentException("Unsupported language");
        context.getSharedPreferences("pcmote", Context.MODE_PRIVATE).edit().putString(KEY, language).apply();
    }

    public static Context wrap(Context base) {
        Locale locale = new Locale(language(base));
        Configuration config = new Configuration(base.getResources().getConfiguration());
        config.setLocale(locale);
        config.setLayoutDirection(locale);
        return base.createConfigurationContext(config);
    }
}
