import os
import re
import shutil
import subprocess
import tempfile
import threading
import tkinter as tk

from pathlib import Path
from tkinter import filedialog, messagebox
from tkinter import ttk


# ============================================================
# SETTINGS
# ============================================================

VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
FPS = 30

IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".bmp"
}

AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".aac",
    ".flac", ".ogg"
}


# ============================================================
# FFMPEG
# ============================================================

def check_ffmpeg():
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=(
                subprocess.CREATE_NO_WINDOW
                if os.name == "nt" else 0
            )
        )

        return result.returncode == 0

    except FileNotFoundError:
        return False


# ============================================================
# FILE NUMBER
# ============================================================

def get_number(path):
    match = re.search(r"\d+", path.stem)

    if match:
        return int(match.group())

    return None


# ============================================================
# COLLECT FILES
# ============================================================

def collect_files(folder, extensions):

    files = {}

    folder = Path(folder)

    if not folder.exists():
        return files

    for path in folder.iterdir():

        if not path.is_file():
            continue

        if path.suffix.lower() not in extensions:
            continue

        number = get_number(path)

        if number is None:
            continue

        if number in files:

            raise RuntimeError(
                f"Duplicate number {number} found:\n\n"
                f"{files[number].name}\n"
                f"{path.name}\n\n"
                "Keep only one file for each number."
            )

        files[number] = path

    return files


# ============================================================
# RUN FFMPEG
# ============================================================

def run_ffmpeg(command):

    creationflags = (
        subprocess.CREATE_NO_WINDOW
        if os.name == "nt" else 0
    )

    process = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=creationflags
    )

    if process.returncode != 0:

        raise RuntimeError(
            process.stderr[-5000:]
        )


# ============================================================
# MAIN VIDEO CREATION
# ============================================================

def make_video(
    images_folder,
    audio_folder,
    output_folder,
    progress_callback=None,
    log_callback=None
):

    def log(text):
        if log_callback:
            log_callback(text)

    def progress(value):
        if progress_callback:
            progress_callback(value)


    # --------------------------------------------------------
    # FFmpeg check
    # --------------------------------------------------------

    if not check_ffmpeg():

        raise RuntimeError(
            "FFmpeg was not found.\n\n"
            "Install FFmpeg and add its bin folder "
            "to Windows PATH."
        )


    # --------------------------------------------------------
    # Find files
    # --------------------------------------------------------

    log("Scanning image folder...")
    images = collect_files(
        images_folder,
        IMAGE_EXTENSIONS
    )

    log("Scanning audio folder...")
    audios = collect_files(
        audio_folder,
        AUDIO_EXTENSIONS
    )


    if not images:
        raise RuntimeError(
            "No numbered images found."
        )

    if not audios:
        raise RuntimeError(
            "No numbered audio files found."
        )


    # --------------------------------------------------------
    # Match files
    # --------------------------------------------------------

    image_numbers = set(images)
    audio_numbers = set(audios)

    missing_audio = sorted(
        image_numbers - audio_numbers
    )

    missing_images = sorted(
        audio_numbers - image_numbers
    )


    if missing_audio or missing_images:

        error = []

        if missing_audio:
            error.append(
                "Images without audio:\n"
                + ", ".join(
                    map(str, missing_audio)
                )
            )

        if missing_images:
            error.append(
                "Audio without images:\n"
                + ", ".join(
                    map(str, missing_images)
                )
            )

        raise RuntimeError(
            "\n\n".join(error)
        )


    numbers = sorted(image_numbers)

    log(
        f"Found {len(numbers)} matching pairs."
    )


    # --------------------------------------------------------
    # Temporary directory
    # --------------------------------------------------------

    temp_dir = Path(
        tempfile.mkdtemp(
            prefix="video_maker_"
        )
    )


    try:

        scene_files = []

        total = len(numbers)


        # ----------------------------------------------------
        # CREATE SCENES
        # ----------------------------------------------------

        for index, number in enumerate(
            numbers,
            start=1
        ):

            image = images[number]
            audio = audios[number]

            scene = temp_dir / (
                f"scene_{index:06d}.mp4"
            )


            log(
                f"[{index}/{total}] "
                f"Creating scene {number}"
            )


            command = [

                "ffmpeg",

                "-y",

                "-loop",
                "1",

                "-i",
                str(image),

                "-i",
                str(audio),

                "-vf",

                (
                    f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:"
                    "force_original_aspect_ratio=decrease,"
                    f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:"
                    "(ow-iw)/2:(oh-ih)/2"
                ),

                "-r",
                str(FPS),

                "-c:v",
                "libx264",

                "-preset",
                "medium",

                "-crf",
                "20",

                "-pix_fmt",
                "yuv420p",

                "-c:a",
                "aac",

                "-b:a",
                "192k",

                "-shortest",

                "-movflags",
                "+faststart",

                str(scene)
            ]


            run_ffmpeg(command)

            scene_files.append(scene)


            progress(
                int(index / total * 90)
            )


        # ----------------------------------------------------
        # CONCAT FILE
        # ----------------------------------------------------

        log("Preparing final video...")

        concat_file = temp_dir / "concat.txt"


        with open(
            concat_file,
            "w",
            encoding="utf-8"
        ) as f:

            for scene in scene_files:

                safe_path = str(
                    scene
                ).replace(
                    "'",
                    r"'\''"
                )

                f.write(
                    f"file '{safe_path}'\n"
                )


        # ----------------------------------------------------
        # OUTPUT
        # ----------------------------------------------------

        output_folder = Path(
            output_folder
        )

        output_folder.mkdir(
            parents=True,
            exist_ok=True
        )


        output_file = (
            output_folder /
            "final_video.mp4"
        )


        log("Combining all scenes...")


        command = [

            "ffmpeg",

            "-y",

            "-f",
            "concat",

            "-safe",
            "0",

            "-i",
            str(concat_file),

            "-c",
            "copy",

            "-movflags",
            "+faststart",

            str(output_file)
        ]


        run_ffmpeg(command)

        progress(100)

        log("Video creation completed!")

        return output_file, total


    finally:

        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )


