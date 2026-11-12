package ru.alexv.pcmote;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;

/** Decoder only called on the icon worker, never on the main thread. */
final class AppIconBitmap {
    private AppIconBitmap() {}

    static Bitmap decode(byte[] bytes) {
        if (!AppIconClient.validPng(bytes)) return null;
        try {
            BitmapFactory.Options bounds = new BitmapFactory.Options();
            bounds.inJustDecodeBounds = true;
            bounds.inScaled = false;
            BitmapFactory.decodeByteArray(bytes, 0, bytes.length, bounds);
            if (bounds.outWidth <= 0 || bounds.outHeight <= 0 || bounds.outWidth > 128
                    || bounds.outHeight > 128 || !"image/png".equals(bounds.outMimeType)) return null;
            BitmapFactory.Options options = new BitmapFactory.Options();
            options.inScaled = false;
            options.inPreferredConfig = Bitmap.Config.ARGB_8888;
            Bitmap bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.length, options);
            if (bitmap != null && (bitmap.getWidth() > 128 || bitmap.getHeight() > 128)) {
                bitmap.recycle();
                return null;
            }
            return bitmap;
        } catch (RuntimeException ignored) {
            return null;
        }
    }
}
