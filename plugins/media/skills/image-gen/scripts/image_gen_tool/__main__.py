import sys

from .cli import main
from .config import load_settings

# The wrapper path: export the settings to the process environment (proxies, CA bundles, HF_HOME, cleared client
# variables) for the libraries and child processes that read them; an in-process `main(argv)` leaves it unchanged.
load_settings()
sys.exit(main())