# ============================================================
# GUI
# ============================================================

class VideoMakerApp:

    def __init__(self, root):

        self.root = root

        self.root.title(
            "Image + Audio Video Maker"
        )

        self.root.geometry(
            "850x650"
        )

        self.root.minsize(
            750,
            600
        )


        self.images_folder = ""
        self.audio_folder = ""
        self.output_folder = ""


        self.setup_style()
        self.create_ui()

        self.auto_detect_folders()


    # ========================================================
    # STYLE
    # ========================================================

    def setup_style(self):

        style = ttk.Style()

        try:
            style.theme_use("vista")
        except:
            pass


        style.configure(
            "Title.TLabel",
            font=(
                "Segoe UI",
                22,
                "bold"
            )
        )


        style.configure(
            "Subtitle.TLabel",
            font=(
                "Segoe UI",
                10
            )
        )


        style.configure(
            "Big.TButton",
            font=(
                "Segoe UI",
                11,
                "bold"
            ),
            padding=10
        )


    # ========================================================
    # UI
    # ========================================================

    def create_ui(self):

        # Header
        header = ttk.Frame(
            self.root,
            padding=20
        )

        header.pack(
            fill="x"
        )


        ttk.Label(
            header,
            text="🎬 Image + Audio Video Maker",
            style="Title.TLabel"
        ).pack(
            anchor="w"
        )


        ttk.Label(
            header,
            text=(
                "Automatically match numbered images "
                "with numbered audio files and create "
                "one MP4 video."
            ),
            style="Subtitle.TLabel"
        ).pack(
            anchor="w",
            pady=(5, 0)
        )


        # ----------------------------------------------------
        # FOLDERS
        # ----------------------------------------------------

        folder_frame = ttk.LabelFrame(
            self.root,
            text="  Project Folders  ",
            padding=15
        )

        folder_frame.pack(
            fill="x",
            padx=20,
            pady=10
        )


        self.create_folder_row(
            folder_frame,
            "🖼 Images:",
            "images"
        )

        self.create_folder_row(
            folder_frame,
            "🔊 Audio:",
            "audio"
        )

        self.create_folder_row(
            folder_frame,
            "📁 Output:",
            "output"
        )


        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------

        status_frame = ttk.LabelFrame(
            self.root,
            text="  Project Status  ",
            padding=15
        )

        status_frame.pack(
            fill="x",
            padx=20,
            pady=10
        )


        self.image_status = tk.StringVar(
            value="Images: --"
        )

        self.audio_status = tk.StringVar(
            value="Audio: --"
        )

        self.match_status = tk.StringVar(
            value="Matching: --"
        )


        status_grid = ttk.Frame(
            status_frame
        )

        status_grid.pack(
            fill="x"
        )


        ttk.Label(
            status_grid,
            textvariable=self.image_status
        ).grid(
            row=0,
            column=0,
            padx=20,
            sticky="w"
        )


        ttk.Label(
            status_grid,
            textvariable=self.audio_status
        ).grid(
            row=0,
            column=1,
            padx=20,
            sticky="w"
        )


        ttk.Label(
            status_grid,
            textvariable=self.match_status
        ).grid(
            row=0,
            column=2,
            padx=20,
            sticky="w"
        )


        # ----------------------------------------------------
        # PROGRESS
        # ----------------------------------------------------

        progress_frame = ttk.LabelFrame(
            self.root,
            text="  Progress  ",
            padding=15
        )

        progress_frame.pack(
            fill="x",
            padx=20,
            pady=10
        )


        self.progress = ttk.Progressbar(
            progress_frame,
            orient="horizontal",
            mode="determinate",
            maximum=100
        )

        self.progress.pack(
            fill="x"
        )


        self.progress_text = tk.StringVar(
            value="Ready"
        )


        ttk.Label(
            progress_frame,
            textvariable=self.progress_text
        ).pack(
            pady=(7, 0)
        )


        # ----------------------------------------------------
        # LOG
        # ----------------------------------------------------

        log_frame = ttk.LabelFrame(
            self.root,
            text="  Activity Log  ",
            padding=10
        )

        log_frame.pack(
            fill="both",
            expand=True,
            padx=20,
            pady=10
        )


        self.log_text = tk.Text(
            log_frame,
            height=8,
            font=(
                "Consolas",
                9
            ),
            state="disabled"
        )

        self.log_text.pack(
            side="left",
            fill="both",
            expand=True
        )


        scrollbar = ttk.Scrollbar(
            log_frame,
            orient="vertical",
            command=self.log_text.yview
        )

        scrollbar.pack(
            side="right",
            fill="y"
        )

        self.log_text.configure(
            yscrollcommand=scrollbar.set
        )


        # ----------------------------------------------------
        # BOTTOM BUTTONS
        # ----------------------------------------------------

        bottom = ttk.Frame(
            self.root,
            padding=(20, 5, 20, 20)
        )

        bottom.pack(
            fill="x"
        )


        self.refresh_button = ttk.Button(
            bottom,
            text="🔄 Refresh",
            command=self.refresh_status
        )

        self.refresh_button.pack(
            side="left"
        )


        self.start_button = ttk.Button(
            bottom,
            text="▶ CREATE VIDEO",
            style="Big.TButton",
            command=self.start_video
        )

        self.start_button.pack(
            side="right"
        )


    # ========================================================
    # FOLDER ROW
    # ========================================================

    def create_folder_row(
        self,
        parent,
        label,
        folder_type
    ):

        frame = ttk.Frame(
            parent
        )

        frame.pack(
            fill="x",
            pady=5
        )


        ttk.Label(
            frame,
            text=label,
            width=12
        ).pack(
            side="left"
        )


        variable = tk.StringVar(
            value="Not selected"
        )


        if folder_type == "images":
            self.images_var = variable

        elif folder_type == "audio":
            self.audio_var = variable

        else:
            self.output_var = variable


        entry = ttk.Entry(
            frame,
            textvariable=variable,
            state="readonly"
        )

        entry.pack(
            side="left",
            fill="x",
            expand=True,
            padx=5
        )


        ttk.Button(
            frame,
            text="Browse",
            command=lambda: self.select_folder(
                folder_type
            )
        ).pack(
            side="right"
        )


    # ========================================================
    # AUTO DETECT
    # ========================================================

    def auto_detect_folders(self):

        base = Path(
            os.path.dirname(
                os.path.abspath(__file__)
            )
        )


        images = base / "images"
        audio = base / "audio"
        output = base / "output"


        if images.exists():
            self.images_folder = str(images)
            self.images_var.set(
                str(images)
            )


        if audio.exists():
            self.audio_folder = str(audio)
            self.audio_var.set(
                str(audio)
            )


        if output.exists():
            self.output_folder = str(output)
            self.output_var.set(
                str(output)
            )


        self.refresh_status()


    # ========================================================
    # SELECT FOLDER
    # ========================================================

    def select_folder(self, folder_type):

        folder = filedialog.askdirectory(
            title=f"Select {folder_type} folder"
        )


        if not folder:
            return


        if folder_type == "images":

            self.images_folder = folder

            self.images_var.set(
                folder
            )


        elif folder_type == "audio":

            self.audio_folder = folder

            self.audio_var.set(
                folder
            )


        else:

            self.output_folder = folder

            self.output_var.set(
                folder
            )


        self.refresh_status()


    # ========================================================
    # REFRESH STATUS
    # ========================================================

    def refresh_status(self):

        try:

            if self.images_folder:

                images = collect_files(
                    self.images_folder,
                    IMAGE_EXTENSIONS
                )

                image_count = len(images)

            else:

                image_count = 0


            if self.audio_folder:

                audios = collect_files(
                    self.audio_folder,
                    AUDIO_EXTENSIONS
                )

                audio_count = len(audios)

            else:

                audio_count = 0


            self.image_status.set(
                f"🖼 Images: {image_count}"
            )

            self.audio_status.set(
                f"🔊 Audio: {audio_count}"
            )


            if image_count == 0 and audio_count == 0:

                self.match_status.set(
                    "Matching: --"
                )

            elif image_count == audio_count:

                self.match_status.set(
                    "✓ Matching: READY"
                )

            else:

                self.match_status.set(
                    "⚠ Matching: CHECK FILES"
                )


        except Exception as e:

            self.match_status.set(
                "⚠ Error"
            )


    # ========================================================
    # LOG
    # ========================================================

    def log(self, message):

        def update():

            self.log_text.config(
                state="normal"
            )

            self.log_text.insert(
                "end",
                message + "\n"
            )

            self.log_text.see(
                "end"
            )

            self.log_text.config(
                state="disabled"
            )

        self.root.after(
            0,
            update
        )


    # ========================================================
    # PROGRESS
    # ========================================================

    def set_progress(self, value):

        def update():

            self.progress["value"] = value

            self.progress_text.set(
                f"{int(value)}%"
            )

        self.root.after(
            0,
            update
        )


    # ========================================================
    # START VIDEO
    # ========================================================

    def start_video(self):

        if not self.images_folder:

            messagebox.showwarning(
                "Images folder",
                "Please select the images folder."
            )

            return


        if not self.audio_folder:

            messagebox.showwarning(
                "Audio folder",
                "Please select the audio folder."
            )

            return


        if not self.output_folder:

            messagebox.showwarning(
                "Output folder",
                "Please select the output folder."
            )

            return


        # Check files first
        try:

            images = collect_files(
                self.images_folder,
                IMAGE_EXTENSIONS
            )

            audios = collect_files(
                self.audio_folder,
                AUDIO_EXTENSIONS
            )


            if not images:

                raise RuntimeError(
                    "No numbered images found."
                )


            if not audios:

                raise RuntimeError(
                    "No numbered audio files found."
                )


            if set(images) != set(audios):

                missing_audio = sorted(
                    set(images) - set(audios)
                )

                missing_images = sorted(
                    set(audios) - set(images)
                )


                message = ""


                if missing_audio:

                    message += (
                        "Missing audio:\n"
                        + ", ".join(
                            map(
                                str,
                                missing_audio
                            )
                        )
                        + "\n\n"
                    )


                if missing_images:

                    message += (
                        "Missing images:\n"
                        + ", ".join(
                            map(
                                str,
                                missing_images
                            )
                        )
                    )


                messagebox.showerror(
                    "Files do not match",
                    message
                )

                return


        except Exception as e:

            messagebox.showerror(
                "Error",
                str(e)
            )

            return


        # Confirm
        count = len(images)


        answer = messagebox.askyesno(
            "Create Video",
            f"Ready to create video.\n\n"
            f"Images: {count}\n"
            f"Audio: {count}\n\n"
            f"Resolution: 1920 × 1080\n"
            f"FPS: 30\n\n"
            f"Start?"
        )


        if not answer:
            return


        # Clear log
        self.log_text.config(
            state="normal"
        )

        self.log_text.delete(
            "1.0",
            "end"
        )

        self.log_text.config(
            state="disabled"
        )


        self.progress["value"] = 0

        self.progress_text.set(
            "Starting..."
        )


        self.start_button.config(
            state="disabled"
        )

        self.refresh_button.config(
            state="disabled"
        )


        # Run in background
        thread = threading.Thread(
            target=self.create_video_thread,
            daemon=True
        )

        thread.start()


    # ========================================================
    # VIDEO THREAD
    # ========================================================

    def create_video_thread(self):

        try:

            output_file, count = make_video(

                self.images_folder,

                self.audio_folder,

                self.output_folder,

                progress_callback=self.set_progress,

                log_callback=self.log
            )


            def finished():

                self.start_button.config(
                    state="normal"
                )

                self.refresh_button.config(
                    state="normal"
                )


                self.progress_text.set(
                    "✓ Finished!"
                )


                messagebox.showinfo(

                    "Video Created",

                    f"Video created successfully!\n\n"
                    f"Scenes: {count}\n\n"
                    f"Saved to:\n{output_file}"
                )


            self.root.after(
                0,
                finished
            )


        except Exception as e:

            def failed():

                self.start_button.config(
                    state="normal"
                )

                self.refresh_button.config(
                    state="normal"
                )


                self.progress_text.set(
                    "❌ Error"
                )


                self.log(
                    "ERROR: " + str(e)
                )


                messagebox.showerror(
                    "Video Creation Error",
                    str(e)
                )


            self.root.after(
                0,
                failed
            )


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":

    root = tk.Tk()

    app = VideoMakerApp(root)

    root.mainloop()