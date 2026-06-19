import time
from abc import ABC
from types import SimpleNamespace
from typing import Dict, TypedDict
import datetime

# qgis.PyQt re-exports PyQt5 on QGIS 3 (Qt5) and PyQt6 on QGIS 4 (Qt6): same code, both versions
from qgis.PyQt.QtCore import QObject, pyqtSlot, pyqtSignal, QThread

from .project_connector import ProjectUpdateState
from .backends import make_backend



class HistoryDataItem (TypedDict):
	changeid:				str
	changename:				str
	project:				str
	metadata:				Dict
	changed_by:				str
	changed_at:				datetime.datetime
	notes:					str
	checksum:				str


class SnapShooterListener (ABC):

	def on_state_update_check(self, collected_at: float, state: ProjectUpdateState):
		raise NotImplementedError


class VerticalShareSnapper:
	"""storage-agnostic versioning facade: keeps the polling thread and exposes
	the same API as before, delegating every DB operation to a backend
	(PostgreSQL or GeoPackage) chosen from the project URI."""

	INSTANCES: Dict[str, "VerticalShareSnapper"] = {}

	@staticmethod
	def get_for (uri: str):
		if uri not in VerticalShareSnapper.INSTANCES:
			VerticalShareSnapper.INSTANCES[uri] = VerticalShareSnapper(uri)
		return VerticalShareSnapper.INSTANCES[uri]

	def __init__(self, uri: str):
		self.backend = make_backend(uri)
		# kept for the dialog labels (project name / author) regardless of backend
		self.parsed_uri = SimpleNamespace(project=self.backend.project, username=self.backend.username)

		self.watcher_worker: ProjectStatePollerWorker = None
		self.watcher_thread: QThread = None

		self.listener: SnapShooterListener = None

	# --- versioning operations (delegated to the backend) ------------------ #

	def get_live_project_update_state (self):
		return self.backend.get_project_update_state()

	def get_latest_snaphost_hash(self):
		return self.backend.get_latest_snapshot_hash()

	def ensure_history_schema_table(self):
		self.backend.ensure_history_table()

	def save_project_snapshot(self, changename: str, notes: str):
		self.ensure_history_schema_table()
		self.backend.save_snapshot(changename, notes)

	def has_schema_tables(self):
		return self.backend.has_history_table()

	def get_history_data (self):
		return self.backend.get_history()

	def get_change_data_raw(self, changeid: str):
		return self.backend.get_change_raw(changeid)

	def delete_change(self, changeid: str):
		self.backend.delete_change(changeid)

	def promote_snapshot (self, changeid: str):
		self.backend.promote(changeid)

	# --- background polling ------------------------------------------------ #

	def on_project_polled (self, ts: float, data: ProjectUpdateState):
		print("project polled at ", ts, data)
		if self.listener is not None:
			self.listener.on_state_update_check(ts, data)

	def start_watch (self):
		if self.watcher_worker is None:
			self.watcher_thread = QThread()
			self.watcher_worker = ProjectStatePollerWorker(self)
			self.watcher_worker.moveToThread(self.watcher_thread)
			self.watcher_worker.on_polling_update.connect(self.on_project_polled)
			self.watcher_thread.start()
			self.watcher_worker.trigger_start.emit()
			print("launched watcher thread ", self.watcher_thread, "worker", self.watcher_worker)
		else:
			print("watcher already running")

	def end_watch (self):

		# FIRST you ALWAYS stop the worker

		if self.watcher_worker is not None:
			print("trying to soft-stop the worker")
			self.watcher_worker.trigger_stop.emit()
		else:
			print("alread stopped worker ", self.watcher_worker, "on", self.watcher_thread)

		if self.watcher_thread is not None:
			print("quitting signal thread")
			self.watcher_thread.quit()
			self.watcher_thread.wait()
			self.watcher_thread = None
		else:
			print("no signal thread running")

		self.watcher_worker = None

	def poll_once (self):
		if self.watcher_worker is not None:
			self.watcher_worker.poll_once()


class ProjectStatePollerWorker (QObject):

	on_polling_update = pyqtSignal(float, dict)  # timestamp, data
	is_running: bool

	trigger_start = pyqtSignal()
	trigger_stop = pyqtSignal()

	def __init__(self, master: "VerticalShareSnapper"):
		super().__init__()
		self.is_running = False
		self.master = master
		self.wait_time = 60
		self.trigger_start.connect(self.start_run)
		self.trigger_stop.connect(self.end_run_clean)

	# NOTE: starter signal callback MUST have pyqtSlot to avoid being blocking
	# ender signal callback MUST NOT have pyqtSlot

	@pyqtSlot()
	def start_run(self, *args, **kwargs):
		print("received start signal", args, kwargs)
		if not self.is_running:
			self.poll_and_wait()
		else:
			print("already running wait_and_signal")

	def end_run_clean (self, *args, **kwargs):
		print("received end signal", args, kwargs)
		if self.is_running:
			self.is_running = False
		else:
			print("already stopped I suppose")

	def breakable_wait_cycle (self,):
		to_wait = self.wait_time
		for i in range(0, to_wait):
			if self.is_running:
				time.sleep(1)
			else:
				break

	def poll_and_wait(self):
		print("polling every %d seconds" % self.wait_time)
		self.is_running = True
		while self.is_running:
			update_state: ProjectUpdateState = self.master.get_live_project_update_state()
			ctimestamp = time.time()
			self.on_polling_update.emit(ctimestamp, update_state)
			self.breakable_wait_cycle()
		print("polling finished")

	def poll_once (self):
		update_state: ProjectUpdateState = self.master.get_live_project_update_state()
		ctimestamp = time.time()
		self.on_polling_update.emit(ctimestamp, update_state)
