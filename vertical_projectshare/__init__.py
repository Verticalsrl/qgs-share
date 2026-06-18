def classFactory(iface):
	from .plugin_runner import PluginRunner
	return PluginRunner(iface)
