# /*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */

import os
import commons
import shutil

install_phase = commons.PRE_INSTALL
enabled = True


def execute(installer):
    if (
        'preinstall' not in installer.install_config
        and 'preinstallscripts' not in installer.install_config
    ):
        return

    tempdir = "/tmp/tempscripts"
    scripts = []
    if not os.path.exists(tempdir):
        os.mkdir(tempdir)

    if 'preinstall' in installer.install_config:
        installer.logger.info("Run preinstall script")
        script = installer.install_config['preinstall']

        script_file = os.path.join(tempdir, 'builtin_preinstall.sh')

        with open(script_file, 'wb') as outfile:
            outfile.write("\n".join(script).encode())
        os.chmod(script_file, 0o700)
        scripts.append('builtin_preinstall.sh')

    if 'preinstallscripts' in installer.install_config:
        for scriptname in installer.install_config['preinstallscripts']:
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
        installer.logger.info("Running script {}".format(script))
        cmd = ["/bin/bash"]
        cmd.append("-c")
        cmd.append("set -a && source {}/{} && env -0".format(tempdir, script))
        installer.cmd.run(cmd, True)

    shutil.rmtree(tempdir, ignore_errors=True)
