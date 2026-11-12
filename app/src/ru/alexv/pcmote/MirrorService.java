package ru.alexv.pcmote;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioPlaybackCaptureConfiguration;
import android.media.AudioRecord;
import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaFormat;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.util.DisplayMetrics;
import android.util.Log;
import android.view.Surface;
import android.view.WindowManager;
import android.graphics.Point;
import java.nio.charset.StandardCharsets;
import java.nio.charset.CodingErrorAction;
import org.json.JSONTokener;

import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Трансляция экрана и звука телефона в клиент на ПК.
 *
 * Телефон слушает TCP-порт, ПК-клиент подключается сам (исходящее соединение
 * на ПК не требует новых правил файрвола), поэтому сервер здесь, а не на ПК.
 * Пакет: [длина: 4 байта BE][тип: 1 байт][данные].
 * Тип 0 - JSON, 1 - JPEG (старый путь), 2 - PCM, 3 - H.264, 4 - H.264 SPS/PPS.
 *
 * Видео кодирует аппаратный MediaCodec прямо с поверхности VirtualDisplay:
 * без чтения пикселей в память, поэтому 60 к/с обходятся почти без CPU.
 * Звук берётся через AudioPlaybackCapture (Android 10+) - телефон при этом
 * продолжает играть сам; «наушники» без root подделать нельзя.
 */
public class MirrorService extends Service {

    public static final String ACTION_START = "ru.alexv.pcmote.action.MIRROR_START";
    public static final String ACTION_STOP = "ru.alexv.pcmote.action.MIRROR_STOP";

    public static final String EXTRA_CODE = "result_code";
    public static final String EXTRA_DATA = "result_data";
    public static final String EXTRA_KEY = "key";
    public static final String EXTRA_HOST = "host";
    public static final String EXTRA_PORT = "port";

    public static final int DEFAULT_PORT = 8768;
    public static volatile boolean running = false;

    private static final int NOTIF_ID = 71;
    private static final String CHANNEL = "mirror";
    private static final String TAG = "PcMirror";
    private static final int TYPE_HELLO = 0;
    private static final int TYPE_JPEG = 1;
    private static final int TYPE_PCM = 2;
    private static final int TYPE_H264 = 3;
    private static final int TYPE_H264_CONFIG = 4;
    private static final int TYPE_CONTROL = 5;
    private static final int MAX_CONTROL_BYTES = 8192;
    private static volatile Object activeControlSession;
    private static volatile int controlRotation = -1, controlWidth, controlHeight;
    private Object authenticatedSession;

    static Object controlSession() { return running ? activeControlSession : null; }
    static boolean isControlSessionActive(Object session) {
        return running && session != null && activeControlSession == session;
    }
    static boolean matchesControlDisplay(int rotation, int width, int height) {
        return running && activeControlSession != null && rotation == controlRotation
                && width == controlWidth && height == controlHeight;
    }
    private void revokeControlSession() {
        if (activeControlSession == authenticatedSession) activeControlSession = null;
        authenticatedSession = null;
    }
    private static final int TARGET_WIDTH = 720;
    private static final int BIT_RATE = 6_000_000;
    private static final int FRAME_RATE = 60;

    private final AtomicBoolean stopped = new AtomicBoolean(false);
    private final Object writeLock = new Object();

    private MediaProjection projection;
    private VirtualDisplay display;
    private MediaCodec encoder;
    private Surface inputSurface;
    private AudioRecord record;
    private ServerSocket server;
    private Socket socket;
    private DataOutputStream out;
    private Thread netThread;
    private Thread pcNotifyThread;
    private final MirrorPcNotifier notifier = new MirrorPcNotifier();
    private volatile boolean pcConnected;
    private Thread videoThread;
    private Thread audioThread;
    private String lastError;

