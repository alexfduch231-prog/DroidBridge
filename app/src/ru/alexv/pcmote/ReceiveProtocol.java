package ru.alexv.pcmote;

/** Untrusted manifest and offset checks, independent of Android/providers. */
final class ReceiveProtocol {
    static final int CHUNK = 4*1024*1024;
    static final long MAX = 50L*1024*1024*1024;
    static void validate(String id,String name,long size,String sha) {
        if(id==null||!id.matches("[0-9a-f]{32}")||sha==null||!sha.matches("[0-9a-f]{64}")
                ||size<0||size>MAX||name==null||name.length()==0||name.length()>240
                ||name.equals(".")||name.equals("..")) throw new IllegalArgumentException("Invalid transfer");
        for(int i=0;i<name.length();i++) if(name.charAt(i)<32||name.charAt(i)=='/'||name.charAt(i)=='\\')
            throw new IllegalArgumentException("Invalid filename");
    }
    static long durableOffset(long length,long size) {
        if(length<0||length>size)throw new IllegalArgumentException("Invalid partial file");
        return length==size?length:length/CHUNK*CHUNK;
    }
    static String hex(byte[] bytes){
        StringBuilder s=new StringBuilder();for(byte b:bytes)s.append(String.format(java.util.Locale.ROOT,"%02x",b&255));return s.toString();
    }
}
