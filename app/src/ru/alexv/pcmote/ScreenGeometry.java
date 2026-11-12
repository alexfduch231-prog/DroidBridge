package ru.alexv.pcmote;

/** Presentation rectangle in parent coordinates; input uses the same rectangle. */
final class ScreenGeometry {
    final int width, height, left, top;
    private ScreenGeometry(int width, int height, int parentWidth, int parentHeight) {
        this.width = width;
        this.height = height;
        this.left = (parentWidth - width) / 2;
        this.top = (parentHeight - height) / 2;
    }
    static ScreenGeometry calculate(int sourceWidth, int sourceHeight, int parentWidth,
                                    int parentHeight, boolean fill) {
        if (sourceWidth <= 0 || sourceHeight <= 0 || parentWidth <= 0 || parentHeight <= 0)
            throw new IllegalArgumentException("Invalid video bounds");
        double sx = parentWidth / (double) sourceWidth;
        double sy = parentHeight / (double) sourceHeight;
        double scale = fill ? Math.max(sx, sy) : Math.min(sx, sy);
        return new ScreenGeometry(Math.max(1, (int) Math.round(sourceWidth * scale)),
                Math.max(1, (int) Math.round(sourceHeight * scale)), parentWidth, parentHeight);
    }
    double normalizedX(double x) { return normalized(x, left, width); }
    double normalizedY(double y) { return normalized(y, top, height); }
    private static double normalized(double value, int origin, int size) {
        double result = (value - origin) / size;
        return result < 0 || result > 1 ? Double.NaN : result;
    }
}
