import clipboard_clean
print('copy_path_to_clipboard:', clipboard_clean.copy_path_to_clipboard)
print('module:', clipboard_clean.copy_path_to_clipboard.__module__)
try:
    from clipboard_win import copy_file_to_clipboard_cfhdrop_ctypes
    print('clipboard_win function:', copy_file_to_clipboard_cfhdrop_ctypes)
except Exception as e:
    print('import error:', e)
