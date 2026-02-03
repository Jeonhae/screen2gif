from clipboard_clean import copy_path_to_clipboard
from utils import timestamped_filename, ensure_dirs
import os

ensure_dirs()
# pick an existing gif in gif/ or create a dummy path
gif_dir = os.path.join(os.path.dirname(__file__), 'gif')
files = [f for f in os.listdir(gif_dir) if f.lower().endswith('.gif')]
if files:
    p = os.path.join(gif_dir, files[-1])
else:
    p = timestamped_filename('gif', 'gif')
    open(p, 'wb').write(b'GIF89a')
print('Testing copy file to clipboard:', p)
ok = copy_path_to_clipboard(p)
print('Result:', ok)
