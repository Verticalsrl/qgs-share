import os

# qgis.PyQt re-exports PyQt5 on QGIS 3 (Qt5) and PyQt6 on QGIS 4 (Qt6): same code, both versions
from qgis.PyQt.QtWidgets import QTextEdit, QLineEdit, QPushButton, QLabel
from qgis.PyQt import uic, QtWidgets

DIALOG_SNAPSHOT_SAVE, _ = uic.loadUiType(os.path.join(
	os.path.dirname(__file__), 'projectshare_snapshot_save.ui'))


class SnapshotSaveDialog(QtWidgets.QDialog, DIALOG_SNAPSHOT_SAVE):

	field_snapshot_notes: QTextEdit
	field_snapshot_title: QLineEdit

	button_cancel: QPushButton
	button_confirm: QPushButton

	label_changes: QLabel

	def __init__(self):
		super().__init__()
		self.setupUi(self)

		# versioning always happens while it is ON: this dialog only collects
		# optional notes, so the buttons are "save with notes" vs "skip notes"
		self.button_confirm.setText("Save with notes")
		self.button_cancel.setText("Skip (save without notes)")

		self.button_confirm.clicked.connect(self.accept)
		self.button_cancel.clicked.connect(self.close)
