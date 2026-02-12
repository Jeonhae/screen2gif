# screenshot2gif

A small utility to capture screen frames and save them as an animated GIF.

Requirements
- Python 3.8+
- See `requirements.txt`

Quickstart

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
```

2. Run the example capture:

```bash
python screenshot2gif.py --duration 5 --fps 2 --output out.gif
```

Notes
- On Windows you may need to grant screen-capture permissions.
- `pyautogui` may require additional OS-level dependencies; consult its docs if screenshots fail.
