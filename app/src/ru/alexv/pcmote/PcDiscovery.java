package ru.alexv.pcmote;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.InterfaceAddress;
import java.net.NetworkInterface;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Enumeration;
import java.util.List;
import java.util.Locale;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/** Bounded, authenticated IPv4 LAN broadcast discovery; no Android services or subnet scans. */
public final class PcDiscovery {
    private static final String PREFIX = "PCMOTE_DISCOVERY|1|";
    private static final int DISCOVERY_PORT = 8766;
    private static final int MAX_PACKET = 512;
    private PcDiscovery() {}

    public static final class Result {
        public final String host, mac, broadcast;
        public final int port;
        public Result(String host, int port, String mac, String broadcast) {
            this.host = host; this.port = port; this.mac = mac; this.broadcast = broadcast;
        }
    }

    private static String hex(byte[] bytes) {
        StringBuilder text = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) text.append(String.format(Locale.US, "%02x", value & 255));
        return text.toString();
    }

    private static String signature(String body, String key) throws Exception {
        if (key == null || key.length() == 0) throw new IllegalArgumentException("Configured key required");
        Mac signer = Mac.getInstance("HmacSHA256");
        signer.init(new SecretKeySpec(key.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        return hex(signer.doFinal(body.getBytes(StandardCharsets.US_ASCII)));
    }

    public static byte[] request(String key, String nonce) throws Exception {
        if (!nonce.matches("[0-9a-f]{32}")) throw new IllegalArgumentException("Invalid nonce");
        String body = PREFIX + "request|" + nonce;
        return (body + "|" + signature(body, key)).getBytes(StandardCharsets.US_ASCII);
    }

    private static boolean ipv4(String text) {
        if (!text.matches("[0-9]{1,3}(\\.[0-9]{1,3}){3}")) return false;
        for (String part : text.split("\\.")) {
            if (Integer.parseInt(part) > 255 || (part.length() > 1 && part.charAt(0) == '0')) return false;
        }
        return true;
    }

    public static Result verify(byte[] packet, String key, String nonce, String source) {
        if (key == null || key.length() == 0 || packet.length > MAX_PACKET || !ipv4(source)) return null;
        try {
            String text = new String(packet, StandardCharsets.US_ASCII);
            String[] fields = text.split("\\|", -1);
            if (fields.length != 8 || !fields[0].equals("PCMOTE_DISCOVERY") || !fields[1].equals("1")
                    || !fields[2].equals("response") || !fields[3].matches("[0-9a-f]{32}")
                    || !fields[3].equals(nonce) || !fields[4].matches("[0-9]{1,5}")
                    || !fields[5].matches("[0-9A-F]{2}(-[0-9A-F]{2}){5}")
                    || !ipv4(fields[6]) || !fields[7].matches("[0-9a-f]{64}")) return null;
            String body = text.substring(0, text.lastIndexOf('|'));
            if (!MessageDigest.isEqual(signature(body, key).getBytes(StandardCharsets.US_ASCII),
                                       fields[7].getBytes(StandardCharsets.US_ASCII))) return null;
            int port = Integer.parseInt(fields[4]);
            if (port < 1 || port > 65535) return null;
            return new Result(source, port, fields[5], fields[6]);
        } catch (Exception ignored) { return null; }
    }

    private static String normalizedMac(String mac) {
        return mac == null ? "" : mac.replace(':', '-').toUpperCase(Locale.US);
    }

    private static int score(Result result, String pairedMac, String pairedHost) {
        if (result == null) return -1;
        if (normalizedMac(result.mac).equals(normalizedMac(pairedMac))) return 2;
        return result.host.equals(pairedHost) ? 1 : 0;
    }

    public static Result prefer(Result current, Result candidate, String pairedMac, String pairedHost) {
        return score(candidate, pairedMac, pairedHost) > score(current, pairedMac, pairedHost) ? candidate : current;
    }

    private static final class Target {
        final InetAddress local, broadcast;
        Target(InetAddress local, InetAddress broadcast) { this.local = local; this.broadcast = broadcast; }
    }

    private static List<Target> targets() throws Exception {
        List<Target> result = new ArrayList<Target>();
        Enumeration<NetworkInterface> interfaces = NetworkInterface.getNetworkInterfaces();
        if (interfaces == null) return result;
        for (NetworkInterface network : Collections.list(interfaces)) {
            if (!network.isUp() || network.isLoopback() || network.isPointToPoint()) continue;
            // Only broadcast-capable LAN interfaces, excluding cellular/tunnel links by capability.
            for (InterfaceAddress address : network.getInterfaceAddresses()) {
                if (address.getAddress() instanceof Inet4Address && address.getBroadcast() != null
                        && !address.getAddress().isLinkLocalAddress()) {
                    result.add(new Target(address.getAddress(), address.getBroadcast()));
                    if (result.size() == 8) return result;
                }
            }
        }
        return result;
    }

    public static Result discover(String key, String pairedMac, String pairedHost) throws Exception {
        if (key == null || key.length() == 0) return null;
        byte[] random = new byte[16];
        new SecureRandom().nextBytes(random);
        String nonce = hex(random);
        byte[] request = request(key, nonce);
        List<DatagramSocket> sockets = new ArrayList<DatagramSocket>();
        Result best = null;
        try {
            for (Target target : targets()) {
                DatagramSocket socket = new DatagramSocket(null);
                try {
                    socket.bind(new InetSocketAddress(target.local, 0));
                    socket.setBroadcast(true);
                    socket.setSoTimeout(90);
                    socket.send(new DatagramPacket(request, request.length, target.broadcast, DISCOVERY_PORT));
                    sockets.add(socket);
                } catch (Exception ignored) { socket.close(); }
            }
            long deadline = System.nanoTime() + 1800000000L;
            byte[] buffer = new byte[MAX_PACKET + 1];
            int packets = 0;
            while (!sockets.isEmpty() && System.nanoTime() < deadline && !Thread.currentThread().isInterrupted() && packets < 128) {
                for (DatagramSocket socket : sockets) {
                    if (System.nanoTime() >= deadline || Thread.currentThread().isInterrupted()) break;
                    try {
                        DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
                        socket.receive(packet);
                        packets++;
                        byte[] data = new byte[packet.getLength()];
                        System.arraycopy(packet.getData(), packet.getOffset(), data, 0, data.length);
                        Result candidate = verify(data, key, nonce, packet.getAddress().getHostAddress());
                        best = prefer(best, candidate, pairedMac, pairedHost);
                    } catch (SocketTimeoutException ignored) { }
                }
            }
            return best;
        } finally {
            for (DatagramSocket socket : sockets) socket.close();
        }
    }
}
