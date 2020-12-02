#/*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */
from setuptools import setup, find_packages

setup(name='photon-installer',
      version='4.0',
      description='Installer code for photon',
      packages=find_packages(include=['photon_installer', 'photon_installer.modules']),
      include_package_data=True,
      author_email='gpiyush@vmware.com')
