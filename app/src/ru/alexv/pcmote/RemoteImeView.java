package ru.alexv.pcmote;

import android.content.Context;
import android.view.View;
import android.view.KeyEvent;
import android.view.inputmethod.BaseInputConnection;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputConnection;
import android.view.inputmethod.InputMethodManager;
import android.text.InputType;

/** Local IME endpoint. No Windows field contents are copied into Android. */
final class RemoteImeView extends View {
    interface Sink { void text(String value); void key(String value); }
    private final Sink sink;
    private final RemoteComposition composition = new RemoteComposition();
    RemoteImeView(Context context, Sink target) {
        super(context); sink=target; setFocusable(true);setFocusableInTouchMode(true);
        if(android.os.Build.VERSION.SDK_INT>=26)setImportantForAutofill(IMPORTANT_FOR_AUTOFILL_NO);
    }
    @Override public boolean onCheckIsTextEditor(){return true;}
    @Override public InputConnection onCreateInputConnection(EditorInfo info){
        info.inputType=InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE
                |InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS;
        info.imeOptions=EditorInfo.IME_FLAG_NO_EXTRACT_UI|EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING
                |EditorInfo.IME_ACTION_NONE;
        return new BaseInputConnection(this,false){
            @Override public boolean commitText(CharSequence text,int cursor){
                String value=composition.commit(text);
                if(value.length()>0)sink.text(value);
                return true;
            }
            // Composing text stays local until the user's IME commits it.
            @Override public boolean setComposingText(CharSequence text,int cursor){composition.set(text);return true;}
            @Override public boolean finishComposingText(){String value=composition.finish();if(value.length()>0)sink.text(value);return true;}
            @Override public boolean deleteSurroundingText(int before,int after){
                if(composition.delete(before,after))return true;
                for(int i=0;i<Math.min(32,Math.max(0,before));i++)sink.key("backspace");
                for(int i=0;i<Math.min(32,Math.max(0,after));i++)sink.key("delete");
                return true;
            }
            @Override public boolean deleteSurroundingTextInCodePoints(int before,int after){return deleteSurroundingText(before,after);}
            @Override public boolean performEditorAction(int action){finishComposingText();sink.key("enter");return true;}
            @Override public boolean sendKeyEvent(KeyEvent e){
                if(e.getAction()!=KeyEvent.ACTION_DOWN)return true;
                if(e.getKeyCode()==KeyEvent.KEYCODE_DEL){if(!composition.delete(1,0))sink.key("backspace");}
                else if(e.getKeyCode()==KeyEvent.KEYCODE_ENTER){finishComposingText();sink.key("enter");}
                else if(e.getKeyCode()==KeyEvent.KEYCODE_TAB){finishComposingText();sink.key("tab");}
                else {int c=e.getUnicodeChar();if(c!=0)sink.text(new String(Character.toChars(c)));}
                return true;
            }
            @Override public CharSequence getTextBeforeCursor(int n,int flags){return "";}
            @Override public CharSequence getTextAfterCursor(int n,int flags){return "";}
        };
    }
    void showKeyboard(){
        requestFocus();
        ((InputMethodManager)getContext().getSystemService(Context.INPUT_METHOD_SERVICE))
                .showSoftInput(this,InputMethodManager.SHOW_IMPLICIT);
    }
    void hideKeyboard(){
        composition.clear();
        ((InputMethodManager)getContext().getSystemService(Context.INPUT_METHOD_SERVICE))
                .hideSoftInputFromWindow(getWindowToken(),0);clearFocus();
    }
}
