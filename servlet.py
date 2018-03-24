#!/usr/bin/env python3

import os
import sys

sys.path.append(os.path.join(os.path.abspath(os.path.dirname(__file__)), './apertium_apy'))
from apy import main  # noqa: E402

if __name__ == '__main__':
    main()
