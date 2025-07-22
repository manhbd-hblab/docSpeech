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

CHUNK_SIZE = 2000  # Giảm kích thước chunk để giọng đọc tự nhiên hơn
MAX_CONCURRENT = 6  # Giảm concurrent để ổn định hơn
PAUSE_BETWEEN_CHUNKS = 300  # Thêm khoảng lặng 300ms giữa các chunk
FADE_DURATION = 50  # Fade in/out 50ms cho mượt mà hơn


def setup_directories():
    """Tạo các thư mục cần thiết"""
    base_dir = os.path.dirname(__file__)
    input_dir = os.path.join(base_dir, "input")
    output_dir = os.path.join(base_dir, "output")
    temp_dir = os.path.join(base_dir, "temp_chunks")

    for directory in [input_dir, output_dir, temp_dir]:
        os.makedirs(directory, exist_ok=True)

    return input_dir, output_dir, temp_dir


def read_docx(file_path):
    doc = Document(file_path)
    return " ".join([paragraph.text for paragraph in doc.paragraphs])


def read_pdf(file_path):
    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        blocks = page.get_text("blocks")
        blocks.sort(key=lambda block: (block[1], block[0]))  # Y trước, X sau
        for block in blocks:
            text += block[4] + " "
        text += "\n"
    return text


def smart_split_text(text, max_length=CHUNK_SIZE):
    """Chia text thông minh hơn để tránh cắt giữa câu"""
    # Làm sạch text trước
    text = re.sub(r"\s+", " ", text.strip())

    # Chia theo câu trước
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks = []
    current_chunk = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # Nếu câu quá dài, chia nhỏ hơn theo dấu phay, chấm phẩy
        if len(sentence) > max_length:
            sub_parts = re.split(r"(?<=[,;:])\s+", sentence)
            for part in sub_parts:
                if len(current_chunk) + len(part) + 2 <= max_length:
                    current_chunk += part + " "
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = part + " "
        else:
            # Kiểm tra xem có vừa chunk hiện tại không
            if len(current_chunk) + len(sentence) + 2 <= max_length:
                current_chunk += sentence + " "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + " "

    # Thêm chunk cuối
    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks


def create_arg_parser():
    parser = argparse.ArgumentParser(
        description="Convert documents to speech with improved quality"
    )
    parser.add_argument("file_name", help="Name of the document file in input folder")
    parser.add_argument(
        "--language",
        default="vi-VN-HoaiMyNeural",
        help="Voice for TTS conversion (default: vi-VN-HoaiMyNeural)",
    )
    parser.add_argument(
        "--concurrent",
        type=int,
        default=MAX_CONCURRENT,
        help=f"Number of concurrent chunks to process (default: {MAX_CONCURRENT})",
    )
    parser.add_argument(
        "--speed", default="0%", help="Speech speed (-50% to +50%, default: 0%)"
    )
    parser.add_argument(
        "--pitch", default="+0Hz", help="Speech pitch (-50Hz to +50Hz, default: +0Hz)"
    )
    return parser


async def process_chunk_with_prosody(
    chunk, chunk_index, language, temp_dir, speed="0%", pitch="+0Hz"
):
    """Xử lý chunk với prosody để giọng đọc tự nhiên hơn"""
    temp_path = os.path.join(temp_dir, f"chunk_{chunk_index:04d}.mp3")

    try:
        # Thêm SSML để kiểm soát prosody
        ssml_text = f"""
        <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="vi-VN">
            <voice name="{language}">
                <prosody rate="{speed}" pitch="{pitch}">
                    {chunk}
                </prosody>
            </voice>
        </speak>
        """

        communicate = edge_tts.Communicate(ssml_text, language)
        await communicate.save(temp_path)

        # Thêm delay nhỏ để tránh rate limit
        await asyncio.sleep(0.1)

        if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
            return chunk_index, temp_path, True
        else:
            return chunk_index, temp_path, False

    except Exception as e:
        print(f"❌ Error processing chunk {chunk_index + 1}: {e}")
        return chunk_index, temp_path, False


async def process_chunks_batch(
    chunks, language, temp_dir, max_concurrent, speed="0%", pitch="+0Hz"
):
    """Xử lý batch với retry logic"""
    semaphore = asyncio.Semaphore(max_concurrent)
    completed_chunks = []

    async def process_with_semaphore_and_retry(chunk, index, max_retries=2):
        async with semaphore:
            for attempt in range(max_retries + 1):
                try:
                    result = await process_chunk_with_prosody(
                        chunk, index, language, temp_dir, speed, pitch
                    )
                    if result[2]:  # success
                        return result
                    elif attempt < max_retries:
                        await asyncio.sleep(1 * (attempt + 1))  # exponential backoff
                except Exception as e:
                    if attempt < max_retries:
                        print(f"⚠️ Retry {attempt + 1} for chunk {index + 1}: {e}")
                        await asyncio.sleep(1 * (attempt + 1))
                    else:
                        return index, "", False
            return index, "", False

    tasks = [
        process_with_semaphore_and_retry(chunk, i) for i, chunk in enumerate(chunks)
    ]

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

    results.sort(key=lambda x: x[0])
    completed_chunks.sort(key=lambda x: x[0])

    return results, completed_chunks


