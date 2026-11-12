package ru.alexv.pcmote;

import android.app.Activity;
import android.content.SharedPreferences;
import android.media.MediaCodec;
import android.media.MediaFormat;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.DisplayMetrics;
import android.util.Log;
import android.view.Gravity;
import android.view.Surface;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import android.view.View;
import android.view.WindowManager;
import android.view.inputmethod.EditorInfo;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.ByteBuffer;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/**
 * Просмотр экрана ПК: телефон принимает H.264 с /stream и декодирует его
 * аппаратно в SurfaceView. Кадры приходят уже сжатыми, поэтому картинка
 * плавная даже на слабом Wi-Fi.
 */
public class ScreenActivity extends Activity {

    private static final String PREFS = "pcmote";
    private static final String K_HOST = "host";
    private static final String K_KEY = "key";
    private static final String DEF_HOST = "";
    private static final int PORT = 8765;
    private static final String TAG = "PcScreen";
    private static final int STREAM_WIDTH = 1080;

    private final Handler ui = new Handler(Looper.getMainLooper());
    private final SimpleDateFormat clock = new SimpleDateFormat("HH:mm:ss", Locale.getDefault());
    private SurfaceView video;
    private TextView message, meta;
    private EditText cmdText;
    private volatile boolean running = true;
    private volatile boolean paused;
    private volatile boolean surfaceReady;
    private volatile Surface surface;
    private volatile MediaCodec currentCodec;
    private volatile HttpURLConnection streamConn;
    private volatile boolean everShown;
    private Thread streamThread;
    private DesktopControl control;
    private String baseUrl;
    private String key;
    private boolean fullscreen, fillScreen;
    private int sourceWidth = 1920, sourceHeight = 1080;
    private View inputBar;
    private Button fullscreenButton, scaleButton;

