# some constants for use across py files
# some may disappear as soon as I find a clean way to get to metadata.txt (rn depends on physical folder name which MAY change for any reason)
import datetime
import os

from qgis._core import QgsCoordinateReferenceSystem

PATH_SCRIPTS = os.path.dirname(os.path.realpath(__file__))
PATH_DATA = os.path.join(PATH_SCRIPTS, "data")
PATH_RESOURCES = os.path.join(PATH_SCRIPTS, "resources")
PATH_ICONS = os.path.join(PATH_RESOURCES, "icons")


def icon_path(name: str) -> str:
	"""full filesystem path to a bundled svg icon (e.g. icon_path('history.svg'))"""
	return os.path.join(PATH_ICONS, name)


def to_local_time(dt: "datetime.datetime"):
	"""QGIS stores last_modified_time in UTC: a naive value coming from the db is
	interpreted as UTC and converted to the local timezone for display."""
	if dt is None:
		return None
	if dt.tzinfo is None:
		dt = dt.replace(tzinfo=datetime.timezone.utc)
	return dt.astimezone()


# for logging
PLUGIN_ID= "VerticalProjectShare"

# for window title, both should be synced with metadata.txt
PLUGIN_TITLE= "Vertical Project Share"

with open(os.path.join(PATH_SCRIPTS, "release.version")) as fp:
	try:
		PLUGIN_VERSION = fp.read().strip()
	except:
		PLUGIN_VERSION = "UNKNOWN"

TABLE_VERTICAL_SHARE = "qgis_projects_share_history"
TABLE_PROJECTS_QGIS = "qgis_projects"

VERTICAL_STORAGETYPE="verticalDbShare"
VERTICAL_STORAGENAME="Vertical Project Share"

VERTICAL_STORAGEPREFIX="verticalshare://"


STRFORMAT_DATE = "%d/%m/%Y"
STRFORMAT_DATETIME = "%d/%m/%Y %H:%M"
STRFORMAT_TIME = "%H:%M"
