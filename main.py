import argparse
import re
import fitz  # PyMuPDF
from docx import Document
import asyncio
import edge_tts
import os
from pydub import AudioSegment
from concurrent.futures import ThreadPoolExecutor
import time

CHUNK_SIZE = 3000  # số ký tự tối đa mỗi chunk
MAX_CONCURRENT = 8  # số chunk xử lý song song

def read_docx(file_path):
    doc = Document(file_path)
    return " ".join([paragraph.text for paragraph in doc.paragraphs])


def read_pdf(file_path):
    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        blocks = page.get_text("blocks")
        blocks.sort(key=lambda block: -block[1])
        for block in blocks:
            text += block[4] + "\n"
    return text


def split_text(text, max_length=CHUNK_SIZE):
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 < max_length:
            current += sentence + " "
        else:
            chunks.append(current.strip())
            current = sentence + " "
    if current:
        chunks.append(current.strip())
    return chunks


def create_arg_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("file_path", help="Path to the document file")
    parser.add_argument("output_path", help="Path to the output audio file")
    parser.add_argument(
        "--language", default="vi-VN-HoaiMyNeural", help="Voice for TTS conversion"
    )
    parser.add_argument(
        "--concurrent",
        type=int,
        default=MAX_CONCURRENT,
        help="Number of concurrent chunks to process (default: 8)",
    )
    return parser


async def process_chunk(chunk, chunk_index, language, temp_dir):
    """Xử lý một chunk riêng biệt"""
    temp_path = os.path.join(temp_dir, f"chunk_{chunk_index:04d}.mp3")

    try:
        communicate = edge_tts.Communicate(chunk, language)
        await communicate.save(temp_path)
        return chunk_index, temp_path, True
    except Exception as e:
        print(f"❌ Error processing chunk {chunk_index}: {e}")
        return chunk_index, temp_path, False


async def process_chunks_batch(chunks, language, temp_dir, max_concurrent):
    """Xử lý nhiều chunk song song với semaphore để giới hạn concurrent"""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_with_semaphore(chunk, index):
        async with semaphore:
            return await process_chunk(chunk, index, language, temp_dir)

    # Tạo tasks cho tất cả chunks
    tasks = [process_with_semaphore(chunk, i) for i, chunk in enumerate(chunks)]

    # Xử lý với progress tracking
    results = []
    completed = 0
    total = len(tasks)

    for coro in asyncio.as_completed(tasks):
        result = await coro
        results.append(result)
        completed += 1

        chunk_index, temp_path, success = result
        status = "✅" if success else "❌"
        print(
            f"{status} Chunk {chunk_index + 1}/{total} {'completed' if success else 'failed'} ({completed}/{total})"
        )

    # Sắp xếp results theo thứ tự chunk
    results.sort(key=lambda x: x[0])
    return results


def combine_audio_files(temp_files, output_path):
    """Kết hợp các file audio với tối ưu"""
    print("🔗 Combining audio files...")
    start_time = time.time()

    try:
        # Sử dụng threading để load audio files nhanh hơn
        def load_audio(path):
            try:
                return AudioSegment.from_file(path, format="mp3")
            except Exception as e:
                print(f"⚠️ Skipping broken chunk: {path} - {e}")
                return None

        with ThreadPoolExecutor(max_workers=4) as executor:
            audio_segments = list(executor.map(load_audio, temp_files))

        # Lọc bỏ các segment None và kết hợp
        valid_segments = [seg for seg in audio_segments if seg is not None]

        if not valid_segments:
            print("❌ No valid audio segments to combine")
            return False

        # Kết hợp audio
        final_audio = AudioSegment.silent(duration=0)
        for segment in valid_segments:
            final_audio += segment

        # Export với tối ưu
        final_audio.export(
            output_path,
            format="mp3",
            bitrate="128k",  # Tối ưu chất lượng/tốc độ
            parameters=["-threads", "4"],  # Sử dụng nhiều thread cho export
        )

        combine_time = time.time() - start_time
        print(f"✅ Audio combined in {combine_time:.2f} seconds")
        return True

    except Exception as e:
        print(f"❌ Error combining audio: {e}")
        return False


async def main():
    start_time = time.time()
    parser = create_arg_parser()
    args = parser.parse_args()

    print("📖 Reading document...")
    if args.file_path.endswith(".docx"):
        text = read_docx(args.file_path)
    elif args.file_path.endswith(".pdf"):
        text = read_pdf(args.file_path)
    else:
        print("❌ Unsupported file format")
        return

    if not text.strip():
        print("❌ No text found in the document.")
        return

    chunks = split_text(text)
    print(f"📝 Split into {len(chunks)} chunks")
    print(f"⚙️ Using {args.concurrent} concurrent processes")

    # Tạo thư mục temp
    temp_dir = os.path.join(os.path.dirname(__file__), "temp_chunks")
    os.makedirs(temp_dir, exist_ok=True)

    temp_files = []

    try:
        print("🎵 Starting TTS conversion...")
        tts_start = time.time()

        # Xử lý chunks song song
        results = await process_chunks_batch(
            chunks, args.language, temp_dir, args.concurrent
        )

        tts_time = time.time() - tts_start
        print(f"🎵 TTS conversion completed in {tts_time:.2f} seconds")

        # Thu thập các file thành công
        temp_files = [temp_path for _, temp_path, success in results if success]
        failed_count = sum(1 for _, _, success in results if not success)

        if failed_count > 0:
            print(f"⚠️ {failed_count} chunks failed to process")

        if temp_files:
            # Kết hợp audio files
            success = combine_audio_files(temp_files, args.output_path)

            if success:
                total_time = time.time() - start_time
                print(f"✅ Total conversion time: {total_time:.2f} seconds")
                print(f"📁 Output saved to {args.output_path}")

        else:
            print("❌ No audio chunks to combine.")

    except KeyboardInterrupt:
        print("\n⛔ Stopped by user.")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
    finally:
        # Cleanup
        cleanup_start = time.time()
        for path in temp_files:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        try:
            os.rmdir(temp_dir)
        except OSError:
            pass
        cleanup_time = time.time() - cleanup_start
        print(f"🧹 Cleanup completed in {cleanup_time:.2f} seconds")


if __name__ == "__main__":
    asyncio.run(main())
