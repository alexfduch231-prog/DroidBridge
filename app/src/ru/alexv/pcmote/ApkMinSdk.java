package ru.alexv.pcmote;
import java.io.*;
import java.util.*;
import java.util.zip.*;

/** Reads only the typed minSdkVersion from bounded Android binary XML (API 21-23). */
final class ApkMinSdk {
    static int read(File apk)throws Exception{
        ZipFile zip=new ZipFile(apk);byte[] xml;
        try{ZipEntry e=zip.getEntry("AndroidManifest.xml");if(e==null||e.getSize()>1048576)throw new IOException();
            InputStream in=zip.getInputStream(e);try{ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] b=new byte[4096];int n;while((n=in.read(b))!=-1){if(out.size()+n>1048576)throw new IOException();out.write(b,0,n);}xml=out.toByteArray();}finally{in.close();}
        }finally{zip.close();}return parse(xml);
    }
    static int u16(byte[] b,int p)throws IOException{if(p<0||p>b.length-2)throw new IOException();return (b[p]&255)|((b[p+1]&255)<<8);}
    static int i32(byte[] b,int p)throws IOException{return u16(b,p)|(u16(b,p+2)<<16);}
    static int length8(byte[] b,int[] p)throws IOException{int n=b[p[0]++]&255;if((n&128)!=0)n=((n&127)<<8)|(b[p[0]++]&255);return n;}
    static int parse(byte[] b)throws Exception{
        if(u16(b,0)!=3||u16(b,2)!=8||i32(b,4)!=b.length)throw new IOException();List<String> strings=null;int min=-1;
        for(int off=8;off<b.length;){int type=u16(b,off),header=u16(b,off+2),size=i32(b,off+4);if(header<8||size<header||size>b.length-off)throw new IOException();
            if(type==1){if(strings!=null||header<28)throw new IOException();int count=i32(b,off+8),flags=i32(b,off+16),start=i32(b,off+20);if(count<0||count>65536||header+4L*count>size||start<header+4L*count||start>=size)throw new IOException();strings=new ArrayList<String>();
                for(int j=0;j<count;j++){int delta=i32(b,off+header+4*j);if(delta<0||delta>=size-start)throw new IOException();int[] p={off+start+delta};String s;
                    if((flags&256)!=0){length8(b,p);int len=length8(b,p);if(len>off+size-p[0]-1||b[p[0]+len]!=0)throw new IOException();s=new String(b,p[0],len,"UTF-8");}
                    else{int len=u16(b,p[0]);p[0]+=2;if((len&32768)!=0){len=((len&32767)<<16)|u16(b,p[0]);p[0]+=2;}if(len<0||2L*len>off+size-p[0]-2||u16(b,p[0]+2*len)!=0)throw new IOException();s=new String(b,p[0],len*2,"UTF-16LE");}strings.add(s);
                }
            }else if(type==0x102){if(strings==null||header<16||size<36)throw new IOException();int ext=off+16;String name=get(strings,i32(b,ext+4));int attrStart=u16(b,ext+8),attrSize=u16(b,ext+10),count=u16(b,ext+12);if(attrSize<20||attrStart<20||ext-off+attrStart+(long)attrSize*count>size)throw new IOException();
                if(name.equals("uses-sdk")){if(min!=-1)throw new IOException();for(int j=0;j<count;j++){int a=ext+attrStart+j*attrSize;if(get(strings,i32(b,a+4)).equals("minSdkVersion")){if(min!=-1||!get(strings,i32(b,a)).equals("http://schemas.android.com/apk/res/android")||u16(b,a+12)!=8||b[a+15]!=0x10)throw new IOException();min=i32(b,a+16);}}if(min<1||min>1000)throw new IOException();}
            }off+=size;
        }if(min<1)throw new IOException();return min;
    }
    static String get(List<String> strings,int index)throws IOException{if(index<0||index>=strings.size())throw new IOException();return strings.get(index);}
}
