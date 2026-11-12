package ru.alexv.pcmote;

import android.content.Context;
import android.util.AttributeSet;
import android.widget.LinearLayout;

/**
 * Плитка приложения: высота всегда равна ширине, чтобы сетка оставалась квадратной
 * при любой ширине экрана. Ширину задаёт вес в строке, из неё и берём сторону.
 */
public class SquareLayout extends LinearLayout {

    public SquareLayout(Context context) {
        super(context);
    }

    public SquareLayout(Context context, AttributeSet attrs) {
        super(context, attrs);
    }

    public SquareLayout(Context context, AttributeSet attrs, int defStyleAttr) {
        super(context, attrs, defStyleAttr);
    }

    @Override
    protected void onMeasure(int widthMeasureSpec, int heightMeasureSpec) {
        super.onMeasure(widthMeasureSpec, heightMeasureSpec);
        int side = getMeasuredWidth();
        setMeasuredDimension(side, side);
    }
}
