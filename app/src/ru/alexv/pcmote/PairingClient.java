package ru.alexv.pcmote;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.IOException;
import java.net.URL;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.security.cert.CertificateException;
import java.security.cert.X509Certificate;
import java.security.interfaces.RSAPublicKey;
import javax.net.ssl.*;

/** Per-session pinned TLS only. No shared TLS defaults and no HTTP fallback. */
public final class PairingClient implements java.io.Closeable {
    private final PairingLink link;
    private final SSLSocketFactory sockets;
    private volatile HttpsURLConnection active;
    private volatile boolean closed;
    public PairingClient(PairingLink link) throws Exception {
        this.link=link;
        SSLContext context=SSLContext.getInstance("TLS");
        context.init(null,new TrustManager[]{new X509TrustManager(){
            public X509Certificate[] getAcceptedIssuers(){return new X509Certificate[0];}
            public void checkClientTrusted(X509Certificate[] c,String a)throws CertificateException{throw new CertificateException("Client not accepted");}
            public void checkServerTrusted(X509Certificate[] c,String a)throws CertificateException {
                if(c==null || c.length==0)throw new CertificateException("Certificate missing");
                verifyCertificate(c[0],PairingClient.this.link.fingerprint);
            }
        }},new SecureRandom());
        sockets=context.getSocketFactory();
    }
    public static void verifyCertificate(X509Certificate cert,String fingerprint)throws CertificateException {
        try {
            cert.checkValidity();
            if(!(cert.getPublicKey() instanceof RSAPublicKey)
                    || ((RSAPublicKey)cert.getPublicKey()).getModulus().bitLength()<2048)throw new CertificateException("Certificate key rejected");
            byte[] expected=new byte[32];
            if(fingerprint==null || !fingerprint.matches("[0-9a-fA-F]{64}"))throw new CertificateException("Certificate pin rejected");
            for(int i=0;i<32;i++)expected[i]=(byte)Integer.parseInt(fingerprint.substring(i*2,i*2+2),16);
            if(!MessageDigest.isEqual(expected,MessageDigest.getInstance("SHA-256").digest(cert.getEncoded())))throw new CertificateException("Certificate pin rejected");
        }catch(CertificateException e){throw e;}catch(Exception e){throw new CertificateException("Certificate rejected");}
    }
    public String post(String path,String json,boolean acknowledgement)throws Exception {
        if(closed || Thread.currentThread().isInterrupted())throw new IOException("Cancelled");
        if(!path.matches("/pair/v1/(claim|status|ack)"))throw new IOException("Invalid endpoint");
        HttpsURLConnection c=(HttpsURLConnection)new URL("https://"+link.host+":8767"+path).openConnection();
        active=c;
        try {
            if(closed)throw new IOException("Cancelled");
            c.setSSLSocketFactory(sockets);
            c.setHostnameVerifier(new HostnameVerifier(){public boolean verify(String host,SSLSession session){
                try {
                    if(!link.host.equals(host) || !link.host.equals(session.getPeerHost()))return false;
                    verifyCertificate((X509Certificate)session.getPeerCertificates()[0],link.fingerprint);return true;
                }catch(Exception ignored){return false;}
            }});
            c.setInstanceFollowRedirects(false);
            c.setConnectTimeout(4000);c.setReadTimeout(4000);
            c.setRequestMethod("POST");c.setDoOutput(true);
            c.setRequestProperty("Content-Type","application/json; charset=utf-8");
            byte[] bytes=json.getBytes("UTF-8");c.setFixedLengthStreamingMode(bytes.length);
            try(OutputStream out=c.getOutputStream()){out.write(bytes);}
            int code=c.getResponseCode();
            if(acknowledgement){if(code!=204)throw new IOException("Acknowledgement failed");return "";}
            if(code!=200 && code!=202)throw new IOException("Pairing rejected");
            try(InputStream in=c.getInputStream();ByteArrayOutputStream out=new ByteArrayOutputStream()) {
                byte[] buffer=new byte[1024];int n;
                while((n=in.read(buffer))!=-1){if(out.size()+n>8192)throw new IOException("Response too large");out.write(buffer,0,n);}
                return out.toString("UTF-8");
            }
        } finally {c.disconnect();if(active==c)active=null;}
    }
    public void close(){closed=true;HttpsURLConnection c=active;if(c!=null)c.disconnect();}
}
