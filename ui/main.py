import sys
from PyQt5.QtWidgets import QApplication
from ui.main_window import MainWindow
from shared.logger import get_logger

logger = get_logger(__name__)

def main():
    logger.info("Taktik arayüz başlatılıyor...")
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    logger.info("Arayüz hazır.")
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()