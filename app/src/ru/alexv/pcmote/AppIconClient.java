package ru.alexv.pcmote;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;

/** One sequential worker owns an instance; cancellation permanently closes that session. */
public final class AppIconClient {
    private static final int MAX_BYTES = 65536;
    private boolean cancelled;
    private HttpURLConnection connection;

    public synchronized void cancel() {
        cancelled = true;
        if (connection != null) connection.disconnect();
    }

    private synchronized boolean attach(HttpURLConnection value) {
        if (cancelled || Thread.currentThread().isInterrupted()) return false;
        connection = value;
        return true;
    }

    private synchronized boolean stopped() {
        return cancelled || Thread.currentThread().isInterrupted();
    }

    public byte[] fetch(String host, String key, String id) {
        HttpURLConnection request = null;
        try {
            if (stopped()) return null;
            request = (HttpURLConnection) new URL("http://" + host + ":8765/app-icon?id="
                    + URLEncoder.encode(id, "UTF-8")).openConnection();
            request.setInstanceFollowRedirects(false);
            request.setUseCaches(false);
            request.setConnectTimeout(4000);
            request.setReadTimeout(4000);
            request.setRequestMethod("GET");
            request.setRequestProperty("Authorization", "Bearer " + key);
            request.setRequestProperty("Accept", "image/png");
            if (!attach(request) || stopped()) return null;
            if (request.getResponseCode() != 200 || stopped()) return null;
            if (request.getContentLength() > MAX_BYTES) return null;
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (InputStream input = request.getInputStream()) {
                byte[] buffer = new byte[2048];
                int count;
                while ((count = input.read(buffer)) != -1) {
                    if (stopped() || count > MAX_BYTES - bytes.size()) return null;
                    bytes.write(buffer, 0, count);
                }
            }
            byte[] result = bytes.toByteArray();
            return !stopped() && validPng(result) ? result : null;
        } catch (Exception ignored) {
            // Icons are optional, including old listeners that answer 404.
            return null;
        } finally {
            if (request != null) request.disconnect();
            synchronized (this) { if (connection == request) connection = null; }
        }
    }

    /** Check the PNG signature and IHDR dimensions before invoking any bitmap decoder. */
    public static boolean validPng(byte[] bytes) {
        if (bytes == null || bytes.length < 33 || bytes.length > MAX_BYTES) return false;
        int[] signature = {137,80,78,71,13,10,26,10,0,0,0,13,73,72,68,82};
        for (int i = 0; i < signature.length; i++) {
            if ((bytes[i] & 255) != signature[i]) return false;
        }
        long width = uint32(bytes, 16), height = uint32(bytes, 20);
        return width > 0 && width <= 128 && height > 0 && height <= 128;
    }

    private static long uint32(byte[] bytes, int offset) {
        return ((long)(bytes[offset] & 255) << 24) | ((long)(bytes[offset+1] & 255) << 16)
                | ((long)(bytes[offset+2] & 255) << 8) | (bytes[offset+3] & 255);
    }
}
