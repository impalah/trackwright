"""``python -m trackwright`` is the same as the ``trackwright`` executable."""

import sys

from trackwright.cli import main

sys.exit(main())
