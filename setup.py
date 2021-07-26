#
# Copyright © 2020-2021 VMware, Inc.
# SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
#

from version import get_installer_version
from setuptools import setup, find_packages


setup(name='photon-installer',
      description='Installer code for photon',
      packages=find_packages(include=['photon_installer', 'photon_installer.modules']),
      include_package_data=True,
      version=get_installer_version(),
      author_email='gpiyush@vmware.com')
