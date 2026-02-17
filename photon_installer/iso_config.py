# /*
#  * Copyright © 2020 VMware, Inc.
#  * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
#  */

import curses
import getopt
import json
import re
import secrets
import sys

import cracklib
import requests
from commandutils import CommandUtils
from confirmwindow import ConfirmWindow
from custompartition import CustomPartition
from filedownloader import FileDownloader
from license import License
from linuxselector import LinuxSelector
from logger import Logger
from netconfig import NetworkConfigure
from packageselector import PackageSelector
from selectdisk import SelectDisk
from stigenable import StigEnable
from windowstringreader import WindowStringReader


class IsoConfig(object):
    """This class handles iso installer configuration."""
    def __init__(self, root_dir="/"):
        self.alpha_chars = list(range(65, 91))
        self.alpha_chars.extend(range(97, 123))
        self.hostname_accepted_chars = self.alpha_chars
        # Adding the numeric chars
        self.hostname_accepted_chars.extend(range(48, 58))
        # Adding the . and -
        self.hostname_accepted_chars.extend([ord('.'), ord('-')])
        self.random_id = '%12x' % secrets.randbelow(16**12)
        self.random_hostname = "photon-" + self.random_id.strip()
        self.logger = Logger.get_logger()
        self.root_dir = root_dir

    @staticmethod
    def validate_hostname(hostname):
        """A valid hostname must start with a letter"""
        error_empty = "Empty hostname or domain is not allowed"
        error_dash = "Hostname or domain should not start or end with '-'"
        error_hostname = "Hostname should start with alpha char and <= 64 chars"

        if hostname is None or not hostname:
            return False, error_empty

        fields = hostname.split('.')
        for field in fields:
            if not field:
                return False, error_empty
            if field[0] == '-' or field[-1] == '-':
                return False, error_dash

        machinename = fields[0]
        return (len(machinename) <= 64 and
                machinename[0].isalpha(), error_hostname)

    @staticmethod
    def validate_http_response(url, checks, exception_text, error_text):
        try:
            response = requests.get(url, verify=True, stream=True, timeout=5.0)
        except Exception:
            return exception_text
        else:
            if response.status_code != 200:
                return error_text

        html = response.content.decode('utf-8', errors="replace")

        for pattern, count, failed_check_text in checks:
            match = re.findall(pattern, html)
            if len(match) != count:
                return failed_check_text

        return ""

    @staticmethod
    def validate_password(text):
        """Validate password with cracklib"""
        try:
            password = cracklib.VeryFascistCheck(text)
        except ValueError as message:
            password = str(message)
        return password == text, "Error: " + password

    def configure(self, stdscreen, ui_config):
        """Configuration through UI"""
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_WHITE)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_GREEN)
        curses.init_pair(4, curses.COLOR_RED, curses.COLOR_WHITE)
        stdscreen.bkgd(' ', curses.color_pair(1))
        maxy, maxx = stdscreen.getmaxyx()
        stdscreen.addstr(maxy - 1, 0, '  Arrow keys make selections; <Enter> activates.')
        curses.curs_set(0)

        install_config = {}
        # force UI progress screen
        install_config['ui'] = True

        items = self.add_ui_pages(install_config, ui_config, maxy, maxx)
        index = 0
        # Used to continue direction if some screen was skipped
        go_next = True

        # UI screens showing
        while True:
            ar = items[index][0]()
            # Skip inactive window and continue previous direction.
            if ar.result and ar.result.get('inactive_screen', False):
                ar.success = go_next
            go_next = ar.success
            if ar.success:
                index += 1
                if index == len(items):
                    # confirm window
                    if ar.result['yes']:
                        break
                    else:
                        exit(0)
            else:
                index -= 1
                while index >= 0 and items[index][1] is False:
                    index -= 1
                if index < 0:
                    index = 0
        return install_config

    def add_ui_pages(self, install_config, ui_config, maxy, maxx):
        items = []
        license_agreement = License(maxy, maxx, ui_config['eula_file_path'], ui_config['license_display_title'])
        select_disk = SelectDisk(maxy, maxx, install_config)
        custom_partition = CustomPartition(maxy, maxx, install_config)
        package_selector = PackageSelector(maxy, maxx, install_config, ui_config['options_file'])
        hostname_reader = WindowStringReader(
            maxy, maxx, 10, 70,
            'hostname',
            None,  # confirmation error msg if it's a confirmation text
            None,  # echo char
            self.hostname_accepted_chars,  # set of accepted chars
            IsoConfig.validate_hostname,  # validation function of the input
            None,  # post processing of the input field
            'Choose the hostname for your system', 'Hostname:', 2, install_config,
            self.random_hostname,
            True)
        root_password_reader = WindowStringReader(
            maxy, maxx, 10, 70,
            'shadow_password',
            None,  # confirmation error msg if it's a confirmation text
            '*',  # echo char
            None,  # set of accepted chars
            IsoConfig.validate_password,  # validation function of the input
            None,  # post processing of the input field
            'Set up root password', 'Root password:', 2, install_config)
        confirm_password_reader = WindowStringReader(
            maxy, maxx, 10, 70,
            'shadow_password',
            # confirmation error msg if it's a confirmation text
            "Passwords don't match, please try again.",
            '*',  # echo char
            None,  # set of accepted chars
            None,  # validation function of the input
            CommandUtils.generate_password_hash,  # post processing of the input field
            'Confirm root password', 'Confirm Root password:', 2, install_config)

        confirm_window = ConfirmWindow(
            11,
            60,
            maxy,
            maxx,
            (maxy - 11) // 2 + 7,
            'Start installation? All data on the selected disk will be lost.\n\n'
            'Press <Yes> to confirm, or <No> to quit',
        )

        # This represents the installer screens, the bool indicates if
        # we can go back to this window or not
        items.append((license_agreement.display, False))
        items.append((select_disk.display, True))
        items.append((custom_partition.display, False))
        items.append((package_selector.display, True))
        net_cfg = NetworkConfigure(maxy, maxx, install_config)
        items.append((net_cfg.display, True))

        if 'download_screen' in ui_config:
            title = ui_config['download_screen'].get('title', None)
            intro = ui_config['download_screen'].get('intro', None)
            dest = ui_config['download_screen'].get('destination', None)
            fd = FileDownloader(maxy, maxx, install_config, title, intro, dest, True, root_dir=self.root_dir)
            items.append((fd.display, True))

        linux_selector = LinuxSelector(maxy, maxx, install_config)
        items.append((linux_selector.display, True))

        stig_enable = StigEnable(maxy, maxx, install_config)
        items.append((stig_enable.display, True))

        items.append((hostname_reader.get_user_string, True))
        items.append((root_password_reader.get_user_string, True))
        items.append((confirm_password_reader.get_user_string, False))
        items.append((confirm_window.do_action, True))

        return items


# for debugging
def main():
    config_file = None
    root_dir = "/"

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'D:f:')
    except Exception:
        print("invalid option")
        sys.exit(2)

    for o, a in opts:
        if o == '-D':
            root_dir = a
        elif o == '-f':
            config_file = a
        else:
            assert False, "unhandled option 'o'"

    if config_file:
        f = open(config_file, 'r')
    else:
        f = sys.stdin

    ui_config = json.load(f)
    if f != sys.stdin:
        f.close()

    # EVIL hack
    ui_config['options_file'] = "input.json"

    ui = IsoConfig(root_dir=root_dir)
    config = curses.wrapper(ui.configure, ui_config)

    print(json.dumps(config, indent=4))


if __name__ == "__main__":
    main()
