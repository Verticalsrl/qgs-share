import os
import time

# Qt5/Qt6 compatible: qgis.PyQt re-exports PyQt5 on QGIS 3 (Qt5) and PyQt6 on QGIS 4 (Qt6);
# qgis.core/qgis.gui are the public API (not the private qgis._core/_gui). Same code, both versions.
from qgis.PyQt.QtCore import QObject, pyqtSignal, pyqtSlot, QThread
from qgis.PyQt.QtGui import QIcon
# note: QAction is NOT imported here on purpose -> in Qt6 it lives in QtGui, not QtWidgets
from qgis.PyQt.QtWidgets import QToolBar, QWidget, QCheckBox, QLabel, QMenu, QPushButton, QFileDialog, QDialog, QVBoxLayout, QTextBrowser, QDialogButtonBox
from qgis.core import QgsApplication, QgsProject, Qgis
from qgis.gui import QgisInterface, QgsGui, QgsMessageBar

from .constants import PLUGIN_TITLE, PLUGIN_VERSION, icon_path, to_local_time
from .project_connector import DbProjectConnector
from .dialog_project_history import ProjectHistoryDialog
from .snapshooter import VerticalShareSnapper, ProjectUpdateState, SnapShooterListener
from .dialog_snapshot_save import SnapshotSaveDialog



