# /*
# * Copyright © 2020-2024 Broadcom, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */

import os
import commons
import shutil


install_phase = commons.POST_INSTALL
enabled = True


def _execute_scripts(installer, scripts):
    for script in scripts:
        if not os.access(os.path.join(installer.photon_root, script.lstrip("/")), os.X_OK):
            raise Exception(f"post install script {script} is not executable. ")
        installer.logger.info(f"Running script {script}")
        retval = installer.cmd.run_in_chroot(installer.photon_root, script)
        if retval != 0:
            raise Exception(f"script {script} failed")


def _make_script(dir, script_name, lines):
    script = os.path.join(dir, script_name)

    with open(script, "wt") as f:
        for l in lines:
            f.write(f"{l}\n")

    os.chmod(script, 0o700)


def execute(installer):
    if (
        'postinstall' not in installer.install_config
        and 'postinstallscripts' not in installer.install_config
    ):
        return

    script = None
    scripts = []

    tmpdir = os.path.join("/tmp", "post-install")
    tmpdir_abs = os.path.join(installer.photon_root, tmpdir.lstrip("/"))
    os.makedirs(tmpdir_abs, exist_ok=True)

    if 'postinstall' in installer.install_config:
        script_name = "postinstall-tmp.sh"
        script = _make_script(tmpdir_abs, script_name, installer.install_config['postinstall'])
        scripts.append(os.path.join(tmpdir, script_name))

    for script in installer.install_config.get('postinstallscripts', []):
        script_file = installer.getfile(script)
        shutil.copy(script_file, tmpdir_abs)
        scripts.append(os.path.join(tmpdir, os.path.basename(script_file)))

    _execute_scripts(installer, scripts)

    shutil.rmtree(tmpdir_abs, ignore_errors=True)
