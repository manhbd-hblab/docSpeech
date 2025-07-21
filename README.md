
## Python script to convert .docx and .pdf files to audio (mp3) files

This script uses the following libraries:

* `fitz`: PyMuPDF library for reading and parsing PDF files
* `docx`: Library for reading and writing Microsoft Word documents
* `edge_tts`: Library for converting text to speech using Microsoft Edge TTS

To use the script, simply run it with the following arguments:

```
python main.py <input_file_path> <output_file_path> [--language <language>]
```

The `<input_file_path>` and `<output_file_path>` arguments are the paths to the input and output files, respectively. The `--language` argument is optional and specifies the language for the text-to-speech conversion. The default language is `en-GB-SoniaNeural`.

**Example:**

```
python main.py my_document.docx my_audio.mp3
```

This will convert the `my_document.docx` file to the `my_audio.mp3` file using the French MichelNeural voice.

**Supported file formats:**

* .docx
* .pdf

**Output file format:**

* .mp3

**Requirements:**

* Python 3.6 or later
* fitz
* docx
* edge_tts

**Installation:**

1. Install the required Python libraries using `pip`:

```
pip install -r requirements.txt
```

2. Run the script:

```
python main.py
```