class PluginRunner (SnapShooterListener):


	toolbar: QToolBar

	flag_versioning_on: bool

	control_toggle_versioning: QCheckBox
	button_project_history: QPushButton

	flag_savesyncmode: bool # when the project is syncing metadata so it will IGNORE update calls from poller

	def __init__(self, iface):
		"""
		sets up the UI connections (toolbars, windows, etc)
		:param iface: UI connection to QGIS
		"""

		self.iface: QgisInterface = iface
		self.plugin_dir = os.path.dirname(__file__)

		self.menuId = "Vertical Project Share"

		# self.action_enable_versioning = QAction("enable versioning")
		# self.action_enable_versioning.triggered.connect(self.enable_project_versioning)
		# self.iface.addPluginToMenu(self.menuId, self.action_enable_versioning)
		#
		# self.action_disable_versioning = QAction("disable_versioning")
		# self.action_disable_versioning.triggered.connect(self.disable_project_versioning)
		# self.iface.addPluginToMenu(self.menuId, self.action_disable_versioning)


		self.toolbar = self.iface.addToolBar(self.menuId)
		self.toolbar.setObjectName(self.menuId)

		bartitle = QLabel()
		bartitle.setText("VerticalShare  ")
		self.toolbar.addWidget(bartitle)

		self.button_save = QPushButton()
		self.button_save.setObjectName("BUTTON_SAVE")
		self.button_save.setIcon(QIcon(icon_path("save.svg")))
		self.button_save.setFlat(True)
		self.button_save.setToolTip("Salva il progetto")
		self.button_save.clicked.connect(self.on_save_request)
		self.toolbar.addWidget(self.button_save)

		self.control_toggle_versioning = QCheckBox()
		self.control_toggle_versioning.setText("versionamento attivo")
		self.control_toggle_versioning.setIcon(QIcon(icon_path("versioning.svg")))
		self.toolbar.addWidget(self.control_toggle_versioning)
		self.control_toggle_versioning.clicked.connect(self.toggle_project_versioning)


		self.button_project_history = QPushButton()
		history_icon = QIcon(icon_path("history.svg"))
		self.button_project_history.setIcon(history_icon)
		self.button_project_history.setFlat(True)
		self.button_project_history.setToolTip("Lista snapshot")
		self.button_project_history.clicked.connect(self.open_history_dialog)
		self.toolbar.addWidget(self.button_project_history)


		self.button_sync: QPushButton = QPushButton()
		self.button_sync.setObjectName("BUTTON_SYNC")
		self.button_sync.setIcon(QIcon(icon_path("sync.svg")))
		self.button_sync.setFlat(True)
		self.button_sync.setToolTip("Ricarica versione aggiornata dal db")
		self.button_sync.clicked.connect(self.reload_project_from_db)
		self.toolbar.addWidget(self.button_sync)

		self.button_check_updates: QPushButton = QPushButton()
		self.button_check_updates.setObjectName("BUTTON_CHECKUPDATES")
		self.button_check_updates.setIcon(QIcon(icon_path("check_updates.svg")))
		self.button_check_updates.setFlat(True)
		self.button_check_updates.setToolTip("Verifica aggiornamenti su db")
		self.button_check_updates.clicked.connect(self.check_updates_manually)
		self.toolbar.addWidget(self.button_check_updates)

		self.desync_notified: ProjectUpdateState = None

		self.button_project_quickdump = QPushButton()
		self.button_project_quickdump.setObjectName("BUTTON_QUICKDUMP")
		self.button_project_quickdump.setFlat(True)
		self.button_project_quickdump.setToolTip("Salva copia locale in QGZ")
		self.button_project_quickdump.setIcon(QIcon(icon_path("save_local.svg")))
		self.button_project_quickdump.clicked.connect(self.on_project_dump_request)
		self.toolbar.addWidget(self.button_project_quickdump)

		self.button_info = QPushButton()
		self.button_info.setObjectName("BUTTON_INFO")
		self.button_info.setIcon(QIcon(icon_path("info.svg")))
		self.button_info.setFlat(True)
		self.button_info.setToolTip("Informazioni e istruzioni d'uso")
		self.button_info.clicked.connect(self.open_info_dialog)
		self.toolbar.addWidget(self.button_info)

		# always-visible notification bell: idle (grey) when aligned, alert (red dot)
		# when the db holds a newer version. Click reloads when alerting, otherwise
		# checks the db right away.
		self.out_of_sync = False
		self.button_notify = QPushButton()
		self.button_notify.setObjectName("BUTTON_NOTIFY")
		self.button_notify.setIcon(QIcon(icon_path("bell.svg")))
		self.button_notify.setFlat(True)
		self.button_notify.clicked.connect(self.on_notify_clicked)
		self.toolbar.addWidget(self.button_notify)
		# note: the bell state is initialised by setActiveStates() below, once
		# flag_versioning_on exists

		self.iface.addToolBar(self.toolbar)

		self.flag_versioning_on = False

		self.setActiveStates()

		QgsProject.instance().readProject.connect(self.on_project_load)
		QgsProject.instance().projectSaved.connect(self.on_project_save)
		QgsProject.instance().cleared.connect(self.on_project_closed)
		QgsProject.instance().dirtySet.connect(self.on_project_changing)

		self.versionable_changes_left = False

		self.latest_state: ProjectUpdateState = None
		self.snapper: VerticalShareSnapper = None

		self.cproject_uri = None

		self.flag_savesyncmode = False

		self.savesync_thread: QThread = None
		self.savesync_worker: ProjectSaverWatcherWorker = None

	def dump_project_copy_to (self, filepath):
		p = QgsProject.instance()
		# save the current dirtyness and name
		dirtState = p.isDirty()
		src_uri = p.fileName()
		savedir = p.fileInfo().absolutePath()
		# set the new name and write it
		p.setFileName(os.path.join(savedir,filepath))
		p.write()

		# restore original name and dirtiness
		p.setFileName(src_uri)
		p.setDirty(dirtState)

		self.setActiveStates()

		return True

	def on_state_update_check (self, ts: float, state: ProjectUpdateState):
		# print ("received at ", ts, "state_local", self.latest_state, "state_db", state, "check", state == self.latest_state)
		if self.flag_savesyncmode or state is None:
			return
		if state != self.latest_state:
			self.show_out_of_sync(state)
		else:
			self.clear_out_of_sync()

	def desync_description (self, state: ProjectUpdateState):
		author = state.get("last_author") or "un altro utente"
		when = to_local_time(state["last_updated"]).strftime("%H:%M") if state.get("last_updated") else "?"
		return author, when

	def update_notify_ui (self):
		"""reflect the current sync state on the always-visible notification bell"""
		if self.out_of_sync:
			self.button_notify.setIcon(QIcon(icon_path("bell_alert.svg")))
		else:
			self.button_notify.setIcon(QIcon(icon_path("bell.svg")))
			if self.flag_versioning_on:
				self.button_notify.setToolTip("Sei allineato all'ultima versione. Clicca per verificare ora.")
			else:
				self.button_notify.setToolTip("Attiva il versionamento per ricevere le notifiche di nuove versioni.")

	def show_out_of_sync (self, state: ProjectUpdateState):
		"""idempotent indicator: the bell stays in 'alert' until realignment,
		while the message bar heads-up fires only once per distinct new version"""
		author, when = self.desync_description(state)
		self.out_of_sync = True
		self.button_notify.setIcon(QIcon(icon_path("bell_alert.svg")))
		self.button_notify.setToolTip(
			"Nuova versione disponibile (aggiornata da %s alle %s). Clicca per ricaricare dal db." % (author, when))
		# one-shot heads-up only when this specific new version was not announced yet
		if self.desync_notified != state:
			message = "Aggiornata da %s alle %s. Ricarica per allinearti." % (author, when)
			widget = self.iface.messageBar().createMessage("Progetto aggiornato su db", message)
			self.iface.messageBar().pushWidget(widget, level=Qgis.MessageLevel.Warning)
			self.desync_notified = state

	def clear_out_of_sync (self):
		self.out_of_sync = False
		self.desync_notified = None
		self.update_notify_ui()

	def on_notify_clicked (self):
		if self.out_of_sync:
			self.reload_project_from_db()
			return
		if self.flag_versioning_on and self.snapper is not None:
			self.check_updates_manually()
			if not self.out_of_sync:
				self.iface.messageBar().pushMessage("Nessuna nuova versione: sei allineato all'ultima.", level=Qgis.MessageLevel.Info)
		else:
			self.iface.messageBar().pushMessage("Attiva il versionamento per ricevere le notifiche.", level=Qgis.MessageLevel.Info)

	def reload_project_from_db(self):
		was_tracking = self.flag_versioning_on
		print("reloading while tracking status was", was_tracking)
		QgsProject.instance().read()
		self.align_update_state()
		self.clear_out_of_sync()
		self.iface.messageBar().pushMessage("Caricata ultima versione aggiornata dal db principale")
		if was_tracking:
			self.control_toggle_versioning.setChecked(True)
			self.enable_project_versioning()


	def on_save_request(self):
		# reuse QGIS' own save action so the normal save flow (and the
		# projectSaved signal the plugin relies on for versioning) fires
		save_action = self.iface.actionSaveProject()
		if save_action is not None:
			save_action.trigger()
		else:
			QgsProject.instance().write()

	def on_project_dump_request(self):
		dialog = QFileDialog()
		dialog.setFileMode(QFileDialog.FileMode.AnyFile)
		dialog.setViewMode(QFileDialog.ViewMode.Detail)
		dialog.setDefaultSuffix("qgz")
		dialog.setNameFilter("Qgis compressed project (*.qgz)")
		dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
		if dialog.exec():
			try:
				selection = dialog.selectedFiles()
				if selection is not None and len(selection) == 1:
					dest_path = selection[0]
					self.dump_project_copy_to(dest_path)
					self.iface.messageBar().pushMessage("Modifica salvata localmente su : " + str(dest_path), level=Qgis.MessageLevel.Success)
			except Exception as ex:
				self.iface.messageBar().pushMessage("Salvataggio fallito: " + str(ex), level=Qgis.MessageLevel.Critical)

	def on_project_changing(self):
		print("project set to dirty -- straight")
		self.versionable_changes_left = True

	def on_snapshot_promoted (self, changeid: str):
		try:
			QgsProject.instance().read()
			self.align_update_state()
			self.iface.messageBar().pushMessage("Progetto aggiornato da snapshot", level=Qgis.MessageLevel.Info)
		except Exception as ex:
			self.iface.messageBar().pushMessage("Errore nell'aggiornamento del progetto: " + str(ex), level=Qgis.MessageLevel.Critical)

	def open_history_dialog(self):
		print("showing history")
		dialog = ProjectHistoryDialog(QgsProject.instance().fileName())
		dialog.promoted_snapshot.connect(self.on_snapshot_promoted)
		dialog.show()
		dialog.exec()

		# we get no feedback, it's all handled in the dialog

		pass

	def build_info_html(self) -> str:
		return """
			<h2>{title}</h2>
			<p><b>Versione:</b> {version}<br>
			<b>Autore:</b> Vertical Srl &mdash; <a href="https://vertical-srl.it">vertical-srl.it</a></p>
			<p>Condivide e versiona i progetti QGIS salvati su PostgreSQL: ogni
			salvataggio pu&ograve; essere registrato come snapshot nello storico,
			cos&igrave; pi&ugrave; utenti possono lavorare sullo stesso progetto
			senza sovrascriversi a vicenda.</p>
			<h3>Barra degli strumenti</h3>
			<ul>
				<li><b>Salva il progetto</b>: salva il progetto come il normale comando
				di QGIS; con il versionamento attivo propone anche lo snapshot.</li>
				<li><b>Campanella notifiche</b>: sempre visibile. Spenta quando sei
				allineato; con il <b>pallino rosso</b> quando sul database esiste una
				versione pi&ugrave; recente di quella aperta. Cliccala per ricaricare e
				allinearti (o, se sei gi&agrave; allineato, per verificare subito sul db).</li>
				<li><b>Versionamento attivo</b>: quando attivo, a ogni salvataggio
				il plugin propone di registrare una nuova versione nello storico
				e controlla periodicamente se altri hanno aggiornato il progetto sul db.</li>
				<li><b>Lista snapshot</b>: apre lo storico delle versioni del progetto,
				da cui &egrave; possibile promuovere, scaricare o eliminare una versione.</li>
				<li><b>Ricarica versione aggiornata dal db</b>: ricarica dal database
				l'ultima versione corrente del progetto.</li>
				<li><b>Verifica aggiornamenti su db</b>: controlla subito se sul
				database esiste una versione pi&ugrave; recente di quella aperta.</li>
				<li><b>Salva copia locale in QGZ</b>: esporta una copia del progetto
				corrente in un file <code>.qgz</code> sul disco.</li>
				<li><b>Informazioni</b>: questa finestra.</li>
			</ul>
			<h3>Finestra storico</h3>
			<ul>
				<li><b>Promuovi a working copy</b>: rende la versione selezionata
				quella corrente per tutti gli utenti.</li>
				<li><b>Salva snapshot su disco</b>: esporta la versione selezionata
				come file <code>.qgz</code>.</li>
				<li><b>Elimina</b>: rimuove la versione selezionata dallo storico.</li>
			</ul>
			<h3>Requisiti</h3>
			<p>Il plugin si attiva solo quando il progetto aperto &egrave; archiviato
			su PostgreSQL (storage <i>postgresql</i>). Con progetti su file i comandi
			restano disabilitati.</p>
		""".format(title=PLUGIN_TITLE, version=PLUGIN_VERSION)

	def open_info_dialog(self):
		dialog = QDialog(self.iface.mainWindow())
		dialog.setWindowTitle("%s - Informazioni" % PLUGIN_TITLE)
		dialog.setWindowIcon(QIcon(icon_path("info.svg")))
		dialog.resize(560, 600)

		layout = QVBoxLayout(dialog)
		browser = QTextBrowser()
		browser.setOpenExternalLinks(True)
		browser.setHtml(self.build_info_html())
		layout.addWidget(browser)

		buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
		buttons.rejected.connect(dialog.close)
		buttons.accepted.connect(dialog.close)
		layout.addWidget(buttons)

		dialog.exec()

	def prompt_add_version_to_history (self, version_state: ProjectUpdateState):
		self.latest_state = version_state
		self.flag_savesyncmode = False
		self.clear_out_of_sync()
		if self.flag_versioning_on:
			print("now we should ask about how to deal with changes")
			self.on_versionable_save()
		pass

	def clear_savesync_thread_and_worker (self):
		if self.savesync_worker is not None:
			self.savesync_worker.trigger_stop.emit()
		if self.savesync_thread is not None:
			self.savesync_thread.quit()
			self.savesync_thread.wait()
			self.savesync_thread = None
		self.savesync_worker = None
		pass

	def on_save_mode_sync_done(self, ts: float, elapsed: float, state_new: ProjectUpdateState):
		print("found version for alginment in %.2f" % (elapsed,))
		self.prompt_add_version_to_history(state_new)
		self.clear_savesync_thread_and_worker()

	def on_save_mode_sync_fail(self, ts: float, elapsed: float):
		self.iface.messageBar().pushMessage("Verifica allineamento db fallita dopo %d secondi, ricaricare il progetto" % (elapsed,), level=Qgis.MessageLevel.Critical)
		self.flag_savesyncmode = False
		self.clear_savesync_thread_and_worker()

	def sync_update_state (self):
		# DEPRECATED: the old save flow waited on this background watcher to detect
		# the db change before prompting. Now on_project_save versions directly, so
		# this is no longer wired up (kept for reference / possible reuse).
		if not self.flag_savesyncmode:
			self.flag_savesyncmode = True
			self.savesync_thread = QThread()
			self.savesync_worker = ProjectSaverWatcherWorker(self.cproject_uri, self.latest_state, retry_times=10)
			self.savesync_worker.moveToThread(self.savesync_thread)
			self.savesync_worker.on_change_missed.connect(self.on_save_mode_sync_fail)
			self.savesync_worker.on_change_found.connect(self.on_save_mode_sync_done)
			self.savesync_thread.start()
			self.savesync_worker.trigger_start.emit()
		else:
			print("already in save sync mode")

	def align_update_state (self):
		db_state = self.get_shooter(False).get_live_project_update_state()
		print("aligning ", self.latest_state, "to", db_state)
		self.latest_state = {**db_state}
		print("aligned state to ", self.latest_state)

	def isPostgresProject (self):
		projectstorage = QgsProject.instance().projectStorage()
		storagetype = projectstorage.type() if projectstorage is not None else None
		return storagetype == "postgresql"

	def on_project_load(self):
		print("loaded project signal fired")
		# self.marker_unversioned_changes.hide()
		loaded_uri = QgsProject.instance().fileName()
		if self.cproject_uri != loaded_uri:
			self.cproject_uri = loaded_uri
			self.setActiveStates()
		if self.isPostgresProject(): # loading ANYWAY
			print("aligning state")
			self.align_update_state()
		if self.flag_versioning_on:
			self.versionable_changes_left = True
			self.snapper = self.get_shooter()
		self.clear_out_of_sync()

	def on_project_closed(self):
		print("closedproject signal fired")
		# self.marker_unversioned_changes.hide()
		if self.snapper is not None:
			self.snapper.end_watch()
			self.versionable_changes_left = False
			self.latest_state = None
			self.clear_out_of_sync()
		try:
			self.clear_savesync_thread_and_worker()

			self.setActiveStates()

		except Exception as ex:
			print("closing issue (maybe forced?)", str(ex))


	def on_project_save(self):
		print("project saved signal fired")
		self.setActiveStates()
		print("verified plugin state (e.g. project storage change)")
		if not self.isPostgresProject():
			return
		# versioning is a binary choice of the toggle: while it is ON, every save
		# records a version. The only optional thing is the notes.
		if self.flag_versioning_on:
			self.on_versionable_save()
		# realign to the just-saved state so our own save does not light the bell
		self.align_update_state()
		self.clear_out_of_sync()

	def setActiveStates (self):

		projectstorage = QgsProject.instance().projectStorage()
		storagetype = projectstorage.type() if projectstorage is not None else None
		print("storage type is now : ", storagetype, "flag versioning on ", self.flag_versioning_on)

		plugin_enabled = storagetype == "postgresql"
		if not plugin_enabled:
			self.flag_versioning_on = False
			print("disabled plugin and flag is off")
		else:
			print("plugin is enabled and flag is ", self.flag_versioning_on)


		self.button_project_history.setEnabled(plugin_enabled)
		# self.action_enable_versioning.setEnabled(plugin_enabled)
		# self.action_disable_versioning.setEnabled(plugin_enabled)
		# self.action_enable_versioning.setVisible(not self.flag_versioning_on)
		# self.action_disable_versioning.setVisible(self.flag_versioning_on)

		self.control_toggle_versioning.setEnabled(plugin_enabled)
		self.control_toggle_versioning.setChecked(self.flag_versioning_on)
		self.button_sync.setEnabled(plugin_enabled)
		self.button_check_updates.setEnabled(plugin_enabled and self.flag_versioning_on)

		# the notification bell is shown on pg projects; with no live polling
		# (versioning off) it falls back to the idle state
		self.button_notify.setVisible(plugin_enabled)
		if not (plugin_enabled and self.flag_versioning_on):
			self.out_of_sync = False
		self.update_notify_ui()

		if not plugin_enabled or not self.flag_versioning_on:
			# any stuff to do?
			pass

	def get_shooter(self, set_listener=True):
		versionable_uri = QgsProject.instance().fileName()
		shooter = VerticalShareSnapper.get_for(versionable_uri)
		if set_listener:
			shooter.listener = self
		return shooter

	def check_updates_manually (self):
		self.snapper.poll_once()

	def toggle_project_versioning (self):
		if self.control_toggle_versioning.isChecked():
			self.enable_project_versioning()
		else:
			self.disable_project_versioning()
		# self.flag_versioning_on = self.control_toggle_versioning.isChecked()
		# self.setActiveStates()
		# if self.flag_versioning_on:
		# 	self.changes_to_save = True

	def enable_project_versioning (self):
		self.flag_versioning_on = True
		self.versionable_changes_left = True
		self.setActiveStates()
		if self.flag_versioning_on:
			self.versionable_changes_left = True
		if self.snapper is None:
			self.snapper = self.get_shooter()
			self.snapper.ensure_history_schema_table()
		self.snapper.start_watch()


	def disable_project_versioning(self):
		self.flag_versioning_on = False
		self.versionable_changes_left = False
		self.setActiveStates()
		if self.snapper is not None:
			self.snapper.end_watch()


	def on_versionable_save(self):
		# versioning is ON, so we ALWAYS record a version here; the dialog only
		# collects optional notes (Conferma = with notes, Salta = without)
		versionable_uri = QgsProject.instance().fileName()
		print("versioning for ", versionable_uri)
		shooter = VerticalShareSnapper.get_for(versionable_uri)

		dialog = SnapshotSaveDialog()
		dialog.label_changes.setText("Modifiche di %s a %s" % (shooter.parsed_uri.username, shooter.parsed_uri.project))
		dialog.show()
		if dialog.exec():
			changename = dialog.field_snapshot_title.text()
			changenotes = dialog.field_snapshot_notes.toPlainText()
		else:
			# skipped: version saved anyway, just without user notes
			changename = ""
			changenotes = ""

		try:
			shooter.save_project_snapshot(changename, changenotes)
			self.versionable_changes_left = False
			self.iface.messageBar().pushMessage("Versione salvata nello storico", level=Qgis.MessageLevel.Success)
		except Exception as ex:
			self.iface.messageBar().pushMessage("Salvataggio della versione fallito: " + str(ex), level=Qgis.MessageLevel.Critical)


	def initToolbar (self):


		pass

	def initGui(self):
		"""Note that initGUI runs EVERY TIME the plugin is loaded"""
		print("running initGUI method")
		pass

	def unload(self):
		"""cleans up resources when plugin is removed"""
		print("unloading plugin project_share")

		self.disable_project_versioning()
		if self.snapper is not None:
			self.snapper.end_watch()

		try:
			self.toolbar.deleteLater()
			# self.iface.removePluginMenu(self.menuId, self.action_disable_versioning)
			# self.iface.removePluginMenu(self.menuId, self.action_enable_versioning)
		except Exception as ex:
			print("failed to remove toolbar because ", ex)


