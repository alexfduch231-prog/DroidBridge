package ru.alexv.pcmote;

/** Pure gesture classification; transport and coordinate conversion stay outside. */
final class HybridGesture {
    static final int CLICK=1, MOVE=2, SCROLL=3;
    static final class Event {
        final int kind, count;
        final float x,y,dx,dy;
        final boolean right;
        Event(int k,float px,float py,float mx,float my,boolean r,int c) {
            kind=k;x=px;y=py;dx=mx;dy=my;right=r;count=c;
        }
    }
    private final float slop;
    private float scrollRemainder;
    int scrollSteps(float delta,float pixelsPerStep){
        scrollRemainder+=delta;
        int steps=(int)(scrollRemainder/pixelsPerStep);
        steps=Math.max(-10,Math.min(10,steps));
        scrollRemainder-=steps*pixelsPerStep;
        return steps;
    }
    private float startX,startY,lastX,lastY,scrollY,tapX,tapY;
    private long downTime,lastTap=-10000;
    private boolean active,moved,multiple,lifted;
    HybridGesture(float touchSlop){slop=touchSlop;}
    void down(float x,float y,long time){
        startX=lastX=x;startY=lastY=y;downTime=time;
        active=true;moved=multiple=lifted=false;scrollRemainder=0;
    }
    Event move(float x,float y){
        if(!active||multiple||lifted)return null;
        if(!moved&&Math.hypot(x-startX,y-startY)<=slop)return null;
        moved=true;float dx=x-lastX,dy=y-lastY;lastX=x;lastY=y;
        return new Event(MOVE,x,y,dx,dy,false,0);
    }
    void twoFingers(float centroidY){if(active){multiple=true;scrollY=centroidY;lastTap=-10000;}}
    Event scroll(float centroidY){
        if(!active||!multiple||lifted)return null;
        float delta=centroidY-scrollY;
        if(Math.abs(delta)<slop)return null;
        scrollY=centroidY;return new Event(SCROLL,0,0,0,delta,false,0);
    }
    void pointerLift(){lifted=true;}
    Event up(float x,float y,long time){
        if(!active)return null;active=false;
        if(moved||multiple||lifted||Math.hypot(x-startX,y-startY)>slop){lastTap=-10000;return null;}
        boolean right=time-downTime>=600;
        int count=!right&&time-lastTap<=350&&Math.hypot(x-tapX,y-tapY)<=slop*2?2:1;
        lastTap=right||count==2?-10000:time;tapX=x;tapY=y;
        return new Event(CLICK,x,y,0,0,right,count);
    }
    void cancel(){active=false;lastTap=-10000;scrollRemainder=0;}
}
