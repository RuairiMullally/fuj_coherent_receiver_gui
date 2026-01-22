import sys
import logging

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSlider,
)
from PySide6.QtCore import Qt


# --------------------
# Logging configuration
# --------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("FUJ Coherent Receiver GUI")
        self.setMinimumWidth(400)

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)

        self.sliders = []

        for i in range(8):
            slider_layout = QHBoxLayout()

            label = QLabel(f"Channel {i + 1}")
            label.setFixedWidth(80)

            slider = QSlider(Qt.Horizontal)
            slider.setMinimum(0)
            slider.setMaximum(1000)  # map 0–1000 → 0.0–1.0
            slider.setValue(0)

            value_label = QLabel("0.000")
            value_label.setFixedWidth(60)

            slider.valueChanged.connect(
                lambda value, idx=i, vlabel=value_label: self.on_slider_changed(
                    idx, value, vlabel
                )
            )

            slider_layout.addWidget(label)
            slider_layout.addWidget(slider)
            slider_layout.addWidget(value_label)

            layout.addLayout(slider_layout)
            self.sliders.append(slider)


    def on_slider_changed(self, index: int, raw_value: int, value_label: QLabel):
        value = raw_value / 1000.0
        value_label.setText(f"{value:.3f}")

        logger.info(
            "Slider %d updated → %.3f",
            index + 1,
            value,
        )


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
