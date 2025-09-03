#
# Copyright © 2020-2021 VMware, Inc.
# SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
#

import glob
import sys
from os.path import basename, dirname, isfile, join

import pkg_resources

modules = glob.glob(join(dirname(__file__), "*.py"))
__all__ = [basename(f)[:-3] for f in modules if isfile(f) and not f.endswith('__init__.py')]
sys.path.append(dirname(__file__))

__version__ = pkg_resources.get_distribution(__name__).version
