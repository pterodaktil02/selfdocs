# Copyright (C) 2026 pterodaktil02
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from tkinter import BOTH, LEFT, Button, Label, Tk

import uvicorn

from app.main import app


APP_NAME = "SelfDocs"
HOST = "127.0.0.1"


def executable_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


def wait_for_server(url: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
            time.sleep(0.2)

    raise RuntimeError(
        f"SelfDocs не запустился за {timeout:.0f} секунд"
    ) from last_error


class SelfDocsLauncher:
    def __init__(self) -> None:
        self.port = find_free_port()
        self.base_url = f"http://{HOST}:{self.port}"
        self.health_url = f"{self.base_url}/health"

        self.server = uvicorn.Server(
            uvicorn.Config(
                app=app,
                host=HOST,
                port=self.port,
                workers=1,
                log_level="info",
                access_log=False,
            )
        )

        self.server_thread = threading.Thread(
            target=self.server.run,
            name="selfdocs-uvicorn",
            daemon=True,
        )

        self.root = Tk()
        self.root.title(APP_NAME)
        self.root.geometry("430x170")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.shutdown)

        self.status_label = Label(
            self.root,
            text="SelfDocs запускается...",
            padx=20,
            pady=20,
            justify=LEFT,
        )
        self.status_label.pack(fill=BOTH, expand=True)

        self.open_button = Button(
            self.root,
            text="Открыть SelfDocs",
            command=self.open_browser,
            state="disabled",
        )
        self.open_button.pack(pady=(0, 8))

        self.exit_button = Button(
            self.root,
            text="Завершить SelfDocs",
            command=self.shutdown,
        )
        self.exit_button.pack(pady=(0, 16))

    def start(self) -> None:
        self.server_thread.start()

        threading.Thread(
            target=self.finish_startup,
            name="selfdocs-startup",
            daemon=True,
        ).start()

        self.root.mainloop()

    def finish_startup(self) -> None:
        try:
            wait_for_server(self.health_url)
        except Exception as exc:
            self.root.after(0, self.show_startup_error, str(exc))
            return

        self.root.after(0, self.show_ready)
        self.root.after(0, self.open_browser)

    def show_ready(self) -> None:
        data_dir = executable_directory() / "data"

        self.status_label.config(
            text=(
                "SelfDocs работает локально.\n\n"
                f"Адрес: {self.base_url}\n"
                f"Данные: {data_dir}"
            )
        )
        self.open_button.config(state="normal")

    def show_startup_error(self, message: str) -> None:
        self.status_label.config(
            text=f"Ошибка запуска SelfDocs:\n\n{message}"
        )
        self.open_button.config(state="disabled")

    def open_browser(self) -> None:
        webbrowser.open(self.base_url, new=1)

    def shutdown(self) -> None:
        self.open_button.config(state="disabled")
        self.exit_button.config(state="disabled")
        self.status_label.config(text="SelfDocs завершается...")

        self.server.should_exit = True

        if self.server_thread.is_alive():
            self.server_thread.join(timeout=5.0)

        self.root.destroy()


def main() -> int:
    launcher = SelfDocsLauncher()
    launcher.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
