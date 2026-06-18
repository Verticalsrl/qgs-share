import os
from typing import TypedDict, Dict, List

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QTextEdit, QLineEdit, QPushButton, QLabel, QTabBar, QTableWidget, QTableWidgetItem, QHBoxLayout, QMessageBox, QFileDialog, QApplication
from qgis.PyQt import uic, QtWidgets
from qgis._core import Qgis
from qgis._gui import QgsMessageBar

from .constants import STRFORMAT_DATETIME, STRFORMAT_DATE, STRFORMAT_TIME
from .snapshooter import VerticalShareSnapper, HistoryDataItem

DIALOG_PROJECT_HISTORY, _ = uic.loadUiType(os.path.join(
	os.path.dirname(__file__), 'projectshare_history.ui'))



class ProjectHistoryDialog(QtWidgets.QDialog, DIALOG_PROJECT_HISTORY):

	label_listing_title: QLabel

	table_snapshots: QTableWidget

	button_close: QPushButton

	promoted_snapshot = pyqtSignal(str)  # changeid


	def __init__(self, uri: str):
		super().__init__()

		self.setupUi(self)

		self.messageBar = QgsMessageBar(self)

		self.button_close.clicked.connect(self.close)

		self.snapper = VerticalShareSnapper.get_for(uri)

		self.refresh_history_table()

		self.label_listing_title.setText("Modifiche a %s" % (self.snapper.parsed_uri.project,))

	def refresh_history_table (self):
		data: List[HistoryDataItem] = self.snapper.get_history_data()
		# print("opening w history", data)

		self.table_snapshots.clearContents()
		self.table_snapshots.setRowCount(len(data))
		# tableWidget.setColumnCount(len(entries[0]))

		for i in range (0, len(data)):

			rowdata = data[i]
			# print("filling line ", i, "w ", rowdata)
			self.table_snapshots.setCellWidget(i, 0, QLabel(rowdata["changename"]))
			self.table_snapshots.setCellWidget(i, 1, QLabel(rowdata["changed_by"]))

			has_date = rowdata["changed_at"] is not None
			if has_date:
				datestr = rowdata["changed_at"].strftime(STRFORMAT_DATETIME)
				self.table_snapshots.setCellWidget(i, 2, QLabel(datestr))


			btn_delete = QPushButton()
			btn_delete.setFlat(True)
			btn_delete.setToolTip("Elimina questa versione dallo storico")
			btn_delete.setIcon(QIcon(":images/themes/default/mActionDeleteSelected.svg"))
			btn_delete.clicked.connect(self.get_delete_requester(rowdata))
			self.table_snapshots.setCellWidget(i, 5, btn_delete)

			btn_promote = QPushButton()
			btn_promote.setFlat(True)
			btn_promote.setToolTip("Promuovi a versione corrent per tutti")
			btn_promote.setIcon(QIcon(":images/themes/default/mActionCollapseTree.svg"))
			btn_promote.clicked.connect(self.get_promote_requester(rowdata))
			self.table_snapshots.setCellWidget(i, 3, btn_promote)

			btn_backup = QPushButton()
			btn_backup.setFlat(True)
			btn_backup.setToolTip("Salva snapshot su disco")
			btn_backup.clicked.connect(self.get_backup_requester(rowdata))
			btn_backup.setIcon(QIcon(":images/themes/default/mActionFileSaveAs.svg"))
			self.table_snapshots.setCellWidget(i, 4, btn_backup)


	def get_change_desc (self, change: HistoryDataItem):
		fulldesc = ""
		title = change["changename"] if change["changename"] is not None else ""
		if len(title.strip()) > 0:
			fulldesc += "la modifica " + title
		else:
			fulldesc += "questa modifica"

		author = change["changed_by"] if change["changed_by"] is not None else ""
		if len(author.strip()) > 0:
			fulldesc += " di " + author

		changedate = change["changed_at"]
		if changedate is not None:
			datestr = changedate.strftime(STRFORMAT_DATE)
			timestr = changedate.strftime(STRFORMAT_TIME)
			fulldesc += " del %s alle %s" % (datestr, timestr)

		return fulldesc

	def get_delete_requester(self, change: HistoryDataItem):
		def internal ():
			self.request_delete_history_item(change)
		return internal

	def request_delete_history_item(self, change: HistoryDataItem):
		changedesc = self.get_change_desc(change)
		print("had request to remove ", change)
		msgBox = QMessageBox(self)
		msgBox.setText("Conferma eliminazione")
		msgBox.setInformativeText("Vuoi cancellare %s dallo storico?" % (changedesc,))
		msgBox.setStandardButtons(QMessageBox.Ok | QMessageBox.StandardButton.Cancel)
		msgBox.setDefaultButton(QMessageBox.Cancel)
		result = msgBox.exec()
		if result == QMessageBox.Ok:
			try:
				print("delete confirmed")
				self.snapper.delete_change(change["changeid"])
				self.refresh_history_table()
			except Exception as ex:
				self.messageBar.pushMessage("Cancellazione fallita: " + str(ex), level=Qgis.Critical)
				self.refresh_history_table()
		else:
			print("delete cancelled")

	def get_backup_requester (self, change: HistoryDataItem):
		def internal ():
			self.request_download_history_item(change)
		return internal

	def request_download_history_item(self, change: HistoryDataItem):
		dialog = QFileDialog(self)
		dialog.setFileMode(QFileDialog.AnyFile)
		dialog.setViewMode(QFileDialog.Detail)
		dialog.setDefaultSuffix("qgz")
		dialog.setNameFilter("Qgis compressed project (*.qgz)")
		dialog.setAcceptMode(QFileDialog.AcceptSave)
		if dialog.exec_():
			try:
				selection = dialog.selectedFiles()
				if selection is not None and len(selection) == 1:
					dest_path = selection[0]
					data_checksum = self.snapper.get_change_data_raw(change["changeid"])
					content = data_checksum["content"]
					with open(dest_path, 'w+b') as fp:
						fp.write(content)
					self.messageBar.pushMessage("Modifica salvata localmente su : " + str(dest_path), level=Qgis.Success)

			except Exception as ex:
				self.messageBar.pushMessage("Cancellazione fallita: " + str(ex), level=Qgis.Critical)
				pass


	def get_promote_requester (self, change: HistoryDataItem):
		def internal ():
			self.request_promote_history_item(change)
		return internal

	def request_promote_history_item(self, change: HistoryDataItem):
		changedesc = self.get_change_desc(change)
		print("had request to promote ", change)
		msgBox = QMessageBox(self)
		msgBox.setText("Promozione modifica")
		msgBox.setInformativeText("Vuoi promuovere %s a working copy?" % (changedesc,))
		msgBox.setStandardButtons(QMessageBox.Ok | QMessageBox.StandardButton.Cancel)
		msgBox.setDefaultButton(QMessageBox.Cancel)
		result = msgBox.exec()
		if result == QMessageBox.Ok:
			print("promote confirmed")
			try:
				self.snapper.promote_snapshot(change["changeid"])
				self.promoted_snapshot.emit(change["changeid"])
				self.close()
			except Exception as ex:
				self.messageBar.pushMessage("Promozione a working copy fallita: " + str(ex), level=Qgis.Critical)
		else:
			print("promote cancelled")
