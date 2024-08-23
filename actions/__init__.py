from .actions import Action
from .connect import Connect
from .connect_or_open import ConnectOrOpen
from .disconnect import Disconnect
from .quit_and_disconnect import QuitAndDisconnect
from .refresh import Refresh
from .run_async import RunAsync

__all__ = (
    Action,
    Connect,
    ConnectOrOpen,
    Disconnect,
    QuitAndDisconnect,
    Refresh,
    RunAsync
)

actions = {'connect': 'Connect',
            'connect_or_open': 'ConnectOrOpen',
            'disconnect': 'Disconnect',
            'quit_and_disconnect': 'QuitAndDisconnect',
            'refresh': 'Refresh',
            'run_async': 'RunAsync'
           }
