package ru.alexv.pcmote;

import android.app.Activity;
import android.app.ProgressDialog;
import android.content.DialogInterface;
import android.database.Cursor;
import android.net.Uri;
import android.provider.OpenableColumns;
import java.io.*;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import org.json.JSONObject;

/** One foreground upload, using the document URI grant rather than storage permission. */
final class FileUpload {
    interface Result { void done(String message); }
    private static final long MAX = 50L * 1024 * 1024 * 1024;
    private final Activity activity;
    private final Result result;
    private final ProgressDialog dialog;
    private volatile boolean cancelled;
    private volatile HttpURLConnection connection;
    private volatile InputStream activeInput;
    private final android.os.CancellationSignal providerCancel = new android.os.CancellationSignal();
    private long lastProgress;
    private boolean resultDelivered;

    FileUpload(Activity activity, Result result) {
        this.activity = activity;
        this.result = result;
        dialog = new ProgressDialog(activity);
        dialog.setTitle(activity.getString(R.string.upload_title));
        dialog.setMessage(activity.getString(R.string.upload_preparing));
        dialog.setProgressStyle(ProgressDialog.STYLE_HORIZONTAL);
        dialog.setMax(100);
        dialog.setIndeterminate(true);
        dialog.setCanceledOnTouchOutside(false);
        dialog.setButton(DialogInterface.BUTTON_NEGATIVE, activity.getString(R.string.cancel), new DialogInterface.OnClickListener() {
            public void onClick(DialogInterface d, int which) { cancel(); }
        });
        dialog.setOnCancelListener(new DialogInterface.OnCancelListener() {
            public void onCancel(DialogInterface d) { cancel(); }
        });
    }

    void dispose() {
        resultDelivered = true;
        cancel();
    }

    void cancel() {
        cancelled = true;
        dialog.dismiss();
        activity.runOnUiThread(new Runnable() {
            public void run() { finish(activity.getString(R.string.upload_cancelled_details)); }
        });
        new Thread(new Runnable() {
            public void run() {
                providerCancel.cancel();
                InputStream in = activeInput;
                if (in != null) try { in.close(); } catch (IOException ignored) { }
                HttpURLConnection c = connection;
                if (c != null) c.disconnect();
            }
        }, "upload-cancel").start();
    }

