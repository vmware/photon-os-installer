# /*
#  * Copyright © 2020 VMware, Inc.
#  * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
#  */
#

import os

from actionresult import ActionResult
from textpane import TextPane
from window import Window


class License(object):
    def __init__(self, maxy, maxx, eula_file_path, display_title):
        self.maxx = maxx
        self.maxy = maxy
        self.win_width = maxx - 4
        self.win_height = maxy - 4

        self.win_starty = (self.maxy - self.win_height) // 2
        self.win_startx = (self.maxx - self.win_width) // 2

        self.text_starty = self.win_starty + 4
        self.text_height = self.win_height - 6
        self.text_width = self.win_width - 6

        self.window = Window(self.win_height, self.win_width, self.maxy, self.maxx,
                             'Welcome to the Photon installer', False)

        if eula_file_path:
            self.eula_file_path = eula_file_path
        else:
            self.eula_file_path = os.path.join(os.path.dirname(__file__), 'EULA.txt')

        if display_title:
            self.title = display_title
        else:
            self.title = 'VMWARE LICENSE AGREEMENT'

    def display(self):
        accept_decline_items = [('<Accept>', self.accept_function),
                                ('<Cancel>', self.exit_function)]

        self.window.addstr(0, (self.win_width - len(self.title)) // 2, self.title)
        self.text_pane = TextPane(self.text_starty, self.maxx, self.text_width,
                                  self.eula_file_path, self.text_height, accept_decline_items)

        self.window.set_action_panel(self.text_pane)

        return self.window.do_action()

    def accept_function(self):
        return ActionResult(True, None)

    def exit_function(self):
        exit(0)
