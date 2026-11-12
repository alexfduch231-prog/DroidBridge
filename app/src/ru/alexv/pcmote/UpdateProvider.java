package ru.alexv.pcmote;
import android.content.*;
import android.database.*;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import java.io.*;

/** Exactly one read-only verified APK; never maps caller-controlled paths. */
public final class UpdateProvider extends ContentProvider {
    public boolean onCreate(){return true;}
    private void uri(Uri u){if(u==null||!"content".equals(u.getScheme())||!(getContext().getPackageName()+".updates").equals(u.getAuthority())||!"/update.apk".equals(u.getEncodedPath())||u.getQuery()!=null||u.getFragment()!=null)throw new SecurityException();}
    public String getType(Uri u){uri(u);return "application/vnd.android.package-archive";}
    public ParcelFileDescriptor openFile(Uri u,String mode)throws FileNotFoundException{
        uri(u);if(!"r".equals(mode))throw new SecurityException("Read only");
        try{return ParcelFileDescriptor.open(StartupUpdate.verifyCached(getContext()),ParcelFileDescriptor.MODE_READ_ONLY);}catch(Exception ignored){throw new FileNotFoundException("Verified update unavailable");}
    }
    public Cursor query(Uri u,String[] projection,String selection,String[] args,String sort){
        uri(u);if(selection!=null||args!=null||sort!=null)throw new UnsupportedOperationException();
        try{File f=StartupUpdate.verifyCached(getContext());String[] cols=projection==null?new String[]{OpenableColumns.DISPLAY_NAME,OpenableColumns.SIZE}:projection;
            MatrixCursor c=new MatrixCursor(cols);Object[] row=new Object[cols.length];for(int i=0;i<cols.length;i++){if(OpenableColumns.DISPLAY_NAME.equals(cols[i]))row[i]="update.apk";else if(OpenableColumns.SIZE.equals(cols[i]))row[i]=Long.valueOf(f.length());else throw new UnsupportedOperationException();}c.addRow(row);return c;
        }catch(UnsupportedOperationException e){throw e;}catch(Exception e){throw new SecurityException("Verified update unavailable");}
    }
    public Uri insert(Uri u,ContentValues v){throw new UnsupportedOperationException();}
    public int delete(Uri u,String s,String[] a){throw new UnsupportedOperationException();}
    public int update(Uri u,ContentValues v,String s,String[] a){throw new UnsupportedOperationException();}
}