    @Override
    protected void attachBaseContext(android.content.Context base) {
        super.attachBaseContext(AppLocale.wrap(base));
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent == null ? null : intent.getAction();
        if (ACTION_STOP.equals(action)) {
            running = false;
            revokeControlSession();
            stopSelf();
            return START_NOT_STICKY;
        }
        // Ignore duplicate/null starts without tearing down a healthy projection.
        if (running || stopped.get()) return START_NOT_STICKY;
        if (intent == null) {
            stopSelf();
            return START_NOT_STICKY;
        }
        startForegroundCompat(getString(R.string.mirror_notif_wait));
        running = true;

        int code = intent.getIntExtra(EXTRA_CODE, 0);
        Intent data = parcelable(intent);
        String key = intent.getStringExtra(EXTRA_KEY);
        String host = intent.getStringExtra(EXTRA_HOST);
        int port = intent.getIntExtra(EXTRA_PORT, DEFAULT_PORT);
        if (data == null || key == null || key.isEmpty()) {
            fail(getString(R.string.mirror_no_key));
            return START_NOT_STICKY;
        }
        if (host == null || host.isEmpty()) {
            fail(getString(R.string.mirror_no_host));
            return START_NOT_STICKY;
        }
        Log.i(TAG, "старт: порт " + port);

        MediaProjectionManager mgr = (MediaProjectionManager) getSystemService(MEDIA_PROJECTION_SERVICE);
        try {
            projection = mgr.getMediaProjection(code, data);
        } catch (Exception e) {
            projection = null;
        }
        if (projection == null) {
            fail(getString(R.string.mirror_denied));
            return START_NOT_STICKY;
        }
        projection.registerCallback(new MediaProjection.Callback() {
            @Override
            public void onStop() {
                running = false;
                revokeControlSession();
                stopSelf();
            }
        }, new Handler(Looper.getMainLooper()));

        netThread = new Thread(new Runnable() {
            public void run() { serve(key, port, host); }
        }, "mirror-net");
        netThread.start();
        return START_NOT_STICKY;
    }

    @SuppressWarnings("deprecation")
    private static Intent parcelable(Intent intent) {
        if (Build.VERSION.SDK_INT >= 33) return intent.getParcelableExtra(EXTRA_DATA, Intent.class);
        return (Intent) intent.getParcelableExtra(EXTRA_DATA);
    }

    // ---------- сеть ----------

    private void startPcNotifier(final String host, final String key, final int port) {
        pcNotifyThread = new Thread(new Runnable() {
            public void run() {
                boolean accepted = notifier.notifyPc(host, 8765, key, port, new MirrorPcNotifier.Alive() {
                    public boolean isAlive() { return running && !stopped.get() && !pcConnected; }
                });
                // A lost HTTP response must never tear down an already authenticated viewer.
                if (!accepted && running && !stopped.get() && !pcConnected) {
                    Log.w(TAG, "PC cast request failed after bounded retries");
                    MirrorService.this.notify(getString(R.string.mirror_pc_unreachable));
                }
            }
        }, "mirror-pc-notify");
        pcNotifyThread.start();
    }

