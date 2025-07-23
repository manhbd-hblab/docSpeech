# utils.py

import os


def setup_dirs():
    base = os.path.dirname(__file__)
    input_dir = os.path.join(base, "../input")
    output_dir = os.path.join(base, "../output")
    temp_dir = os.path.join(base, "../temp_chunks")
    for d in [input_dir, output_dir, temp_dir]:
        os.makedirs(d, exist_ok=True)
    return input_dir, output_dir, temp_dir


def format_seconds(seconds):
    hours = int(seconds) // 3600
    minutes = (int(seconds) % 3600) // 60
    secs = int(seconds) % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
