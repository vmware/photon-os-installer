# /*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */

import commons
import os
import shutil


install_phase = commons.POST_INSTALL
enabled = True


def replace_passwd(filepath, passwd, user="root"):

    filepath_tmp = f"{filepath}.tmp"
    with open(filepath, "rt") as fin:
        with open(filepath_tmp, "wt") as fout:
            for line in fin:
                l = line.split(":")
                if l[0] == user:
                    l[1] = passwd
                fout.write(":".join(l))
    shutil.copystat(filepath, filepath_tmp)
    os.rename(filepath_tmp, filepath)


def execute(installer):
    shadow_password = installer.install_config['shadow_password']
    installer.logger.info("Set root password")

    passwd_filename = os.path.join(installer.photon_root, 'etc/passwd')
    shadow_filename = os.path.join(installer.photon_root, 'etc/shadow')

    # replace root blank password in passwd file to point to shadow file
    replace_passwd(passwd_filename, "x")

    if not os.path.isfile(shadow_filename):
        with open(shadow_filename, "w") as destination:
            destination.write(f"root:{shadow_password}:")
    else:
        replace_passwd(shadow_filename, shadow_password)

    installer.cmd.run_in_chroot(installer.photon_root, "/usr/sbin/pwconv")
    installer.cmd.run_in_chroot(installer.photon_root, "/usr/sbin/grpconv")

    if 'age' in installer.install_config.get('password', {}):
        age = installer.install_config['password']['age']
        login_defs_filename = os.path.join(
            installer.photon_root, 'etc/login.defs'
        )

        # Do not run 'chroot -R' from outside. It will not find nscd socket.
        if age == -1:
            installer.cmd.run_in_chroot(
                installer.photon_root,
                "chage -I -1 -m 0 -M 99999 -E -1 -W 7 root",
            )
            commons.replace_string_in_file(
                login_defs_filename,
                r'(PASS_MAX_DAYS)\s+\d+\s*',
                'PASS_MAX_DAYS\t99999\n',
            )
        elif age == 0:
            installer.cmd.run_in_chroot(
                installer.photon_root, "chage -d 0 root"
            )
        else:
            installer.cmd.run_in_chroot(
                installer.photon_root, f"chage -M {age} root"
            )
            commons.replace_string_in_file(
                login_defs_filename,
                r'(PASS_MAX_DAYS)\s+\d+\s*',
                f'PASS_MAX_DAYS\t{age}\n',
            )
