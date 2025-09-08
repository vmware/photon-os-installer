# /*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */

import os
import shutil

import commons

install_phase = commons.PRE_INSTALL
enabled = True


def execute(installer):
    if (
        'preinstall' not in installer.install_config
        and 'preinstallscripts' not in installer.install_config
    ):
        return

    scripts = []

    tmpdir = os.path.join("/tmp", "pre-install")
    os.makedirs(tmpdir, exist_ok=True)

    if 'preinstall' in installer.install_config:
        script_name = "preinstall-tmp.sh"
        commons.make_script(tmpdir, script_name, installer.install_config['preinstall'])
        scripts.append(os.path.join(tmpdir, script_name))

    for script in installer.install_config.get('preinstallscripts', []):
        script_file = installer.getfile(script)
        shutil.copy(script_file, tmpdir)
        scripts.append(os.path.join(tmpdir, os.path.basename(script_file)))

    commons.execute_scripts(installer, scripts, update_env=True)

    shutil.rmtree(tmpdir, ignore_errors=True)
