"""Entry point — launches the Win-AirPlay GUI."""

import sys

# Ensure the project root is on the path when run as a script or bundled exe.
import os
sys.path.insert(0, os.path.dirname(__file__))

from gui.app import App


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
