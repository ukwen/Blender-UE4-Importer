"""Send actual X11 Escape and Return to the source recovery confirmation.
Dedicated test display only; requires python-xlib and Pillow.
"""
import sys,time
from pathlib import Path
from Xlib import X,XK,display
from Xlib.ext import xtest
from PIL import Image
out=Path(sys.argv[1]);d=display.Display();root=d.screen().root

def wait(name):
    end=time.monotonic()+90
    while time.monotonic()<end:
        if (out/'error').exists():raise RuntimeError((out/'error').read_text())
        if (out/name).exists():return
        time.sleep(.05)
    raise TimeoutError(name)
def send(key,marker):
    windows=[w for w in root.query_tree().children if w.get_wm_name() and 'Blender' in str(w.get_wm_name())];assert windows
    windows[-1].set_input_focus(X.RevertToParent,X.CurrentTime);d.sync()
    code=d.keysym_to_keycode(XK.string_to_keysym(key));xtest.fake_input(d,X.KeyPress,code);xtest.fake_input(d,X.KeyRelease,code);d.sync();(out/marker).write_text(key)
def capture(name):
    geom=root.get_geometry();raw=root.get_image(0,0,geom.width,geom.height,X.ZPixmap,0xffffffff)
    Image.frombytes('RGB',(geom.width,geom.height),raw.data,'raw','BGRX').save(out/name)
wait('first_prompt');time.sleep(.5);capture('confirmation.png');send('Escape','cancel_sent')
wait('second_prompt');time.sleep(.5);send('Return','confirm_sent');wait('done');print((out/'result.json').read_text());(out/'quit').write_text('yes')
