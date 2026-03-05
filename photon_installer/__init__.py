#
# Copyright © 2020-2021 VMware, Inc.
# SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
#

import glob
import os
import sys
from importlib.metadata import version

modules = glob.glob(os.path.join(os.path.dirname(__file__), "*.py"))
__all__ = [os.path.basename(f)[:-3] for f in modules if os.path.isfile(f) and not f.endswith('__init__.py')]
sys.path.append(os.path.dirname(__file__))

__version__ = version(__name__)
