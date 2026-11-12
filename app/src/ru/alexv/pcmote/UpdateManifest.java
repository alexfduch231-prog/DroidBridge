package ru.alexv.pcmote;

import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.Charset;
import java.security.KeyFactory;
import java.security.Signature;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.X509EncodedKeySpec;
import java.text.SimpleDateFormat;
import java.text.ParsePosition;
import java.util.*;

/** Android-independent signed protocol. No payload field is interpreted before verification. */
public final class UpdateManifest {
    public static final String FEED="https://github.com/alexfduch231-prog/DroidBridge/releases/latest/download/update-manifest.json";
    public static final String REPOSITORY="alexfduch231-prog/DroidBridge";
    private static final String PUBLIC_KEY="MIIBojANBgkqhkiG9w0BAQEFAAOCAY8AMIIBigKCAYEAuDbZDgHDC3XNP0eH2nQGxYD33yWhS6lgUZ2gVyNB+E6p4YArsY4XKKa2rT52IAZKJEhYlqd28bBncIzVJ4pK1OXl14qMs7HSgVZl52fIryE3g0vQUXE+dQ0Oa/5nKXxbFmD/r/VHBAnnJOZqoeNLVM+Prw3y9fUpxKCHVLAFjtySuF+ltVROTGUBTzF2ttO3NrSHOPBMBT778QwYg1bC/gj87boQYTRD/g/qUNweRLBy0qtsz52kg1A+gIEw2wzVyMDeyRTWRM9ooXS9Nxw5E0f9qwmkjeKSqwllazlBna34lY7RPl5h4LUzihzedJoV0hP1fPt79MemZOwviTpOHy4V3FSoCwpLL+b04VOqm//gG7oeBb1fIVCvzEy7mKc6ws+1OyxDXaVvMhMBhL/aK9A60z8g4qSEQzgXsJ0NPPl24XyH2T2NXza20CKjpSwNtt9mW7nCtqqq8gVNAb88i7X6zK0GMAOip9bPC+81Zz692r2exBehf8e59wEaGTszAgMBAAE=";
    public final long sequence, expiresAt, size;
    public final int versionCode, minSdk;
    public final String packageName, versionName, assetName, url, sha256;
    public final Set<String> signerCertSha256;
    private UpdateManifest(Map<String,Object> a,long seq,long expiry) {
        sequence=seq;expiresAt=expiry;versionCode=(int)number(a,"versionCode",1,Integer.MAX_VALUE);
        minSdk=(int)number(a,"minSdk",21,1000);packageName=text(a,"packageName",128);
        require(packageName.equals("ru.alexv.pcmote"));versionName=text(a,"versionName",64);
        require(versionName.matches("[0-9]+(?:\\.[0-9]+){1,3}"));
        assetName=text(a,"assetName",128);url=text(a,"url",2048);size=number(a,"size",1,128L*1024*1024);
        sha256=hash(a,"sha256");asset(a,".apk");
        Object certs=a.get("signerCertSha256");require(certs instanceof List);
        List<?> list=(List<?>)certs;require(list.size()>=1&&list.size()<=8);
        Set<String> set=new HashSet<String>();for(Object c:list){require(c instanceof String&&((String)c).matches("[0-9a-f]{64}"));require(set.add((String)c));}
        signerCertSha256=Collections.unmodifiableSet(set);
    }
    public boolean isNewer(long installedVersionCode){return versionCode>installedVersionCode;}
    public static UpdateManifest verify(byte[] envelope,long now,long maxSequence) {
        try {
            require(envelope.length<=65536);Map<String,Object> outer=object(parseJson(utf8(envelope)));
            fields(outer,"payload","signature");byte[] payload=base64(text(outer,"payload",45000));
            require(payload.length<=32768);byte[] signature=base64(text(outer,"signature",1024));require(signature.length==384);
            RSAPublicKey key=(RSAPublicKey)KeyFactory.getInstance("RSA").generatePublic(new X509EncodedKeySpec(base64(PUBLIC_KEY)));
            require(key.getModulus().bitLength()==3072);Signature verifier=Signature.getInstance("SHA256withRSA");verifier.initVerify(key);
            verifier.update("DroidBridge/update-manifest/v1\n".getBytes("UTF-8"));verifier.update(payload);require(verifier.verify(signature));
            Map<String,Object> p=object(parseJson(utf8(payload)));
            fields(p,"schema","repository","channel","sequence","publishedAt","expiresAt","windows","android");
            require(number(p,"schema",1,1)==1);require(text(p,"repository",128).equals(REPOSITORY));require(text(p,"channel",16).equals("stable"));
            long seq=number(p,"sequence",1,9007199254740991L);require(seq>=maxSequence);
            long published=date(text(p,"publishedAt",20)),expiry=date(text(p,"expiresAt",20));require(published<=now&&published<expiry&&expiry>now);
            Map<String,Object> w=object(p.get("windows"));fields(w,"version","architecture","assetName","url","size","sha256");
            String version=text(w,"version",64);require(version.matches("[0-9]+\\.[0-9]+\\.[0-9]+"));
            for(String part:version.split("\\."))require(Long.parseLong(part)<=Integer.MAX_VALUE);
            require(text(w,"architecture",8).equals("x64"));number(w,"size",1,512L*1024*1024);hash(w,"sha256");asset(w,".exe");
            Map<String,Object> a=object(p.get("android"));fields(a,"packageName","versionName","versionCode","minSdk","assetName","url","size","sha256","signerCertSha256");
            return new UpdateManifest(a,seq,expiry);
        }catch(Exception ex){throw new IllegalArgumentException("Invalid update manifest");}
    }
    private static void asset(Map<String,Object> m,String extension){
        String name=text(m,"assetName",128);require(name.matches("[A-Za-z0-9][A-Za-z0-9._-]{0,127}")&&name.endsWith(extension)&&!name.contains(".."));
        String s=text(m,"url",2048);URI u=redirectUrl(s);require(u.getHost().equals("github.com")&&u.getRawQuery()==null);
        String prefix="/"+REPOSITORY+"/releases/download/";String path=u.getRawPath();require(path.startsWith(prefix));
        String rest=path.substring(prefix.length());require(rest.matches("[A-Za-z0-9][A-Za-z0-9._-]{0,127}/"+java.util.regex.Pattern.quote(name)));
    }
    public static URI redirectUrl(String text){
        try{URI u=new URI(text);String h=u.getHost();require("https".equals(u.getScheme())&&u.getUserInfo()==null&&u.getFragment()==null&&(u.getPort()==-1||u.getPort()==443));
            require(h!=null&&(h.equals("github.com")||h.equals("api.github.com")||h.equals("release-assets.githubusercontent.com")||h.equals("objects.githubusercontent.com")));return u;
        }catch(Exception ex){throw new IllegalArgumentException("Invalid update URL");}
    }
    private static long date(String s){
        require(s.matches("[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z"));
        SimpleDateFormat f=new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'",Locale.US);f.setLenient(false);f.setTimeZone(TimeZone.getTimeZone("UTC"));ParsePosition pos=new ParsePosition(0);Date d=f.parse(s,pos);require(d!=null&&pos.getIndex()==s.length());return d.getTime();
    }
    private static String utf8(byte[] b)throws Exception{return Charset.forName("UTF-8").newDecoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(b)).toString();}
    private static String hash(Map<String,Object> m,String k){String s=text(m,k,64);require(s.matches("[0-9a-f]{64}"));return s;}
    private static String text(Map<String,Object> m,String k,int max){Object v=m.get(k);require(v instanceof String);String s=(String)v;require(s.length()>0&&s.length()<=max);return s;}
    private static long number(Map<String,Object> m,String k,long min,long max){Object v=m.get(k);require(v instanceof Long);long n=((Long)v).longValue();require(n>=min&&n<=max);return n;}
    @SuppressWarnings("unchecked") private static Map<String,Object> object(Object o){require(o instanceof Map);return (Map<String,Object>)o;}
    private static void fields(Map<String,Object> m,String... keys){require(m.keySet().equals(new HashSet<String>(Arrays.asList(keys))));}
    private static void require(boolean ok){if(!ok)throw new IllegalArgumentException("Invalid update data");}
    private static final String B64="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    private static byte[] base64(String s){
        require(s.length()%4==0&&s.matches("[A-Za-z0-9+/]*={0,2}"));ByteArrayOutputStream out=new ByteArrayOutputStream();
        for(int i=0;i<s.length();i+=4){int a=B64.indexOf(s.charAt(i)),b=B64.indexOf(s.charAt(i+1));char cc=s.charAt(i+2),dd=s.charAt(i+3);int c=cc=='='?0:B64.indexOf(cc),d=dd=='='?0:B64.indexOf(dd);require(a>=0&&b>=0&&c>=0&&d>=0);require(cc!='='||dd=='=');if(cc=='='||dd=='=')require(i+4==s.length());if(cc=='=')require((b&15)==0);else if(dd=='=')require((c&3)==0);out.write((a<<2)|(b>>4));if(cc!='=')out.write((b<<4)|(c>>2));if(dd!='=')out.write((c<<6)|d);}
        return out.toByteArray();
    }
    /** Small bounded JSON tokenizer: duplicate decoded keys, non-integers, bad Unicode and trailing input rejected. */
    public static Object parseJson(String s){require(s.length()<=65536);Parser p=new Parser(s);Object result=p.value(0);p.ws();require(p.i==s.length());return result;}
    private static final class Parser {
        final String s;int i;Parser(String s){this.s=s;}
        void ws(){while(i<s.length()&&" \r\n\t".indexOf(s.charAt(i))>=0)i++;}
        char next(){require(i<s.length());return s.charAt(i++);}
        Object value(int depth){require(depth<=8);ws();require(i<s.length());char c=s.charAt(i);
            if(c=='{'){i++;Map<String,Object> m=new LinkedHashMap<String,Object>();ws();if(i<s.length()&&s.charAt(i)=='}'){i++;return m;}do{ws();String k=string();require(!m.containsKey(k));ws();require(next()==':');m.put(k,value(depth+1));require(m.size()<=32);ws();c=next();if(c=='}')return m;require(c==',');}while(true);}
            if(c=='['){i++;List<Object> a=new ArrayList<Object>();ws();if(i<s.length()&&s.charAt(i)==']'){i++;return a;}do{a.add(value(depth+1));require(a.size()<=32);ws();c=next();if(c==']')return a;require(c==',');}while(true);}
            if(c=='"')return string();
            if(c=='-'||(c>='0'&&c<='9')){int start=i;if(c=='-')i++;require(i<s.length());if(s.charAt(i)=='0')i++;else{require(s.charAt(i)>='1'&&s.charAt(i)<='9');while(i<s.length()&&s.charAt(i)>='0'&&s.charAt(i)<='9')i++;}try{return Long.valueOf(s.substring(start,i));}catch(Exception ex){throw new IllegalArgumentException("Invalid integer");}}
            for(String literal:new String[]{"true","false","null"})if(s.startsWith(literal,i)){i+=literal.length();return literal.equals("null")?null:Boolean.valueOf(literal);}
            throw new IllegalArgumentException("Invalid JSON");
        }
        String string(){require(next()=='"');StringBuilder b=new StringBuilder();while(true){char c=next();if(c=='"')break;require(c>=32);if(c=='\\'){c=next();int n="\"\\/bfnrt".indexOf(c);if(n>=0)c="\"\\/\b\f\n\r\t".charAt(n);else{require(c=='u');require(i+4<=s.length());String h=s.substring(i,i+4);require(h.matches("[0-9a-fA-F]{4}"));c=(char)Integer.parseInt(h,16);i+=4;}}b.append(c);require(b.length()<=45000);}
            String r=b.toString();for(int x=0;x<r.length();x++){char c=r.charAt(x);if(Character.isHighSurrogate(c)){require(x+1<r.length()&&Character.isLowSurrogate(r.charAt(++x)));}else require(!Character.isLowSurrogate(c));}return r;
        }
    }
}
