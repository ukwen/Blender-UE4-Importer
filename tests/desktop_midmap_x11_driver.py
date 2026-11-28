"""Actual keyboard cancellation on a dedicated X11 display only."""
import sys,time
from pathlib import Path
from Xlib import X,XK,display
from Xlib.ext import xtest
out=Path(sys.argv[1]);d=display.Display();root=d.screen().root

def wait(name,timeout=180):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if (out/'error').exists():raise RuntimeError((out/'error').read_text())
        if (out/name).exists():return
        time.sleep(.005)
    raise TimeoutError(name)
wait('partial');windows=[w for w in root.query_tree().children if w.get_wm_name() and 'Blender' in str(w.get_wm_name())];assert windows
win=windows[-1];win.set_input_focus(X.RevertToParent,X.CurrentTime);d.sync();key=d.keysym_to_keycode(XK.string_to_keysym('Escape'));xtest.fake_input(d,X.KeyPress,key);xtest.fake_input(d,X.KeyRelease,key);d.sync();(out/'escape_sent').write_text('XTEST Escape')
wait('done');(out/'quit').write_text('yes');print((out/'result.json').read_text())
