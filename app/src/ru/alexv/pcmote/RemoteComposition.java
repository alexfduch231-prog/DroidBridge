package ru.alexv.pcmote;

/** Only text currently composed by the local IME; never remote field contents. */
final class RemoteComposition {
    private String pending = "";
    void set(CharSequence text) { pending = text == null ? "" : text.toString(); }
    String commit(CharSequence text) { clear(); return text == null ? "" : text.toString(); }
    String finish() { String value = pending; clear(); return value; }
    void clear() { pending = ""; }
    boolean delete(int before, int after) {
        if (pending.length() == 0) return false;
        int count = Math.min(Math.max(0, before), pending.codePointCount(0, pending.length()));
        pending = pending.substring(0, pending.offsetByCodePoints(pending.length(), -count));
        return true;
    }
}
