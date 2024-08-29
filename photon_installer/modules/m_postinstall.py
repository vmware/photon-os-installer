# /*
# * Copyright © 2020-2024 Broadcom, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */

import os
import commons
import shutil


install_phase = commons.POST_INSTALL
enabled = True


def execute(installer):
    if (
        'postinstall' not in installer.install_config
        and 'postinstallscripts' not in installer.install_config
    ):
        return

    scripts = []

    tmpdir = os.path.join("/tmp", "post-install")
    tmpdir_abs = os.path.join(installer.photon_root, tmpdir.lstrip("/"))
    os.makedirs(tmpdir_abs, exist_ok=True)

    if 'postinstall' in installer.install_config:
        script_name = "postinstall-tmp.sh"
        commons.make_script(tmpdir_abs, script_name, installer.install_config['postinstall'])
        scripts.append(os.path.join(tmpdir, script_name))

    for script in installer.install_config.get('postinstallscripts', []):
        script_file = installer.getfile(script)
        shutil.copy(script_file, tmpdir_abs)
        scripts.append(os.path.join(tmpdir, os.path.basename(script_file)))

    commons.execute_scripts(installer, scripts, chroot=installer.photon_root)

    shutil.rmtree(tmpdir_abs, ignore_errors=True)
