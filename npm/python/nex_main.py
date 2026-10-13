"""Starts the NEXORA interpreter bundled in the npm package.

Python puts the directory of this script first in its search path, so `nexora` below is the
copy that sits next to this file, not one installed elsewhere.
"""

import sys

from nexora.cli import main

if __name__ == "__main__":
    sys.exit(main())
