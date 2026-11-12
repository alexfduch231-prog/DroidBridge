package ru.alexv.pcmote;

/** View-independent navigation state; selecting a section never recreates its views. */
public final class NavigationState {
    public static final int COUNT = 5;
    private int section;
    private boolean drawerOpen;
    private final int[] scrollPositions = new int[COUNT];
    public int section() { return section; }
    public boolean isDrawerOpen() { return drawerOpen; }
    public void openDrawer() { drawerOpen = true; }
    public boolean back() { boolean wasOpen = drawerOpen; drawerOpen = false; return wasOpen; }
    public void rememberScroll(int scrollY) { scrollPositions[section] = Math.max(0, scrollY); }
    public int select(int next, int scrollY) {
        if (next < 0 || next >= COUNT) next = 0;
        rememberScroll(scrollY);
        section = next;
        drawerOpen = false;
        return scrollPositions[section];
    }
    public int[] positions() { return scrollPositions.clone(); }
    public void restore(int selected, int[] positions) {
        section = selected >= 0 && selected < COUNT ? selected : 0;
        if (positions != null && positions.length == COUNT)
            for (int i = 0; i < COUNT; i++) scrollPositions[i] = Math.max(0, positions[i]);
    }
}
