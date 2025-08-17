# /*
#  * Copyright © 2020 VMware, Inc.
#  * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
#  */


import subprocess


# see https://www.kernel.org/doc/Documentation/admin-guide/devices.txt
LSBLK_EXCLUDE = "2,9,11,15,16,17,18,19,20,23,24,25,26,27,28,29,30,32,35"
LSBLK_EXCLUDE += ",37,46,103,113,144,145,146"


class Device(object):
    def __init__(self, model, path, size):
        self.model = model
        self.path = path
        self.size = size

    @staticmethod
    def refresh_devices(bytes=False):
        args = [
            "lsblk",
            "-d",
            "-e", LSBLK_EXCLUDE,
            "-n",
            "--output", "NAME,SIZE,MODEL"
        ]
        if bytes:
            args.append("--bytes")
        devices_list = subprocess.check_output(args,
                                               stderr=subprocess.DEVNULL)
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
            # skip Virtual NVDIMM from install list
            colstr = cols[0].decode()
            if colstr.startswith("pmem"):
                continue
            model = "Unknown"
            if len(cols) >= 3:
                model = cols[2].decode()
            devices.append(
                Device(
                    model,  # Model
                    '/dev/' + cols[0].decode(),  # Path
                    cols[1].decode()  # size
                )
            )

        return devices
