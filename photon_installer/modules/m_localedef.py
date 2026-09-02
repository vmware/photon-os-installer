# /*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */

import commons

# The other half of locale setup, and the half that cannot move earlier.
#
# m_locale writes /etc/locale.conf at PRE_PKGS_INSTALL because dracut needs it
# before the package transaction ends. localedef cannot follow it there: it runs
# inside the chroot, and at PRE_PKGS_INSTALL the target holds only an
# initialised rpm database and the `filesystem` rpm - glibc, which provides
# /usr/bin/localedef, is not installed until _install_packages(). So this stays
# at POST_INSTALL.
install_phase = commons.POST_INSTALL
enabled = True


def execute(installer):
    """
    locale-gen.sh needs /usr/share/locale/locale.alias which is shipped
    with glibc-lang rpm, in some photon installations glibc-lang rpm is
    not installed by default. Call localedef directly here to define
    locale environment.
    """
    installer.cmd.run_in_chroot(
        installer.photon_root,
        "/usr/bin/localedef -c -i en_US -f UTF-8 en_US.UTF-8",
    )
