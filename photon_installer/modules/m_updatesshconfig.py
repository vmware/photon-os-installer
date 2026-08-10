# /*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */

import os
import re

import commons

install_phase = commons.POST_INSTALL
enabled = True

PERMIT_ROOT_LOGIN_RE = re.compile(r'^\s*PermitRootLogin\s+no')


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
    with open(sshd_config_filename) as f:
        lines = f.readlines()

    updated_lines = []
    changed = False
    for line in lines:
        new_line, count = PERMIT_ROOT_LOGIN_RE.subn("PermitRootLogin yes", line)
        if count:
            changed = True
        updated_lines.append(new_line)

    if not changed:
        # No existing "PermitRootLogin no" line to replace; add one.
        if updated_lines and not updated_lines[-1].endswith("\n"):
            updated_lines[-1] += "\n"
        updated_lines.append("PermitRootLogin yes\n")

    with open(sshd_config_filename, "w") as f:
        f.writelines(updated_lines)
