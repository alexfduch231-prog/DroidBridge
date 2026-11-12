package ru.alexv.pcmote;

/** Platform-independent drawer progress and invalidatable completion generation. */
public final class DrawerMotion {
    private float progress;
    private boolean target;
    private int generation;
    public float progress() { return progress; }
    public int begin(boolean open) { target = open; return ++generation; }
    public void cancel() { generation++; }
    public void move(float value) { progress = Math.max(0f, Math.min(1f, value)); }
    public boolean finish(int token) {
        if (token != generation) return false;
        progress = target ? 1f : 0f;
        return true;
    }
    public float translation(int width) { return (progress - 1f) * width; }
    public float dimAlpha() { return progress; }
    public static boolean settle(float progress, float velocity, float minimumVelocity) {
        return Math.abs(velocity) >= minimumVelocity ? velocity > 0 : progress >= .5f;
    }
    public static long duration(float from, float to, float scale) {
        return scale <= 0f ? 0L : Math.round(240f * Math.abs(to - from));
    }
}
