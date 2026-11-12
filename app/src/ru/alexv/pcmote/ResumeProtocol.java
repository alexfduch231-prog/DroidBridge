package ru.alexv.pcmote;

import java.io.*;
import java.security.MessageDigest;

/** Streaming primitives shared by preparation, restart verification and chunk delivery. */
final class ResumeProtocol {
    static final int CHUNK = 4 * 1024 * 1024;
    static final long MAX = 50L * 1024 * 1024 * 1024;
    interface Check { void check() throws IOException; }
    static MessageDigest digest() {
        try { return MessageDigest.getInstance("SHA-256"); }
        catch (Exception e) { throw new IllegalStateException(e); }
    }
    static String hex(byte[] value) {
        StringBuilder out = new StringBuilder(value.length * 2);
        for (byte b : value) { out.append(Character.forDigit((b & 255) >> 4, 16)); out.append(Character.forDigit(b & 15, 16)); }
        return out.toString();
    }
    static String fingerprint(String key) throws IOException { return hex(digest().digest(key.getBytes("UTF-8"))); }
    static boolean bound(String host, String key, String owner, String fingerprint) throws IOException {
        return host.equals(owner) && fingerprint(key).equals(fingerprint);
    }
    static String hash(InputStream in, long expected, Check check) throws IOException {
        MessageDigest md = digest(); byte[] buffer = new byte[65536]; long count = 0; int n;
        while (true) {
            if (check != null) check.check();
            n = in.read(buffer); if (n == -1) break;
            count += n;
            if (count > MAX || (expected >= 0 && count > expected)) throw new IOException("Source size changed");
            md.update(buffer, 0, n);
        }
        if (expected >= 0 && count != expected) throw new IOException("Source size changed");
        return hex(md.digest());
    }
    static void checkOffset(long offset, long size) throws IOException {
        if (size < 0 || size > MAX || offset < 0 || offset > size || (offset != size && offset % CHUNK != 0)) throw new IOException("Invalid upload offset");
    }
    static void skipFully(InputStream in, long count) throws IOException { skipFully(in, count, null); }
    static void skipFully(InputStream in, long count, Check check) throws IOException {
        byte[] buffer = new byte[65536];
        while (count > 0) {
            if (check != null) check.check();
            int n = in.read(buffer, 0, (int)Math.min(count, buffer.length));
            if (n < 0) throw new EOFException("Source size changed"); count -= n;
        }
    }
    static boolean mayCreate(boolean attempted) { return !attempted; }
    static boolean needsSource(boolean prepared, boolean complete) { return prepared && !complete; }
    static boolean needsRemoteAbort(boolean localOnly) { return !localOnly; }
    static long retryDelay(int attempt) { return attempt >= 0 && attempt < 3 ? 1000L << attempt : -1; }
}