    void start(final Uri uri, final String host, final String key) {
        dialog.show();
        new Thread(new Runnable() {
            public void run() {
                String message;
                File cached = null;
                try {
                    String name = "file";
                    long size = -1;
                    try (Cursor cursor = activity.getContentResolver().query(uri,
                            new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE}, null, null, null, providerCancel)) {
                        if (cursor != null && cursor.moveToFirst()) {
                            int n = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                            int s = cursor.getColumnIndex(OpenableColumns.SIZE);
                            if (n >= 0 && !cursor.isNull(n)) name = cursor.getString(n);
                            if (s >= 0 && !cursor.isNull(s)) size = cursor.getLong(s);
                        }
                    }
                    if (size > MAX) throw new IOException(activity.getString(R.string.upload_max_size));
                    if (size < 0) {
                        cached = File.createTempFile("pc-upload-", ".tmp", activity.getCacheDir());
                        try (InputStream in = open(uri); OutputStream out = new FileOutputStream(cached)) {
                            byte[] buffer = new byte[65536];
                            size = 0;
                            int n;
                            while ((n = in.read(buffer)) != -1) {
                                checkCancelled();
                                size += n;
                                if (size > MAX) throw new IOException(activity.getString(R.string.upload_max_size));
                                out.write(buffer, 0, n);
                            }
                        }
                    }
                    checkCancelled();
                    progress(0, size, name, true);
                    HttpURLConnection c = (HttpURLConnection) new URL("http://" + host + ":8765/upload").openConnection();
                    connection = c;
                    c.setRequestMethod("POST");
                    c.setConnectTimeout(10000);
                    c.setReadTimeout(60000);
                    c.setInstanceFollowRedirects(false);
                    c.setDoOutput(true);
                    c.setFixedLengthStreamingMode(size);
                    c.setRequestProperty("Content-Type", "application/octet-stream");
                    c.setRequestProperty("Authorization", "Bearer " + key);
                    c.setRequestProperty("X-File-Name", URLEncoder.encode(name, "UTF-8").replace("+", "%20"));
                    try (InputStream in = cached != null ? new FileInputStream(cached) : open(uri);
                         OutputStream out = c.getOutputStream()) {
                        byte[] buffer = new byte[65536];
                        long sent = 0;
                        int n;
                        while ((n = in.read(buffer)) != -1) {
                            checkCancelled();
                            if (sent + n > size) throw new IOException(activity.getString(R.string.upload_size_changed));
                            out.write(buffer, 0, n);
                            sent += n;
                            progress(sent, size, name, false);
                        }
                        if (sent != size) throw new IOException(activity.getString(R.string.upload_incomplete));
                    }
                    checkCancelled();
                    int code = c.getResponseCode();
                    InputStream response = code < 400 ? c.getInputStream() : c.getErrorStream();
                    String text = readReply(response);
                    JSONObject reply;
                    try { reply = new JSONObject(text); }
                    catch (Exception e) {
                        throw new IOException(activity.getString(R.string.upload_http_fmt, code));
                    }
                    if (code != 201 || !reply.optBoolean("ok")) {
                        throw new IOException(reply.optString("error", activity.getString(R.string.http_error_fmt, code)));
                    }
                    message = activity.getString(R.string.upload_saved_fmt, reply.getString("path"));
                } catch (Exception e) {
                    message = cancelled ? activity.getString(R.string.upload_cancelled_details)
                            : activity.getString(R.string.upload_failed_fmt, e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage());
                } finally {
                    if (connection != null) connection.disconnect();
                    connection = null;
                    if (cached != null) cached.delete();
                }
                final String text = message;
                activity.runOnUiThread(new Runnable() {
                    public void run() {
                        finish(text);
                    }
                });
            }
        }, "pc-file-upload").start();
    }

    private void finish(String message) {
        if (resultDelivered || activity.isFinishing() || activity.isDestroyed()) return;
        resultDelivered = true;
        dialog.dismiss();
        result.done(message);
    }

    private InputStream open(Uri uri) throws IOException {
        checkCancelled();
        android.content.res.AssetFileDescriptor descriptor = activity.getContentResolver()
                .openAssetFileDescriptor(uri, "r", providerCancel);
        if (descriptor == null) throw new IOException(activity.getString(R.string.upload_open_failed));
        InputStream in;
        try { in = descriptor.createInputStream(); }
        catch (IOException e) { descriptor.close(); throw e; }
        activeInput = in;
        if (cancelled) { in.close(); checkCancelled(); }
        return in;
    }

    private void checkCancelled() throws IOException {
        if (cancelled) throw new IOException(activity.getString(R.string.upload_cancelled));
    }

    private String readReply(InputStream in) throws IOException {
        if (in == null) return "";
        try (InputStream stream = in; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] bytes = new byte[1024];
            int n;
            while ((n = stream.read(bytes)) != -1) {
                if (out.size() + n > 16384) throw new IOException(activity.getString(R.string.invalid_reply));
                out.write(bytes, 0, n);
            }
            return out.toString("UTF-8");
        }
    }

    private void progress(final long sent, final long total, final String name, boolean force) {
        long now = android.os.SystemClock.elapsedRealtime();
        if (!force && sent != total && now - lastProgress < 150) return;
        lastProgress = now;
        activity.runOnUiThread(new Runnable() {
            public void run() {
                if (cancelled || activity.isFinishing() || activity.isDestroyed()) return;
                dialog.setIndeterminate(false);
                dialog.setMessage(activity.getString(R.string.upload_progress_fmt, name));
                dialog.setProgress(total == 0 ? 100 : (int) (sent * 100 / total));
            }
        });
    }
}
