# /*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */

import os

import commons

# PRE_PKGS_INSTALL, not POST_INSTALL: dracut's 20i18n module reads
# /etc/locale.conf when it builds an initrd, and the initramfs rpm installs a
# file trigger that runs mkinitrd at the END of the package transaction started
# by _install_packages(). A file written after that transaction is written too
# late. Without it dracut aborts i18n setup with
#     "i18n_vars not set!  Please set up i18n_vars in  configuration file."
# and falls back to embedding every keymap.
#
# _initialize_system() runs immediately before this phase, so the file lands at
# very nearly the same point in the sequence as it would have from there, but
# in the module that owns locale rather than in the installer body.
install_phase = commons.PRE_PKGS_INSTALL
enabled = True


def execute(installer):
    # Set locale
    locale_conf_path = os.path.join(installer.photon_root, "etc/locale.conf")
    os.makedirs(os.path.dirname(locale_conf_path), exist_ok=True)
    with open(locale_conf_path, "w") as locale_conf:
        locale_conf.write("LANG=en_US.UTF-8\n")
