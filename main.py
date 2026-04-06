from __future__ import annotations

import os
import sys

from gamer_translator.defaults import APP_NAME
from gamer_translator.settings_store import SettingsStore


def _extract_csv_flag_values(flags: list[str], key: str) -> tuple[list[str], set[str]]:
    prefix = f"{key}="
    remaining_flags: list[str] = []
    values: set[str] = set()

    for flag in flags:
        if flag.startswith(prefix):
            raw_value = flag[len(prefix):]
            values.update(part.strip() for part in raw_value.split(",") if part.strip())
            continue

        remaining_flags.append(flag)

    return remaining_flags, values


def _append_csv_flag(flags: list[str], key: str, values: set[str]) -> None:
    if values:
        flags.append(f"{key}={','.join(sorted(values))}")


def configure_webengine_environment() -> None:
    if sys.platform != "win32":
        return

    settings = SettingsStore().load_settings()
    disabled_flags = {
        "--disable-gpu",
        "--disable-gpu-compositing",
    }
    existing_flags = [
        flag
        for flag in os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").split()
        if flag not in disabled_flags
    ]
    existing_flags, disabled_features = _extract_csv_flag_values(existing_flags, "--disable-features")
    acceleration_flags = {
        "--enable-gpu-rasterization",
        "--enable-zero-copy",
    }
    background_keepalive_flags = {
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-backgrounding-occluded-windows",
    }

    if not settings.webview_gpu_acceleration_enabled:
        existing_flags = [flag for flag in existing_flags if flag not in acceleration_flags]
        existing_flags = [flag for flag in existing_flags if flag not in background_keepalive_flags]
        existing_flags.extend(sorted(disabled_flags))
        disabled_features.discard("CalculateNativeWinOcclusion")
    else:
        existing_flags.extend(sorted(acceleration_flags))

        if settings.keep_chatgpt_in_background:
            existing_flags.extend(sorted(background_keepalive_flags))
            disabled_features.add("CalculateNativeWinOcclusion")
        else:
            existing_flags = [flag for flag in existing_flags if flag not in background_keepalive_flags]
            disabled_features.discard("CalculateNativeWinOcclusion")

    deduplicated_flags = list(dict.fromkeys(existing_flags))
    _append_csv_flag(deduplicated_flags, "--disable-features", disabled_features)

    if deduplicated_flags:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(deduplicated_flags)
        return

    os.environ.pop("QTWEBENGINE_CHROMIUM_FLAGS", None)


configure_webengine_environment()

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from gamer_translator.main_window import MainWindow


class SingleInstanceController(QObject):
    activation_requested = Signal()

    def __init__(self, server_name: str) -> None:
        super().__init__()
        self.server_name = server_name
        self.server: QLocalServer | None = None

    def ensure_primary_instance(self) -> bool:
        if self._notify_existing_instance():
            return False

        QLocalServer.removeServer(self.server_name)
        self.server = QLocalServer(self)

        if not self.server.listen(self.server_name):
            if self._notify_existing_instance():
                return False

            raise RuntimeError("A programpéldány figyelése nem indítható el.")

        self.server.newConnection.connect(self._handle_new_connection)
        return True

    def _notify_existing_instance(self) -> bool:
        socket = QLocalSocket(self)
        socket.connectToServer(self.server_name)

        if not socket.waitForConnected(250):
            return False

        socket.write(b"show")
        socket.flush()
        socket.waitForBytesWritten(250)
        socket.disconnectFromServer()
        return True

    def _handle_new_connection(self) -> None:
        if self.server is None:
            return

        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()

            if socket is None:
                continue

            socket.disconnectFromServer()
            socket.deleteLater()
            self.activation_requested.emit()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationDisplayName(APP_NAME)

    single_instance = SingleInstanceController("GamerTranslatorDesktopSingleton")

    try:
        if not single_instance.ensure_primary_instance():
            return 0
    except RuntimeError:
        return 1

    window = MainWindow()
    single_instance.activation_requested.connect(window.show_from_external_request)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
