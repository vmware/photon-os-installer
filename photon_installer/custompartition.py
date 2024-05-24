# /*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */
from window import Window
from windowstringreader import WindowStringReader
from partitionpane import PartitionPane
from readmultext import ReadMulText
from confirmwindow import ConfirmWindow
from actionresult import ActionResult
from device import Device
from installer import BIOSSIZE, ESPSIZE

class CustomPartition:
    HEADER = 'Welcome to the Photon installer'
    PARTITION_TYPES = ['swap', 'ext3', 'ext4', 'xfs', 'btrfs']

    def __init__(self, maxy, maxx, install_config):
        self.maxy = maxy
        self.maxx = maxx
        self.win_width = maxx - 4
        self.win_height = maxy - 4
        self.install_config = install_config
        self.path_checker = []
        self.cp_config = {'partitionsnumber': 0}
        self.disk_size = []
        self.disk_to_index = {}
        self.devices = None
        self.has_slash = False
        self.has_remain = False
        self.has_empty = False

        self.win_starty = (self.maxy - self.win_height) // 2
        self.win_startx = (self.maxx - self.win_width) // 2
        self.text_starty = self.win_starty + 4
        self.text_height = self.win_height - 6
        self.text_width = self.win_width - 6

        self.window = self._initialize_window()
        Device.refresh_devices()

    def _initialize_window(self):
        return Window(self.win_height, self.win_width, self.maxy, self.maxx,
                      self.HEADER, False, can_go_next=False)

    def initialize_devices(self):
        self.devices = Device.refresh_devices(bytes=True)
        for index, device in enumerate(self.devices):
            available_size = int(device.size) / 1048576 - (BIOSSIZE + ESPSIZE + 2)
            self.disk_size.append((device.path, available_size))
            self.disk_to_index[device.path] = index

    def display(self):
        self.initialize_devices()
        if self.install_config.get('autopartition'):
            return ActionResult(True, None)

        self.device_index = self.disk_to_index[self.install_config['disk']]
        self.disk_bottom_items = [
            ('<Next>', self.next),
            ('<Create New>', self.create_function),
            ('<Delete All>', self.delete_function),
            ('<Go Back>', self.go_back)
        ]
        self.text_items = [('Disk', 20), ('Size', 5), ('Type', 5), ('Mountpoint', 20)]
        self.table_space = 5

        title = 'Current partitions:\n'
        self.window.addstr(0, (self.win_width - len(title)) // 2, title)
        info = (f"Unpartitioned space: {self.disk_size[self.device_index][1]} MB, "
                f"Total size: {int(self.devices[self.device_index].size) / 1048576} MB")
        self.partition_pane = PartitionPane(self.text_starty, self.maxx, self.text_width,
                                            self.text_height, self.disk_bottom_items,
                                            config=self.cp_config, text_items=self.text_items,
                                            table_space=self.table_space, info=info,
                                            size_left=str(self.disk_size[self.device_index][1]))
        self.window.set_action_panel(self.partition_pane)
        return self.window.do_action()

    def validate_partition(self, pstr):
        if not pstr:
            return ActionResult(False, None)

        size, type_, mountpoint = pstr[0], pstr[1], pstr[2]
        device_path = self.devices[self.device_index].path

        if type_ == 'swap' and (mountpoint or not type_ or not device_path):
            return False, "Invalid swap data"
        if type_ != 'swap' and (not size or not mountpoint or not type_ or not device_path):
            if not self.has_empty and mountpoint and type_ and device_path:
                self.has_empty = True
            else:
                return False, "Input cannot be empty"
        if type_ not in self.PARTITION_TYPES:
            return False, "Invalid type"
        if mountpoint and mountpoint[0] != '/':
            return False, "Invalid path"
        if mountpoint in self.path_checker:
            return False, "Path already exists"

        if size:
            try:
                size = int(size)
            except ValueError:
                return False, "Invalid device size"
            if self.disk_size[self.device_index][1] < size:
                return False, "Invalid device size"
            self.disk_size[self.device_index] = (device_path, self.disk_size[self.device_index][1] - size)

        if mountpoint == "/":
            self.has_slash = True

        self.path_checker.append(mountpoint)
        return True, None

    def create_function(self):
        self.window.hide_window()
        self.cp_config['partition_disk'] = self.devices[self.device_index].path
        partition_items = [
            f'Size in MB: {self.disk_size[self.device_index][1]} available',
            'Type: (ext3, ext4, xfs, btrfs, swap)',
            'Mountpoint:'
        ]
        create_window = ReadMulText(self.maxy, self.maxx, 0, self.cp_config,
                                    f"{self.cp_config['partitionsnumber']}partition_info",
                                    partition_items, None, None, None,
                                    self.validate_partition, None, True)
        result = create_window.do_action()
        if result.success:
            self.cp_config['partitionsnumber'] += 1
        return self.display()

    def delete_function(self):
        self.delete()
        return self.display()

    def go_back(self):
        self.delete()
        self.window.hide_window()
        self.partition_pane.hide()
        return ActionResult(False, {'goBack': True})

    def next(self):
        if self.cp_config['partitionsnumber'] == 0:
            self._show_confirmation('Partition information cannot be empty')
            return self.display()
        if not self.has_slash:
            self._show_confirmation('Missing /')
            return self.display()
        self.window.hide_window()
        self.partition_pane.hide()
        self.install_config['partitions'] = [
            {
                "mountpoint": self.cp_config[f"{i}partition_info2"],
                "size": int(self.cp_config[f"{i}partition_info0"]) if self.cp_config[f"{i}partition_info0"] else 0,
                "filesystem": self.cp_config[f"{i}partition_info1"]
            }
            for i in range(self.cp_config['partitionsnumber'])
        ]
        return ActionResult(True, {'goNext': True})

    def delete(self):
        for i in range(self.cp_config['partitionsnumber']):
            for j in range(4):
                self.cp_config[f"{i}partition_info{j}"] = ''
        self.disk_size = [(device.path, int(device.size) / 1048576 - (BIOSSIZE + ESPSIZE + 2)) for device in self.devices]
        self.path_checker.clear()
        self.has_slash = False
        self.has_remain = False
        self.has_empty = False
        self.cp_config['partitionsnumber'] = 0

    def _show_confirmation(self, message):
        window_height, window_width = 9, 40
        window_starty = (self.maxy - window_height) // 2 + 5
        confirm_window = ConfirmWindow(window_height, window_width, self.maxy, self.maxx,
                                       window_starty, message, info=True)
        confirm_window.do_action()
