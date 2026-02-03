import glob, os
from screen2gif import clipboard

files = glob.glob('screen2gif/gif/*.gif')
if not files:
    print('no gif found')
    raise SystemExit(1)
f = max(files, key=os.path.getmtime)
print('testing with', f)
ok = clipboard.copy_file_to_clipboard_cfhdrop(f)
print('result:', ok)
