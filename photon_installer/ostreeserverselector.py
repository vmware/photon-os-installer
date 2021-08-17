#!/usr/bin/python2
#/*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */
#
#
#    Author: Mahmoud Bassiouny <mbassiouny@vmware.com>

import json
import os
import curses
from jsonwrapper import JsonWrapper
from menu import Menu
from window import Window
from actionresult import ActionResult

class OSTreeServerSelector(object):
    def __init__(self,  maxy, maxx, install_config):
        self.install_config = install_config
        win_width = 50
        win_height = 12

        win_starty = (maxy - win_height) // 2
        win_startx = (maxx - win_width) // 2

        menu_starty = win_starty + 3

        ostree_host_menu_items = [
                                        ("Default RPM-OSTree Server", self.set_default_repo_installation, True),
                                        ("Custom RPM-OSTree Server", self.set_default_repo_installation, False)
                                    ]

        host_menu = Menu(menu_starty,  maxx, ostree_host_menu_items, default_selected=0, tab_enable=False)
        self.window = Window(win_height, win_width, maxy, maxx, 'Select OSTree Server', True, host_menu, can_go_next=True)

    def set_default_repo_installation(self,  is_default_repo ):
        self.install_config['ostree']['default_repo'] = is_default_repo
        return ActionResult(True, None)

    def display(self):
        if 'ostree' in self.install_config:
            return self.window.do_action()
        return ActionResult(True, None)
