# __init__.py
from .document_reader import DocumentReader
from .text_splitter import TextSplitter
from .tts_processor import TTSProcessor
from .audio_combiner import AudioCombiner
from .utils import setup_dirs

__all__ = [
    "DocumentReader",
    "TextSplitter",
    "TTSProcessor",
    "AudioCombiner",
    "setup_dirs",
]
