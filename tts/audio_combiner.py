# audio_combiner.py
from pydub import AudioSegment
from concurrent.futures import ThreadPoolExecutor

class AudioCombiner:
    def __init__(self, pause_ms=300, fade_ms=50):
        self.pause = AudioSegment.silent(duration=pause_ms)
        self.fade = fade_ms

    def combine(self, chunks, output_path):
        def load(path):
            audio = AudioSegment.from_file(path, format="mp3").normalize()
            if len(audio) > self.fade * 2:
                audio = audio.fade_in(self.fade).fade_out(self.fade)
            return audio

        with ThreadPoolExecutor(max_workers=4) as ex:
            segments = list(ex.map(load, chunks))

        final = segments[0]
        for seg in segments[1:]:
            final += self.pause + seg

        final = final.normalize()
        final.export(output_path, format="mp3", bitrate="192k")
