# /*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */

import os
import commons

install_phase = commons.POST_INSTALL
enabled = True


def execute(installer):
    if 'public_key' not in installer.install_config:
        return

    pubkey_config = installer.install_config['public_key']

    # insist on having a reason, so having a key does not get missed
    # reason can be "debug", meabning it should not be released
    # or reason can describe a desired feature
    assert type(pubkey_config) is dict, "'public_key' setting must be a dictionary with the keys 'key' and 'reason'"
    assert 'reason' in pubkey_config, "need to set a reason to add a public key"

    installer.logger.info(f"add public key for reason '{pubkey_config['reason']}'")

    authorized_keys_dir = os.path.join(installer.photon_root, "root/.ssh")
    authorized_keys_filename = os.path.join(
        authorized_keys_dir, "authorized_keys"
    )
    sshd_config_filename = os.path.join(
        installer.photon_root, "etc/ssh/sshd_config"
    )

    # Adding the authorized keys
    if not os.path.exists(authorized_keys_dir):
        os.makedirs(authorized_keys_dir)
    with open(authorized_keys_filename, "a") as destination:
        destination.write(f"{pubkey_config['key']}\n")
    os.chmod(authorized_keys_filename, 0o600)

    # Change the sshd config to allow root login
    return (
        installer.cmd.run(
            [
                "sed",
                "-i",
                "s/^\\s*PermitRootLogin\s\+no/PermitRootLogin yes/",
                sshd_config_filename,
            ]
        )
        == 0
    )
