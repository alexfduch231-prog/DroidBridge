package ru.alexv.pcmote;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.BroadcastReceiver;
import android.content.IntentFilter;
import android.net.wifi.WifiManager;
import android.os.SystemClock;
import android.text.Editable;
import android.text.TextWatcher;
import android.content.DialogInterface;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.res.Configuration;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.view.animation.DecelerateInterpolator;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.IOException;
import java.net.ConnectException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.SocketTimeoutException;
import java.net.URL;
import java.net.UnknownHostException;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;

import org.json.JSONObject;

/**
 * Управление домашним ПК с телефона, всё в рамках локальной сети:
 *   ВКЛЮЧИТЬ  -> magic packet по UDP (Wake-on-LAN), работает даже когда ПК обесточен логически;
 *   ВЫКЛЮЧИТЬ -> HTTP-запрос к слушателю на ПК, тот запускает shutdown с окном на отмену;
 *   ОТМЕНИТЬ  -> /cancel на том же слушателе (видна только после нажатия "Выключить");
 *   ПЛИТКИ    -> /app?id=... запускает приложение из белого списка apps.json на ПК,
 *                долгое нажатие — закрыть его;
 *   КОМАНДЫ   -> «ушёл из дома», таймер выключения, медиа-клавиши;
 *   СТАТУС    -> /status показывает CPU/RAM/uptime, если ПК на связи.
 * Сеть и файлы вводятся руками и хранятся в SharedPreferences.
 */
public class MainActivity extends Activity {

    // Порт слушателя на ПК. Должен совпадать с --port в pc-listener.py.
    private static final int PORT = 8765;

    private static final String PREFS = "pcmote";
    private static final String K_MAC = "mac";
    private static final String K_BCAST = "bcast";
    private static final String K_HOST = "host";
    private static final String K_KEY = "key";
    private static final String K_THEME = "theme";

    // No machine-specific defaults; authenticated discovery fills these after pairing.
    private static final String DEF_MAC = "";
    private static final String DEF_BCAST = "";
    private static final String DEF_HOST = "";

    private static final int THEME_AUTO = 0;
    private static final int THEME_DAY = 1;
    private static final int THEME_NIGHT = 2;

    // Порт TCP-сервера телефона для трансляции экрана/звука на ПК.
    private static final int MIRROR_PORT = 8768;
    private static final int REQ_PROJECTION = 2001;
    private static final int REQ_PERMS = 2002;
    private static final int REQ_UPLOAD = 2003;
    private static final int REQ_PAIR = 2004;
    private FileUpload fileUpload;
    private Button btnUpload;

    private static final class RemoteApp {
        final String id,name;final boolean canClose;
        RemoteApp(String id,String name,boolean canClose){this.id=id;this.name=name;this.canClose=canClose;}
    }
    private final List<RemoteApp> remoteApps=new ArrayList<RemoteApp>();
    private int appsGeneration;
    private volatile HttpURLConnection appsConnection;
    private volatile Thread appsThread;
    private boolean appsLoaded;

    // Быстрые команды: ключ совпадает с action/маршрутом на слушателе.
    private static final String[] ACT_KEYS = {
            "away", "timer30", "timer60", "playpause", "next", "prev",
            "volup", "voldown", "mute"
    };
    private static final int[] ACT_ICONS = {
            R.drawable.ic_shoe, R.drawable.ic_timer, R.drawable.ic_timer,
            R.drawable.ic_play_pause, R.drawable.ic_next, R.drawable.ic_prev,
            R.drawable.ic_vol_up, R.drawable.ic_vol_down, R.drawable.ic_mute
    };
    private static final int[] ACT_LABELS = {
            R.string.act_away, R.string.act_timer30, R.string.act_timer60,
            R.string.act_playpause, R.string.act_next, R.string.act_prev,
            R.string.act_volup, R.string.act_voldown, R.string.act_mute
    };

    private SharedPreferences prefs;
    private String loadedPairKey;
    private long loadedPairRevision;
    private EditText editMac, editBcast, editHost, editKey;
    private Button btnOn, btnOff, btnRestart, btnLock, btnScreen, btnView, btnMirror,
            btnCancel, btnSave, btnTheme;
    private TextView statusView, pcStatus;
    private TextView monCpu, monRam, monGpu, monVram, monitorUpdated;
    private ProgressBar barCpu, barRam, barGpu, barVram;
    private AlertDialog monitorDialog;
    private TextView dCpu, dRam, dGpu, dVram, dGpuName, dTemp, dUptime, dUpdated, dOffline;
    private ProgressBar dBarCpu, dBarRam, dBarGpu, dBarVram;
    private JSONObject lastStatus;
    private ScrollView scroll;
    private final List<View> appTiles = new ArrayList<View>();
    private final List<View> actionTiles = new ArrayList<View>();

    private final SimpleDateFormat ts = new SimpleDateFormat("HH:mm:ss", Locale.getDefault());
    private final Handler refreshHandler = new Handler(Looper.getMainLooper());
    private final Runnable autoRefresh = new Runnable() {
        public void run() {
            refreshStatus(false);
            updateMirrorButton();
            refreshHandler.postDelayed(this, 5000L);
        }
    };
    private int themeMode = THEME_AUTO;
    private boolean discoveryResumed, discoveryRegistered, discoveryRunning;
    private int discoveryGeneration, discoveryEditRevision;
    private long lastDiscoveryAt;
    private final BroadcastReceiver discoveryReceiver = new BroadcastReceiver() {
        @Override public void onReceive(Context context, Intent intent) {
            // Invalidate a search on the old network; debounce connect/disconnect storms.
            discoveryGeneration++;
            refreshHandler.removeCallbacks(discoveryRetry);
            if (discoveryResumed) refreshHandler.postDelayed(discoveryRetry, 1000L);
        }
    };
    private final Runnable discoveryRetry = new Runnable() {
        @Override public void run() { startPcDiscovery(); }
    };

