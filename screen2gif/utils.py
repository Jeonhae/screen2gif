import os
from datetime import datetime


def ensure_dirs(base_dir=None):
    base = base_dir or os.path.dirname(__file__)
    for d in ('video', 'gif', 'logs'):
        p = os.path.join(base, d)
        os.makedirs(p, exist_ok=True)


def timestamped_filename(folder: str, ext: str) -> str:
    base = os.path.dirname(__file__)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    return os.path.join(base, folder, f'{ts}.{ext}')
