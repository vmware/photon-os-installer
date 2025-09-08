# /*
#  * Copyright © 2020 VMware, Inc.
#  * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
#  */
#

import sys

from actionresult import ActionResult
from device import Device
from menu import Menu
from window import Window


class SelectDisk(object):
    def __init__(self, maxy, maxx, install_config):
        self.install_config = install_config
        self.menu_items = []

        self.maxx = maxx
        self.maxy = maxy
        self.win_width = 70
        self.win_height = 16

        self.win_starty = (self.maxy - self.win_height) // 2
        self.win_startx = (self.maxx - self.win_width) // 2

        self.menu_starty = self.win_starty + 6
        self.menu_height = 5

        self.disk_buttom_items = []
        self.disk_buttom_items.append(('<Custom>', self.custom_function, False))
        self.disk_buttom_items.append(('<Auto>', self.auto_function, False))

        self.window = Window(self.win_height, self.win_width, self.maxy, self.maxx,
                             'Select a disk', True,
                             items=self.disk_buttom_items, menu_helper=self.save_index,
                             position=2, tab_enabled=False)
        self.devices = None

    def display(self):

        self.disk_menu_items = []

        self.devices = Device.refresh_devices()

        if len(self.devices) == 0:
            err_win = Window(self.win_height, self.win_width, self.maxy, self.maxx,
                             'Select a disk', False, position=2, tab_enabled=False)
            err_win.addstr(
                0,
                0,
                (
                    "No block devices found to select\n"
                    "Press any key to get to bash."
                )
            )

            err_win.show_window()
            err_win.content_window().getch()
            sys.exit(1)

            self.window.addstr(
                0,
                0,
                (
                    "Please select a disk and a method how to partition it:\n"
                    "Auto - single partition for /, no swap partition.\n"
                    "Custom - for customized partitioning"
                )
            )

        # Fill in the menu items
        for index, device in enumerate(self.devices):
            # if index > 0:
            self.disk_menu_items.append(
                (
                    '{2} - {1} @ {0}'.format(device.path, device.size, device.model),
                    self.save_index,
                    index
                ))

        self.disk_menu = Menu(self.menu_starty, self.maxx, self.disk_menu_items,
                              self.menu_height, tab_enable=False)
        self.disk_menu.can_save_sel(True)

        self.window.set_action_panel(self.disk_menu)
        return self.window.do_action()

    def save_index(self, device_index):
        self.install_config['disk'] = self.devices[device_index].path
        return ActionResult(True, None)

    def auto_function(self):    # default is no partition
        self.install_config['autopartition'] = True
        return ActionResult(True, None)

    def custom_function(self):  # custom minimize partition number is 1
        self.install_config['autopartition'] = False
        return ActionResult(True, None)
