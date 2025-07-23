import tkinter as tk
from tkinter import filedialog, ttk, messagebox, scrolledtext
import asyncio
import threading
import os
import subprocess
import logging
import time
from pathlib import Path

# Import your TTS modules
from tts.document_reader import DocumentReader
from tts.text_splitter import TextSplitter
from tts.tts_processor import TTSProcessor
from tts.audio_combiner import AudioCombiner
from tts.utils import setup_dirs, format_seconds


# Configure logging
def setup_logging():
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "tts_app.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


setup_logging()
logger = logging.getLogger(__name__)


class TTSApp:
    def __init__(self, root):
        self.root = root
        self.root.title("📚 Document To Speech Converter")
        self.root.geometry("700x600")
        self.root.minsize(600, 500)

        # Configure style
        style = ttk.Style()
        style.theme_use("clam")

        self.file_path = ""
        self.output_path = ""
        self.is_processing = False

        self.setup_ui()
        self.setup_dirs()

        # Bind close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_dirs(self):
        """Initialize directories"""
        try:
            self.input_dir, self.output_dir, self.temp_dir = setup_dirs()
            logger.info("Directories initialized successfully")
        except Exception as e:
            logger.error(f"Failed to setup directories: {e}")
            messagebox.showerror("Lỗi", f"Không thể tạo thư mục: {e}")

    def setup_ui(self):
        """Setup the user interface"""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)

        # Title
        title_label = ttk.Label(
            main_frame,
            text="📚 Document To Speech Converter",
            font=("Arial", 16, "bold"),
        )
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))

        # File selection
        ttk.Label(main_frame, text="📄 Chọn file:").grid(
            row=1, column=0, sticky="w", pady=5
        )

        self.file_entry = ttk.Entry(main_frame, width=50)
        self.file_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(10, 5), pady=5)

        self.btn_browse = ttk.Button(
            main_frame, text="📂 Chọn file", command=self.browse_file
        )
        self.btn_browse.grid(row=1, column=2, padx=(5, 0), pady=5)

        # Voice selection
        ttk.Label(main_frame, text="🎤 Giọng nói:").grid(
            row=2, column=0, sticky="w", pady=5
        )

        self.voice_var = tk.StringVar(value="vi-VN-HoaiMyNeural")
        voice_combo = ttk.Combobox(
            main_frame,
            textvariable=self.voice_var,
            values=["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural", "vi-VN-HoaiMyNeural"],
        )
        voice_combo.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=(10, 5), pady=5)
        voice_combo.state(["readonly"])

        # Speed control
        ttk.Label(main_frame, text="⚡ Tốc độ:").grid(
            row=3, column=0, sticky="w", pady=5
        )

        speed_frame = ttk.Frame(main_frame)
        speed_frame.grid(row=3, column=1, sticky=(tk.W, tk.E), padx=(10, 5), pady=5)

        self.speed_var = tk.StringVar(value="0")
        speed_scale = ttk.Scale(
            speed_frame,
            from_=-50,
            to=50,
            variable=self.speed_var,
            orient="horizontal",
            length=200,
        )
        speed_scale.pack(side="left", fill="x", expand=True)

        self.speed_label = ttk.Label(speed_frame, text="0%")
        self.speed_label.pack(side="right", padx=(10, 0))

        speed_scale.configure(command=self.update_speed_label)

        # Pitch control
        ttk.Label(main_frame, text="🎵 Cao độ:").grid(
            row=4, column=0, sticky="w", pady=5
        )

        pitch_frame = ttk.Frame(main_frame)
        pitch_frame.grid(row=4, column=1, sticky=(tk.W, tk.E), padx=(10, 5), pady=5)

        self.pitch_var = tk.StringVar(value="0")
        pitch_scale = ttk.Scale(
            pitch_frame,
            from_=-100,
            to=100,
            variable=self.pitch_var,
            orient="horizontal",
            length=200,
        )
        pitch_scale.pack(side="left", fill="x", expand=True)

        self.pitch_label = ttk.Label(pitch_frame, text="+0Hz")
        self.pitch_label.pack(side="right", padx=(10, 0))

        pitch_scale.configure(command=self.update_pitch_label)

        # Concurrent processing
        ttk.Label(main_frame, text="🔀 Xử lý đồng thời:").grid(
            row=5, column=0, sticky="w", pady=5
        )

        self.concurrent_var = tk.IntVar(value=6)
        concurrent_spin = ttk.Spinbox(
            main_frame, from_=1, to=12, textvariable=self.concurrent_var, width=10
        )
        concurrent_spin.grid(row=5, column=1, sticky="w", padx=(10, 5), pady=5)

        # Progress section
        progress_frame = ttk.LabelFrame(main_frame, text="📊 Tiến trình", padding="10")
        progress_frame.grid(
            row=6, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(20, 10)
        )
        progress_frame.columnconfigure(0, weight=1)

        self.progress = ttk.Progressbar(
            progress_frame, orient="horizontal", length=400, mode="determinate"
        )
        self.progress.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        self.status_label = ttk.Label(
            progress_frame, text="Sẵn sàng xử lý", font=("Arial", 10)
        )
        self.status_label.grid(row=1, column=0, sticky="w")

        self.time_label = ttk.Label(
            progress_frame, text="", font=("Arial", 9), foreground="gray"
        )
        self.time_label.grid(row=2, column=0, sticky="w")

        # Control buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=7, column=0, columnspan=3, pady=20)

        self.btn_start = ttk.Button(
            button_frame,
            text="🚀 Bắt đầu chuyển đổi",
            command=self.start_process,
            style="Accent.TButton",
        )
        self.btn_start.pack(side="left", padx=(0, 10))

        self.btn_stop = ttk.Button(
            button_frame, text="⏹️ Dừng", command=self.stop_process, state="disabled"
        )
        self.btn_stop.pack(side="left", padx=(0, 10))

        self.btn_open_output = ttk.Button(
            button_frame,
            text="📁 Mở thư mục kết quả",
            command=self.open_output,
            state="disabled",
        )
        self.btn_open_output.pack(side="left")

        # Log display
        log_frame = ttk.LabelFrame(main_frame, text="📝 Nhật ký", padding="10")
        log_frame.grid(
            row=8, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0)
        )
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, width=70)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure grid weights for resizing
        main_frame.rowconfigure(8, weight=1)

    def update_speed_label(self, value):
        """Update speed label"""
        speed_val = int(float(value))
        self.speed_label.config(text=f"{speed_val:+d}%")

    def update_pitch_label(self, value):
        """Update pitch label"""
        pitch_val = int(float(value))
        self.pitch_label.config(text=f"{pitch_val:+d}Hz")

    def log_message(self, message):
        """Add message to log display"""
        self.log_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} - {message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def browse_file(self):
        """Browse for input file"""
        file_path = filedialog.askopenfilename(
            title="Chọn file DOCX hoặc PDF",
            filetypes=[("Document files", "*.docx *.pdf"), ("All files", "*.*")],
        )

        if file_path:
            self.file_path = file_path
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, os.path.basename(file_path))
            self.log_message(f"Đã chọn file: {os.path.basename(file_path)}")
            logger.info(f"File selected: {file_path}")

    def start_process(self):
        """Start TTS conversion process"""
        if not self.file_path:
            messagebox.showerror("Lỗi", "Vui lòng chọn file trước!")
            return

        if not os.path.exists(self.file_path):
            messagebox.showerror("Lỗi", "File không tồn tại!")
            return

        self.is_processing = True
        self.btn_start.config(state="disabled")
        self.btn_browse.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.btn_open_output.config(state="disabled")

        self.progress["value"] = 0
        self.status_label.config(text="🔄 Đang khởi tạo...")
        self.time_label.config(text="")

        # Clear log
        self.log_text.delete(1.0, tk.END)

        self.log_message("Bắt đầu quá trình chuyển đổi...")
        logger.info(f"Starting TTS conversion for: {self.file_path}")

        # Start processing in separate thread
        self.processing_thread = threading.Thread(target=self.run_tts_thread)
        self.processing_thread.daemon = True
        self.processing_thread.start()

    def stop_process(self):
        """Stop TTS conversion process"""
        self.is_processing = False
        self.log_message("Đang dừng quá trình...")
        self.status_label.config(text="⏹️ Đang dừng...")

    def run_tts_thread(self):
        """Run TTS in separate thread"""
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Run the async TTS process
            loop.run_until_complete(self.process_tts())

        except Exception as e:
            logger.exception(f"Error in TTS thread: {e}")
            self.root.after(0, lambda e=e: self.handle_error(str(e)))
        finally:
            loop.close()

    async def process_tts(self):
        """Main TTS processing function"""
        start_time = time.time()

        try:
            # Prepare output path
            filename = os.path.basename(self.file_path)
            output_filename = os.path.splitext(filename)[0] + ".mp3"
            self.output_path = os.path.join(self.output_dir, output_filename)

            # Update UI
            self.root.after(0, lambda: self.log_message(f"Đọc file: {filename}"))
            self.root.after(
                0, lambda: self.status_label.config(text="📖 Đang đọc file...")
            )

            # Read document
            if filename.lower().endswith(".docx"):
                text = DocumentReader.read_docx(self.file_path)
            elif filename.lower().endswith(".pdf"):
                text = DocumentReader.read_pdf(self.file_path)
            else:
                raise ValueError("Chỉ hỗ trợ file DOCX và PDF")

            if not text or not text.strip():
                logger.error(f"Đọc xong nhưng text rỗng. Kích thước: {len(text)}")
                raise ValueError("File rỗng hoặc không đọc được nội dung")

            self.root.after(
                0, lambda: self.log_message(f"Đọc thành công {len(text)} ký tự")
            )
            logger.info(f"Document read: {len(text)} characters")

            # Split into chunks
            self.root.after(
                0, lambda: self.status_label.config(text="✂️ Đang chia nhỏ văn bản...")
            )
            chunks = TextSplitter.smart_split(text, max_length=2000)

            self.root.after(
                0, lambda: self.log_message(f"Chia thành {len(chunks)} đoạn")
            )
            logger.info(f"Text split into {len(chunks)} chunks")

            if not self.is_processing:
                return

            # Prepare TTS settings
            speed = f"{int(float(self.speed_var.get())):+d}%"
            pitch = f"{int(float(self.pitch_var.get())):+d}Hz"
            concurrent = self.concurrent_var.get()
            voice = self.voice_var.get()

            self.root.after(
                0,
                lambda: self.log_message(
                    f"Cài đặt: Giọng={voice}, Tốc độ={speed}, Cao độ={pitch}"
                ),
            )

            # Initialize TTS processor
            tts = TTSProcessor(
                voice=voice, temp_dir=self.temp_dir, speed=speed, pitch=pitch
            )

            # Process chunks
            self.root.after(
                0,
                lambda: self.status_label.config(
                    text="🎤 Đang chuyển đổi thành giọng nói..."
                ),
            )

            total_chunks = len(chunks)
            processed = 0

            # Process in batches to show progress
            batch_size = min(12, concurrent * 2)
            success_files = []

            for i in range(0, total_chunks, batch_size):
                if not self.is_processing:
                    break

                batch = chunks[i : i + batch_size]
                batch_results = await tts.process_batch(batch, concurrent)

                # Collect successful files
                for idx, (orig_idx, path, success) in enumerate(batch_results):
                    if success:
                        success_files.append(path)
                    processed += 1

                    # Update progress
                    progress = (
                        processed / total_chunks
                    ) * 90  # Reserve 10% for combining
                    self.root.after(0, lambda p=progress: self.progress.config(value=p))

                    if processed % 5 == 0 or processed == total_chunks:
                        self.root.after(
                            0,
                            lambda: self.log_message(
                                f"Hoàn thành {processed}/{total_chunks} đoạn"
                            ),
                        )

            if not self.is_processing:
                self.root.after(0, lambda: self.log_message("Quá trình đã bị dừng"))
                return

            if not success_files:
                raise ValueError("Không có đoạn audio nào được tạo thành công")

            # Combine audio files
            self.root.after(
                0, lambda: self.status_label.config(text="🔄 Đang ghép file audio...")
            )
            self.root.after(0, lambda: self.log_message("Bắt đầu ghép file audio..."))

            combiner = AudioCombiner(pause_ms=300, fade_ms=50)
            combiner.combine(success_files, self.output_path)

            # Clean up temp files
            for temp_file in success_files:
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

            # Final update
            elapsed_time = time.time() - start_time
            self.root.after(0, lambda: self.progress.config(value=100))
            self.root.after(0, lambda: self.status_label.config(text="✅ Hoàn tất!"))
            self.root.after(
                0,
                lambda: self.time_label.config(
                    text=f"Thời gian xử lý: {format_seconds(elapsed_time)}"
                ),
            )
            self.root.after(
                0, lambda: self.log_message(f"Hoàn tất! File đã lưu: {output_filename}")
            )
            self.root.after(
                0,
                lambda: self.log_message(
                    f"Thời gian xử lý: {format_seconds(elapsed_time)}"
                ),
            )

            logger.info(f"TTS conversion completed: {self.output_path}")

            # Enable open button
            self.root.after(0, lambda: self.btn_open_output.config(state="normal"))

        except Exception as e:
            logger.exception(f"Error during TTS processing: {e}")
            self.root.after(0, lambda e=e: self.handle_error(str(e)))

        finally:
            # Re-enable controls
            self.root.after(0, self.reset_controls)

    def handle_error(self, error_message):
        """Handle errors in UI thread"""
        self.log_message(f"❌ Lỗi: {error_message}")
        self.status_label.config(text="❌ Có lỗi xảy ra")
        messagebox.showerror("Lỗi", f"Có lỗi xảy ra:\n{error_message}")
        self.reset_controls()

    def reset_controls(self):
        """Reset control states"""
        self.is_processing = False
        self.btn_start.config(state="normal")
        self.btn_browse.config(state="normal")
        self.btn_stop.config(state="disabled")

    def open_output(self):
        """Open output directory"""
        if not os.path.exists(self.output_dir):
            messagebox.showerror("Lỗi", "Thư mục output không tồn tại!")
            return

        try:
            if os.name == "nt":  # Windows
                os.startfile(self.output_dir)
            elif os.name == "posix":  # macOS and Linux
                subprocess.Popen(
                    [
                        "open" if "darwin" in os.sys.platform else "xdg-open",
                        self.output_dir,
                    ]
                )
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể mở thư mục: {e}")

    def on_close(self):
        """Handle window close event"""
        if self.is_processing:
            if messagebox.askokcancel(
                "Thoát", "Quá trình đang chạy. Bạn có muốn dừng và thoát?"
            ):
                self.is_processing = False
                self.root.after(100, self.force_quit)
            return

        logger.info("Application closing")
        self.root.destroy()

    def force_quit(self):
        """Force quit the application"""
        self.root.destroy()
        os._exit(0)


def main():
    """Main application entry point"""
    try:
        root = tk.Tk()

        # Set application icon (optional)
        # root.iconbitmap("icon.ico")  # Uncomment if you have an icon file
        TTSApp(root)
        root.mainloop()

    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        messagebox.showerror("Lỗi nghiêm trọng", f"Ứng dụng gặp lỗi:\n{e}")


if __name__ == "__main__":
    main()