    @Override
    protected void attachBaseContext(android.content.Context base) {
        super.attachBaseContext(AppLocale.wrap(base));
    }

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        setContentView(R.layout.screen_view);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        fullscreen = saved != null && saved.getBoolean("fullscreen", false);
        fillScreen = saved != null && saved.getBoolean("fillScreen", false);
        inputBar = findViewById(R.id.screen_input_bar);
        fullscreenButton = (Button) findViewById(R.id.screen_fullscreen);
        scaleButton = (Button) findViewById(R.id.screen_scale);
        fullscreenButton.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { fullscreen = !fullscreen; applyPresentation(); }
        });
        scaleButton.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { fillScreen = !fillScreen; applyPresentation(); }
        });
        video = (SurfaceView) findViewById(R.id.video);
        message = (TextView) findViewById(R.id.shot_message);
        meta = (TextView) findViewById(R.id.shot_meta);
        cmdText = (EditText) findViewById(R.id.cmd_text);
        Button cmdSend = (Button) findViewById(R.id.cmd_send);
        Button cmdBack = (Button) findViewById(R.id.cmd_back);

        video.getHolder().addCallback(new SurfaceHolder.Callback() {
            public void surfaceCreated(SurfaceHolder h) {
                surface = h.getSurface();
                surfaceReady = true;
                startStream();
            }

            public void surfaceChanged(SurfaceHolder h, int format, int w, int hgt) {
                surface = h.getSurface();
                surfaceReady = true;
            }

            public void surfaceDestroyed(SurfaceHolder h) {
                surfaceReady = false;
                surface = null;
            }
        });

        SharedPreferences p = getSharedPreferences(PREFS, MODE_PRIVATE);
        String host = p.getString(K_HOST, DEF_HOST).trim();
        String key = p.getString(K_KEY, "");
        if (host.length() == 0 || key.length() == 0) {
            message.setText(R.string.screen_no_cfg);
            return;
        }
        baseUrl = "http://" + host + ":" + PORT;
        this.key = key;
        control = new DesktopControl(this, video, baseUrl, key);

        cmdSend.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { sendText(); }
        });
        cmdBack.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { pressKey("backspace", false); }
        });
        cmdText.setOnEditorActionListener(new TextView.OnEditorActionListener() {
            public boolean onEditorAction(TextView v, int actionId, android.view.KeyEvent event) {
                if (actionId == EditorInfo.IME_ACTION_SEND) {
                    sendText();
                    return true;
                }
                return false;
            }
        });

        ((View) video.getParent()).addOnLayoutChangeListener(new View.OnLayoutChangeListener() {
            public void onLayoutChange(View v, int l, int t, int r, int b, int ol, int ot, int or, int ob) {
                fitSurface(sourceWidth, sourceHeight);
            }
        });
        applyPresentation();
        startStream();
    }

    private void applyPresentation() {
        int flags = View.SYSTEM_UI_FLAG_LAYOUT_STABLE;
        if (fullscreen) flags |= View.SYSTEM_UI_FLAG_FULLSCREEN | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY;
        getWindow().getDecorView().setSystemUiVisibility(flags);
        inputBar.setVisibility(fullscreen ? View.GONE : View.VISIBLE);
        meta.setVisibility(fullscreen ? View.GONE : View.VISIBLE);
        if (control != null) control.setToolbarVisible(!fullscreen);
        fullscreenButton.setText(fullscreen ? R.string.screen_exit_fullscreen : R.string.screen_fullscreen);
        scaleButton.setText(fillScreen ? R.string.screen_fill : R.string.screen_fit);
        fitSurface(sourceWidth, sourceHeight);
    }

    @Override public void onWindowFocusChanged(boolean focused) {
        super.onWindowFocusChanged(focused);
        if (focused && video != null) applyPresentation();
    }
    @Override public void onBackPressed() {
        if (fullscreen) { fullscreen = false; applyPresentation(); return; }
        super.onBackPressed();
    }
    @Override protected void onSaveInstanceState(Bundle out) {
        out.putBoolean("fullscreen", fullscreen);
        out.putBoolean("fillScreen", fillScreen);
        super.onSaveInstanceState(out);
    }

    // ---------- удалённый ввод ----------

    private void sendText() {
        final String text = cmdText.getText().toString();
        if (text.trim().length() == 0) return;
        if (control != null) control.text(text);
    }

    private void pressKey(final String name, final boolean quiet) {
        if (control != null) control.key(name);
    }

    private String call(String path) {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(baseUrl + path + "&key=" + encode(key)).openConnection();
            c.setConnectTimeout(5000);
            c.setReadTimeout(8000);
            c.setUseCaches(false);
            c.setRequestProperty("Connection", "close");
            int code = c.getResponseCode();
            InputStream in = code == 200 ? c.getInputStream() : c.getErrorStream();
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[4096];
            int n;
            while (in != null && (n = in.read(buf)) > 0) out.write(buf, 0, n);
            if (in != null) in.close();
            String body = out.toString("UTF-8");
            if (code == 200) return body;
            return body.length() > 0 ? body : getString(R.string.type_failed);
        } catch (Exception e) {
            return getString(R.string.type_failed);
        } finally {
            if (c != null) c.disconnect();
        }
    }

    // ---------- видеопоток ----------

    private synchronized void startStream() {
        if (!running || paused || baseUrl == null) return;
        if (streamThread != null && streamThread.isAlive()) return;
        streamThread = new Thread(new Runnable() {
            public void run() { streamLoop(); }
        }, "pc-screen");
        streamThread.start();
    }

    private void streamLoop() {
        while (running) {
            Surface target = surface;
            if (paused || !surfaceReady || target == null) {
                sleepQuiet(250L);
                continue;
            }
            HttpURLConnection c = null;
            MediaCodec codec = null;
            try {
                c = openStream();
                int w = c.getHeaderFieldInt("X-Video-Width", 1920);
                int h = c.getHeaderFieldInt("X-Video-Height", 1080);
                if (w < 16 || h < 16) {
                    w = 1920;
                    h = 1080;
                }
                postFit(w, h);

                MediaFormat format = MediaFormat.createVideoFormat(
                        MediaFormat.MIMETYPE_VIDEO_AVC, w, h);
                if (Build.VERSION.SDK_INT >= 30) {
                    format.setInteger(MediaFormat.KEY_LOW_LATENCY, 1);
                }
                codec = MediaCodec.createDecoderByType(MediaFormat.MIMETYPE_VIDEO_AVC);
                codec.configure(format, target, null, 0);
                codec.start();
                currentCodec = codec;
                // Input becomes live only when a decoded output buffer is rendered.
                Log.i(TAG, "поток подключён: " + w + "x" + h);

                final MediaCodec streamCodec = codec;
                H264Feeder feeder = new H264Feeder(codec, new Runnable() {
                    public void run() {
                        if (running && !paused && surfaceReady && currentCodec == streamCodec
                                && control != null) control.frame();
                    }
                });
                InputStream in = new BufferedInputStream(c.getInputStream(), 65536);
                byte[] chunk = new byte[65536];
                long win = System.currentTimeMillis();
                int frames = 0;
                long bytes = 0;
                while (running && !paused && surfaceReady) {
                    int n = in.read(chunk);
                    if (n < 0) break;
                    bytes += n;
                    frames += feeder.feed(chunk, n);
                    long now = System.currentTimeMillis();
                    if (now - win >= 1000) {
                        postStats(Math.round(frames * 1000f / (now - win)),
                                Math.round((bytes * 1000f / (now - win)) / 1024f));
                        win = now;
                        frames = 0;
                        bytes = 0;
                    }
                }
                feeder.finish();
                if (!paused && running) postLost();
                if (!paused && running) sleepQuiet(800L);
            } catch (Exception e) {
                Log.w(TAG, "поток: " + e);
                if (!paused && running) {
                    postLost();
                    sleepQuiet(1200L);
                }
            } finally {
                currentCodec = null;
                if (codec != null) {
                    try {
                        codec.stop();
                    } catch (Exception ignored) {
                    }
                    try {
                        codec.release();
                    } catch (Exception ignored) {
                    }
                }
                if (c != null) c.disconnect();
                streamConn = null;
            }
        }
    }

    private HttpURLConnection openStream() throws IOException {
        String url = baseUrl + "/stream?w=" + STREAM_WIDTH + "&fps=60&key=" + encode(key);
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(5000);
        c.setReadTimeout(8000);
        c.setUseCaches(false);
        c.setRequestProperty("Connection", "close");
        streamConn = c;
        int code = c.getResponseCode();
        if (code != 200) throw new IOException("HTTP " + code);
        return c;
    }

    private void postFit(final int w, final int h) {
        ui.post(new Runnable() {
            public void run() {
                fitSurface(w, h);
            }
        });
    }

    private void fitSurface(int w, int h) {
        sourceWidth = w; sourceHeight = h;
        DisplayMetrics dm = getResources().getDisplayMetrics();
        View parent = (View) video.getParent();
        int parentW = parent.getWidth() > 0 ? parent.getWidth() : dm.widthPixels;
        int parentH = parent.getHeight() > 0 ? parent.getHeight() : dm.heightPixels;
        int top = fullscreen ? 0 : Math.round(132 * dm.density);
        int bottom = fullscreen ? 0 : Math.round(84 * dm.density);
        int availH = Math.max(1, parentH - top - bottom);
        ScreenGeometry rect = ScreenGeometry.calculate(w, h, parentW, availH, fillScreen);
        FrameLayout.LayoutParams lp = (FrameLayout.LayoutParams) video.getLayoutParams();
        int y = top + rect.top;
        if (lp.width == rect.width && lp.height == rect.height
                && lp.leftMargin == rect.left && lp.topMargin == y) return;
        lp.width = rect.width; lp.height = rect.height;
        lp.gravity = Gravity.TOP | Gravity.LEFT;
        lp.leftMargin = rect.left; lp.topMargin = y;
        video.setLayoutParams(lp);
    }

    private void postLive() {
        ui.post(new Runnable() {
            public void run() {
                if (isFinishing()) return;
                everShown = true;
                message.setVisibility(View.GONE);
                meta.setText(getString(R.string.screen_stream_fmt,
                        clock.format(new Date()), 0, 0));
            }
        });
    }

    private void postStats(final int fps, final int kbs) {
        final String at = clock.format(new Date());
        ui.post(new Runnable() {
            public void run() {
                if (isFinishing()) return;
                everShown = true;
                message.setVisibility(View.GONE);
                meta.setText(getString(R.string.screen_stream_fmt, at, fps, kbs));
            }
        });
    }

    private void postLost() {
        ui.post(new Runnable() {
            public void run() {
                if (isFinishing()) return;
                if (control != null) control.live(false);
                if (!everShown) {
                    message.setText(R.string.screen_offline);
                    message.setVisibility(View.VISIBLE);
                    meta.setText("");
                } else {
                    meta.setText(R.string.screen_stale);
                }
            }
        });
    }

    private void dropConnection() {
        HttpURLConnection c = streamConn;
        if (c != null) {
            try {
                c.disconnect();
            } catch (Exception ignored) {
            }
        }
    }

    private static void sleepQuiet(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException ignored) {
        }
    }

    private static String encode(String s) {
        try {
            return URLEncoder.encode(s, "UTF-8");
        } catch (Exception e) {
            return s;
        }
    }

    // ---------- разбор Annex-B и подача в декодер ----------

    /**
     * ffmpeg вставляет AUD перед каждым кадром, поэтому границей access unit
     * служит NAL типа 9: всё, что накопилось до него, — один кадр.
     */
    private final class H264Feeder {
        private final MediaCodec codec;
        private final MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
        private final ByteArrayOutputStream au = new ByteArrayOutputStream(128 * 1024);
        private byte[] buf = new byte[128 * 1024];
        private int len;
        private long ptsUs;
        private int fed;

        private final Runnable rendered;
        H264Feeder(MediaCodec codec, Runnable rendered) {
            this.codec = codec;
            this.rendered = rendered;
        }

        int feed(byte[] data, int n) throws IOException {
            append(data, n);
            int before = fed;
            int pos = 0;
            int nalStart = -1;
            while (pos + 3 <= len) {
                int sc = startCode(pos);
                if (sc == 0) {
                    pos++;
                    continue;
                }
                if (nalStart >= 0) handleNal(nalStart, pos);
                nalStart = pos;
                pos += sc;
            }
            if (nalStart > 0) {
                System.arraycopy(buf, nalStart, buf, 0, len - nalStart);
                len -= nalStart;
            }
            return fed - before;
        }

        void finish() throws IOException {
            if (au.size() > 0) flush();
        }

        private void handleNal(int start, int end) throws IOException {
            int sc = startCode(start);
            if (start + sc >= end) return;
            int type = buf[start + sc] & 0x1F;
            if (type == 9 && au.size() > 0) flush();
            if (au.size() > 4 * 1024 * 1024) flush();
            au.write(buf, start, end - start);
        }

        private void flush() throws IOException {
            byte[] data = au.toByteArray();
            au.reset();
            long pts = ptsUs;
            ptsUs += 16667L;
            int idx = -1;
            try {
                for (int i = 0; i < 500; i++) {
                    idx = codec.dequeueInputBuffer(4000);
                    if (idx >= 0) break;
                    drain();
                }
                if (idx < 0) return;
                ByteBuffer ib = codec.getInputBuffer(idx);
                if (ib == null) return;
                ib.clear();
                ib.put(data);
                codec.queueInputBuffer(idx, 0, data.length, pts, 0);
                fed++;
                drain();
            } catch (IllegalStateException e) {
                throw new IOException(getString(R.string.decoder_stopped), e);
            }
        }

        private void drain() {
            try {
                while (true) {
                    int idx = codec.dequeueOutputBuffer(info, 0);
                    if (idx >= 0) {
                        codec.releaseOutputBuffer(idx, true);
                        rendered.run();
                    } else if (idx == MediaCodec.INFO_TRY_AGAIN_LATER) {
                        return;
                    }
                }
            } catch (IllegalStateException ignored) {
            }
        }

        private int startCode(int i) {
            if (i + 4 <= len && buf[i] == 0 && buf[i + 1] == 0
                    && buf[i + 2] == 0 && buf[i + 3] == 1) {
                return 4;
            }
            if (i + 3 <= len && buf[i] == 0 && buf[i + 1] == 0 && buf[i + 2] == 1) {
                return 3;
            }
            return 0;
        }

        private void append(byte[] data, int n) {
            if (len + n > buf.length) {
                byte[] nb = new byte[Math.max(buf.length * 2, len + n)];
                System.arraycopy(buf, 0, nb, 0, len);
                buf = nb;
            }
            System.arraycopy(data, 0, buf, len, n);
            len += n;
        }
    }

    // ---------- жизненный цикл ----------

    @Override
    protected void onResume() {
        super.onResume();
        paused = false;
        startStream();
    }

    @Override
    protected void onPause() {
        paused = true;
        if (control != null) control.pause();
        dropConnection();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        running = false;
        if (control != null) control.close();
        paused = true;
        dropConnection();
        if (streamThread != null) streamThread.interrupt();
        super.onDestroy();
    }
}
