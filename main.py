# main.py

import argparse
import asyncio
import os
import logging
import time
from tts.document_reader import DocumentReader
from tts.text_splitter import TextSplitter
from tts.tts_processor import TTSProcessor
from tts.audio_combiner import AudioCombiner
from tts.utils import setup_dirs, format_seconds

os.makedirs("logs", exist_ok=True)
LOG_FILE = "logs/tts_process.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)


async def main():
    # Cài đặt logging cơ bản
    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(
        description="📚 Convert DOCX/PDF to speech with Edge TTS"
    )
    parser.add_argument("file", help="Tên file trong thư mục input/")
    parser.add_argument(
        "--voice",
        default="vi-VN-HoaiMyNeural",
        help="Tên giọng TTS (mặc định: vi-VN-HoaiMyNeural)",
    )
    parser.add_argument("--speed", default="0%", help="Tốc độ nói, VD: -10% / +10%")
    parser.add_argument("--pitch", default="+0Hz", help="Tông giọng, VD: -20Hz / +20Hz")
    parser.add_argument(
        "--concurrent", type=int, default=6, help="Số chunk xử lý đồng thời"
    )

    args = parser.parse_args()

    # Tạo thư mục cần thiết
    input_dir, output_dir, temp_dir = setup_dirs()

    input_path = os.path.join(input_dir, args.file)
    output_file = os.path.splitext(args.file)[0] + ".mp3"
    output_path = os.path.join(output_dir, output_file)

    logger.info(f"📁 Input: {input_path}")
    logger.info(f"📁 Output: {output_path}")

    if not os.path.exists(input_path):
        logger.error(f"❌ File không tồn tại: {input_path}")
        return

    # Đọc file
    try:
        if args.file.lower().endswith(".docx"):
            text = DocumentReader.read_docx(input_path)
        elif args.file.lower().endswith(".pdf"):
            text = DocumentReader.read_pdf(input_path)
        else:
            logger.error("❌ Chỉ hỗ trợ DOCX hoặc PDF.")
            return
    except Exception as e:
        logger.error(f"❌ Lỗi đọc file: {e}")
        return

    if not text.strip():
        logger.error("❌ File rỗng.")
        return

    # Tách chunk
    chunks = TextSplitter.smart_split(text, max_length=2000)
    logger.info(f"📝 Tổng số chunk: {len(chunks)}")

    if chunks:
        logger.info(f"📄 Chunk 1: {chunks[0][:100]}...")

    # TTS processor
    tts = TTSProcessor(
        voice=args.voice, temp_dir=temp_dir, speed=args.speed, pitch=args.pitch
    )

    # Đo thử 3 chunk đầu để ước tính
    test_chunks = chunks[:12]
    t0 = time.time()
    await tts.process_batch(test_chunks, args.concurrent)
    t1 = time.time()
    avg_time_per_chunk = (t1 - t0) / len(test_chunks)
    estimated_total = avg_time_per_chunk * len(chunks) / args.concurrent

    logger.info(f"⏱️ Avg time per chunk: {format_seconds(avg_time_per_chunk)}")
    logger.info(f"⏳ Estimated TTS time: {format_seconds(estimated_total)}")

    # Xử lý batch
    logger.info("🎙️ Bắt đầu chuyển đổi TTS...")
    results = await tts.process_batch(chunks, max_concurrent=args.concurrent)

    # Lọc file thành công
    success_files = [path for _, path, ok in results if ok]
    fail_count = sum(1 for _, _, ok in results if not ok)

    logger.info(f"✅ Hoàn tất {len(success_files)}/{len(chunks)} chunks thành công")
    if fail_count:
        logger.warning(f"⚠️ Có {fail_count} chunks lỗi")

    if not success_files:
        logger.error("❌ Không có audio nào để ghép.")
        return

    # Ghép file
    combiner = AudioCombiner()
    combiner.combine(success_files, output_path)

    logger.info(f"🎉 File cuối cùng đã lưu: {output_path}")

    # Xoá file tạm
    for path in success_files:
        try:
            os.remove(path)
        except Exception:
            pass

    if os.path.exists(temp_dir) and not os.listdir(temp_dir):
        os.rmdir(temp_dir)

    logger.info("🧹 Đã xoá file tạm.")


if __name__ == "__main__":
    asyncio.run(main())
