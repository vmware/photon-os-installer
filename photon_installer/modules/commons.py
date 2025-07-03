# /*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */

import os
import re

PRE_INSTALL = "pre-install"
PRE_PKGS_INSTALL = "pre-pkgs-install"
POST_INSTALL = "post-install"


def replace_string_in_file(filename, search_string, replace_string):
    with open(filename, "r") as source:
        lines = source.readlines()

    with open(filename, "w") as destination:
        for line in lines:
            destination.write(re.sub(search_string, replace_string, line))


def execute_scripts(installer, scripts, chroot=None, update_env=False):
    for script in scripts:

        abs_path = script
        if chroot is not None:
            abs_path = os.path.join(chroot, script.lstrip("/"))

        if not os.access(abs_path, os.X_OK):
            raise Exception(f"script {script} is not executable. ")

        if update_env:
            # Use set -a to export all variables, then source the script
            # The run() method will handle capturing environment variables
            script = ["/bin/bash", "-c", f"set -a && source {script}"]

        installer.logger.info(f"Running script {script}")
        if chroot is None:
            retval = installer.cmd.run(script, update_env=update_env)
        else:
            retval = installer.cmd.run_in_chroot(chroot, script, update_env=update_env)
        if retval != 0:
            raise Exception(f"script {script} failed")


def make_script(dir, script_name, lines):
    script = os.path.join(dir, script_name)

    with open(script, "wt") as f:
        for l in lines:
            f.write(f"{l}\n")

    os.chmod(script, 0o700)
