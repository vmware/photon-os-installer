# /*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */

import os
import commons

install_phase = commons.POST_INSTALL
enabled = True


def execute(installer):
    hostname = installer.install_config['hostname']

    installer.logger.info(f"Set /etc/hostname to {hostname}")
    hostname_file = os.path.join(installer.photon_root, "etc/hostname")
    hosts_file = os.path.join(installer.photon_root, "etc/hosts")

    with open(hostname_file, "wt") as fout:
        fout.write(hostname)

    with open(hosts_file, "at") as fout:
        fout.write(f"127.0.1.1 {hostname}\n")
