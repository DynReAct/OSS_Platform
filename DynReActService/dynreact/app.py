from dynreact.app_config import DynReActSrvConfig, ConfigProvider
from dynreact.plugins import Plugins
from dynreact.state import DynReActSrvState

config: DynReActSrvConfig = ConfigProvider.config
plugins = Plugins(config)
state = DynReActSrvState(config, plugins)
