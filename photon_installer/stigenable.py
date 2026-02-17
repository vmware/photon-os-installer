# /*
#  * Copyright © 2023 VMware, Inc.
#  * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
#  */
#

from actionresult import ActionResult
from menu import Menu
from window import Window

KS_STIG_ANSIBLE = [
    {
        'playbook': "/usr/share/ansible/stig-hardening/playbook.yml",
        'logfile': "ansible-stig.log",
        'verbosity': 2,
        'extra-vars': "@/usr/share/ansible/stig-hardening/vars-chroot.yml",
        'skip-tags': ["PHTN-50-000245"]
    }
]

KS_STIG_PACKAGES = [
    "audit",
    "rsyslog",
    "openssl-fips-provider",
    "selinux-policy",
    "libselinux-utils",
    "ntp",
    "aide",
    "libgcrypt"
]


class StigEnable(object):
    def __init__(self, maxy, maxx, install_config):
        self.install_config = install_config
        win_width = 50
        win_height = 12

        win_starty = (maxy - win_height) // 2

        menu_starty = win_starty + 3

        menu_items = [
            ("No", self.set_stig_enabled, False),
            ("Yes", self.set_stig_enabled, True)
        ]

        menu = Menu(menu_starty, maxx, menu_items, default_selected=0, tab_enable=False)
        self.window = Window(win_height, win_width, maxy, maxx, "Apply STIG hardening", True, menu, can_go_next=True)

    def set_stig_enabled(self, is_enabled):
        if is_enabled:
            self.install_config['ansible'] = KS_STIG_ANSIBLE
            self.install_config['additional_packages'] = KS_STIG_PACKAGES
        else:
            if 'ansible' in self.install_config:
                del self.install_config['ansible']
            if 'additional_packages' in self.install_config:
                del self.install_config['additional_packages']

        return ActionResult(True, None)

    def display(self):
        return self.window.do_action()
