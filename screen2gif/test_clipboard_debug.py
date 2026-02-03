import glob, os
import importlib
import screen2gif.clipboard as cb
importlib.reload(cb)
files = glob.glob('screen2gif/gif/*.gif')
if not files:
    print('no gif found')
    raise SystemExit(1)
f = max(files, key=os.path.getmtime)
print('testing with', f)
ok = cb.copy_gif_to_clipboard_pywin32(f)
print('pywin32 copy returned', ok)
ok2 = cb.copy_gif_to_clipboard(f)
print('ctypes copy returned', ok2)
ok3 = cb.copy_file_to_clipboard_cfhdrop(f)
print('cfhdrop copy returned', ok3)
print('log file: screen2gif/logs/clipboard_debug.log')