class ProjectSaverWatcherWorker (QObject):

	on_change_found = pyqtSignal(float, float, dict)  # timestamp, elapsed, data
	on_change_missed = pyqtSignal(float, float) # timestamp, elapsed

	trigger_start = pyqtSignal()
	trigger_stop = pyqtSignal() # no actual need for stop signal but there for turn off etc on longer ones

	def __init__(self, project_uri: str, state_old: ProjectUpdateState, retry_wait=5, retry_times=0):
		super().__init__()
		self.project_connector = DbProjectConnector(project_uri)
		self.state_old = state_old
		self.retry_wait = retry_wait
		self.retry_times = retry_times

		self.is_running = False
		self.trigger_start.connect(self.start_run)
		self.trigger_stop.connect(self.end_run_clean)


	@pyqtSlot()
	def start_run(self, *args, **kwargs):
		print("received start signal", args, kwargs)
		if not self.is_running:
			self.loop_check_updates()
		else:
			print("already running wait_and_signal")

	def end_run_clean (self, *args, **kwargs):
		print("received end signal", args, kwargs)
		if self.is_running:
			self.is_running = False
		else:
			print("already stopped I suppose")

	def breakable_wait_cycle (self,):
		for i in range(0, self.retry_wait):
			if self.is_running:
				time.sleep(1)
			else:
				break

	def loop_check_updates(self):
		self.is_running = True

		tried = 0
		time_start = time.time()
		state_new = self.project_connector.get_project_update_state()
		while state_new == self.state_old and (self.retry_times == 0 or tried <= self.retry_times):
			self.breakable_wait_cycle()
			state_new = self.project_connector.get_project_update_state()
			tried += 1
		time_done = time.time()
		if state_new == self.state_old:
			self.on_change_missed.emit(time_done, time_done-time_start)
		else:
			# print("project state updated from ", state_old, "to", state_new, "in %.2f secs" % (time_diff,))
			# runner.prompt_add_version_to_history(state_new)
			self.on_change_found.emit(time_done, time_done-time_start, state_new)