    private void serve(String key, int port, String host) {
        ServerSocket listener = null;
        Socket accepted = null;
        try {
            listener = new ServerSocket();
            server = listener;
            if (stopped.get() || !running) return;
            listener.setReuseAddress(true);
            listener.bind(new InetSocketAddress(port));
            listener.setSoTimeout(30000);
            if (stopped.get() || !running) return;
            notify(getString(R.string.mirror_notif_wait));
            startPcNotifier(host, key, port);
            accepted = listener.accept();
            Socket s = accepted;
            s.setTcpNoDelay(true);
            socket = s;
            s.setSoTimeout(10000); // Bound authentication, not idle viewing.
            DataInputStream in = new DataInputStream(new BufferedInputStream(s.getInputStream()));
            out = new DataOutputStream(new BufferedOutputStream(s.getOutputStream(), 64 * 1024));

            int len = in.readInt();
            int type = in.readUnsignedByte();
            if (type != TYPE_HELLO || len <= 0 || len > 8192) {
                throw new IOException(getString(R.string.mirror_no_hello));
            }
            byte[] payload = new byte[len];
            in.readFully(payload);
            JSONObject hello = new JSONObject(new String(payload, "UTF-8"));
            Object token = hello.opt("token");
            if (!(token instanceof String)) throw new IOException("invalid token");
            String got = (String) token;
            if (!MessageDigest.isEqual(got.getBytes("UTF-8"), key.getBytes("UTF-8"))) {
                throw new IOException(getString(R.string.mirror_bad_token));
            }

            if (stopped.get() || !running) return;
            pcConnected = true;
            notifier.cancel();
            if (pcNotifyThread != null) pcNotifyThread.interrupt();
            android.view.Display physical = ((WindowManager) getSystemService(WINDOW_SERVICE)).getDefaultDisplay();
            Point physicalSize = new Point();
            physical.getRealSize(physicalSize);
            controlRotation = physical.getRotation();
            controlWidth = physicalSize.x;
            controlHeight = physicalSize.y;
            DisplayMetrics dm = new DisplayMetrics();
            physical.getRealMetrics(dm);
            int width = Math.min(TARGET_WIDTH, dm.widthPixels);
            int height = Math.round(width * (float) dm.heightPixels / dm.widthPixels);
            if ((width & 1) == 1) width--;
            if ((height & 1) == 1) height++;

            JSONObject info = new JSONObject();
            info.put("token", key);
            info.put("name", Build.MODEL);
            info.put("w", width);
            info.put("h", height);
            info.put("sr", 44100);
            info.put("ch", 2);
            info.put("video", "h264");
            info.put("control", PhoneControlService.isAvailable());
            send(TYPE_HELLO, info.toString().getBytes("UTF-8"));
            Log.i(TAG, "клиент " + s.getInetAddress() + ", поток " + width + "x" + height);

            startEncoder(width, height, dm.densityDpi);

            notify(getString(R.string.mirror_notif_live));

            videoThread = new Thread(new Runnable() {
                public void run() { videoLoop(); }
            }, "mirror-video");
            videoThread.start();

            if (Build.VERSION.SDK_INT >= 29) {
                audioThread = new Thread(new Runnable() {
                    public void run() { audioLoop(); }
                }, "mirror-audio");
                audioThread.start();
            }
            // No control before a successful handshake AND a live capture.
            authenticatedSession = new Object();
            activeControlSession = authenticatedSession;
            if (stopped.get() || !running) { revokeControlSession(); return; }
            s.setSoTimeout(0);
            readControls(in);
        } catch (Exception e) {
            if (!stopped.get() && running) {
                lastError = e.getMessage();
                fail(describe(e));
            }
        } finally {
            // cleanup() may run before this worker publishes either field. Local ownership
            // closes late-created sockets even on an early stop/permission-revocation return.
            try { if (accepted != null) accepted.close(); } catch (IOException ignored) { }
            try { if (listener != null) listener.close(); } catch (IOException ignored) { }
        }
    }

    private void readControls(DataInputStream in) throws IOException {
        try {
            while (!stopped.get() && running) {
                int len = in.readInt();
                int type = in.readUnsignedByte();
                // Never allocate from an untrusted length; invalid framing closes session.
                if (len <= 0 || len > MAX_CONTROL_BYTES || type != TYPE_CONTROL) {
                    send(TYPE_CONTROL, PhoneControlService.result("invalid_control_frame").toString().getBytes("UTF-8"));
                    throw new IOException("invalid control frame");
                }
                byte[] payload = new byte[len];
                socket.setSoTimeout(10000); // Partial payload cannot hold the session indefinitely.
                in.readFully(payload);
                socket.setSoTimeout(0);
                JSONObject reply;
                try {
                    String json = StandardCharsets.UTF_8.newDecoder()
                            .onMalformedInput(CodingErrorAction.REPORT)
                            .onUnmappableCharacter(CodingErrorAction.REPORT)
                            .decode(ByteBuffer.wrap(payload)).toString();
                    JSONTokener tokener = new JSONTokener(json);
                    Object value = tokener.nextValue();
                    if (!(value instanceof JSONObject) || tokener.nextClean() != 0)
                        throw new IllegalArgumentException("expected JSON object");
                    reply = isControlSessionActive(authenticatedSession)
                            ? PhoneControlService.dispatch((JSONObject) value)
                            : PhoneControlService.result("no_authenticated_session");
                } catch (Exception e) {
                    reply = PhoneControlService.result("invalid_json");
                }
                send(TYPE_CONTROL, reply.toString().getBytes("UTF-8"));
            }
        } finally {
            revokeControlSession();
        }
    }

    private void send(int type, byte[] payload) throws IOException {
        synchronized (writeLock) {
            if (out == null) throw new IOException(getString(R.string.not_connected));
            out.writeInt(payload.length);
            out.writeByte(type);
            out.write(payload);
            out.flush();
        }
    }

