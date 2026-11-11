"""Windows desktop entry point for the original browser-based DeepRake GUI.

This intentionally does not replace templates/dorks.html or its V1 bookmarklet.
The control window keeps the local server alive until the user closes it.
"""

import os
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from werkzeug.serving import make_server

# PyInstaller's --windowed mode can leave these streams as None. Give Flask
# and Werkzeug a safe destination for diagnostic output.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from app import app


URL = "http://localhost:5000/dorks"


def main():
    window = tk.Tk()
    window.title("DeepRake")
    window.geometry("400x205")
    window.resizable(False, False)

    try:
        server = make_server("127.0.0.1", 5000, app, threaded=True)
    except (OSError, SystemExit):
        messagebox.showerror(
            "DeepRake couldn't start",
            "Local port 5000 is already in use. Close the other application "
            "using that port, then launch DeepRake again.",
            parent=window,
        )
        window.destroy()
        return

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def open_browser():
        webbrowser.open(URL, new=2)

    def stop():
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        window.destroy()

    frame = ttk.Frame(window, padding=20)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="DeepRake is running", font=("Segoe UI", 14, "bold")).pack(anchor="w")
    ttk.Label(frame, text="Your original V1 interface is available in your browser.").pack(
        anchor="w", pady=(8, 3)
    )
    ttk.Label(frame, text="Leave this window open while using Quantum-Dig.").pack(anchor="w")
    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=(22, 0))
    ttk.Button(buttons, text="Open DeepRake", command=open_browser).pack(side="left")
    ttk.Button(buttons, text="Stop and Close", command=stop).pack(side="right")

    window.protocol("WM_DELETE_WINDOW", stop)
    window.after(400, open_browser)
    window.mainloop()


if __name__ == "__main__":
    main()
