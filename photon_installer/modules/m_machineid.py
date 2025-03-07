# /*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */

import os
import commons

install_phase = commons.POST_INSTALL
enabled = True


def execute(installer):
    # Generage machine-id for live setup, but keep this file empty for images
    # so it gets regenerated on boot.
    if installer.install_config['live']:
        installer.cmd.run_in_chroot(
            installer.photon_root, "/bin/systemd-machine-id-setup"
        )
    else:
        # see https://www.freedesktop.org/software/systemd/man/latest/machine-id.html
        with open(installer.photon_root + "/etc/machine-id", "wt") as f:
            f.write("uninitialized\n")
        os.chmod(installer.photon_root + "/etc/machine-id", 0o444)
