from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

from gamer_translator.defaults import APP_NAME
from gamer_translator.settings_store import AppSettings, SettingsStore, default_app_data_dir


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


def configure_webengine_environment(settings: AppSettings | None = None) -> None:
    if sys.platform != "win32":
        return

    settings = settings if settings is not None else SettingsStore().load_settings()
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


from PySide6.QtCore import QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

class SingleInstanceController(QObject):
    activation_requested = Signal()

    def __init__(self, server_name: str, root_dir: Path | None = None) -> None:
        super().__init__()
        profile_dir = (root_dir or default_app_data_dir()).resolve()
        profile_dir.mkdir(parents=True, exist_ok=True)
        profile_key = hashlib.sha256(os.path.normcase(str(profile_dir)).encode("utf-8")).hexdigest()[:24]
        self.server_name = f"{server_name}-{profile_key}"
        self.instance_lock = QLockFile(str(profile_dir / "instance.lock"))
        self.instance_lock.setStaleLockTime(0)
        self.server: QLocalServer | None = None

    def ensure_primary_instance(self) -> bool:
        # Windows alatt két QLocalServer is hallgathat ugyanazon a néven.
        if not self.instance_lock.tryLock(0):
            if self._notify_existing_instance(timeout_ms=1000):
                return False

            raise RuntimeError("A másik programpéldány még indul, vagy nem válaszol.")

        QLocalServer.removeServer(self.server_name)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)

        if not self.server.listen(self.server_name):
            self.instance_lock.unlock()
            raise RuntimeError("A programpéldány figyelése nem indítható el.")

        self.server.newConnection.connect(self._handle_new_connection)
        return True

    def _notify_existing_instance(self, timeout_ms: int = 250) -> bool:
        socket = QLocalSocket(self)
        socket.connectToServer(self.server_name)

        if not socket.waitForConnected(timeout_ms):
            socket.deleteLater()
            return False

        socket.write(b"show")
        socket.flush()
        socket.waitForBytesWritten(250)
        socket.disconnectFromServer()
        socket.deleteLater()
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
    parser = argparse.ArgumentParser(description=APP_NAME)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--self-test-report", type=Path, help="Elkülönített offline EXE-önteszt JSON jelentése.")
    mode.add_argument("--staging", action="store_true", help="Friss tesztprofil, rendszerintegrációk nélkül.")
    parser.add_argument("--self-test-duration", type=int, default=60, help="Az offline ismételt teszt hossza másodpercben (1–3600).")
    parser.add_argument("--self-test-model-dir", type=Path, help="Helyi, ellenőrzött OCR-modellek a csomagolt motorok öntesztjéhez.")
    args = parser.parse_args()
    if not 1 <= args.self_test_duration <= 3600:
        parser.error("A teszt időtartama 1 és 3600 másodperc közötti legyen.")
    if args.self_test_model_dir is not None and args.self_test_report is None:
        parser.error("A modellkönyvtár csak offline önteszthez használható.")
    if args.self_test_report is not None or args.staging:
        # A tesztmód még a normál profil és vágólap megnyitása előtt elágazik.
        configure_webengine_environment(AppSettings(webview_gpu_acceleration_enabled=False))
        if args.self_test_report is not None:
            os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from gamer_translator.self_test import run_self_test, run_staging
        return run_self_test(args.self_test_report, args.self_test_duration, args.self_test_model_dir) if args.self_test_report else run_staging()

    configure_webengine_environment()

    from gamer_translator.main_window import MainWindow

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
