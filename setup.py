#
# Copyright © 2020-2023 VMware, Inc.
# SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
#

import os
from version import get_installer_version
from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(here, "requirements.txt")) as requirements_txt:
    REQUIRES = requirements_txt.read().splitlines()

setup(
    name='photon-installer',
    description='Installer code for photon',
    packages=find_packages(include=['photon_installer', 'photon_installer.modules']),
    install_requires=REQUIRES,
    include_package_data=True,
    zip_safe=False,
    entry_points={
        'console_scripts': [
            'photon-installer = photon_installer.main:main',
            'photon-iso-builder = photon_installer.isoBuilder:main'
        ]
    },
    version='2.1+'+get_installer_version(),
    author_email='gpiyush@vmware.com'
)