    // ---------- видео ----------

    @SuppressWarnings("deprecation")
    private void startEncoder(int width, int height, int dpi) throws IOException {
        try {
            MediaFormat format = MediaFormat.createVideoFormat(
                    MediaFormat.MIMETYPE_VIDEO_AVC, width, height);
            format.setInteger(MediaFormat.KEY_COLOR_FORMAT,
                    MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface);
            format.setInteger(MediaFormat.KEY_BIT_RATE, BIT_RATE);
            format.setInteger(MediaFormat.KEY_FRAME_RATE, FRAME_RATE);
            format.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1);
            format.setInteger(MediaFormat.KEY_BITRATE_MODE,
                    MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_CBR);
            if (Build.VERSION.SDK_INT >= 29) {
                format.setInteger(MediaFormat.KEY_PREPEND_HEADER_TO_SYNC_FRAMES, 1);
            }
            encoder = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC);
            encoder.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
            inputSurface = encoder.createInputSurface();
            encoder.start();
            display = projection.createVirtualDisplay("PcMirror", width, height, dpi,
                    DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                    inputSurface, null, null);
            Log.i(TAG, "видео: MediaCodec H.264, " + width + "x" + height
                    + " @" + FRAME_RATE + ", " + (BIT_RATE / 1000) + " кбит/с");
        } catch (Exception e) {
            throw new IOException(getString(R.string.encoder_error_fmt, describe(e)), e);
        }
    }

    private void videoLoop() {
        MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
        while (!stopped.get() && !Thread.currentThread().isInterrupted()) {
            try {
                int index = encoder.dequeueOutputBuffer(info, 10000);
                if (index == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                    MediaFormat of = encoder.getOutputFormat();
                    Log.i(TAG, "формат кодировщика: " + of);
                    byte[] csd = codecConfig(of);
                    if (csd != null) send(TYPE_H264_CONFIG, csd);
                    continue;
                }
                if (index < 0) continue;
                ByteBuffer buffer = encoder.getOutputBuffer(index);
                if (buffer != null && info.size > 0) {
                    byte[] data = new byte[info.size];
                    buffer.position(info.offset);
                    buffer.limit(info.offset + info.size);
                    buffer.get(data);
                    if ((info.flags & MediaCodec.BUFFER_FLAG_CODEC_CONFIG) != 0) {
                        send(TYPE_H264_CONFIG, data);
                    } else {
                        send(TYPE_H264, data);
                    }
                }
                encoder.releaseOutputBuffer(index, false);
            } catch (IOException e) {
                fail(describe(e));
                return;
            } catch (IllegalStateException e) {
                if (!stopped.get()) fail(describe(e));
                return;
            } catch (Exception e) {
                try {
                    Thread.sleep(20);
                } catch (InterruptedException ie) {
                    return;
                }
            }
        }
    }

    /** SPS/PPS из формата кодировщика: клиенту они нужны до первого кадра. */
    private static byte[] codecConfig(MediaFormat format) {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        for (String name : new String[]{"csd-0", "csd-1"}) {
            try {
                ByteBuffer b = format.getByteBuffer(name);
                if (b == null) continue;
                ByteBuffer copy = b.duplicate();
                byte[] part = new byte[copy.remaining()];
                copy.get(part);
                out.write(part, 0, part.length);
            } catch (Exception ignored) {
            }
        }
        return out.size() == 0 ? null : out.toByteArray();
    }

    // ---------- звук ----------

    private void audioLoop() {
        if (Build.VERSION.SDK_INT < 29) return;
        if (checkSelfPermission(android.Manifest.permission.RECORD_AUDIO)
                != PackageManager.PERMISSION_GRANTED) {
            return;
        }
        AudioRecord rec = null;
        try {
            AudioPlaybackCaptureConfiguration cfg =
                    new AudioPlaybackCaptureConfiguration.Builder(projection)
                            .addMatchingUsage(AudioAttributes.USAGE_MEDIA)
                            .addMatchingUsage(AudioAttributes.USAGE_GAME)
                            .addMatchingUsage(AudioAttributes.USAGE_UNKNOWN)
                            .build();
            AudioFormat format = new AudioFormat.Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(44100)
                    .setChannelMask(AudioFormat.CHANNEL_IN_STEREO)
                    .build();
            int min = AudioRecord.getMinBufferSize(44100,
                    AudioFormat.CHANNEL_IN_STEREO, AudioFormat.ENCODING_PCM_16BIT);
            rec = new AudioRecord.Builder()
                    .setAudioFormat(format)
                    .setAudioPlaybackCaptureConfig(cfg)
                    .setBufferSizeInBytes(Math.max(min, 16384) * 2)
                    .build();
            if (rec.getState() != AudioRecord.STATE_INITIALIZED) {
                rec.release();
                return;
            }
            record = rec;
            rec.startRecording();
            Log.i(TAG, "звук: AudioPlaybackCapture запущен");
            byte[] buf = new byte[4096];
            while (!stopped.get()) {
                int n = rec.read(buf, 0, buf.length);
                if (n > 0) send(TYPE_PCM, Arrays.copyOf(buf, n));
                else if (n < 0) break;
            }
        } catch (Exception e) {
            // Звук не критичен: экран продолжает идти.
            lastError = describe(e);
        } finally {
            if (rec != null) {
                try {
                    rec.stop();
                } catch (Exception ignored) {
                }
                rec.release();
            }
        }
    }

    // ---------- уведомление ----------

    private void startForegroundCompat(String text) {
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel ch = new NotificationChannel(CHANNEL,
                    getString(R.string.mirror_notif_channel), NotificationManager.IMPORTANCE_LOW);
            nm.createNotificationChannel(ch);
        }
        Notification n = buildNotification(text);
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(NOTIF_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION);
        } else {
            startForeground(NOTIF_ID, n);
        }
    }

    private Notification buildNotification(String text) {
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent openPi = PendingIntent.getActivity(this, 0, open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Intent stop = new Intent(this, MirrorService.class).setAction(ACTION_STOP);
        PendingIntent stopPi = PendingIntent.getService(this, 1, stop,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        Notification.Builder b = (Build.VERSION.SDK_INT >= 26)
                ? new Notification.Builder(this, CHANNEL)
                : new Notification.Builder(this);
        b.setSmallIcon(R.drawable.ic_eye)
                .setContentTitle(getString(R.string.mirror_notif_title))
                .setContentText(text)
                .setOngoing(true)
                .setContentIntent(openPi)
                .addAction(0, getString(R.string.mirror_notif_stop), stopPi);
        return b.build();
    }

    private void notify(String text) {
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        nm.notify(NOTIF_ID, buildNotification(text));
    }

    private void fail(String why) {
        if (stopped.getAndSet(true)) return;
        running = false;
        lastError = why;
        try {
            notify(getString(R.string.mirror_notif_error, why));
        } catch (Exception ignored) {
        }
        cleanup();
        stopSelf();
    }

    private static String describe(Exception e) {
        String m = e.getMessage();
        return (m == null || m.isEmpty()) ? e.getClass().getSimpleName() : m;
    }

    private void cleanup() {
        stopped.set(true);
        running = false;
        notifier.cancel();
        if (pcNotifyThread != null) pcNotifyThread.interrupt();
        revokeControlSession();
        try {
            if (record != null) {
                record.stop();
                record.release();
            }
        } catch (Exception ignored) {
        }
        record = null;
        try {
            if (display != null) display.release();
        } catch (Exception ignored) {
        }
        display = null;
        try {
            if (encoder != null) {
                encoder.stop();
                encoder.release();
            }
        } catch (Exception ignored) {
        }
        encoder = null;
        try {
            if (inputSurface != null) inputSurface.release();
        } catch (Exception ignored) {
        }
        inputSurface = null;
        try {
            if (socket != null) socket.close();
        } catch (Exception ignored) {
        }
        socket = null;
        try {
            if (server != null) server.close();
        } catch (Exception ignored) {
        }
        server = null;
        out = null;
        try {
            if (projection != null) projection.stop();
        } catch (Exception ignored) {
        }
        projection = null;
    }

    @Override
    public android.os.IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onDestroy() {
        cleanup();
        running = false;
        stopForeground(true);
        super.onDestroy();
    }
}
