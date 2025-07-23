#!/usr/bin/env python3
"""
Build script for Document To Speech Desktop Application
"""

import os
import sys
import subprocess
import shutil


def run_command(cmd, description=""):
    """Run a command and handle errors"""
    print(f"\n{'=' * 50}")
    print(f"🔄 {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'=' * 50}")

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("✅ Success!")
        if result.stdout:
            print("Output:", result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e}")
        if e.stdout:
            print("stdout:", e.stdout)
        if e.stderr:
            print("stderr:", e.stderr)
        return False


def clean_build():
    """Clean previous build artifacts"""
    print("🧹 Cleaning previous build artifacts...")

    dirs_to_clean = ["build", "dist", "__pycache__"]
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            print(f"   Removed: {dir_name}")

    # Clean .pyc files
    for root, dirs, files in os.walk("."):
        for file in files:
            if file.endswith(".pyc"):
                os.remove(os.path.join(root, file))
                print(f"   Removed: {os.path.join(root, file)}")


def check_dependencies():
    """Check if all required dependencies are installed"""
    print("🔍 Checking dependencies...")

    required_packages = ["python-docx", "PyMuPDF", "pydub", "edge-tts", "pyinstaller"]

    missing_packages = []

    for package in required_packages:
        try:
            __import__(package.replace("-", "_"))
        except ImportError:
            missing_packages.append(package)

    if missing_packages:
        print("❌ Missing packages:")
        for pkg in missing_packages:
            print(f"   - {pkg}")

        install = input("\n📦 Do you want to install missing packages? (y/n): ")
        if install.lower() in ["y", "yes"]:
            cmd = [sys.executable, "-m", "pip", "install"] + missing_packages
            if not run_command(cmd, "Installing missing packages"):
                return False
        else:
            print("❌ Cannot build without required packages")
            return False

    print("✅ All dependencies are available")
    return True


def create_build_info():
    """Create build information file"""
    build_info = f"""# Build Information
Built on: {subprocess.check_output(["date"], shell=True, text=True).strip()}
Python version: {sys.version}
Platform: {sys.platform}

# Usage
1. Extract the application to any folder
2. Run DocumentToSpeech.exe (Windows) or DocumentToSpeech (Linux/Mac)
3. Select a DOCX or PDF file
4. Configure voice settings
5. Click "Bắt đầu chuyển đổi" to start conversion

# Requirements
- No additional installation required
- Internet connection needed for text-to-speech conversion
- Audio output device for playback
"""
    with open("BUILD_INFO.txt", "w", encoding="utf-8") as f:
        f.write(build_info)
