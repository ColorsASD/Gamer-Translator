from __future__ import annotations

import sys

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from gamer_translator.defaults import APP_NAME
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
