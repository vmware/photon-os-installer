#/*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */

import os
import subprocess
import commons
import shutil

install_phase = commons.POST_INSTALL
enabled = True

def execute(installer):
    if 'postinstall' not in installer.install_config and 'postinstallscripts' not in installer.install_config:
        return

    tempdir = "/tmp/tempscripts"
    tempdir_full = installer.photon_root + tempdir
    scripts = []
    if not os.path.exists(tempdir_full):
        os.mkdir(tempdir_full)

    if 'postinstall' in installer.install_config:
        installer.logger.info("Run postinstall script")
        # run the script in the chroot environment
        script = installer.install_config['postinstall']

        script_file = os.path.join(tempdir_full, 'builtin_postinstall.sh')

        with open(script_file, 'wb') as outfile:
            outfile.write("\n".join(script).encode())
        os.chmod(script_file, 0o700)
        scripts.append('builtin_postinstall.sh')

    if 'postinstallscripts' in installer.install_config:
        for scriptname in installer.install_config['postinstallscripts']:
            script_file = installer.getfile(scriptname)
            shutil.copy(script_file, tempdir_full)
            scripts.append(os.path.basename(scriptname))

    for script in scripts:
        if not os.access(os.path.join(tempdir_full, script), os.X_OK):
            installer.logger.warning("Post install script {} is not executable. Skipping execution of script.".format(script))
            continue
        installer.logger.info("Running script {}".format(script))
        installer.cmd.run_in_chroot(installer.photon_root, "{}/{}".format(tempdir, script))

    shutil.rmtree(tempdir_full, ignore_errors=True)
