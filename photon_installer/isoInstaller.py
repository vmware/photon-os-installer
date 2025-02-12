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
import base64
from device import Device
from argparse import ArgumentParser
from installer import Installer
from commandutils import CommandUtils
from jsonwrapper import JsonWrapper
from device import Device
from defaults import Defaults

class IsoInstaller(object):
    def __init__(self, options, params={}):
        install_config = None
        self.media_mount_path = None
        photon_media = None
        ks_path = options.install_config_file
        self.params = params
        # Comma separated paths to RPMS repository: local media or remote URL
        # If --repo-paths= provided - use it,
        # if not provided - use kernel repos= parameter,
        # if not provided - use /RPMS path from photon_media,
        # exit otherwise.
        repo_paths = options.repo_paths
        insecure_installation = Defaults.INSECURE_INSTALLATION
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
            elif arg.startswith("repos="):
                if not repo_paths:
                    repo_paths = arg[len("repos="):]
            elif arg.startswith("repo="):
                print("WARNING: 'repo=url1,url2' will get deprecated soon, please use 'repos=url1,url2' key instead")
                if not repo_paths:
                    repo_paths = arg[len("repo="):]
            elif arg.startswith("photon.media="):
                photon_media = arg[len("photon.media="):]
            elif arg.startswith("insecure_installation="):
                insecure_installation = bool(int(arg[len("insecure_installation="):]))
            elif arg.startswith("photon.media.mount_retry="):
                self.retry_mount_media = int(arg[len("photon.media.mount_retry="):])

        if photon_media:
            self.media_mount_path = self.mount_media(photon_media)

        if not repo_paths:
            if self.media_mount_path:
                repo_paths = self.media_mount_path + "/RPMS"
            else:
                print("Please specify RPM repo path.")
                return

        if ks_path:
            if ks_path.startswith("http://") and not insecure_installation:
                raise Exception("Refusing to download kick start configuration from non-https URLs. \
                                \nPass insecure_installation=1 as a parameter when giving http url in ks.")
            install_config = self._load_ks_config_url(ks_path, verify=not insecure_installation)
        else:
            install_config = self._load_ks_config_platform(verify=not insecure_installation)

        # 'live' should be True for iso installs
        if 'live' not in install_config:
            install_config['live'] = True

        if insecure_installation and install_config is not None:
            install_config['insecure_repo'] = True

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
            installer = Installer(repo_paths=repo_paths, log_path="/var/log",
                                photon_release_version=options.photon_release_version)

            installer.configure(install_config, ui_config)
            installer.execute()
        except Exception as err:
            raise Exception(f"Failed with error: {err}")

    def _load_ks_config_http(self, url, retries=5, timeout=3, verify=True):
        # Do 5 trials to get the kick start
        # TODO: make sure the installer runs after network is up
        wait = 1
        while True:
            try:
                response = requests.get(url, timeout=3, verify=verify)
                response.raise_for_status()
                break
            except Exception as e:
                if retries > 0:
                    print(f"error msg: {e} Retry after {wait} seconds")
                    time.sleep(wait)
                    wait *= 2
                    retries -= 1
                else:
                    print(f"Failed to get the kickstart file at {url}")
                    raise

        return CommandUtils.readConfig(response.text, params=self.params)

    def _load_ks_config_url(self, path, verify=True):
        """kick start configuration"""
        if path.startswith("https+insecure://"):
            verify = False
            path = "https://" + path[len("https+insecure://"):]
        if path.startswith("https://") or path.startswith("http://"):
            return self._load_ks_config_http(path, verify=verify)
        else:
            mnt_path = None
            if path.startswith("cdrom:/"):
                if self.media_mount_path is None:
                    raise Exception("cannot read ks config from cdrom, no cdrom specified")
                path = os.path.join(self.media_mount_path, path.replace("cdrom:/", "", 1))
            elif not path.startswith("/"):
                path = os.path.join(os.getcwd(), path)
            elif len(path.split(':')) == 2:
                device, rel_path = path.split(':')
                rel_path = rel_path.strip("/")
                mnt_path = self.mount_media(device, mount_path="/mnt/ks")
                path = os.path.join(mnt_path, rel_path)
            else:
                raise Exception("Kickstart file path provided is not in correct format.")

            with open(path, "rt") as f:
                config = CommandUtils.readConfig(f, params=self.params)

            if mnt_path is not None:
                subprocess.check_call(['umount', mnt_path])

            return config

    def _load_ks_config_platform(self, verify=True):
        if CommandUtils.is_vmware_virtualization():
            return self._load_ks_config_vmware(verify=verify)
        else:
            return None

    def _load_ks_config_vmware(self, verify=True):
        try:
            result = subprocess.run(['vmtoolsd', '--cmd', 'info-get guestinfo.kickstart.data'],
                    universal_newlines=True, stdout=subprocess.PIPE)
            if result.returncode == 0:
                return CommandUtils.readConfig(base64.b64decode(result.stdout.rstrip('\n')), params=self.params)
            result = subprocess.run(['vmtoolsd', '--cmd', 'info-get guestinfo.kickstart.url'],
                    universal_newlines=True, stdout=subprocess.PIPE)
            if result.returncode == 0:
                return self._load_ks_config_url(result.stdout.rstrip('\n'), verify=verify)
        except OSError as e:
            print(f"Failed to run vmtoolsd, do you have open-vm-tools installed? Error: {e}")

    def mount_media(self, photon_media, mount_path=Defaults.MOUNT_PATH):
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
            # Check if cdrom is listed in block devices.
            if not Device.check_cdrom():
                raise Exception("Cannot proceed with the installation because the installation medium "
                                "is not readable. Ensure that you select a medium connected to a SATA "
                                "interface and try again.")
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
        raise Exception(f"Cannot mount the device {str(photon_media)}")


if __name__ == '__main__':
    usage = "Usage: %prog [options]"
    parser = ArgumentParser(usage)
    parser.add_argument("-c", "--config", dest="install_config_file")
    parser.add_argument("-u", "--ui-config", dest="ui_config_file")
    parser.add_argument("-j", "--json-file", dest="options_file", default="input.json")
    # Comma separated paths to RPMS
    parser.add_argument("-r", "--repo-paths", dest="repo_paths")
    options = parser.parse_args()

    IsoInstaller(options)
