package ru.alexv.pcmote;

import android.animation.Animator;
import android.animation.AnimatorListenerAdapter;
import android.animation.ValueAnimator;
import android.content.Context;
import android.os.Build;
import android.provider.Settings;
import android.util.AttributeSet;
import android.view.MotionEvent;
import android.view.VelocityTracker;
import android.view.View;
import android.view.ViewConfiguration;
import android.view.animation.DecelerateInterpolator;
import android.widget.FrameLayout;

/** A horizontal gesture owner; vertical gestures remain with the drawer's ScrollView. */
public final class DrawerHost extends FrameLayout {
    public interface Listener { void onDrawerTarget(boolean open); }
    private final DrawerMotion motion = new DrawerMotion();
    private View panel, dim;
    private Listener listener;
    private ValueAnimator animator;
    private VelocityTracker velocity;
    private boolean targetOpen, dragging, eligible, downTarget;
    private float downX, downY, downProgress;
    private int pointer = -1;
    private final int slop, minimumVelocity, maximumVelocity;

    public DrawerHost(Context context, AttributeSet attrs) {
        super(context, attrs);
        ViewConfiguration config = ViewConfiguration.get(context);
        slop = config.getScaledTouchSlop();
        minimumVelocity = config.getScaledMinimumFlingVelocity();
        maximumVelocity = config.getScaledMaximumFlingVelocity();
    }
    public void bind(View panel, View dim, Listener listener) {
        this.panel = panel; this.dim = dim; this.listener = listener;
        snap(false);
    }
    private float direction() { return getLayoutDirection() == View.LAYOUT_DIRECTION_RTL ? -1f : 1f; }
    private int width() { return panel.getWidth() > 0 ? panel.getWidth() : panel.getLayoutParams().width; }
    private void cancelAnimation() {
        motion.cancel();
        if (animator != null) { ValueAnimator old = animator; animator = null; old.cancel(); }
    }
    private void paint() {
        if (panel == null) return;
        panel.setTranslationX(direction() * motion.translation(width()));
        dim.setAlpha(motion.dimAlpha());
    }
    private void visibility(boolean visible) {
        panel.setVisibility(visible ? View.VISIBLE : View.GONE);
        dim.setVisibility(visible ? View.VISIBLE : View.GONE);
    }
    private boolean animationsEnabled() {
        if (Build.VERSION.SDK_INT >= 26) return ValueAnimator.areAnimatorsEnabled();
        return Settings.Global.getFloat(getContext().getContentResolver(), Settings.Global.ANIMATOR_DURATION_SCALE, 1f) > 0f;
    }
    public void show(boolean open, boolean animate) {
        if (panel == null) return;
        cancelAnimation(); targetOpen = open;
        final int token = motion.begin(open);
        float to = open ? 1f : 0f;
        long duration = DrawerMotion.duration(motion.progress(), to, animate && animationsEnabled() ? 1f : 0f);
        if (duration == 0L) {
            motion.finish(token); paint(); visibility(open); return;
        }
        visibility(true);
        animator = ValueAnimator.ofFloat(motion.progress(), to);
        animator.setDuration(duration);
        animator.setInterpolator(new DecelerateInterpolator(2f));
        animator.addUpdateListener(new ValueAnimator.AnimatorUpdateListener() {
            public void onAnimationUpdate(ValueAnimator value) {
                motion.move(((Float)value.getAnimatedValue()).floatValue()); paint();
            }
        });
        animator.addListener(new AnimatorListenerAdapter() {
            @Override public void onAnimationEnd(Animator value) {
                if (!motion.finish(token)) return;
                animator = null; paint(); visibility(targetOpen);
            }
        });
        animator.start();
    }
    public void snap(boolean open) {
        cancelAnimation(); targetOpen = open; motion.move(open ? 1f : 0f);
        if (panel != null) { paint(); visibility(open); }
        resetTouch();
    }
    public void settleImmediately() { snap(targetOpen); }
    private void resetTouch() {
        dragging = false; eligible = false; pointer = -1;
        if (velocity != null) { velocity.recycle(); velocity = null; }
    }
    private void settle(boolean open) {
        getParentDisallow(false);
        resetTouch();
        if (listener != null) listener.onDrawerTarget(open);
        show(open, true);
    }
    @Override public boolean onInterceptTouchEvent(MotionEvent event) {
        int action = event.getActionMasked();
        if (action == MotionEvent.ACTION_DOWN) {
            resetTouch();
            eligible = panel != null && panel.getVisibility() == View.VISIBLE && motion.progress() > 0f;
            if (eligible) {
                pointer = event.getPointerId(0); downX = event.getX(); downY = event.getY();
                downProgress = motion.progress(); downTarget = targetOpen;
                velocity = VelocityTracker.obtain(); velocity.addMovement(event);
            }
        } else if (eligible && action == MotionEvent.ACTION_MOVE) {
            int index = event.findPointerIndex(pointer);
            if (index < 0) { settle(downTarget); return false; }
            float dx = event.getX(index) - downX, dy = event.getY(index) - downY;
            if (Math.abs(dy) > slop && Math.abs(dy) > Math.abs(dx)) { resetTouch(); return false; }
            if (Math.abs(dx) > slop && Math.abs(dx) > Math.abs(dy)) {
                cancelAnimation(); dragging = true;
                // The animator may have advanced since DOWN: begin dragging from what is visible now.
                downProgress = motion.progress(); downX = event.getX(index);
                getParentDisallow(true);
                return true;
            }
        } else if (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_CANCEL) resetTouch();
        return dragging;
    }
    private void getParentDisallow(boolean disallow) {
        if (getParent() != null) getParent().requestDisallowInterceptTouchEvent(disallow);
    }
    @Override public boolean onTouchEvent(MotionEvent event) {
        if (!dragging) return super.onTouchEvent(event);
        if (velocity != null) velocity.addMovement(event);
        int action = event.getActionMasked(), index = event.findPointerIndex(pointer);
        if (action == MotionEvent.ACTION_CANCEL || index < 0 || action == MotionEvent.ACTION_POINTER_DOWN
                || action == MotionEvent.ACTION_POINTER_UP) { settle(downTarget); return true; }
        if (action == MotionEvent.ACTION_MOVE) {
            motion.move(downProgress + direction() * (event.getX(index) - downX) / Math.max(1, width()));
            paint(); return true;
        }
        if (action == MotionEvent.ACTION_UP) {
            velocity.computeCurrentVelocity(1000, maximumVelocity);
            boolean open = DrawerMotion.settle(motion.progress(), direction() * velocity.getXVelocity(pointer), minimumVelocity);
            getParentDisallow(false); settle(open); return true;
        }
        return true;
    }
    @Override protected void onSizeChanged(int w, int h, int oldw, int oldh) {
        super.onSizeChanged(w, h, oldw, oldh); paint();
    }
    @Override protected void onDetachedFromWindow() {
        settleImmediately(); listener = null;
        super.onDetachedFromWindow();
    }
}
