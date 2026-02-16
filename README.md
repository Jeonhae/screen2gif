# screen2gif

A small utility to capture screen frames and save them as an animated GIF.

## Features

- Capture screen recordings and convert to GIF
- Support for various output formats
- Cross-platform (Windows, macOS, Linux)
- Uses Git LFS for large files (e.g., ffmpeg.exe, sample GIFs)

## Requirements

- Python 3.8+
- Dependencies listed in `requirements.txt`:
  - Pillow
  - imageio
  - imageio-ffmpeg
  - pyautogui
  - numpy
  - PyQt5
  - mss
  - opencv-python
  - pyperclip

## Installation

1. Clone the repository:

```bash
git clone https://github.com/Jeonhae/screen2gif.git
cd screen2gif
```

2. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
# On Windows:
.\.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

Run the main script to capture and convert:

```bash
python screen2gif.py --duration 5 --fps 2 --output out.gif
```

For more options, see:

```bash
python screen2gif.py --help
```

## Notes

- On Windows, you may need to grant screen-capture permissions.
- `pyautogui` may require additional OS-level dependencies; consult its documentation if screenshots fail.
- Large files (e.g., ffmpeg.exe, sample GIFs) are stored using Git LFS. Ensure Git LFS is installed to clone/pull these files.

## Development

- Run tests: Execute test scripts in `tests/` directory, e.g., `python test_import.py`
- Build: See scripts in `pkg/` directory
- Code style: Uses flake8 (see `.flake8`)

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.
