# some constants for use across py files
# some may disappear as soon as I find a clean way to get to metadata.txt (rn depends on physical folder name which MAY change for any reason)
import os

from qgis._core import QgsCoordinateReferenceSystem

PATH_SCRIPTS = os.path.dirname(os.path.realpath(__file__))
PATH_DATA = os.path.join(PATH_SCRIPTS, "data")

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
