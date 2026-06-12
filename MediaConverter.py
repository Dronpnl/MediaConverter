import os
import shutil
import zipfile
import urllib.request
import subprocess
import threading
import time
import sys
import requests
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import asyncio
from PIL import Image  

from tkinterdnd2 import DND_FILES, TkinterDnD

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

FFMPEG_PATH = os.path.join(BASE_DIR, "ffmpeg.exe")
FFPROBE_PATH = os.path.join(BASE_DIR, "ffprobe.exe")

ICON_FILE = "app.ico"
MAX_DOWNLOADS = 4


def get_duration_seconds(input_path):
    try:
        cmd = [FFMPEG_PATH, "-i", input_path]
        process = subprocess.Popen(
            cmd,
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        for line in process.stdout:
            if "Duration:" in line:
                part = line.split("Duration:")[1].split(",")[0].strip()
                h, m, s = part.split(":")
                s = float(s)
                total = int(h) * 3600 + int(m) * 60 + s
                return total
    except:
        pass
    return None

def estimate_size_mb(duration_sec, audio_kbps=0, video_kbps=0):
    total_kbps = audio_kbps + video_kbps
    if duration_sec is None or total_kbps <= 0:
        return None
    size_mb = (total_kbps * duration_sec) / 8000.0
    return size_mb

def get_audio_for_video(video_kbps: int) -> int:
    if video_kbps <= 2000:
        return 128
    elif video_kbps <= 5000:
        return 160
    elif video_kbps <= 10000:
        return 192
    else:
        return 256

def format_size(bytes_val):
    if bytes_val < 1024:
        return f"{bytes_val:.1f} KB"
    mb = bytes_val / (1024 * 1024)
    if mb < 1024:
        return f"{mb:.1f} MB"
    gb = mb / 1024
    return f"{gb:.2f} GB"

def download_gif():
    url = url_entry.get().strip()
    folder = OUTPUT_FOLDER.get().strip()

    if not url:
        messagebox.showerror("Error", "No URL provided")
        return

    if not folder:
        messagebox.showerror("Error", "No output folder selected")
        return

    try:
        filename = f"gif_{int(time.time())}.gif"
        save_path = os.path.join(folder, filename)

        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()

        with open(save_path, "wb") as f:
            f.write(response.content)

        if not disable_popups.get():
            messagebox.showinfo("Success", f"GIF downloaded:\n{save_path}")

    except Exception as e:
        messagebox.showerror("Error", f"GIF download failed:\n{e}")


def update_estimate_for_temp(temp_path, fmt):
    duration = get_duration_seconds(temp_path)
    if fmt == "mp3":
        audio_kbps = int(mp3_bitrate_var.get().replace("k", ""))
        video_kbps = 0
    else:
        video_kbps = int(video_bitrate_var.get())
        audio_kbps = get_audio_for_video(video_kbps)
    size_mb = estimate_size_mb(duration, audio_kbps, video_kbps)
    if size_mb:
        size_bytes = size_mb * 1024 * 1024
        estimate_label.config(text=f"Estimated Size: {format_size(size_bytes)}")
    else:
        estimate_label.config(text="Estimated Size: N/A")

def ensure_ffmpeg():
    if os.path.exists(FFMPEG_PATH) and os.path.exists(FFPROBE_PATH):
        return
    messagebox.showerror(
        "FFmpeg Missing",
        "ffmpeg.exe and ffprobe.exe were not found.\n\n"
        "Place ffmpeg.exe and ffprobe.exe in the same folder as this EXE."
    )
    raise SystemExit

def drop(event):
    file_path = event.data.strip("{}")
    input_entry.delete(0, tk.END)
    input_entry.insert(0, file_path)

download_slots = []

class DownloadSlot:
    def __init__(self, index, parent_frame):
        self.index = index
        self.frame = tk.Frame(parent_frame)
        self.frame.pack(fill="x", pady=2)

        self.label = tk.Label(self.frame, text=f"Slot {index+1}: idle")
        self.label.pack(side="left", padx=5)

        self.bar = ttk.Progressbar(self.frame, orient="horizontal", length=250, mode="determinate")
        self.bar.pack(side="left", padx=5)

        self.stop_btn = tk.Button(self.frame, text="STOP", width=6, command=self.stop)
        self.stop_btn.pack(side="right", padx=5)

        self.proc = None
        self.thread = None
        self.temp_base = None
        self.active = False
        self.target_fmt = None

    def start(self, url, fmt):
        if self.active:
            return

        self.active = True
        self.target_fmt = fmt
        self.temp_base = f"slot_{self.index}"
        self.label.config(text=f"Slot {self.index+1}: preparing")
        self.bar["value"] = 0

        def run():
            try:
                title_cmd = [
                    os.path.join(BASE_DIR, "yt-dlp.exe"),
                    "--skip-download",
                    "--print", "title",
                    url
                ]

                title_proc = subprocess.Popen(
                    title_cmd,
                    cwd=BASE_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )

                video_title = title_proc.stdout.read().strip() or "download"
                safe_title = "".join(c for c in video_title if c not in "\\/:*?\"<>|")

                if self.target_fmt in ("mp3", "wav"):
                    ytdlp_format = "bestaudio"
                else:
                    ytdlp_format = "bestvideo+bestaudio/best"


                cmd = [
                    os.path.join(BASE_DIR, "yt-dlp.exe"),
                    "-f", ytdlp_format,
                    "-o", self.temp_base + ".%(ext)s",
                    url
                ]

                self.proc = subprocess.Popen(
                    cmd,
                    cwd=BASE_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )

                for line in self.proc.stdout:
                    line = line.strip()

                    if "[download]" in line and "%" in line:
                        try:
                            parts = line.split()
                            percent_str = [p for p in parts if "%" in p][0]
                            percent = float(percent_str.replace("%", ""))

                            speed = next((p for p in parts if "iB/s" in p), "")
                            eta = ""
                            if "ETA" in parts:
                                idx = parts.index("ETA")
                                if idx + 1 < len(parts):
                                    eta = parts[idx + 1]

                            size_val = next((p for p in parts if any(x in p for x in ["KiB", "MiB", "GiB"])), "")

                            display_percent = percent * 0.90
                            self.bar["value"] = display_percent
                            self.label.config(
                                text=f"Slot {self.index+1}: {display_percent:.1f}% | ETA {eta} | {size_val} | {speed}"
                            )
                        except:
                            pass

                    elif "[Merger]" in line or "[ffmpeg]" in line or "Merging" in line:
                        for p in range(90, 101):
                            self.bar["value"] = p
                            self.label.config(text=f"Slot {self.index+1}: {p}% | Processing…")
                            time.sleep(0.05)

                
                self.proc.wait()
                time.sleep(0.3)

                downloaded_file = None
                for file in os.listdir(BASE_DIR):
                    if self.temp_base in file:
                        downloaded_file = os.path.join(BASE_DIR, file)
                        break

                if not downloaded_file:
                    raise RuntimeError("Download failed")

                update_estimate_for_temp(downloaded_file, self.target_fmt)

                output_path = os.path.join(OUTPUT_FOLDER.get(), safe_title + "." + self.target_fmt)
                run_ffmpeg(downloaded_file, output_path, self.target_fmt)

                
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    for file in os.listdir(BASE_DIR):
                        if file.startswith(self.temp_base + "."):
                            try:
                                os.remove(os.path.join(BASE_DIR, file))
                            except:
                                pass

            except Exception as e:
                messagebox.showerror("Error", f"Download/convert failed in slot {self.index+1}:\n{e}")

            finally:
                self.reset()

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def stop(self):
        if self.proc and self.active:
            try:
                subprocess.Popen(f"taskkill /F /T /PID {self.proc.pid}", shell=True)
            except:
                pass
        self.reset()

    def reset(self):
        self.active = False
        self.proc = None
        self.thread = None
        self.temp_base = None
        self.target_fmt = None
        self.bar["value"] = 0
        self.label.config(text=f"Slot {self.index+1}: idle")



def get_free_slot():
    for slot in download_slots:
        if not slot.active:
            return slot
    return None

def stop_all_downloads():
    for slot in download_slots:
        slot.stop()
def download_url():
    url = url_entry.get().strip()
    folder = OUTPUT_FOLDER.get().strip()

    if not url:
        messagebox.showerror("Error", "No URL provided")
        return

    if not folder:
        messagebox.showerror("Error", "No output folder selected")
        return

    try:
        filename = os.path.basename(url.split("?")[0]).strip()
        if not filename:
            filename = "downloaded_file"
        if "." not in filename:
            filename += ".bin"

        save_path = os.path.join(folder, filename)

        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()

        with open(save_path, "wb") as f:
            f.write(response.content)

        if not disable_popups.get():
            messagebox.showinfo("Success", f"File downloaded:\n{save_path}")

    except Exception as e:
        messagebox.showerror("Error", f"Download failed:\n{e}")

def run_ffmpeg(input_path, output_path, fmt):
    try:
        if not os.path.exists(input_path) or os.path.getsize(input_path) < 1000:
            messagebox.showerror("Error", "Downloaded file is incomplete or corrupted.")
            return

        audio_only_exts = (".m4a", ".mp3", ".aac", ".wav", ".flac")
        is_audio_only = input_path.lower().endswith(audio_only_exts)

        if fmt == "mp4" and is_audio_only:
            cmd = [
                FFMPEG_PATH,
                "-i", input_path,
                "-f", "lavfi",
                "-i", "color=size=1280x720:rate=30:color=black",
                "-shortest",
                "-c:a", "copy",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-y",
                output_path
            ]

        elif fmt == "mp4":
            cmd = [
                FFMPEG_PATH,
                "-i", input_path,
                "-progress", "pipe:1",
                "-nostats",
                "-c:v", "libx264",
                "-preset", "fast",
                "-c:a", "copy",
                "-pix_fmt", "yuv420p",
                "-y",
                output_path
            ]

        elif fmt.lower() == "mkv":
            cmd = [
                FFMPEG_PATH,
                "-i", input_path,
                "-progress", "pipe:1",
                "-nostats",
                "-c:v", "libx264",
                "-preset", "superfast",
                "-crf", "24",
                "-c:a", "aac",
                "-b:a", "192k",
                "-pix_fmt", "yuv420p",
                "-y",
                output_path
            ]

        elif fmt.lower() == "mov":
            cmd = [
                FFMPEG_PATH,
                "-i", input_path,
                "-progress", "pipe:1",
                "-nostats",
                "-c:v", "libx264",
                "-preset", "superfast",  
                "-crf", "23",            
                "-c:a", "aac",
                "-b:a", "192k",          
                "-pix_fmt", "yuv420p",
                "-y",
                output_path
            ]

        elif fmt == "wav" and is_audio_only:
            cmd = [
                FFMPEG_PATH,
                "-i", input_path,
                "-vn",
                "-acodec", "pcm_s16le",
                "-ar", "44100",
                "-ac", "2",
                "-y",
                output_path
            ]

        elif fmt == "mp3" and is_audio_only:
            cmd = [
                FFMPEG_PATH,
                "-i", input_path,
                "-vn",
                "-c:a", "libmp3lame",
                "-b:a", mp3_bitrate_var.get(),
                "-y",
                output_path
            ]

        else:
            cmd = [
                FFMPEG_PATH,
                "-i", input_path,
                "-progress", "pipe:1",
                "-nostats",
                "-y",
                output_path
            ]

        process = subprocess.Popen(
            cmd,
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        duration = get_duration_seconds(input_path)
        current = 0

        while True:
            line = process.stdout.readline()
            if not line:
                break

            if "out_time_ms" in line:
                try:
                    ms = int(line.split("=")[1].strip())
                    current = ms / 1_000_000
                except:
                    pass

                if duration:
                    percent = (current / duration) * 100
                    root.after(0, lambda: progress_bar.config(value=percent))


                    remaining = max(0, duration - current)
                    eta_str = time.strftime("%M:%S", time.gmtime(remaining))

                    if os.path.exists(output_path):
                        size_bytes = os.path.getsize(output_path)
                        size_str = format_size(size_bytes)
                    else:
                        size_str = "0 KB"

                    estimate_label.config(
                        text=f"Converting: {percent:.1f}% | ETA {eta_str} | {size_str}"
                    )
                    progress_bar.update()

        process.wait()
        progress_bar["value"] = 100

        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            if not disable_popups.get():
                messagebox.showinfo("Success", f"Converted to {fmt.upper()}:\n{output_path}")
                try:
                    os.startfile(output_path)
                except:
                    pass
        else:
            messagebox.showerror("Error", f"Conversion failed or output file is empty:\n{output_path}")

    except Exception as e:
        messagebox.showerror("Error", f"Conversion failed:\n{e}")


def convert_video(fmt):
    input_path = input_entry.get().strip()

    if not input_path:
        messagebox.showerror("Error", "No file selected")
        return

    if not os.path.exists(input_path):
        messagebox.showerror("Error", "File does not exist")
        return

    base = os.path.splitext(os.path.basename(input_path))[0]
    safe_title = "".join(c for c in base if c not in "\\/:*?\"<>|")
    output_path = os.path.join(OUTPUT_FOLDER.get(), safe_title + f".{fmt}")

    progress_bar["value"] = 0

    threading.Thread(target=run_ffmpeg, args=(input_path, output_path, fmt), daemon=True).start()

def convert_from_url(fmt):
    url = url_entry.get().strip()

    if not url:
        messagebox.showerror("Error", "No URL provided")
        return

    slot = get_free_slot()
    if slot is None:
        messagebox.showerror("Error", "Maximum downloads (4) already running")
        return

    progress_bar["value"] = 0
    slot.start(url, fmt)

def convert_image(input_path, output_path, fmt):
    img = Image.open(input_path)

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    img.save(output_path, fmt.upper())

def convert_to_ico(input_path, output_path):
    img = Image.open(input_path).convert("RGBA")

    img = img.resize((256, 256), Image.LANCZOS)

    sizes = [
        (256, 256),
        (128, 128),
        (64, 64),
        (48, 48),
        (32, 32),
        (24, 24),
        (16, 16)
    ]

    img.save(output_path, format="ICO", sizes=sizes)

def convert_image_ui(fmt):
    input_path = input_entry.get().strip()

    if not input_path:
        messagebox.showerror("Error", "No image selected")
        return

    if not os.path.exists(input_path):
        messagebox.showerror("Error", "File does not exist")
        return

    base = os.path.splitext(os.path.basename(input_path))[0]
    output_path = os.path.join(OUTPUT_FOLDER.get(), base + f".{fmt}")

    try:
        if fmt == "ico":
            convert_to_ico(input_path, output_path)
        else:
            convert_image(input_path, output_path, fmt)

        if not disable_popups.get():
            messagebox.showinfo("Success", f"Converted to {fmt.upper()}:\n{output_path}")
            try:
                os.startfile(output_path)
            except:
                pass

    except Exception as e:
        messagebox.showerror("Error", f"Image conversion failed:\n{e}")

def browse_file():
    file_path = filedialog.askopenfilename(
        title="Select a file",
        filetypes=[("Media & Image Files", "*.mp4 *.webm *.mov *.mkv *.avi *.mp3 *.wav *.m4a *.aac *.flac *.png *.jpg *.jpeg *.webp *.bmp *.tiff *.gif")]
    )
    if file_path:
        input_entry.delete(0, tk.END)
        input_entry.insert(0, file_path)

def browse_output_folder():
    folder = filedialog.askdirectory()
    if folder:
        OUTPUT_FOLDER.set(folder)

def kill_all_processes():
    for slot in download_slots:
        try:
            if slot.proc:
                subprocess.Popen(f"taskkill /F /T /PID {slot.proc.pid}", shell=True)
        except:
            pass

def on_close():
    kill_all_processes()
    try:
        root.destroy()
    except:
        pass
    os._exit(0)



def main():

    global root, input_entry, output_entry, url_entry
    global mp3_bitrate_var, video_bitrate_var, estimate_label, progress_bar
    global OUTPUT_FOLDER
    global disable_popups


    root = TkinterDnD.Tk()
    root.title("Media Converter")
    root.geometry("750x600")

    disable_popups = tk.BooleanVar(value=False)


    OUTPUT_FOLDER = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads"))

    if os.path.exists(ICON_FILE):
        root.iconbitmap(ICON_FILE)

    tk.Label(root, text="Drag & Drop a File or Browse").pack(pady=5)

    input_entry = tk.Entry(root, width=80)
    input_entry.pack(pady=5)

    input_entry.drop_target_register(DND_FILES)
    input_entry.dnd_bind("<<Drop>>", drop)

    tk.Button(root, text="Browse", command=browse_file).pack(pady=5)

    output_frame = tk.Frame(root)
    output_frame.pack(pady=5)

    tk.Label(output_frame, text="Save to:").pack(side="left", padx=5)

    output_entry = tk.Entry(output_frame, textvariable=OUTPUT_FOLDER, width=60)
    output_entry.pack(side="left", padx=5)

    tk.Button(output_frame, text="Browse", command=browse_output_folder).pack(side="left", padx=5)

    tk.Label(root, text="Or paste a video link (YouTube, etc.)").pack(pady=5)
    url_entry = tk.Entry(root, width=80)
    url_entry.pack(pady=5)

    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=10)

    tk.Button(btn_frame, text="File → MP4", width=18,
              command=lambda: convert_video("mp4")).grid(row=0, column=0, padx=5, pady=5)
    tk.Button(btn_frame, text="File → WEBM", width=18,
              command=lambda: convert_video("webm")).grid(row=0, column=1, padx=5, pady=5)
    tk.Button(btn_frame, text="File → MP3", width=18,
              command=lambda: convert_video("mp3")).grid(row=0, column=2, padx=5, pady=5)
    tk.Button(btn_frame, text="File → WAV", width=18,
              command=lambda: convert_video("wav")).grid(row=0, column=3, padx=5, pady=5)
    tk.Button(btn_frame, text="File → MOV", width=18,
          command=lambda: convert_video("mov")).grid(row=0, column=4, padx=5, pady=5)


    tk.Button(btn_frame, text="URL → MP3", width=18,
              command=lambda: convert_from_url("mp3")).grid(row=1, column=0, padx=5, pady=5)
    tk.Button(btn_frame, text="URL → MOV", width=18,
          command=lambda: convert_from_url("mov")).grid(row=1, column=1, padx=5, pady=5)
    tk.Button(btn_frame, text="URL → MP4", width=18,
          command=lambda: convert_from_url("mp4")).grid(row=1, column=2, padx=5, pady=5)
    tk.Button(btn_frame, text="URL → MKV", width=18,
          command=lambda: convert_from_url("mkv")).grid(row=1, column=3, padx=5, pady=5)



    tk.Button(btn_frame, text="URL → GIF", width=18,
            command=download_gif
    ).grid(row=1, column=4, padx=5, pady=5)

    tk.Button(btn_frame, text="Image → PNG", width=18,
              command=lambda: convert_image_ui("png")).grid(row=2, column=0, padx=5, pady=5)
    tk.Button(btn_frame, text="Image → JPG", width=18,
              command=lambda: convert_image_ui("jpg")).grid(row=2, column=1, padx=5, pady=5)
    tk.Button(btn_frame, text="Image → WEBP", width=18,
              command=lambda: convert_image_ui("webp")).grid(row=2, column=2, padx=5, pady=5)
    tk.Button(btn_frame, text="Image → ICO", width=18,
              command=lambda: convert_image_ui("ico")).grid(row=2, column=3, padx=5, pady=5)



    bitrate_frame = tk.Frame(root)
    bitrate_frame.pack(pady=5)

    popup_frame = tk.Frame(root)
    popup_frame.pack(pady=2)

    popup_check = tk.Checkbutton(
        popup_frame,
        text="Disable success popups",
        variable=disable_popups,
        font=("Segoe UI", 9)
    )
    popup_check.pack(side="left")


    tk.Label(bitrate_frame, text="MP3 Bitrate:").grid(row=0, column=0, padx=5, sticky="e")
    mp3_bitrate_var = tk.StringVar(value="192k")
    mp3_bitrate_box = ttk.Combobox(
        bitrate_frame,
        textvariable=mp3_bitrate_var,
        values=["64k", "96k", "128k", "192k", "256k", "320k"],
        width=10,
        state="readonly"
    )
    mp3_bitrate_box.grid(row=0, column=1, padx=5, sticky="w")

    tk.Label(bitrate_frame, text="Video Bitrate (kbps):").grid(row=0, column=2, padx=5, sticky="e")
    video_bitrate_var = tk.StringVar(value="5000")
    video_bitrate_box = ttk.Combobox(
        bitrate_frame,
        textvariable=video_bitrate_var,
        values=["2000", "5000", "10000", "20000"],
        width=10,
        state="readonly"
    )
    video_bitrate_box.grid(row=0, column=3, padx=5, sticky="w")

    estimate_label = tk.Label(root, text="Estimated Size: N/A")
    estimate_label.pack(pady=5)

    progress_bar = ttk.Progressbar(root, orient="horizontal", length=650, mode="determinate")
    progress_bar.pack(pady=10)

    downloads_frame = tk.LabelFrame(root, text="Active Downloads (max 4)")
    downloads_frame.pack(fill="x", padx=10, pady=10)

    for i in range(MAX_DOWNLOADS):
        slot = DownloadSlot(i, downloads_frame)
        download_slots.append(slot)

    tk.Button(root, text="STOP ALL DOWNLOADS", command=stop_all_downloads).pack(pady=5)

  
    root.protocol("WM_DELETE_WINDOW", on_close)

    ensure_ffmpeg()
    root.mainloop()

if __name__ == "__main__":
    main()
