#/*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */
#
#
#    Author: Mahmoud Bassiouny <mbassiouny@vmware.com>

import subprocess
import os

class Device(object):
    def __init__(self, model, path, size):
        self.model = model
        self.path = path
        self.size = size

    @staticmethod
    def refresh_devices():
        devices_list = subprocess.check_output(['lsblk', '-d', '-I', '7,8,179,202,254,259', '-n',
                                                '--output', 'NAME,SIZE,MODEL'],
                                               stderr=open(os.devnull, 'w'))
        return Device.wrap_devices_from_list(devices_list)

    @staticmethod
    def refresh_devices_bytes():
        devices_list = subprocess.check_output(['lsblk', '-d', '--bytes', '-I',
                                                '7,8,179,202,254,259', '-n', '--output', 'NAME,SIZE,MODEL'],
                                               stderr=open(os.devnull, 'w'))
        return Device.wrap_devices_from_list(devices_list)

    @staticmethod
    def check_cdrom():
        process = subprocess.Popen(["blockdev", "/dev/cdrom"])
        retval = process.wait()
        if retval:
            return False
        return True

    @staticmethod
    def wrap_devices_from_list(list):
        devices = []
        deviceslines = list.splitlines()
        for deviceline in deviceslines:
            cols = deviceline.split(None, 2)
            #skip Virtual NVDIMM from install list
            colstr = cols[0].decode()
            if colstr.startswith("pmem"):
                continue
            model = "Unknown"
            if len(cols) >= 3:
                model = cols[2].decode()
            devices.append(
                Device(model #Model
                       , '/dev/' + cols[0].decode() #Path
                       , cols[1].decode() #size
                      ))

        return devices
