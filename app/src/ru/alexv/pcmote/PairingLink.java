package ru.alexv.pcmote;

import java.net.URI;
import java.util.HashMap;
import java.util.Map;

/** Strict bootstrap parser. Never include input in exceptions or logs. */
public final class PairingLink {
    public final String host, fingerprint, ticket;
    private PairingLink(String host, String fingerprint, String ticket) {
        this.host=host; this.fingerprint=fingerprint; this.ticket=ticket;
    }
    public static boolean privateIPv4(String host) {
        if (host==null || !host.matches("(?:0|[1-9][0-9]{0,2})(?:\\.(?:0|[1-9][0-9]{0,2})){3}")) return false;
        String[] parts=host.split("\\."); int[] n=new int[4];
        for(int i=0;i<4;i++){n[i]=Integer.parseInt(parts[i]);if(n[i]>255)return false;}
        return n[0]==10 || n[0]==172 && n[1]>=16 && n[1]<=31 || n[0]==192 && n[1]==168;
    }
    public static boolean secret(String value) {
        // 32 bytes unpadded base64url: the final two padding bits must be zero.
        return value!=null && value.matches("[A-Za-z0-9_-]{42}[AEIMQUYcgkosw048]");
    }
    public static PairingLink parse(String input) {
        try {
            if(input==null || input.length()>512)throw new Exception();
            URI uri=new URI(input);
            if(!"pcmote".equals(uri.getScheme()) || !"pair".equals(uri.getRawAuthority())
                    || uri.getRawUserInfo()!=null || uri.getPort()!=-1
                    || uri.getRawPath()==null || !uri.getRawPath().isEmpty() || uri.getRawFragment()!=null)throw new Exception();
            String query=uri.getRawQuery(); if(query==null)throw new Exception();
            Map<String,String> values=new HashMap<String,String>();
            for(String item:query.split("&",-1)) {
                String[] pair=item.split("=",-1);
                if(pair.length!=2 || values.put(pair[0],pair[1])!=null)throw new Exception();
            }
            if(values.size()!=5 || !"1".equals(values.get("v")) || !"8767".equals(values.get("port"))
                    || !privateIPv4(values.get("host")) || values.get("fp")==null
                    || !values.get("fp").matches("[0-9a-fA-F]{64}") || !secret(values.get("ticket")))throw new Exception();
            return new PairingLink(values.get("host"),values.get("fp").toLowerCase(java.util.Locale.US),values.get("ticket"));
        } catch(Exception ignored) {throw new IllegalArgumentException("Invalid pairing link");}
    }
}
