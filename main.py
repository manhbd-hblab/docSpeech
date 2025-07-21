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
        # FIX: Bỏ dấu trừ để đọc từ trên xuống dưới
        blocks.sort(key=lambda block: (block[1], block[0]))  # Y trước, X sau
        for block in blocks:
            text += block[4] + " "
        text += "\n"
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

        # Kiểm tra file được tạo thành công
        if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
            return chunk_index, temp_path, True
        else:
            return chunk_index, temp_path, False

    except Exception as e:
        print(f"❌ Error processing chunk {chunk_index + 1}: {e}")
        return chunk_index, temp_path, False


async def process_chunks_batch(chunks, language, temp_dir, max_concurrent):
    """Xử lý nhiều chunk song song với semaphore để giới hạn concurrent"""
    semaphore = asyncio.Semaphore(max_concurrent)
    completed_chunks = []

    async def process_with_semaphore(chunk, index):
        async with semaphore:
            return await process_chunk(chunk, index, language, temp_dir)

    # Tạo tasks cho tất cả chunks
    tasks = [process_with_semaphore(chunk, i) for i, chunk in enumerate(chunks)]

    # Xử lý với progress tracking
    results = []
    completed = 0
    total = len(tasks)

    try:
        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)
            completed += 1

            chunk_index, temp_path, success = result
            status = "✅" if success else "❌"
            print(
                f"{status} Chunk {chunk_index + 1}/{total} {'completed' if success else 'failed'} ({completed}/{total})"
            )

            if success:
                completed_chunks.append((chunk_index, temp_path))

    except KeyboardInterrupt:
        print(f"\n⛔ Interrupted! Completed {len(completed_chunks)}/{total} chunks.")
        # Vẫn trả về kết quả đã hoàn thành
        pass

    # Sắp xếp results theo thứ tự chunk index
    results.sort(key=lambda x: x[0])
    completed_chunks.sort(key=lambda x: x[0])

    return results, completed_chunks


def combine_audio_files(completed_chunks, output_path):
    """Kết hợp các file audio theo đúng thứ tự"""
    if not completed_chunks:
        print("❌ No completed chunks to combine")
        return False

    print(f"🔗 Combining {len(completed_chunks)} audio files in correct order...")
    start_time = time.time()

    try:
        # Sắp xếp lại theo chunk index để đảm bảo thứ tự
        completed_chunks.sort(key=lambda x: x[0])

        # Lấy danh sách file paths theo thứ tự
        temp_files = [temp_path for _, temp_path in completed_chunks]

        def load_audio(path):
            try:
                if os.path.exists(path) and os.path.getsize(path) > 0:
                    return AudioSegment.from_file(path, format="mp3")
                else:
                    print(f"⚠️ Invalid file: {os.path.basename(path)}")
                    return None
            except Exception as e:
                print(f"⚠️ Error loading {os.path.basename(path)}: {e}")
                return None

        # Load audio files với threading
        print("📂 Loading audio segments...")
        with ThreadPoolExecutor(max_workers=4) as executor:
            audio_segments = list(executor.map(load_audio, temp_files))

        # Lọc và combine theo thứ tự
        valid_segments = []
        for i, (segment, (chunk_idx, path)) in enumerate(
            zip(audio_segments, completed_chunks)
        ):
            if segment is not None:
                valid_segments.append(segment)
                print(f"  ➕ Chunk {chunk_idx + 1}: {os.path.basename(path)}")
            else:
                print(f"  ❌ Skipped chunk {chunk_idx + 1}: {os.path.basename(path)}")

        if not valid_segments:
            print("❌ No valid audio segments to combine")
            return False

        # Kết hợp audio theo thứ tự
        print("🎵 Combining audio segments...")
        final_audio = AudioSegment.silent(duration=0)
        for segment in valid_segments:
            final_audio += segment

        # Export với tối ưu
        print("💾 Exporting final audio...")
        final_audio.export(
            output_path, format="mp3", bitrate="128k", parameters=["-threads", "4"]
        )

        combine_time = time.time() - start_time
        duration = len(final_audio) / 1000  # seconds
        print(f"✅ Audio combined in {combine_time:.2f} seconds")
        print(f"🎵 Final audio duration: {duration:.1f} seconds")
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

    # In ra vài chunk đầu để kiểm tra thứ tự
    print(f"📄 First chunk preview: {chunks[0][:100]}..." if chunks else "No chunks")

    # Tạo thư mục temp
    temp_dir = os.path.join(os.path.dirname(__file__), "temp_chunks")
    os.makedirs(temp_dir, exist_ok=True)

    completed_chunks = []
    all_temp_files = []

    try:
        print("🎵 Starting TTS conversion...")
        tts_start = time.time()

        # Xử lý chunks song song
        results, completed_chunks = await process_chunks_batch(
            chunks, args.language, temp_dir, args.concurrent
        )

        tts_time = time.time() - tts_start
        print(f"🎵 TTS conversion completed in {tts_time:.2f} seconds")

        # Thu thập tất cả file paths để cleanup
        all_temp_files = [temp_path for _, temp_path, _ in results]
        failed_count = sum(1 for _, _, success in results if not success)

        if failed_count > 0:
            print(f"⚠️ {failed_count} chunks failed to process")

        print(
            f"📊 Successfully processed: {len(completed_chunks)}/{len(chunks)} chunks"
        )

        if completed_chunks:
            # Kết hợp audio files theo đúng thứ tự
            success = combine_audio_files(completed_chunks, args.output_path)

            if success:
                total_time = time.time() - start_time
                print(f"✅ Total conversion time: {total_time:.2f} seconds")
                print(f"📁 Output saved to {args.output_path}")
            else:
                print("❌ Failed to create final audio file")
        else:
            print("❌ No audio chunks to combine.")

    except KeyboardInterrupt:
        print("\n⛔ Stopped by user.")
        # Vẫn cố gắng combine các chunk đã hoàn thành
        if completed_chunks:
            print("🔗 Creating partial audio from completed chunks...")
            combine_audio_files(completed_chunks, args.output_path)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
    finally:
        # Cleanup - xóa tất cả temp files
        print("🧹 Cleaning up temporary files...")
        cleanup_start = time.time()
        cleaned_count = 0

        for path in all_temp_files:
            try:
                if os.path.exists(path):
                    os.remove(path)
                    cleaned_count += 1
            except Exception:
                pass

        try:
            os.rmdir(temp_dir)
        except OSError:
            pass

        cleanup_time = time.time() - cleanup_start
        print(
            f"🗑️ Cleanup completed in {cleanup_time:.2f} seconds ({cleaned_count} files removed)"
        )


if __name__ == "__main__":
    asyncio.run(main())
