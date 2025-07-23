# tts_processor.py
import asyncio
import os
import edge_tts
import logging

logger = logging.getLogger(__name__)


class TTSProcessor:
    def __init__(self, voice, temp_dir, speed="0%", pitch="+0Hz"):
        self.voice = voice
        self.temp_dir = temp_dir
        self.speed = speed
        self.pitch = pitch

    async def process_chunk(self, chunk, index):
        temp_path = os.path.join(self.temp_dir, f"chunk_{index:04d}.mp3")
        chunk = chunk.strip()
        if not chunk:
            logger.warning(f"Chunk {index} is empty, skipping")
            return index, "", False

        try:
            if self.speed != "0%" or self.pitch != "+0Hz":
                chunk = (
                    chunk.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                ssml = f'<speak version="1.0" xml:lang="vi-VN"><prosody rate="{self.speed}" pitch="{self.pitch}">{chunk}</prosody></speak>'
                communicate = edge_tts.Communicate(ssml, self.voice)
            else:
                communicate = edge_tts.Communicate(chunk, self.voice)

            await communicate.save(temp_path)
            await asyncio.sleep(0.2)

            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 100:
                logger.info(f"✅ Chunk {index + 1} done: {temp_path}")
                return index, temp_path, True
            else:
                logger.error(f"❌ Chunk {index + 1} failed, file too small or missing")
                return index, "", False

        except Exception as e:
            logger.error(f"❌ Exception in chunk {index + 1}: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return index, "", False

    async def process_batch(self, chunks, max_concurrent):
        semaphore = asyncio.Semaphore(max_concurrent)

        async def worker(chunk, idx):
            async with semaphore:
                for attempt in range(3):
                    logger.info(f"🚀 Processing chunk {idx + 1}, attempt {attempt + 1}")
                    result = await self.process_chunk(chunk, idx)
                    if result[2]:
                        return result
                    logger.warning(
                        f"⚠️ Chunk {idx + 1} failed attempt {attempt + 1}, retrying..."
                    )
                    await asyncio.sleep(2 * (attempt + 1))
                logger.error(f"❌ Chunk {idx + 1} failed after 3 attempts")
                return result

        tasks = [worker(chunk, idx) for idx, chunk in enumerate(chunks)]
        results = await asyncio.gather(*tasks)
        return results
