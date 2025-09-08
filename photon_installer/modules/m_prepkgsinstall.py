# /*
# * Copyright © 2024 Broadcom, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */

import os
import shutil

import commons

install_phase = commons.PRE_PKGS_INSTALL
enabled = True


def execute(installer):
    if (
        'prepkgsinstall' not in installer.install_config
        and 'prepkgsinstallscripts' not in installer.install_config
    ):
        return

    os.environ['POI_ROOT'] = installer.photon_root

    scripts = []

    tmpdir = os.path.join("/tmp", "prepkgs-install")
    os.makedirs(tmpdir, exist_ok=True)

    if 'prepkgsinstall' in installer.install_config:
        script_name = "prepkgsinstall-tmp.sh"
        commons.make_script(tmpdir, script_name, installer.install_config['prepkgsinstall'])
        scripts.append(os.path.join(tmpdir, script_name))

    for script in installer.install_config.get('prepkgsinstallscripts', []):
        script_file = installer.getfile(script)
        shutil.copy(script_file, tmpdir)
        scripts.append(os.path.join(tmpdir, os.path.basename(script_file)))

    commons.execute_scripts(installer, scripts)

    shutil.rmtree(tmpdir, ignore_errors=True)
