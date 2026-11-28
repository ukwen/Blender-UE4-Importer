"""External X11 clipboard and keyboard driver; requires python-xlib and Xvfb.
Run against a dedicated display, never the user's desktop. No test assets modified.
"""
import sys,time
from pathlib import Path
from Xlib import X, XK, display
from Xlib.ext import xtest
out=Path(sys.argv[1]);d=display.Display();root=d.screen().root

def wait(name,timeout=60):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if (out/'error').exists():raise RuntimeError((out/'error').read_text())
        if (out/name).exists():return
        time.sleep(.01)
    raise TimeoutError(name)

def screenshot(name):
    from PIL import Image
    geom=root.get_geometry();raw=root.get_image(0,0,geom.width,geom.height,X.ZPixmap,0xffffffff)
    Image.frombytes('RGB',(geom.width,geom.height),raw.data,'raw','BGRX').save(out/name)

wait('ready')
# For the dedicated 1440x1000 default Layout window: select the visible Unreal sidebar tab.
# The isolated user preferences disable the first-run splash.
xtest.fake_input(d,X.MotionNotify,x=1176,y=250);xtest.fake_input(d,X.ButtonPress,1);xtest.fake_input(d,X.ButtonRelease,1);d.sync();time.sleep(.6)
screenshot('sidebar.png')
w=root.create_window(0,0,1,1,0,X.CopyFromParent,event_mask=X.PropertyChangeMask)
sel=d.intern_atom('CLIPBOARD');target=d.intern_atom('UTF8_STRING');prop=d.intern_atom('UE_DESKTOP_CLIPBOARD_TEST')
w.convert_selection(sel,target,prop,X.CurrentTime);d.flush();end=time.monotonic()+10;actual=None
while time.monotonic()<end:
    if d.pending_events():
        e=d.next_event()
        if e.type==X.SelectionNotify:
            if e.property==X.NONE:raise RuntimeError('Clipboard rejected')
            p=w.get_full_property(prop,X.AnyPropertyType);actual=p.value if isinstance(p.value,str) else bytes(p.value).decode('utf-8');break
    time.sleep(.01)
assert actual==(out/'clipboard_expected').read_text(),(len(actual or ''),len((out/'clipboard_expected').read_text()))
(out/'clipboard_checked').write_text('exact')
wait('first_staged')
# Select Blender's actual top-level window and send Escape using XTEST.
windows=[w for w in root.query_tree().children if w.get_wm_name() and 'Blender' in str(w.get_wm_name())]
assert windows,[(w.id,w.get_wm_name()) for w in root.query_tree().children]
win=windows[-1];win.set_input_focus(X.RevertToParent,X.CurrentTime);d.sync();key=d.keysym_to_keycode(XK.string_to_keysym('Escape'));xtest.fake_input(d,X.KeyPress,key);xtest.fake_input(d,X.KeyRelease,key);d.sync();(out/'escape_sent').write_text('XTEST Escape')
wait('expanded_ready');time.sleep(.3);screenshot('advanced.png');(out/'expanded_checked').write_text('captured')
wait('done');time.sleep(.3);screenshot('completed.png');(out/'quit').write_text('yes');print((out/'result.json').read_text())
