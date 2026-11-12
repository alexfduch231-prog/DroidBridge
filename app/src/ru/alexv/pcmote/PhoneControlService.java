package ru.alexv.pcmote;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.accessibilityservice.GestureDescription;
import android.content.Intent;
import android.graphics.Path;
import android.graphics.Point;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Display;
import android.view.WindowManager;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityManager;
import android.view.accessibility.AccessibilityNodeInfo;
import org.json.JSONObject;
import java.util.concurrent.Callable;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;

/** Explicit user opt-in only. No clipboard, node text collection or background input. */
public class PhoneControlService extends AccessibilityService {
    private static volatile PhoneControlService instance;
    private final Handler main = new Handler(Looper.getMainLooper());
    private boolean gestureBusy;

    @Override protected void onServiceConnected() { instance = this; }
    @Override public void onAccessibilityEvent(AccessibilityEvent event) { }
    @Override public void onInterrupt() { }
    @Override public boolean onUnbind(Intent intent) {
        if (instance == this) instance = null;
        return super.onUnbind(intent);
    }
    @Override public void onDestroy() {
        if (instance == this) instance = null;
        main.removeCallbacksAndMessages(null);
        super.onDestroy();
    }

    public static boolean isAvailable() {
        PhoneControlService s = instance;
        if (Build.VERSION.SDK_INT < 24 || s == null) return false;
        AccessibilityManager am = (AccessibilityManager) s.getSystemService(ACCESSIBILITY_SERVICE);
        if (am == null || !am.isEnabled()) return false;
        for (AccessibilityServiceInfo info : am.getEnabledAccessibilityServiceList(
                AccessibilityServiceInfo.FEEDBACK_ALL_MASK)) {
            android.content.pm.ServiceInfo si = info.getResolveInfo().serviceInfo;
            if (s.getPackageName().equals(si.packageName)
                    && PhoneControlService.class.getName().equals(si.name)) return true;
        }
        return false;
    }

    static JSONObject result(String error) {
        JSONObject r = new JSONObject();
        try {
            r.put("ok", error == null);
            if (error != null) r.put("error", error);
        } catch (Exception ignored) { }
        return r;
    }

    /** Strict JSON types: do not coerce strings/booleans to coordinates or durations. */
    static String validate(JSONObject event) {
        if (event == null) return "invalid_event";
        Object a = event.opt("action");
        if (!(a instanceof String)) return "invalid_action";
        String action = (String) a;
        if ("tap".equals(action) || "longpress".equals(action) || "swipe".equals(action)) {
            if (!coordinate(event.opt("x")) || !coordinate(event.opt("y"))) return "invalid_coordinates";
            if ("swipe".equals(action)) {
                if (!coordinate(event.opt("x2")) || !coordinate(event.opt("y2"))) return "invalid_coordinates";
                Object d = event.opt("duration");
                if (!(d instanceof Number)) return "invalid_duration";
                double n = ((Number) d).doubleValue();
                if (Double.isNaN(n) || Double.isInfinite(n) || n < 50 || n > 2000 || n != Math.rint(n))
                    return "invalid_duration";
            }
        } else if ("global".equals(action)) {
            Object n = event.opt("name");
            if (!(n instanceof String) || !("back".equals(n) || "home".equals(n)
                    || "recents".equals(n) || "notifications".equals(n))) return "invalid_global";
        } else if ("text".equals(action)) {
            Object t = event.opt("text");
            if (!(t instanceof String) || ((String) t).length() > 2000) return "invalid_text";
        } else return "unknown_action";
        return null;
    }

    private static boolean coordinate(Object value) {
        if (!(value instanceof Number)) return false;
        double n = ((Number) value).doubleValue();
        return !Double.isNaN(n) && !Double.isInfinite(n) && n >= 0 && n <= 1;
    }

