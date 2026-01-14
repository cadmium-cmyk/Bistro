import sys
import os
from gi.repository import Gio
from bistro.app import UnifiedApp

if __name__ == "__main__":

    app = UnifiedApp()
    sys.exit(app.run(sys.argv))
    
