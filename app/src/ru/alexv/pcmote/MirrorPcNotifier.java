package ru.alexv.pcmote;

import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;

/** Service-owned, bounded request to the already paired PC. Never logs its URL/key. */
final class MirrorPcNotifier {
    interface Alive { boolean isAlive(); }
    private HttpURLConnection connection;
    private boolean cancelled;

    static long retryDelay(int retry) {
        return retry >= 0 && retry < 3 ? 1000L << retry : -1L;
    }

    boolean notifyPc(String host, int pcPort, String key, int mirrorPort, Alive alive) {
        for (int attempt = 0; attempt < 4; attempt++) {
            if (!alive.isAlive() || Thread.currentThread().isInterrupted()) return false;
            if (request(host, pcPort, key, mirrorPort)) return alive.isAlive();
            long delay = retryDelay(attempt);
            if (delay < 0 || !alive.isAlive()) return false;
            try { Thread.sleep(delay); }
            catch (InterruptedException e) { Thread.currentThread().interrupt(); return false; }
        }
        return false;
    }

    boolean request(String host, int pcPort, String key, int mirrorPort) {
        HttpURLConnection current = null;
        try {
            // URL's host constructor handles IPv6 without treating host text as a path.
            URL url = new URL("http", host, pcPort, "/mirror?port=" + mirrorPort
                    + "&key=" + URLEncoder.encode(key, "UTF-8"));
            current = (HttpURLConnection) url.openConnection();
            current.setConnectTimeout(2000);
            current.setReadTimeout(2000);
            current.setInstanceFollowRedirects(false);
            synchronized (this) {
                if (cancelled) return false;
                connection = current;
            }
            int status = current.getResponseCode();
            return status >= 200 && status < 300;
        } catch (IOException | IllegalArgumentException e) {
            return false;
        } finally {
            synchronized (this) {
                if (connection == current) connection = null;
            }
            if (current != null) current.disconnect();
        }
    }

    void cancel() {
        HttpURLConnection current;
        synchronized (this) { cancelled = true; current = connection; }
        if (current != null) current.disconnect();
    }
}