    /** Called by the authenticated socket reader, never by a binder/exported receiver. */
    public static JSONObject dispatch(final JSONObject event) {
        if (event == null || event.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8).length > 8192)
            return result("invalid_event_size");
        String invalid = validate(event);
        if (invalid != null) return result(invalid);
        final Object session = MirrorService.controlSession();
        if (!MirrorService.running || session == null) return result("no_authenticated_session");
        final PhoneControlService s = instance;
        if (!isAvailable() || s == null) return result("accessibility_unavailable");
        final FutureTask<JSONObject> task = new FutureTask<JSONObject>(new Callable<JSONObject>() {
            public JSONObject call() {
                // Re-check after crossing threads: queued input must not survive disconnect/stop.
                if (!MirrorService.running || !MirrorService.isControlSessionActive(session))
                    return result("no_authenticated_session");
                if (instance != s || !isAvailable()) return result("accessibility_unavailable");
                try { return s.perform(event); }
                catch (Exception e) { return result("action_failed"); }
            }
        });
        if (Looper.myLooper() == Looper.getMainLooper()) task.run();
        else if (!s.main.post(task)) return result("accessibility_unavailable");
        try { return task.get(2, TimeUnit.SECONDS); }
        catch (Exception e) {
            task.cancel(false);
            s.main.removeCallbacks(task);
            return result("dispatch_timeout");
        }
    }

    @SuppressWarnings("deprecation")
    private JSONObject perform(JSONObject event) throws Exception {
        String action = event.getString("action");
        if ("global".equals(action)) {
            String name = event.getString("name");
            int id = "back".equals(name) ? GLOBAL_ACTION_BACK : "home".equals(name) ? GLOBAL_ACTION_HOME
                    : "recents".equals(name) ? GLOBAL_ACTION_RECENTS : GLOBAL_ACTION_NOTIFICATIONS;
            return result(performGlobalAction(id) ? null : "global_action_rejected");
        }
        if ("text".equals(action)) {
            AccessibilityNodeInfo root = getRootInActiveWindow();
            if (root == null) return result("no_focused_editable");
            AccessibilityNodeInfo node = null;
            try {
                node = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT);
                if (node == null || !node.isEditable() || !node.isEnabled()
                        || (Build.VERSION.SDK_INT >= 26 && node.isPassword()))
                    return result("no_focused_editable");
                Bundle args = new Bundle();
                args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,
                        event.getString("text"));
                return result(node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
                        ? null : "text_action_rejected");
            } finally {
                if (node != null && node != root) node.recycle();
                root.recycle();
            }
        }
        if (Build.VERSION.SDK_INT < 24) return result("gestures_require_api24");
        WindowManager wm = (WindowManager) getSystemService(WINDOW_SERVICE);
        Display display = wm.getDefaultDisplay();
        Point size = new Point();
        display.getRealSize(size);
        if (!MirrorService.matchesControlDisplay(display.getRotation(), size.x, size.y))
            return result("rotation_mismatch");
        if (gestureBusy) return result("gesture_busy");
        Path path = new Path();
        path.moveTo((float) event.getDouble("x") * (size.x - 1),
                (float) event.getDouble("y") * (size.y - 1));
        long duration = "longpress".equals(action) ? 650L : 70L;
        if ("swipe".equals(action)) {
            path.lineTo((float) event.getDouble("x2") * (size.x - 1),
                    (float) event.getDouble("y2") * (size.y - 1));
            duration = event.getLong("duration");
        }
        GestureDescription gesture = new GestureDescription.Builder()
                .addStroke(new GestureDescription.StrokeDescription(path, 0, duration)).build();
        gestureBusy = true;
        boolean accepted = dispatchGesture(gesture, new GestureResultCallback() {
            @Override public void onCompleted(GestureDescription gesture) { gestureBusy = false; }
            @Override public void onCancelled(GestureDescription gesture) { gestureBusy = false; }
        }, main);
        if (!accepted) gestureBusy = false;
        return result(accepted ? null : "gesture_rejected");
    }
}
