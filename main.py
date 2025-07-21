import argparse
import re
import fitz  # PyMuPDF
from docx import Document
import asyncio
import edge_tts
import os
from pydub import AudioSegment

CHUNK_SIZE = 3000  # số ký tự tối đa mỗi chunk


def read_docx(file_path):
    doc = Document(file_path)
    return " ".join([paragraph.text for paragraph in doc.paragraphs])


def read_pdf(file_path):
    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        blocks = page.get_text("blocks")
        # Sắp xếp theo tọa độ Y từ trên xuống dưới (ascending order)
        blocks.sort(key=lambda block: block[1])  # Bỏ dấu trừ
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
    return parser


async def main():
    parser = create_arg_parser()
    args = parser.parse_args()

    if args.file_path.endswith(".docx"):
        text = read_docx(args.file_path)
    elif args.file_path.endswith(".pdf"):
        text = read_pdf(args.file_path)
    else:
        print("Unsupported file format")
        return

    if not text.strip():
        print("No text found in the document.")
        return

    chunks = split_text(text)
    print(f"Total chunks: {len(chunks)}")

    # Tạo thư mục lưu file tạm
    temp_dir = os.path.join(os.path.dirname(__file__), "temp_chunks")
    os.makedirs(temp_dir, exist_ok=True)

    temp_files = []

    try:
        for i, chunk in enumerate(chunks):
            print(f"[{i + 1}/{len(chunks)}] Processing chunk...")
            temp_path = os.path.join(temp_dir, f"chunk_{i}.mp3")
            temp_files.append(temp_path)

            communicate = edge_tts.Communicate(chunk, args.language)
            await communicate.save(temp_path)

            print(f"✅ Chunk {i + 1} saved: {temp_path}")

    except KeyboardInterrupt:
        print("\n⛔ Stopped by user. Combining finished parts...")
    except Exception as e:
        print(f"\n❌ Error occurred: {e}\nCombining finished parts...")
    finally:
        if temp_files:
            final_audio = AudioSegment.silent(duration=0)
            for path in temp_files:
                try:
                    audio = AudioSegment.from_file(path, format="mp3")
                    final_audio += audio
                except Exception:
                    print(f"⚠️ Skipping broken chunk: {path}")
            final_audio.export(args.output_path, format="mp3")
            print(f"✅ Output saved to {args.output_path}")
        else:
            print("⚠️ No audio chunks to combine.")

        # Cleanup folder nếu bạn muốn
        for path in temp_files:
            try:
                os.remove(path)
            except Exception:
                pass
        try:
            os.rmdir(temp_dir)
        except OSError:
            pass  # Nếu thư mục không rỗng vì lỗi nào đó thì bỏ qua


if __name__ == "__main__":
    asyncio.run(main())
