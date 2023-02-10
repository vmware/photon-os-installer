#! /usr/bin/python3
#/*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */
#
#
#    Author: Mahmoud Bassiouny <mbassiouny@vmware.com>
import os
import subprocess
import shlex
import requests
import time
import json
from argparse import ArgumentParser
from installer import Installer
from commandutils import CommandUtils
from jsonwrapper import JsonWrapper
from device import Device

class IsoInstaller(object):
    def __init__(self, options):
        install_config=None
        self.media_mount_path = None
        photon_media = None
        ks_path = options.install_config_file
        # Path to RPMS repository: local media or remote URL
        # If --repo-path= provided - use it,
        # if not provided - use kernel repo= parameter,
        # if not provided - use /RPMS path from photon_media,
        # exit otherwise.
        repo_path = options.repo_path
        self.insecure_installation = False
        # On Baremetal, time to emulate /dev/cdrom on different
        # servers varies. So, adding a commandline parameter
        # for retry count.
        self.retry_mount_media = 3

        with open('/proc/cmdline', 'r') as f:
            kernel_params = shlex.split(f.read().replace('\n', ''))

        for arg in kernel_params:
            if arg.startswith("ks="):
                if not ks_path:
                    ks_path = arg[len("ks="):]
            elif arg.startswith("repo="):
                if not repo_path:
                    repo_path = arg[len("repo="):]
            elif arg.startswith("photon.media="):
                photon_media = arg[len("photon.media="):]
            elif arg.startswith("insecure_installation="):
                self.insecure_installation = bool(int(arg[len("insecure_installation="):]))
            elif arg.startswith("photon.media.mount_retry="):
                self.retry_mount_media = int(arg[len("photon.media.mount_retry="):])

        if photon_media:
            self.media_mount_path = self.mount_media(photon_media)

        if not repo_path:
            if self.media_mount_path:
                repo_path = self.media_mount_path + "/RPMS"
            else:
                print("Please specify RPM repo path.")
                return

        if ks_path:
            install_config = self._load_ks_config(ks_path)

        if options.ui_config_file:
            ui_config = (JsonWrapper(options.ui_config_file)).read()
        else:
            ui_config={}
        ui_config['options_file'] = options.options_file

        #initializing eula file path
        ui_config['eula_file_path'] = options.eula_file_path

        #initializing license display text
        ui_config['license_display_title'] = options.license_display_title


        try:
            # Run installer
            installer = Installer(rpm_path=repo_path, log_path="/var/log",
                                insecure_installation=self.insecure_installation,
                                photon_release_version=options.photon_release_version)

            installer.configure(install_config, ui_config)
            installer.execute()
        except Exception:
            pass

    def _load_ks_config(self, path):
        """kick start configuration"""

        if path.startswith("http://") and not self.insecure_installation:
            raise Exception("Refusing to download kick start configuration from non-https URLs. \
                            \nPass insecure_installation=1 as a parameter when giving http url in ks.")

        if path.startswith("https://") or path.startswith("http://"):
            # Do 5 trials to get the kick start
            # TODO: make sure the installer run after network is up
            ks_file_error = "Failed to get the kickstart file at {0}".format(path)
            wait = 1
            for _ in range(0, 5):
                err_msg = ""
                try:
                    if self.insecure_installation:
                        response = requests.get(path, timeout=3, verify=False)
                    else:
                        response = requests.get(path, timeout=3, verify=True)
                except Exception as e:
                    err_msg = e
                else:
                    return json.loads(response.text)

                print("error msg: {0}  Retry after {1} seconds".format(err_msg, wait))
                time.sleep(wait)
                wait = wait * 2

            # Something went wrong
            print(ks_file_error)
            raise Exception(err_msg)
        else:
            if path.startswith("cdrom:/"):
                if self.media_mount_path is None:
                    raise Exception("cannot read ks config from cdrom, no cdrom specified")
                path = os.path.join(self.media_mount_path, path.replace("cdrom:/", "", 1))
            elif not path.startswith("/"):
                path = os.path.join(os.getcwd(), path)
            elif len(path.split(':')) == 2:
                ks_path_split = path.split(':')
                ks_mounted_path = self.mount_media(ks_path_split[0], mount_path='/mnt/ks')
                if ks_path_split[1].startswith("/"):
                    ks_path_split[1] = ks_path_split[1][1:]
                path = os.path.join(ks_mounted_path, ks_path_split[1])
            else:
                raise Exception("Kickstart file provided is not in correct format.")
            return (JsonWrapper(path)).read()

    def mount_media(self, photon_media, mount_path="/mnt/media"):
        """Mount the external media"""

        # Make the mounted directories
        os.makedirs(mount_path, exist_ok=True)

        # Construct mount cmdline
        cmdline = ['mount']
        if photon_media.startswith("UUID="):
            cmdline.extend(['-U', photon_media[len("UUID="):] ])
        elif photon_media.startswith("LABEL="):
            cmdline.extend(['-L', photon_media[len("LABEL="):] ])
        elif photon_media == "cdrom":
            cmdline.append('/dev/cdrom')
        else:
            #User specified mount path
            cmdline.append(photon_media)

        cmdline.extend(['-o', 'ro', mount_path])

        # Retry mount the CD
        for _ in range(0, self.retry_mount_media):
            process = subprocess.Popen(cmdline)
            retval = process.wait()
            if retval == 0:
                return mount_path
            print("Failed to mount the device, retry in 5 seconds")
            Device.refresh_devices()
            time.sleep(5)
        print("Failed to mount the device, exiting the installer")
        print("check the logs for more details")
        raise Exception(f"Can not mount the device {str(photon_media)}")


if __name__ == '__main__':
    usage = "Usage: %prog [options]"
    parser = ArgumentParser(usage)
    parser.add_argument("-c", "--config", dest="install_config_file")
    parser.add_argument("-u", "--ui-config", dest="ui_config_file")
    parser.add_argument("-j", "--json-file", dest="options_file", default="input.json")
    parser.add_argument("-r", "--repo-path", dest="repo_path")
    options = parser.parse_args()

    IsoInstaller(options)
