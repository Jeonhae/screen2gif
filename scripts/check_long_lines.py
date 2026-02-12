from pathlib import Path

p = Path('main.py')
text = p.read_text(encoding='utf-8', errors='replace')
for i, l in enumerate(text.splitlines(), start=1):
    if len(l) > 88:
        print(i, len(l), l)