    private void startPcDiscovery() {
        if (!discoveryResumed) return;
        long remaining = 3500L - (SystemClock.elapsedRealtime() - lastDiscoveryAt);
        if (discoveryRunning || remaining > 0) {
            refreshHandler.removeCallbacks(discoveryRetry);
            refreshHandler.postDelayed(discoveryRetry, Math.max(250L, remaining));
            return;
        }
        // Pairing is explicit. Discovery must not use or save an unconfigured key.
        final String key = prefs.getString(K_KEY, "");
        if (key.length() == 0 || !key.equals(clean(editKey.getText()))) return;
        final String mac = clean(editMac.getText());
        final String host = clean(editHost.getText());
        final String broadcast = clean(editBcast.getText());
        final int generation = ++discoveryGeneration;
        final int editRevision = discoveryEditRevision;
        discoveryRunning = true;
        lastDiscoveryAt = SystemClock.elapsedRealtime();
        new Thread(new Runnable() {
            @Override public void run() {
                PcDiscovery.Result found = null;
                try { found = PcDiscovery.discover(key, mac, host); }
                catch (Exception ignored) { }
                final PcDiscovery.Result result = found;
                runOnUiThread(new Runnable() {
                    @Override public void run() {
                        discoveryRunning = false;
                        if (!discoveryResumed || isFinishing() || generation != discoveryGeneration
                                || discoveryEditRevision != editRevision || result == null
                                || !key.equals(prefs.getString(K_KEY, ""))
                                || !key.equals(clean(editKey.getText()))
                                || !mac.equals(clean(editMac.getText()))
                                || !host.equals(clean(editHost.getText()))
                                || !broadcast.equals(clean(editBcast.getText()))) return;
                        // Other consumers still use the established HTTP port 8765.
                        if (result.port != PORT) return;
                        editHost.setText(result.host);
                        editMac.setText(result.mac);
                        editBcast.setText(result.broadcast);
                        prefs.edit().putString(K_HOST, result.host).putString(K_MAC, result.mac)
                                .putString(K_BCAST, result.broadcast).apply();
                        if (!host.equals(result.host) || !mac.equals(result.mac) || !broadcast.equals(result.broadcast)) {
                            log(getString(R.string.discovery_found));
                            loadApps();
                            refreshStatus(false);
                        }
                    }
                });
            }
        }, "pc-lan-discovery").start();
    }

    @Override
    protected void attachBaseContext(Context newBase) {
        int mode = newBase.getSharedPreferences(PREFS, MODE_PRIVATE).getInt(K_THEME, THEME_AUTO);
        super.attachBaseContext(withNightMode(AppLocale.wrap(newBase), mode));
    }