def combine_audio_with_smooth_transitions(completed_chunks, output_path):
    """Kết hợp audio với transitions mượt mà hơn"""
    if not completed_chunks:
        print("❌ No completed chunks to combine")
        return False

    print(
        f"🔗 Combining {len(completed_chunks)} audio files with smooth transitions..."
    )
    start_time = time.time()

    try:
        completed_chunks.sort(key=lambda x: x[0])
        temp_files = [temp_path for _, temp_path in completed_chunks]

        def load_and_process_audio(path):
            try:
                if os.path.exists(path) and os.path.getsize(path) > 0:
                    audio = AudioSegment.from_file(path, format="mp3")
                    # Normalize volume
                    audio = audio.normalize()
                    # Thêm fade in/out nhẹ
                    if len(audio) > FADE_DURATION * 2:
                        audio = audio.fade_in(FADE_DURATION).fade_out(FADE_DURATION)
                    return audio
                else:
                    return None
            except Exception as e:
                print(f"⚠️ Error loading {os.path.basename(path)}: {e}")
                return None

        # Load audio segments
        print("📂 Loading and processing audio segments...")
        with ThreadPoolExecutor(max_workers=4) as executor:
            audio_segments = list(executor.map(load_and_process_audio, temp_files))

        # Combine với pause giữa các chunk
        valid_segments = [seg for seg in audio_segments if seg is not None]

        if not valid_segments:
            print("❌ No valid audio segments to combine")
            return False

        print("🎵 Combining with smooth transitions...")
        final_audio = valid_segments[0]

        # Thêm pause nhỏ giữa các chunk để tự nhiên hơn
        pause = AudioSegment.silent(duration=PAUSE_BETWEEN_CHUNKS)

        for segment in valid_segments[1:]:
            final_audio += pause + segment

        # Normalize final audio
        final_audio = final_audio.normalize()

        # Export với chất lượng cao hơn
        print("💾 Exporting final audio...")
        final_audio.export(
            output_path,
            format="mp3",
            bitrate="192k",  # Tăng bitrate
            parameters=["-q:a", "0", "-threads", "4"],  # Chất lượng cao nhất
        )

        combine_time = time.time() - start_time
        duration = len(final_audio) / 1000
        file_size = os.path.getsize(output_path) / (1024 * 1024)  # MB

        print(f"✅ Audio combined in {combine_time:.2f} seconds")
        print(f"🎵 Final audio duration: {duration:.1f} seconds")
        print(f"📦 File size: {file_size:.1f} MB")
        return True

    except Exception as e:
        print(f"❌ Error combining audio: {e}")
        return False


async def main():
    start_time = time.time()
    parser = create_arg_parser()
    args = parser.parse_args()

    # Setup directories
    input_dir, output_dir, temp_dir = setup_directories()

    # Construct full paths
    input_path = os.path.join(input_dir, args.file_name)
    output_filename = os.path.splitext(args.file_name)[0] + ".mp3"
    output_path = os.path.join(output_dir, output_filename)

    print(f"📁 Input folder: {input_dir}")
    print(f"📁 Output folder: {output_dir}")
    print(f"📖 Reading document: {args.file_name}")

    # Check if input file exists
    if not os.path.exists(input_path):
        print(f"❌ File not found: {input_path}")
        print("💡 Please place your document in the 'input' folder")
        return

    # Read document
    try:
        if args.file_name.lower().endswith(".docx"):
            text = read_docx(input_path)
        elif args.file_name.lower().endswith(".pdf"):
            text = read_pdf(input_path)
        else:
            print("❌ Unsupported file format. Use .docx or .pdf")
            return
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return

    if not text.strip():
        print("❌ No text found in the document.")
        return

    # Smart text splitting
    chunks = smart_split_text(text, CHUNK_SIZE)
    print(f"📝 Split into {len(chunks)} chunks (improved splitting)")
    print(f"⚙️ Using {args.concurrent} concurrent processes")
    print(f"🎵 Voice: {args.language}, Speed: {args.speed}, Pitch: {args.pitch}")

    # Preview
    if chunks:
        print(f"📄 First chunk preview: {chunks[0][:100]}...")

    completed_chunks = []
    all_temp_files = []

    try:
        print("🎵 Starting enhanced TTS conversion...")
        tts_start = time.time()

        results, completed_chunks = await process_chunks_batch(
            chunks, args.language, temp_dir, args.concurrent, args.speed, args.pitch
        )

        tts_time = time.time() - tts_start
        print(f"🎵 TTS conversion completed in {tts_time:.2f} seconds")

        all_temp_files = [temp_path for _, temp_path, _ in results]
        failed_count = sum(1 for _, _, success in results if not success)

        if failed_count > 0:
            print(f"⚠️ {failed_count} chunks failed to process")

        print(
            f"📊 Successfully processed: {len(completed_chunks)}/{len(chunks)} chunks"
        )

        if completed_chunks:
            success = combine_audio_with_smooth_transitions(
                completed_chunks, output_path
            )

            if success:
                total_time = time.time() - start_time
                print(f"✅ Total conversion time: {total_time:.2f} seconds")
                print(f"📁 Output saved to: {output_path}")
            else:
                print("❌ Failed to create final audio file")
        else:
            print("❌ No audio chunks to combine.")

    except KeyboardInterrupt:
        print("\n⛔ Stopped by user.")
        if completed_chunks:
            print("🔗 Creating partial audio from completed chunks...")
            combine_audio_with_smooth_transitions(completed_chunks, output_path)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
    finally:
        # Cleanup
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
            if os.path.exists(temp_dir) and len(os.listdir(temp_dir)) == 0:
                os.rmdir(temp_dir)
        except OSError:
            pass

        cleanup_time = time.time() - cleanup_start
        print(
            f"🗑️ Cleanup completed in {cleanup_time:.2f} seconds ({cleaned_count} files removed)"
        )


if __name__ == "__main__":
    asyncio.run(main())
