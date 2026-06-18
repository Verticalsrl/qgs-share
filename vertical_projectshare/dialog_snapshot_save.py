import os

from PyQt5.QtWidgets import QTextEdit, QLineEdit, QPushButton, QLabel
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

		self.button_confirm.clicked.connect(self.accept)
		self.button_cancel.clicked.connect(self.close)