    /**
     * Тема. values-* и values-night/* выбираются по uiMode конфигурации.
     *
     * Почему именно обёртка контекста, а не updateConfiguration(): второй способ
     * на практике применяет тему частично - проверено на устройстве с Android 13.
     * Страница перекрашивалась в светлую, а карточки оставались тёмными, потому что
     * Drawable.ConstantState (card_bg/status_bg/field_bg) переиспользуется из кэша
     * старых Resources и добирает цвета прежней конфигурации. createConfigurationContext
     * даёт свежий ResourcesImpl со своими кэшами - и цвета, и тема окна разрешаются
     * целиком под выбранный режим.
     *
     * "Авто" = ничего не подменяем, система сама решает по своей тёмной теме.
     * Через UiModeManager.setApplicationNightMode (API 31+) путь не сделан: там нет
     * публичного значения "вернуть системную тему" (в android.jar API 34 только
     * AUTO/NO/YES/CUSTOM), то есть обратно в "авто" вернуться было бы нечем.
     */
    private static Context withNightMode(Context base, int mode) {
        if (mode == THEME_AUTO) return base;
        int want = (mode == THEME_NIGHT)
                ? Configuration.UI_MODE_NIGHT_YES
                : Configuration.UI_MODE_NIGHT_NO;
        Configuration cfg = new Configuration(base.getResources().getConfiguration());
        cfg.uiMode = (cfg.uiMode & ~Configuration.UI_MODE_NIGHT_MASK) | want;
        return base.createConfigurationContext(cfg);
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        themeMode = prefs.getInt(K_THEME, THEME_AUTO);
        super.onCreate(savedInstanceState);
        setContentView(R.layout.main);

        editMac = (EditText) findViewById(R.id.edit_mac);
        editBcast = (EditText) findViewById(R.id.edit_bcast);
        editHost = (EditText) findViewById(R.id.edit_host);
        editKey = (EditText) findViewById(R.id.edit_key);
        btnOn = (Button) findViewById(R.id.btn_on);
        btnOff = (Button) findViewById(R.id.btn_off);
        btnRestart = (Button) findViewById(R.id.btn_restart);
        btnLock = (Button) findViewById(R.id.btn_lock);
        btnScreen = (Button) findViewById(R.id.btn_screen);
        btnView = (Button) findViewById(R.id.btn_view);
        btnMirror = (Button) findViewById(R.id.btn_mirror);
        addPhoneControlSetup();
        btnUpload = (Button) findViewById(R.id.btn_upload);
        btnUpload.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                if (fileUpload != null) return;
                savePrefsIfNeeded();
                if (prefs.getString(K_HOST, DEF_HOST).isEmpty() || prefs.getString(K_KEY, "").isEmpty()) {
                    log(getString(R.string.connection_required));
                    return;
                }
                Intent pick = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                pick.addCategory(Intent.CATEGORY_OPENABLE);
                pick.setType("*/*");
                pick.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                try { startActivityForResult(pick, REQ_UPLOAD); }
                catch (android.content.ActivityNotFoundException e) { log(getString(R.string.picker_missing)); }
            }
        });
        btnCancel = (Button) findViewById(R.id.btn_cancel);
        btnSave = (Button) findViewById(R.id.btn_save);
        btnTheme = (Button) findViewById(R.id.btn_theme);
        final ViewGroup languageParent = (ViewGroup) btnTheme.getParent();
        Button languageButton = new Button(this);
        languageButton.setText(R.string.language_button);
        languageParent.addView(languageButton, languageParent.indexOfChild(btnTheme) + 1);
        languageButton.setOnClickListener(new View.OnClickListener() {
            public void onClick(View view) {
                new AlertDialog.Builder(MainActivity.this)
                        .setTitle(R.string.language_title)
                        .setSingleChoiceItems(new String[]{"Русский", "English"},
                                "ru".equals(AppLocale.language(MainActivity.this)) ? 0 : 1,
                                new DialogInterface.OnClickListener() {
                                    public void onClick(DialogInterface dialog, int which) {
                                        String language = which == 0 ? "ru" : "en";
                                        dialog.dismiss();
                                        if (language.equals(AppLocale.language(MainActivity.this))) return;
                                        // Recreate restores EditText view state; do not save pairing/key here.
                                        AppLocale.select(MainActivity.this, language);
                                        recreate();
                                    }
                                }).show();
            }
        });
        Button pairButton = new Button(this);
        pairButton.setText(R.string.pair_title);
        languageParent.addView(pairButton);
        pairButton.setOnClickListener(new View.OnClickListener(){public void onClick(View v){startActivityForResult(new Intent(MainActivity.this, PairingActivity.class), REQ_PAIR);}});
        statusView = (TextView) findViewById(R.id.status_view);
        pcStatus = (TextView) findViewById(R.id.pc_status);
        monCpu = (TextView) findViewById(R.id.mon_cpu);
        monRam = (TextView) findViewById(R.id.mon_ram);
        monGpu = (TextView) findViewById(R.id.mon_gpu);
        monVram = (TextView) findViewById(R.id.mon_vram);
        monitorUpdated = (TextView) findViewById(R.id.monitor_updated);
        barCpu = (ProgressBar) findViewById(R.id.bar_cpu);
        barRam = (ProgressBar) findViewById(R.id.bar_ram);
        barGpu = (ProgressBar) findViewById(R.id.bar_gpu);
        barVram = (ProgressBar) findViewById(R.id.bar_vram);
        scroll = (ScrollView) findViewById(R.id.scroll);

        editMac.setText(prefs.getString(K_MAC, DEF_MAC));
        editBcast.setText(prefs.getString(K_BCAST, DEF_BCAST));
        editHost.setText(prefs.getString(K_HOST, DEF_HOST));
        editKey.setText(prefs.getString(K_KEY, ""));
        loadedPairKey = prefs.getString(K_KEY, "");
        loadedPairRevision = prefs.getLong("pair_revision", 0);
        TextWatcher discoveryEdits = new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int start, int count, int after) { }
            public void onTextChanged(CharSequence s, int start, int before, int count) { discoveryEditRevision++; }
            public void afterTextChanged(Editable s) { }
        };
        editMac.addTextChangedListener(discoveryEdits);
        editHost.addTextChangedListener(discoveryEdits);
        editBcast.addTextChangedListener(discoveryEdits);
        editKey.addTextChangedListener(discoveryEdits);
        btnTheme.setText(themeLabel(themeMode));

        btnSave.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { savePrefs(); }
        });
        btnOn.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { sendWake(); }
        });
        btnOff.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { requestPower("off"); }
        });
        btnRestart.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { requestPower("restart"); }
        });
        btnLock.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { requestPower("lock"); }
        });
        btnScreen.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { requestPower("screen"); }
        });
        btnView.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                startActivity(new Intent(MainActivity.this, ScreenActivity.class));
            }
        });
        btnMirror.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { onMirrorClick(); }
        });
        btnCancel.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { requestPower("cancel"); }
        });
        btnTheme.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { cycleTheme(); }
        });

        buildAppTiles();
        buildActionTiles();
        if (pcStatus != null) {
            pcStatus.setOnClickListener(new View.OnClickListener() {
                public void onClick(View v) { showMonitorDialog(); }
            });
        }
        playIntro();
    }

    @Override
    protected void onResume() {
        super.onResume();
        // An external camera/deep-link can finish pairing outside startActivityForResult.
        String currentPairKey = prefs.getString(K_KEY, "");
        long currentPairRevision = prefs.getLong("pair_revision", 0);
        if (loadedPairRevision != currentPairRevision || loadedPairKey != null && !loadedPairKey.equals(currentPairKey)) {
            editMac.setText(prefs.getString(K_MAC, DEF_MAC));
            editBcast.setText(prefs.getString(K_BCAST, DEF_BCAST));
            editHost.setText(prefs.getString(K_HOST, DEF_HOST));
            editKey.setText(currentPairKey);
        }
        loadedPairKey = currentPairKey;
        loadedPairRevision = currentPairRevision;
        discoveryResumed = true;
        if (!discoveryRegistered) {
            IntentFilter filter = new IntentFilter(WifiManager.NETWORK_STATE_CHANGED_ACTION);
            if (Build.VERSION.SDK_INT >= 33) registerReceiver(discoveryReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
            else registerReceiver(discoveryReceiver, filter);
            discoveryRegistered = true;
        }
        startPcDiscovery();
        loadApps();
        refreshStatus(false);
        refreshHandler.removeCallbacks(autoRefresh);
        refreshHandler.postDelayed(autoRefresh, 5000L);
        updateMirrorButton();
    }

    @Override
    protected void onPause() {
        discoveryResumed = false;
        appsGeneration++;
        HttpURLConnection catalogConnection=appsConnection;if(catalogConnection!=null)catalogConnection.disconnect();
        Thread catalogThread=appsThread;if(catalogThread!=null)catalogThread.interrupt();
        discoveryGeneration++;
        refreshHandler.removeCallbacks(discoveryRetry);
        if (discoveryRegistered) {
            unregisterReceiver(discoveryReceiver);
            discoveryRegistered = false;
        }
        super.onPause();
        refreshHandler.removeCallbacks(autoRefresh);
    }

    @Override
    protected void onDestroy() {
        if (fileUpload != null) fileUpload.dispose();
        super.onDestroy();
    }

    // ---------- трансляция телефона на ПК ----------

    private void addPhoneControlSetup() {
        final ViewGroup parent = (ViewGroup) btnMirror.getParent();
        Button setup = (Button) getLayoutInflater().inflate(R.layout.phone_control_setup, parent, false);
        parent.addView(setup, parent.indexOfChild(btnMirror) + 1);
        setup.setOnClickListener(new View.OnClickListener() {
            public void onClick(View view) {
                new AlertDialog.Builder(MainActivity.this)
                        .setTitle(R.string.phone_control_label)
                        .setMessage(R.string.phone_control_explanation)
                        .setNegativeButton(android.R.string.cancel, null)
                        .setPositiveButton(R.string.phone_control_open_settings, new DialogInterface.OnClickListener() {
                            public void onClick(DialogInterface dialog, int which) {
                                try {
                                    startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS));
                                } catch (android.content.ActivityNotFoundException e) {
                                    log(getString(R.string.phone_control_settings_missing));
                                }
                            }
                        }).show();
            }
        });
    }

    private void updateMirrorButton() {
        if (btnMirror == null) return;
        btnMirror.setText(MirrorService.running
                ? R.string.btn_mirror_stop : R.string.btn_mirror);
    }

    private void onMirrorClick() {
        if (MirrorService.running) {
            stopMirror();
            return;
        }
        savePrefsIfNeeded();
        if (prefs.getString(K_HOST, DEF_HOST).length() == 0) {
            log(getString(R.string.mirror_no_host));
            return;
        }
        if (prefs.getString(K_KEY, "").length() == 0) {
            log(getString(R.string.mirror_no_key));
            return;
        }
        requestMirrorPermissions();
    }

    private void stopMirror() {
        Intent stop = new Intent(this, MirrorService.class).setAction(MirrorService.ACTION_STOP);
        startService(stop);
        log(getString(R.string.mirror_stopping));
        refreshHandler.postDelayed(new Runnable() {
            public void run() { updateMirrorButton(); }
        }, 600L);
    }

    private void requestMirrorPermissions() {
        if (Build.VERSION.SDK_INT < 23) {
            askProjection();
            return;
        }
        ArrayList<String> need = new ArrayList<String>();
        if (Build.VERSION.SDK_INT >= 29
                && checkSelfPermission(Manifest.permission.RECORD_AUDIO)
                != PackageManager.PERMISSION_GRANTED) {
            need.add(Manifest.permission.RECORD_AUDIO);
        }
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            need.add(Manifest.permission.POST_NOTIFICATIONS);
        }
        if (need.isEmpty()) {
            askProjection();
            return;
        }
        requestPermissions(need.toArray(new String[0]), REQ_PERMS);
    }

    private void askProjection() {
        MediaProjectionManager mgr =
                (MediaProjectionManager) getSystemService(MEDIA_PROJECTION_SERVICE);
        // Controls address the physical display, never a cropped single-app capture.
        Intent capture = Build.VERSION.SDK_INT >= 34
                ? mgr.createScreenCaptureIntent(android.media.projection.MediaProjectionConfig.createConfigForDefaultDisplay())
                : mgr.createScreenCaptureIntent();
        startActivityForResult(capture, REQ_PROJECTION);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if (requestCode == REQ_PERMS) {
            // Отказ от микрофона/уведомлений не блокирует экран: звук просто не пойдёт.
            askProjection();
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQ_PAIR) {
            if (resultCode == RESULT_OK) {
                discoveryGeneration++;
                editMac.setText(prefs.getString(K_MAC, DEF_MAC));
                editBcast.setText(prefs.getString(K_BCAST, DEF_BCAST));
                editHost.setText(prefs.getString(K_HOST, DEF_HOST));
                editKey.setText(prefs.getString(K_KEY, ""));
            }
            return;
        }
        if (requestCode == REQ_UPLOAD) {
            if (resultCode == RESULT_OK && data != null && data.getData() != null && fileUpload == null) {
                btnUpload.setEnabled(false);
                fileUpload = new FileUpload(this, new FileUpload.Result() {
                    public void done(String message) {
                        fileUpload = null;
                        btnUpload.setEnabled(true);
                        log(message);
                        new AlertDialog.Builder(MainActivity.this).setTitle(getString(R.string.upload_result_title))
                                .setMessage(message).setPositiveButton(getString(R.string.okay), null).show();
                    }
                });
                fileUpload.start(data.getData(), prefs.getString(K_HOST, DEF_HOST), prefs.getString(K_KEY, ""));
            }
            return;
        }
        if (requestCode != REQ_PROJECTION) return;
        if (resultCode != RESULT_OK || data == null) {
            log(getString(R.string.mirror_denied));
            return;
        }
        final int code = resultCode;
        final Intent grant = data;
        final String host = prefs.getString(K_HOST, DEF_HOST);
        final String key = prefs.getString(K_KEY, "");
        log(getString(R.string.mirror_starting));
        new Thread(new Runnable() {
            public void run() {
                String reply;
                boolean ok = false;
                try {
                    String url = "http://" + host + ":" + PORT + "/mirror?port="
                            + MIRROR_PORT + "&key=" + urlEncode(key);
                    reply = httpGet(url, new String[1]);
                    ok = reply.contains("клиент");
                } catch (Exception e) {
                    reply = describe(e);
                }
                final boolean good = ok;
                final String text = reply;
                runOnUiThread(new Runnable() {
                    public void run() {
                        if (isFinishing()) return;
                        if (!good) {
                            log(getString(R.string.mirror_client_failed, text));
                            return;
                        }
                        startMirrorService(code, grant, key);
                    }
                });
            }
        }).start();
    }

    private void startMirrorService(int code, Intent grant, String key) {
        Intent svc = new Intent(this, MirrorService.class)
                .setAction(MirrorService.ACTION_START)
                .putExtra(MirrorService.EXTRA_CODE, code)
                .putExtra(MirrorService.EXTRA_DATA, grant)
                .putExtra(MirrorService.EXTRA_KEY, key)
                .putExtra(MirrorService.EXTRA_PORT, MIRROR_PORT);
        if (Build.VERSION.SDK_INT >= 26) startForegroundService(svc);
        else startService(svc);
        log(getString(R.string.mirror_started));
        refreshHandler.postDelayed(new Runnable() {
            public void run() { updateMirrorButton(); }
        }, 1500L);
    }

    // ---------- состояние ПК ----------

    private void refreshStatus(final boolean pulse) {
        if (pcStatus == null) return;
        final String host = prefs.getString(K_HOST, DEF_HOST);
        final String key = prefs.getString(K_KEY, "");
        if (host.length() == 0 || key.length() == 0) {
            pcStatus.setText(R.string.pc_no_cfg);
            return;
        }
        final String url = "http://" + host + ":" + PORT + "/status?key=" + urlEncode(key);
        new Thread(new Runnable() {
            public void run() {
                JSONObject data = null;
                try {
                    data = new JSONObject(httpGet(url, new String[] { "connect" }));
                } catch (Exception ignored) {
                }
                final JSONObject result = data;
                runOnUiThread(new Runnable() {
                    public void run() {
                        if (isFinishing() || pcStatus == null) return;
                        if (result == null) {
                            lastStatus = null;
                            pcStatus.setText(R.string.pc_offline);
                            if (monitorUpdated != null) monitorUpdated.setText("");
                            updateDialog(null);
                        } else {
                            lastStatus = result;
                            applyStatus(result);
                        }
                        if (pulse) {
                            pcStatus.animate().cancel();
                            pcStatus.setAlpha(0.6f);
                            pcStatus.animate().alpha(1f).setDuration(220L).start();
                        }
                    }
                });
            }
        }).start();
    }

    private void applyStatus(JSONObject o) {
        int cpu = o.optInt("cpu", 0);
        int ram = o.optInt("ram", 0);
        long totalMb = o.optLong("mem_total_mb", 0L);
        long freeMb = o.optLong("mem_free_mb", 0L);
        long usedMb = Math.max(0L, totalMb - freeMb);
        JSONObject gpu = o.optJSONObject("gpu");
        int gpuUtil = gpu == null ? -1 : gpu.optInt("util", -1);
        int vramUsed = gpu == null ? -1 : gpu.optInt("mem_used_mb", -1);
        int vramTotal = gpu == null ? -1 : gpu.optInt("mem_total_mb", -1);
        int vramPct = vramUsed > 0 && vramTotal > 0
                ? Math.round(100f * vramUsed / vramTotal) : 0;

        pcStatus.setText(getString(R.string.pc_online_fmt, cpu, ram,
                shortDuration(o.optLong("uptime_s", 0L))));

        meter(monCpu, barCpu, cpu, getString(R.string.mon_pct, cpu));
        meter(monRam, barRam, ram, getString(R.string.mon_pair, gb(usedMb), gb(totalMb)));
        meter(monGpu, barGpu, Math.max(0, gpuUtil),
                gpuUtil < 0 ? getString(R.string.mon_na) : getString(R.string.mon_pct, gpuUtil));
        meter(monVram, barVram, vramPct,
                vramTotal > 0 ? getString(R.string.mon_pair, gb(vramUsed), gb(vramTotal))
                              : getString(R.string.mon_na));

        if (monitorUpdated != null) {
            monitorUpdated.setText(getString(R.string.mon_updated, ts.format(new Date())));
        }
        updateDialog(o);
    }

    private void showMonitorDialog() {
        if (monitorDialog == null) {
            View v = LayoutInflater.from(this).inflate(R.layout.dialog_monitor, null);
            dCpu = (TextView) v.findViewById(R.id.dlg_cpu);
            dRam = (TextView) v.findViewById(R.id.dlg_ram);
            dGpu = (TextView) v.findViewById(R.id.dlg_gpu);
            dVram = (TextView) v.findViewById(R.id.dlg_vram);
            dGpuName = (TextView) v.findViewById(R.id.dlg_gpu_name);
            dTemp = (TextView) v.findViewById(R.id.dlg_temp);
            dUptime = (TextView) v.findViewById(R.id.dlg_uptime);
            dUpdated = (TextView) v.findViewById(R.id.dlg_updated);
            dOffline = (TextView) v.findViewById(R.id.dlg_offline);
            dBarCpu = (ProgressBar) v.findViewById(R.id.dlg_bar_cpu);
            dBarRam = (ProgressBar) v.findViewById(R.id.dlg_bar_ram);
            dBarGpu = (ProgressBar) v.findViewById(R.id.dlg_bar_gpu);
            dBarVram = (ProgressBar) v.findViewById(R.id.dlg_bar_vram);
            Button refresh = (Button) v.findViewById(R.id.dlg_refresh);
            refresh.setOnClickListener(new View.OnClickListener() {
                public void onClick(View x) { refreshStatus(true); }
            });
            monitorDialog = new AlertDialog.Builder(this).setView(v).create();
            monitorDialog.setOnDismissListener(new DialogInterface.OnDismissListener() {
                public void onDismiss(DialogInterface dialog) { monitorDialog = null; }
            });
        }
        updateDialog(lastStatus);
        monitorDialog.show();
        refreshStatus(true);
    }

    private void updateDialog(JSONObject o) {
        if (monitorDialog == null || dCpu == null) return;
        if (o == null) {
            dOffline.setVisibility(View.VISIBLE);
            dUpdated.setText("");
            meter(dCpu, dBarCpu, 0, getString(R.string.mon_na));
            meter(dRam, dBarRam, 0, getString(R.string.mon_na));
            meter(dGpu, dBarGpu, 0, getString(R.string.mon_na));
            meter(dVram, dBarVram, 0, getString(R.string.mon_na));
            dGpuName.setText(R.string.mon_na);
            dTemp.setText(R.string.mon_na);
            dUptime.setText(R.string.mon_na);
            return;
        }
        dOffline.setVisibility(View.GONE);

        int cpu = o.optInt("cpu", 0);
        int ram = o.optInt("ram", 0);
        long totalMb = o.optLong("mem_total_mb", 0L);
        long freeMb = o.optLong("mem_free_mb", 0L);
        long usedMb = Math.max(0L, totalMb - freeMb);
        JSONObject gpu = o.optJSONObject("gpu");
        int gpuUtil = gpu == null ? -1 : gpu.optInt("util", -1);
        int vramUsed = gpu == null ? -1 : gpu.optInt("mem_used_mb", -1);
        int vramTotal = gpu == null ? -1 : gpu.optInt("mem_total_mb", -1);
        int vramPct = vramUsed > 0 && vramTotal > 0
                ? Math.round(100f * vramUsed / vramTotal) : 0;

        meter(dCpu, dBarCpu, cpu, getString(R.string.mon_pct, cpu));
        meter(dRam, dBarRam, ram, getString(R.string.mon_pair, gb(usedMb), gb(totalMb)));
        meter(dGpu, dBarGpu, Math.max(0, gpuUtil),
                gpuUtil < 0 ? getString(R.string.mon_na) : getString(R.string.mon_pct, gpuUtil));
        meter(dVram, dBarVram, vramPct,
                vramTotal > 0 ? getString(R.string.mon_pair, gb(vramUsed), gb(vramTotal))
                              : getString(R.string.mon_na));
        dGpuName.setText(gpu == null ? getString(R.string.mon_na)
                : gpu.optString("name", getString(R.string.mon_na)));
        dTemp.setText(gpu == null ? getString(R.string.mon_na)
                : getString(R.string.dlg_temp_fmt, gpu.optInt("temp", 0)));
        dUptime.setText(shortDuration(o.optLong("uptime_s", 0L)));
        dUpdated.setText(getString(R.string.mon_updated, ts.format(new Date())));
    }

    private static void meter(TextView label, ProgressBar bar, int pct, String text) {
        if (label != null) label.setText(text);
        if (bar != null) bar.setProgress(Math.max(0, Math.min(100, pct)));
    }

    private static String gb(long mb) {
        return String.format(Locale.getDefault(), "%.1f", mb / 1024.0);
    }

    private String shortDuration(long seconds) {
        if (seconds >= 3600) {
            return getString(R.string.duration_hm, seconds / 3600, (seconds % 3600) / 60);
        }
        if (seconds >= 60) return getString(R.string.duration_m, seconds / 60);
        return getString(R.string.duration_s, seconds);
    }

    // ---------- плитки приложений ----------

    private void loadApps() {
        final String host=prefs.getString(K_HOST,DEF_HOST),key=prefs.getString(K_KEY,"");
        final int generation=++appsGeneration;
        HttpURLConnection previous=appsConnection;if(previous!=null)previous.disconnect();
        Thread previousThread=appsThread;if(previousThread!=null)previousThread.interrupt();
        remoteApps.clear();appsLoaded=false;buildAppTiles();
        if(!discoveryResumed || host.isEmpty() || key.isEmpty())return;
        appsThread=new Thread(new Runnable(){public void run(){
            final List<RemoteApp> found=new ArrayList<RemoteApp>();boolean success=false;
            HttpURLConnection connection=null;
            try {
                connection=(HttpURLConnection)new URL("http://"+host+":"+PORT+"/apps?key="+urlEncode(key)).openConnection();
                appsConnection=connection;
                connection.setConnectTimeout(4000);connection.setReadTimeout(4000);connection.setInstanceFollowRedirects(false);
                if(Thread.currentThread().isInterrupted())throw new IOException("Cancelled");
                if(connection.getResponseCode()!=200)throw new IOException("Catalog unavailable");
                java.io.ByteArrayOutputStream bytes=new java.io.ByteArrayOutputStream();
                try(InputStream in=connection.getInputStream()){
                    byte[] buffer=new byte[1024];int n;
                    while((n=in.read(buffer))!=-1){if(Thread.currentThread().isInterrupted() || bytes.size()+n>65536)throw new IOException("Catalog limit");bytes.write(buffer,0,n);}
                }
                JSONObject body=new JSONObject(bytes.toString("UTF-8"));
                if(!Boolean.TRUE.equals(body.get("ok")))throw new IOException("Invalid catalog");
                org.json.JSONArray apps=body.getJSONArray("apps");if(apps.length()>100)throw new IOException("Catalog limit");
                java.util.HashSet<String> ids=new java.util.HashSet<String>();
                for(int i=0;i<apps.length();i++){
                    JSONObject app=apps.getJSONObject(i);
                    Object id=app.get("id"),name=app.get("name"),canClose=app.get("can_close");
                    if(!(id instanceof String) || !(name instanceof String) || !(canClose instanceof Boolean))throw new IOException("Invalid catalog");
                    String ident=(String)id,label=(String)name;
                    if(!ident.matches("[A-Za-z0-9][A-Za-z0-9_.-]{0,127}") || !ids.add(ident) || label.trim().isEmpty() || label.length()>200 || label.matches("(?s).*[\\p{Cntrl}].*"))throw new IOException("Invalid catalog");
                    found.add(new RemoteApp(ident,label,(Boolean)canClose));
                }
                success=true;
            }catch(Exception ignored){}finally{if(connection!=null)connection.disconnect();if(appsConnection==connection)appsConnection=null;}
            final boolean loaded=success;
            runOnUiThread(new Runnable(){public void run(){if(!discoveryResumed || isFinishing() || generation!=appsGeneration || !host.equals(prefs.getString(K_HOST,"")) || !key.equals(prefs.getString(K_KEY,"")))return;
                remoteApps.clear();if(loaded)remoteApps.addAll(found);appsLoaded=loaded;buildAppTiles();}});
        }},"pc-app-catalog");appsThread.start();
    }

    private void buildAppTiles() {
        LinearLayout grid=(LinearLayout)findViewById(R.id.apps_grid);if(grid==null)return;
        grid.removeAllViews();appTiles.clear();
        if(remoteApps.isEmpty()){
            TextView empty=new TextView(this);empty.setText(appsLoaded?R.string.apps_empty:R.string.apps_unavailable);grid.addView(empty);
            Button refresh=new Button(this);refresh.setText(R.string.apps_refresh);refresh.setOnClickListener(new View.OnClickListener(){public void onClick(View v){loadApps();}});grid.addView(refresh);return;
        }
        int gap=dpInt(6f);
        for(int i=0;i<remoteApps.size();i+=2){
            LinearLayout row=new LinearLayout(this);row.setOrientation(LinearLayout.HORIZONTAL);
            LinearLayout.LayoutParams rp=new LinearLayout.LayoutParams(-1,-2);rp.bottomMargin=dpInt(12f);row.setLayoutParams(rp);
            addTile(row,remoteApps.get(i),true,gap);
            if(i+1<remoteApps.size())addTile(row,remoteApps.get(i+1),false,gap);
            else {View spacer=new View(this);spacer.setLayoutParams(new LinearLayout.LayoutParams(0,1,1f));row.addView(spacer);}
            grid.addView(row);
        }
    }
    private void addTile(LinearLayout row,final RemoteApp app,boolean left,int gap){
        View tile=getLayoutInflater().inflate(R.layout.tile_app,row,false);
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,-2,1f);lp.setMargins(left?0:gap,0,left?gap:0,0);tile.setLayoutParams(lp);
        ImageView icon=(ImageView)tile.findViewById(R.id.tile_icon);icon.setImageResource(R.drawable.ic_program);icon.setColorFilter(getResources().getColor(R.color.primary));
        ((TextView)tile.findViewById(R.id.tile_label)).setText(app.name);
        tile.setOnClickListener(new View.OnClickListener(){public void onClick(View v){log(getString(R.string.launch_fmt,app.name));sendRequest("/app?id="+urlEncode(app.id),"app");}});
        if(app.canClose)tile.setOnLongClickListener(new View.OnLongClickListener(){public boolean onLongClick(View v){confirmClose(app);return true;}});
        appTiles.add(tile);row.addView(tile);
    }
    private void confirmClose(final RemoteApp app){
        if(!app.canClose)return;
        new AlertDialog.Builder(this).setTitle(getString(R.string.dlg_close_title,app.name)).setMessage(getString(R.string.dlg_close_msg,app.name))
            .setNegativeButton(android.R.string.cancel,null).setPositiveButton(R.string.dlg_close_yes,new DialogInterface.OnClickListener(){public void onClick(DialogInterface d,int w){sendRequest("/app?id="+urlEncode(app.id)+"&action=close","app");}}).show();
    }

    // ---------- быстрые команды ----------

    private void buildActionTiles() {
        LinearLayout grid = (LinearLayout) findViewById(R.id.actions_grid);
        if (grid == null) return;
        int gap = dpInt(8f);
        int columns = 3;
        for (int start = 0; start < ACT_KEYS.length; start += columns) {
            LinearLayout row = new LinearLayout(this);
            row.setOrientation(LinearLayout.HORIZONTAL);
            LinearLayout.LayoutParams rp = new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            rp.bottomMargin = (start + columns < ACT_KEYS.length) ? gap : 0;
            row.setLayoutParams(rp);

            for (int col = 0; col < columns; col++) {
                int index = start + col;
                if (index < ACT_KEYS.length) {
                    addActionTile(row, index, col, columns, gap);
                } else {
                    View spacer = new View(this);
                    spacer.setLayoutParams(new LinearLayout.LayoutParams(0, 1, 1f));
                    row.addView(spacer);
                }
            }
            grid.addView(row);
        }
    }

    private void addActionTile(LinearLayout row, final int index, int col, int columns, int gap) {
        View tile = getLayoutInflater().inflate(R.layout.tile_action, row, false);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        int half = gap / 2;
        lp.setMargins(col == 0 ? 0 : half, 0, col == columns - 1 ? 0 : half, 0);
        tile.setLayoutParams(lp);

        ImageView icon = (ImageView) tile.findViewById(R.id.tile_icon);
        icon.setImageResource(ACT_ICONS[index]);
        // Башмак — зелёный, как кнопка «Включить»; остальные команды — акцентные.
        int tint = getResources().getColor(index == 0 ? R.color.wake_text : R.color.primary);
        icon.setColorFilter(tint);
        TextView label = (TextView) tile.findViewById(R.id.tile_label);
        label.setText(ACT_LABELS[index]);

        tile.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { requestAction(index); }
        });
        actionTiles.add(tile);
        row.addView(tile);
    }

    private void requestAction(int index) {
        String key = ACT_KEYS[index];
        if (key.equals("away")) {
            log(getString(R.string.away_log));
            sendRequest("/away", "away");
        } else if (key.equals("timer30") || key.equals("timer60")) {
            int minutes = key.equals("timer30") ? 30 : 60;
            btnCancel.setVisibility(View.VISIBLE);
            log(getString(R.string.timer_fmt, minutes));
            sendRequest("/timer?min=" + minutes, "timer");
        } else {
            log(getString(R.string.media_fmt, getString(ACT_LABELS[index])));
            sendRequest("/media?action=" + key, "media");
        }
    }

    /**
     * Мягкое каскадное появление блоков: каждый ребёнок корня въезжает на 14dp вверх
     * и проявляется с задержкой в 25 мс. Отдельные id блокам не нужны - порядок детей
     * уже совпадает с порядком чтения сверху вниз.
     */
    private void playIntro() {
        ViewGroup root = (ViewGroup) findViewById(R.id.root);
        if (root == null) return;
        int count = root.getChildCount();
        for (int i = 0; i < count; i++) {
            View v = root.getChildAt(i);
            v.setAlpha(0f);
            v.setTranslationY(dp(14f));
            v.animate()
                    .alpha(1f)
                    .translationY(0f)
                    .setStartDelay(25L * i)
                    .setDuration(260L)
                    .setInterpolator(new DecelerateInterpolator())
                    .start();
        }
    }

    private float dp(float value) {
        return value * getResources().getDisplayMetrics().density;
    }

    private int dpInt(float value) {
        return Math.round(dp(value));
    }

    // ---------- настройки ----------

    private boolean savePrefs() {
        String mac = clean(editMac.getText());
        String bcast = clean(editBcast.getText());
        String host = clean(editHost.getText());
        String key = clean(editKey.getText());
        if (mac.length() > 0 && mac.replaceAll("[^0-9A-Fa-f]", "").length() != 12) {
            log(getString(R.string.error_fmt, getString(R.string.no_mac)));
            return false;
        }
        prefs.edit()
                .putString(K_MAC, mac).putString(K_BCAST, bcast)
                .putString(K_HOST, host).putString(K_KEY, key)
                .apply();
        log(getString(R.string.saved));
        refreshHandler.removeCallbacks(discoveryRetry);
        if (discoveryResumed) { refreshHandler.post(discoveryRetry); loadApps(); }
        return true;
    }

    private static String clean(CharSequence cs) {
        return cs == null ? "" : cs.toString().trim();
    }

    // ---------- тема ----------

    private static int themeLabelRes(int mode) {
        if (mode == THEME_DAY) return R.string.theme_day;
        if (mode == THEME_NIGHT) return R.string.theme_night;
        return R.string.theme_auto;
    }

    private String themeLabel(int mode) {
        return getResources().getString(themeLabelRes(mode));
    }

    private void cycleTheme() {
        themeMode = (themeMode + 1) % 3;
        prefs.edit().putInt(K_THEME, themeMode).apply();
        log(getString(R.string.theme_changed_fmt, themeLabel(themeMode)));
        recreate();
    }

    // ---------- Wake-on-LAN ----------

    private void sendWake() {
        savePrefsIfNeeded();
        final String mac = prefs.getString(K_MAC, DEF_MAC);
        final String bcast = prefs.getString(K_BCAST, DEF_BCAST);
        if (bcast.length() == 0) {
            log(getString(R.string.broadcast_required));
            return;
        }
        final byte[] packet;
        try {
            packet = magicPacket(mac);
        } catch (IllegalArgumentException e) {
            log(getString(R.string.error_fmt, getString(R.string.no_mac)));
            return;
        }
        setBusy(true);
        log("WOL: " + formatMac(mac) + " -> " + bcast + ":9");
        new Thread(new Runnable() {
            public void run() {
                String result;
                DatagramSocket sock = null;
                try {
                    int sent = 0;
                    sock = new DatagramSocket();
                    sock.setBroadcast(true);
                    int[] ports = new int[] { 9, 7 };
                    InetAddress target = InetAddress.getByName(bcast);
                    for (int i = 0; i < ports.length; i++) {
                        DatagramPacket p = new DatagramPacket(packet, packet.length, target, ports[i]);
                        sock.send(p);
                        sent++;
                    }
                    // Вторая отправка точечно на IP ПК: часть домашних роутеров глушит
                    // широковещание, но пропускает обычный unicast внутри той же подсети.
                    String host = prefs.getString(K_HOST, DEF_HOST);
                    if (host.length() > 0 && !host.equals(bcast)) {
                        try {
                            DatagramPacket p2 = new DatagramPacket(packet, packet.length,
                                    InetAddress.getByName(host), 9);
                            sock.send(p2);
                            sent++;
                        } catch (Exception ignored) { }
                    }
                    result = getString(R.string.wake_sent_fmt, sent);
                } catch (Exception e) {
                    result = getString(R.string.send_failed_fmt, describe(e));
                } finally {
                    if (sock != null) sock.close();
                }
                logUi(result);
                setBusy(false);
            }
        }).start();
    }

    /** 6 x FF + 16 x MAC = 102 байта, классический magic packet. */
    private static byte[] magicPacket(String mac) {
        String hex = mac.replaceAll("[^0-9A-Fa-f]", "");
        if (hex.length() != 12) throw new IllegalArgumentException("bad mac");
        byte[] addr = new byte[6];
        for (int i = 0; i < 6; i++) {
            addr[i] = (byte) Integer.parseInt(hex.substring(i * 2, i * 2 + 2), 16);
        }
        byte[] msg = new byte[6 + 16 * 6];
        for (int i = 0; i < 6; i++) msg[i] = (byte) 0xFF;
        for (int r = 0; r < 16; r++) System.arraycopy(addr, 0, msg, 6 + r * 6, 6);
        return msg;
    }

    private static String formatMac(String mac) {
        String hex = mac.replaceAll("[^0-9A-Fa-f]", "").toUpperCase(Locale.US);
        if (hex.length() != 12) return mac;
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 12; i += 2) {
            if (i > 0) sb.append(':');
            sb.append(hex, i, i + 2);
        }
        return sb.toString();
    }

    // ---------- команды по HTTP ----------

    private void requestPower(String command) {
        sendRequest("/" + command, command);
    }

    private void sendRequest(final String path, final String command) {
        savePrefsIfNeeded();
        final String host = prefs.getString(K_HOST, DEF_HOST);
        final String key = prefs.getString(K_KEY, "");
        if (host.length() == 0) { log(getString(R.string.host_required)); return; }
        if (key.length() == 0) { log(getString(R.string.error_fmt, getString(R.string.no_key))); return; }
        if (command.equals("off") || command.equals("restart")) {
            btnCancel.setVisibility(View.VISIBLE);
            log(command.equals("off")
                    ? getString(R.string.shutdown_requested)
                    : getString(R.string.restart_requested));
        }
        setBusy(true);
        final String sep = path.indexOf('?') >= 0 ? "&" : "?";
        final String url = "http://" + host + ":" + PORT + path + sep + "key=" + urlEncode(key);
        new Thread(new Runnable() {
            public void run() {
                String result;
                final String[] stage = { "connect" };
                try {
                    String body = httpGet(url, stage);
                    if (body.length() == 0) body = getString(R.string.empty_reply);
                    result = getString(R.string.reply_fmt, body);
                } catch (Exception e) {
                    result = powerError(e, stage[0], host, command);
                }
                logUi(result);
                setBusy(false);
            }
        }).start();
    }

    /**
     * Текст ошибки зависит от того, чем именно умер запрос, - «ПК выключен» и «порт закрыт
     * брандмауэром» лечатся по-разному, сваливать их в одну строку нельзя.
     * Отдельно важна stage=="response": там соединение уже удалось, значит shutdown мог
     * встать, и молчать про это нельзя - надо звать на «Отменить».
     */
    private String powerError(Exception e, String stage, String host, String command) {
        String detail = describe(e);
        if (e instanceof UnknownHostException) return getString(R.string.power_bad_host, host);
        if (e instanceof ConnectException) return getString(R.string.power_refused, PORT, detail);
        if (e instanceof SocketTimeoutException && stage.equals("connect"))
            return getString(R.string.power_timeout, host, PORT);
        if (stage.equals("response")) {
            if (command.equals("off") || command.equals("restart"))
                return getString(R.string.power_uncertain, detail);
            return getString(R.string.power_response_lost, detail);
        }
        return getString(R.string.power_unreachable, detail);
    }

    private static String httpGet(String url, String[] stage) throws IOException {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(4000);
        c.setReadTimeout(4000);
        c.setRequestMethod("GET");
        c.setUseCaches(false);
        int code = c.getResponseCode();
        stage[0] = "response";
        InputStream in = (code >= 400) ? c.getErrorStream() : c.getInputStream();
        StringBuilder sb = new StringBuilder();
        try {
            if (in != null) {
                BufferedReader r = new BufferedReader(new InputStreamReader(in, "UTF-8"));
                String line;
                while ((line = r.readLine()) != null) sb.append(line);
                r.close();
            }
        } finally {
            // disconnect в finally: без него таймаут на чтении оставлял сокет висеть,
            // а кнопок "выключить/отменить" по тапу на каждую попытку.
            c.disconnect();
        }
        if (code != 200) throw new IOException("HTTP " + code + " " + sb);
        return sb.toString().trim();
    }

    private static String urlEncode(String s) {
        StringBuilder sb = new StringBuilder();
        byte[] bytes;
        try {
            bytes = s.getBytes("UTF-8");
        } catch (Exception e) {
            bytes = s.getBytes();
        }
        for (int b = 0; b < bytes.length; b++) {
            int v = bytes[b] & 0xFF;
            boolean safe = (v >= 'a' && v <= 'z') || (v >= 'A' && v <= 'Z')
                    || (v >= '0' && v <= '9') || v == '-' || v == '_' || v == '.' || v == '~';
            if (safe) {
                sb.append((char) v);
            } else {
                sb.append('%');
                sb.append(Character.toUpperCase(Character.forDigit((v >> 4) & 0xF, 16)));
                sb.append(Character.toUpperCase(Character.forDigit(v & 0xF, 16)));
            }
        }
        return sb.toString();
    }

    // ---------- мелочь для UI ----------

    private void savePrefsIfNeeded() {
        if (!prefs.getString(K_MAC, DEF_MAC).equals(clean(editMac.getText()))
                || !prefs.getString(K_BCAST, DEF_BCAST).equals(clean(editBcast.getText()))
                || !prefs.getString(K_HOST, DEF_HOST).equals(clean(editHost.getText()))
                || !prefs.getString(K_KEY, "").equals(clean(editKey.getText()))) {
            savePrefs();
        }
    }

    private void setBusy(boolean busy) {
        final boolean b = busy;
        runOnUiThread(new Runnable() {
            public void run() {
                if (isFinishing() || btnOn == null) return;
                btnOn.setEnabled(!b);
                btnOff.setEnabled(!b);
                btnRestart.setEnabled(!b);
                btnLock.setEnabled(!b);
                btnScreen.setEnabled(!b);
                btnOn.setAlpha(b ? 0.45f : 1f);
                btnOff.setAlpha(b ? 0.45f : 1f);
                btnRestart.setAlpha(b ? 0.45f : 1f);
                btnLock.setAlpha(b ? 0.45f : 1f);
                btnScreen.setAlpha(b ? 0.45f : 1f);
                for (View tile : appTiles) {
                    tile.setEnabled(!b);
                    tile.setAlpha(b ? 0.45f : 1f);
                }
                for (View tile : actionTiles) {
                    tile.setEnabled(!b);
                    tile.setAlpha(b ? 0.45f : 1f);
                }
            }
        });
    }

    private void logUi(final String text) {
        runOnUiThread(new Runnable() {
            public void run() {
                if (isFinishing() || statusView == null) return;
                log(text);
            }
        });
    }

    private void log(String text) {
        statusView.append("\n[" + ts.format(new Date()) + "] " + text);
        statusView.animate().cancel();
        statusView.setAlpha(0.6f);
        statusView.animate().alpha(1f).setDuration(260L).start();
        scroll.post(new Runnable() {
            public void run() {
                // Автопрокрутка только если журнал уже на экране: иначе плитки
                // «убегали» вниз после каждого нажатия и по ним нельзя было попасть повторно.
                if (statusView == null) return;
                int[] logPos = new int[2];
                int[] scrollPos = new int[2];
                statusView.getLocationOnScreen(logPos);
                scroll.getLocationOnScreen(scrollPos);
                int viewBottom = scrollPos[1] + scroll.getHeight();
                if (logPos[1] < viewBottom - dpInt(40f)) {
                    scroll.fullScroll(View.FOCUS_DOWN);
                }
            }
        });
    }

    private static String describe(Throwable e) {
        String m = e.getMessage();
        String n = e.getClass().getSimpleName();
        if (m == null || m.length() == 0) return n;
        return n + ": " + m;
    }
}
