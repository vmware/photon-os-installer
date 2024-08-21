# /*
# * Copyright © 2024 Broadcom, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */

import os
import commons
import shutil

install_phase = commons.PRE_PKGS_INSTALL
enabled = True


def execute(installer):
    if (
        'prepkgsinstall' not in installer.install_config
        and 'prepkgsinstallscripts' not in installer.install_config
    ):
        return

    tempdir = "/tmp/tempscripts"
    scripts = []
    if not os.path.exists(tempdir):
        os.mkdir(tempdir)

    os.environ['POI_ROOT'] = installer.photon_root

    if 'prepkgsinstall' in installer.install_config:
        installer.logger.info("Run prepkgsinstall script")
        script = installer.install_config['prepkgsinstall']

        script_file = os.path.join(tempdir, 'builtin_prepkgsinstall.sh')

        with open(script_file, "wt") as outfile:
            for line in script:
                outfile.write(f"{line}\n")
        os.chmod(script_file, 0o700)
        scripts.append('builtin_prepkgsinstall.sh')

    if 'prepkgsinstallscripts' in installer.install_config:
        for scriptname in installer.install_config['prepkgsinstallscripts']:
            script_file = installer.getfile(scriptname)
            shutil.copy(script_file, tempdir)
            scripts.append(os.path.basename(scriptname))

    for script in scripts:
        if not os.access(os.path.join(tempdir, script), os.X_OK):
            installer.logger.warning(
                f"Pre install script {script} is not executable. "
                "Skipping execution of script."
            )
            continue
        installer.logger.info(f"Running script {script}")
        cmd = ["/bin/bash"]
        cmd.append("-c")
        cmd.append(f"set -a && source {tempdir}/{script} && env -0")
        installer.cmd.run(cmd, True)

    shutil.rmtree(tempdir, ignore_errors=True)
