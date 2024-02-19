"""
Photon installer
"""
# /*
#  * Copyright © 2020 VMware, Inc.
#  * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
#  */
#

import subprocess
import os
import re
import shutil
import signal
import sys
import glob
import modules.commons
import secrets
import curses
import stat
import tempfile
import copy
import jc
import json
import datetime

from defaults import Defaults
from logger import Logger
from commandutils import CommandUtils
from jsonwrapper import JsonWrapper
from progressbar import ProgressBar
from window import Window
from networkmanager import NetworkManager
from enum import Enum
from collections import abc
from tdnf import Tdnf

BIOSSIZE = 4
ESPSIZE = 10


class PartitionType(Enum):
    SWAP = 1
    LINUX = 2
    LVM = 3
    ESP = 4
    BIOS = 5


class Installer(object):
    """
    Photon installer
    """

    # List of allowed keys in kickstart config file.
    # Please keep ks_config.txt file updated.
    known_keys = {
        'additional_files',
        'additional_packages',
        'additional_rpms_path',
        'ansible',
        'arch',
        'autopartition',
        'bootmode',
        'disk',
        'disks',
        'eject_cdrom',
        'hostname',
        'linux_flavor',
        'live',
        'log_level',
        'manifest_file',
        'ostree',
        'packages',
        'packagelist_file',
        'partition_type',
        'partitions',
        'network',
        'no_unmount',
        'no_clean',
        'password',
        'postinstall',
        'postinstallscripts',
        'preinstall',
        'preinstallscripts',
        'public_key',
        'photon_docker_image',
        'repos',
        'search_path',
        'setup_grub_script',
        'shadow_password',
        'type',
        'ui'
    }

    default_partitions = [{"mountpoint": "/", "size": 0, "filesystem": "ext4"}]
    all_linux_flavors = ["linux", "linux-esx", "linux-aws", "linux-secure", "linux-rt"]
    linux_dependencies = ["devel", "drivers", "docs", "oprofile", "dtb"]

    def __init__(self, working_directory=Defaults.WORKING_DIRECTORY, rpm_path=None,
                 repo_paths=Defaults.REPO_PATHS, log_path=Defaults.LOG_PATH,
                 insecure_installation=Defaults.INSECURE_INSTALLATION,
                 photon_release_version=Defaults.PHOTON_RELEASE_VERSION):
        self.exiting = False
        self.interactive = False
        self.install_config = None
        self.repo_paths = repo_paths
        self.rpm_path = rpm_path
        self.log_path = log_path
        self.logger = None
        self.cmd = None
        self.working_directory = working_directory
        self.insecure_installation = insecure_installation
        self.photon_release_version = photon_release_version
        self.ab_present = False
        self.mounts = []

        # some keys can have arch specific variations
        for key in ['packages', 'linux_flavor']:
            for arch in ['x86_64', 'aarch64']:
                self.known_keys.add(f'{key}_{arch}')

        if os.path.exists(self.working_directory) and os.path.isdir(self.working_directory) and working_directory == Defaults.WORKING_DIRECTORY:
            shutil.rmtree(self.working_directory)
        if not os.path.exists(self.working_directory):
            os.mkdir(self.working_directory)

        self.installer_path = os.path.dirname(os.path.abspath(__file__))

        self.photon_root = os.path.join(self.working_directory, "photon-chroot")
        self.tdnf_conf_path = os.path.join(self.working_directory, "tdnf.conf")

        self.setup_grub_command = os.path.join(os.path.dirname(__file__), "mk-setup-grub.sh")

        signal.signal(signal.SIGINT, self.exit_gracefully)
        self.lvs_to_detach = {'vgs': [], 'pvs': []}


    """
    create, append and validate configuration date - install_config
    """
    def configure(self, install_config, ui_config=None):
        # Initialize logger and cmd first
        if not install_config:
            # UI installation
            log_level = 'debug'
            console = False
        else:
            log_level = install_config.get('log_level', 'info')
            console = not install_config.get('ui', False)
        self.logger = Logger.get_logger(self.log_path, log_level, console)
        self.cmd = CommandUtils(self.logger)

        if self.rpm_path and "repos" not in install_config and self.repo_paths == Defaults.REPO_PATHS:
            self.logger.warning("'rpm_path' key is deprecated, please use 'repo_paths' key instead")
            self.repo_paths = self.rpm_path
        # run preinstall scripts before installation begins
        if install_config:
            self._load_preinstall(install_config)

        # run UI configurator iff install_config param is None
        if not install_config and ui_config:
            from iso_config import IsoConfig
            self.interactive = True
            config = IsoConfig()
            install_config = curses.wrapper(config.configure, ui_config)

        self.tdnf = Tdnf(logger=self.logger,
                         config_file=self.tdnf_conf_path,
                         reposdir=self.working_directory,
                         releasever=self.photon_release_version,
                         installroot=self.photon_root,
                         docker_image=install_config.get('photon_docker_image', None))

        issue = self._check_install_config(install_config)
        if issue:
            self.logger.error(issue)
            raise Exception(issue)

        self._add_defaults(install_config)

        self.install_config = install_config

        self.ab_present = self._is_ab_present()
        self._prepare_devices()
        self._get_disk_sizes()
        self._calc_size_percentages()
        self._insert_boot_partitions()
        self._add_shadow_partitions()
        self._check_disk_space()
        self._get_vg_names()
        self._clear_vgs()


    # collect LVM Volume Group names
    def _get_vg_names(self):
        retval, host_vg_names = self.cmd.get_vgnames()
        self.vg_names = set()
        partitions = self.install_config['partitions']
        for p in partitions:
            if 'lvm' in p:
                vg_name = p['lvm']['vg_name']
                if vg_name in host_vg_names:
                    # creating a VG with the same name as on the host will cause trouble
                    raise Exception(f"vg name {vg_name} is in use by the host - if left over from a previous install remove it with 'vgremove'")
                self.vg_names.add(vg_name)
        self.logger.info(f"using VG names: {self.vg_names}")


    def _prepare_devices(self):
        disks = self.install_config['disks']
        for id, disk in disks.items():
            if not 'device' in disk:
                filename = disk['filename']
                size = disk['size']
                retval = self.cmd.run(["dd", "if=/dev/zero", f"of={filename}", "bs=1M", f"count={size}", "conv=sparse"])
                if retval != 0:
                    raise Exception(f"failed to create disk image '{filename}'")
                device = subprocess.check_output(["losetup", "--show", "-f", filename], text=True).strip()
                disk['device'] = device

            # handle symlinks like /dev/disk/by-path/pci-* -> ../../dev/sd*
            # Example: 'device' : '/dev/disk/by-path/pci-0000:03:00.0-scsi-0:0:0:0'
            disk['device'] = os.path.realpath(disk['device'])

        for p in self.install_config['partitions']:
            disk_id = p['disk_id']
            p['device'] = disks[disk_id]['device']


    def _get_disk_sizes(self):
        partitions = self.install_config['partitions']
        disk_sizes = {}
        all_devices = set([p['device'] for p in partitions])
        for device in all_devices:
            retval, size = CommandUtils.get_disk_size_bytes(device)
            if retval != 0:
                self.logger.info("Error code: {}".format(retval))
                raise Exception(f"Failed to get disk '{device}' size")
            disk_sizes[device] = int(size)
        self.disk_sizes = disk_sizes


    def _calc_size_percentages(self):
        partitions = self.install_config['partitions']
        for partition in partitions:
            if not 'sizepercent' in partition:
                continue
            size_percent = partition['sizepercent']
            device = partition['device']
            partition['size'] = int(self.disk_sizes[device] * size_percent / (100 * 1024**2))


    def _check_disk_space(self):
        partitions = self.install_config['partitions']
        disk_totals = {}
        for partition in partitions:
            device = partition['device']
            if device not in disk_totals:
                disk_totals[device] = 0
            disk_totals[device] += partition['size']
        for device, size in disk_totals.items():
            disk_size = self.disk_sizes[device] / 1024**2
            if size > disk_size:
                raise Exception(f"Total space requested for {device} ({size} MB) exceeds disk size ({disk_size} MB)")


    def execute(self):
        if self.install_config['ui']:
            curses.wrapper(self._install)
        else:
            self._install()


    def _fill_dynamic_conf(self, install_config):
        if isinstance(install_config, abc.Mapping) or isinstance(install_config, list):
            for key, value in install_config.items():
                if isinstance(value, abc.Mapping):
                    yield from self._fill_dynamic_conf(value)
                elif isinstance(value, list):
                    for v in value:
                        yield from self._fill_dynamic_conf(v)
                else:
                    if isinstance(value, str) and (value.startswith('$') and not value.startswith('$$')):
                        if value[1:] in os.environ:
                            install_config[key] = os.environ[value[1:]]
                            self.logger.info(f"Parsed dynamic value for '{key}': '{install_config[key]}'")
                        else:
                            self.logger.warning(f"\nInstall configuration may have dynamic value=\'{value}\' for key=\'{key}\',"
                                                f"check if it need to be exported."
                                                f"If so then please export dynamic values under preinstall script in ks file as below:"
                                                f"\nexport {value[1:]}=\'<my-val>\'"
                                                f"\nPlease refer https://github.com/vmware/photon-os-installer/blob/master/docs/ks_config.md#preinstall-optional")


    def _load_preinstall(self, install_config):
        self.install_config = install_config
        self._execute_modules(modules.commons.PRE_INSTALL)
        for fill_values in self._fill_dynamic_conf(install_config):
            self.logger.info(f"{fill_values}")


    def _add_defaults(self, install_config):
        """
        Add default install_config settings if not specified
        """
        # set arch to host's one if not defined
        if 'arch' not in install_config:
            arch = subprocess.check_output(['uname', '-m'], universal_newlines=True).rstrip('\n')
            install_config['arch'] = arch
        else:
            arch = install_config['arch']

        # 'bootmode' mode
        if 'bootmode' not in install_config:
            if "x86_64" in arch:
                install_config['bootmode'] = 'dualboot'
            else:
                install_config['bootmode'] = 'efi'

        # extend 'packages' by 'packagelist_file' and 'additional_packages'
        packages = install_config.get('packages', [])
        if 'additional_packages' in install_config:
            packages.extend(install_config['additional_packages'])
        if f'packages_{arch}' in install_config:
            packages.extend(install_config[f'packages_{arch}'])
        if 'packagelist_file' in install_config:
            plf = install_config['packagelist_file']
            if not plf.startswith('/'):
                plf = os.path.join(os.getcwd(), plf)

            with open(plf, "rt") as f:
                try:
                    plf_json = json.load(f)
                except json.decoder.JSONDecodeError as e:
                    print(f"failed to read json file {plf}")
                    print(f"json decode failed at line {e.lineno}, at:")
                    print(f"'{e.doc[e.pos:]}'")
                    raise e

            if 'packages' in plf_json:
                packages.extend(plf_json['packages'])
            if f'packages_{arch}' in plf_json:
                packages.extend(plf_json[f'packages_{arch}'])

        # add bootloader packages after bootmode set
        if install_config['bootmode'] in ['dualboot', 'efi']:
            packages.append('grub2-efi-image')

        # ansible needs python3 in the target
        if 'ansible' in install_config:
            packages.append("python3")

        install_config['packages'] = list(set(packages))

        # live means online system, and it's True be default. When you create an image for
        # target system, live should be set to False.
        if 'live' not in install_config:
            install_config['live'] = True
            if 'loop' in install_config.get('disk', ""):
                install_config['live'] = False

        # we can remove this when we have deprecated 'disk'
        if 'disk' in install_config:
            if 'disks' not in install_config:
                install_config['disks'] = {}
            disks = install_config['disks']
            if not 'default' in disks:
                disks['default'] = {'device' : install_config['disk']}

            # for backwards compatibility - handle 'disk' in 'partitions'
            for p in install_config.get('partitions', []):
                if 'disk' in p:
                    # find matching disk:
                    for disk_id, disk in disks.items():
                        if disk['device'] == p['disk']:
                            p['disk_id'] = disk_id
                            break
                    # none found, create entry:
                    if 'disk_id' not in p:
                        disk_id = p['disk'].replace("/", "_")
                        disks[disk_id] = {'device' : p['disk']}
                        p['disk_id'] = disk_id

        # default partition
        if 'partitions' not in install_config:
            install_config['partitions'] = Installer.default_partitions

        for p in install_config['partitions']:
            if not 'disk_id' in p:
                p['disk_id'] = 'default'
            if not 'filesystem' in p:
                p['filesystem'] = 'ext4'

        # define 'hostname' as 'photon-<RANDOM STRING>'
        if "hostname" not in install_config or install_config['hostname'] == "":
            install_config['hostname'] = 'photon-%12x' % secrets.randbelow(16**12)

        # Set password if needed.
        # Installer uses 'shadow_password' and optionally 'password'/'age'
        # to set aging if present. See modules/m_updaterootpassword.py
        if 'shadow_password' not in install_config:
            if 'password' not in install_config:
                install_config['password'] = {'crypted': True, 'text': '*', 'age': -1}

            if install_config['password']['crypted']:
                install_config['shadow_password'] = install_config['password']['text']
            else:
                install_config['shadow_password'] = CommandUtils.generate_password_hash(install_config['password']['text'])

        # Do not show UI progress by default
        if 'ui' not in install_config:
            install_config['ui'] = False

        # Log level
        if 'log_level' not in install_config:
            install_config['log_level'] = 'info'

        # Extend search_path by current dir and script dir
        if 'search_path' not in install_config:
            install_config['search_path'] = []
        for dirname in [os.getcwd(), os.path.abspath(os.path.dirname(__file__))]:
            if dirname not in install_config['search_path']:
                install_config['search_path'].append(dirname)

        # arch specific setting takes precedence
        if f'linux_flavor_{arch}' in install_config:
            install_config['linux_flavor'] = install_config[f'linux_flavor_{arch}']

        if 'linux_flavor' not in install_config:
            install_config['linux_flavor'] = 'linux'

        flavor = install_config['linux_flavor']
        if flavor not in install_config['packages']:
            install_config['packages'].append(flavor)

        # Default Photon docker image
        if 'photon_docker_image' not in install_config:
            install_config['photon_docker_image'] = "photon:latest"

        # if "repos" key not present in install_config or "repos=" provided by user through cmdline prioritize cmdline
        if "repos" not in install_config or (self.repo_paths and self.repo_paths != Defaults.REPO_PATHS):
            # override "repos" provided via ks_config
            install_config['repos'] = {}
            repo_pathslist = self.repo_paths.split(",")
            for idx,url in enumerate(repo_pathslist):
                if url.startswith('/'):
                    url = f"file://{url}"
                install_config['repos'][f"photon-local{idx}"] = {
                                                "name": f"VMware Photon OS Installer-{idx}",
                                                "baseurl": url,
                                                "gpgcheck": 0,
                                                "enabled": 1 }

        if 'setup_grub_script' in install_config:
            script = install_config['setup_grub_script']
            # expect script in current working dir, unless path is absolute
            if not script.startswith("/"):
                script = os.path.join(os.getcwd(), script)
            self.setup_grub_command = script


    def _check_install_config(self, install_config):
        """
        Sanity check of install_config before its execution.
        Return error string or None
        """

        unknown_keys = install_config.keys() - Installer.known_keys
        if len(unknown_keys) > 0:
            return "Unknown install_config keys: " + ", ".join(unknown_keys)

        if 'disk' not in install_config and 'disks' not in install_config:
            return "No disk configured"

        if 'disk' in install_config:
            self.logger.warning("'disk' will be deprecated, use 'disks' instead")

        if 'disks' in install_config:
            if 'disk' in install_config:
                return "only one of 'disk' or 'disks' can be set"
            if 'default' not in install_config['disks']:
                return "a 'default' disk needs to be set in for 'disks'"
            for disk_id, disk in install_config['disks'].items():
                if 'device' not in disk:
                    if 'filename' not in disk:
                        return f"a filename or a device needs to be set for disk '{disk_id}'"
                    if 'size' not in disk:
                        return f"a size needs to be set for disk image '{disk_id}'"

        # if not we'll use Installer.default_partitions in _add_defaults()
        if 'partitions' in install_config:
            # Perform following checks here:
            # 1) Only one extensible partition is allowed per disk
            # 2) /boot can not be LVM
            # 3) / must present
            # 4) Duplicate mountpoints should not be present
            has_extensible = {}
            has_root = False
            mountpoints = []
            for partition in install_config['partitions']:
                if 'disk' in partition and 'disks' in install_config:
                    return "cannot use 'disk' for partitions, use 'disk_id' from 'disks'"

                disk_id = partition.get('disk_id', 'default')
                mntpoint = partition.get('mountpoint', '')

                if disk_id not in has_extensible:
                    has_extensible[disk_id] = False

                if 'size' not in partition and 'sizepercent' not in partition:
                    return "Need to specify 'size' or 'sizepercent'"

                if 'size' in partition:
                    if type(partition['size']) != int:
                        return "'size' must be an integer"
                    if 'sizepercent' in partition:
                        return "only one of 'size' or 'sizepercent' can be specified"
                    size = partition['size']
                    if size == 0:
                        if has_extensible[disk_id]:
                            return f"disk '{disk_id}' has more than one extensible partition"
                        else:
                            has_extensible[disk_id] = True

                if 'sizepercent' in partition:
                    if type(partition['sizepercent']) != int:
                        return "'sizepercent' must be an integer"
                    if partition['sizepercent'] <= 0:
                        return "'sizepercent' must be greater than 0"
                    elif partition['sizepercent'] > 100:
                        return "'sizepercent' must not be greater than 100"

                if mntpoint != '':
                    mountpoints.append(mntpoint)
                if mntpoint == '/boot' and 'lvm' in partition:
                    return "/boot on LVM is not supported"
                elif mntpoint == '/boot/efi' and partition['filesystem'] != 'vfat':
                    return "/boot/efi filesystem must be vfat"
                elif mntpoint == '/':
                    has_root = True
            if not has_root:
                return "There is no partition assigned to root '/'"

            if len(mountpoints) != len(set(mountpoints)):
                return "Duplicate mountpoints exist in partition table!!"

            for partition in install_config['partitions']:
                if partition.get('ab', False):
                    if partition.get('lvm', None):
                        return "ab partition cannot be LVM"

        if 'arch' in install_config:
            if install_config['arch'] not in ["aarch64", "x86_64"]:
                return "Unsupported target architecture {}".format(install_config['arch'])

            # No BIOS for aarch64
            if install_config['arch'] == 'aarch64' and install_config['bootmode'] in ['dualboot', 'bios']:
                return "aarch64 targets do not support BIOS boot. Set 'bootmode' to 'efi'."

        if 'age' in install_config.get('password', {}):
            if install_config['password']['age'] < -1:
                return "Password age should be -1, 0 or positive"

        return None


    def _is_ab_present(self):
        partitions = self.install_config['partitions']
        for partition in partitions:
            if 'lvm' not in partition and partition.get('ab', False):
                return True


    def _add_shadow_partitions(self):
        """
        Add shadow partitions (copy those with 'ab' = true) to list of partitions
        Both will have 'ab' = True
        Shadow will have 'shadow'==True, the active one will have 'shadow'==False
        """
        if self.ab_present:
            shadow_parts = []
            partitions = self.install_config['partitions']
            for partition in partitions:
                if 'lvm' not in partition and partition.get('ab', False):
                    shadow_part = copy.deepcopy(partition)
                    shadow_part['shadow'] = True
                    partition['shadow'] = False
                    shadow_parts.append(shadow_part)
                    self.ab_present = True

            partitions.extend(shadow_parts)


    def _install(self, stdscreen=None):
        """
        Install photon system and handle exception
        """
        if self.install_config['ui']:
            # init the screen
            curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)
            curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_WHITE)
            curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_GREEN)
            curses.init_pair(4, curses.COLOR_RED, curses.COLOR_WHITE)
            stdscreen.bkgd(' ', curses.color_pair(1))
            maxy, maxx = stdscreen.getmaxyx()
            curses.curs_set(0)

            # initializing windows
            height = 10
            width = 75
            progress_padding = 5

            progress_width = width - progress_padding
            starty = (maxy - height) // 2
            startx = (maxx - width) // 2
            self.window = Window(height, width, maxy, maxx,
                                 'Installing Photon', False)
            self.progress_bar = ProgressBar(starty + 3,
                                            startx + progress_padding // 2,
                                            progress_width)
            self.window.show_window()
            self.progress_bar.initialize('Initializing installation...')
            self.progress_bar.show()

        try:
            self._unsafe_install()
        except Exception as inst:
            self.logger.exception(repr(inst))
            self.exit_gracefully()

        # Congratulation screen
        if self.install_config['ui']:
            self.progress_bar.hide()
            self.window.addstr(0, 0, 'Congratulations, Photon has been installed in {0} secs.\n\n'
                               'Press any key to continue to boot...'
                               .format(self.progress_bar.time_elapsed))
            if self.interactive:
                self.window.content_window().getch()
        else:
            self.logger.info("creating image was successful")

        if self.install_config.get('live', True):
            self._eject_cdrom()


    def _unsafe_install(self):
        """
        Install photon system
        """
        self._partition_disks()
        self._format_partitions()
        self._mount_partitions()
        if 'ostree' in self.install_config:
            from ostreeinstaller import OstreeInstaller
            ostree = OstreeInstaller(self)
            ostree.install()
        else:
            self._setup_install_repo()
            self._initialize_system()
            self._mount_special_folders()
            self._install_packages()
            self._install_additional_rpms()
            self._enable_network_in_chroot()
            self._setup_network()
            self._finalize_system()
            self._cleanup_tdnf_cache()
            self._setup_grub()
            self._create_fstab()
            self._update_abupdate()
        self._ansible_run()
        self._execute_modules(modules.commons.POST_INSTALL)
        self._deactivate_network_in_chroot()
        self._write_manifest()
        self._cleanup_install_repo()
        self._unmount_all()


    def exit_gracefully(self, signal1=None, frame1=None):
        """
        This will be called if the installer interrupted by Ctrl+C, exception
        or other failures
        """
        del signal1
        del frame1
        if not self.exiting and self.install_config:
            self.exiting = True
            if self.install_config['ui']:
                self.progress_bar.hide()
                self.window.addstr(0, 0, 'Oops, Installer got interrupted.\n\n' +
                                   'Press any key to get to the bash...')
                self.window.content_window().getch()

            self._cleanup_install_repo()
            self._unmount_all()
        raise Exception("Installer failed")


    def _setup_network(self):
        if 'network' not in self.install_config:
            return

        # setup network config files in chroot
        nm = NetworkManager(self.install_config['network'], root_dir=self.photon_root)
        if not nm.setup_network():
            self.logger.error("Failed to setup network!")
            self.exit_gracefully()
        nm.set_perms()

        # Configure network when in live mode (ISO)
        if (self.install_config.get('live', True)):
            nm.restart_networkd()


    def _ansible_run(self):
        if 'ansible' not in self.install_config:
            return

        if self.install_config['ui']:
            self.progress_bar.update_message('Running ansible scripts')

        ansibles = self.install_config['ansible']
        for ans_cfg in ansibles:
            playbook = ans_cfg['playbook']
            cmd = [
                "/usr/bin/ansible-playbook",
                "-c", "chroot",
                # the comma is important:
                "-i", self.photon_root + ",",
                "-u", "root",
                playbook]

            verbose= "-v"
            if 'verbosity' in ans_cfg:
                if ans_cfg['verbosity'] > 0:
                    verbose = "-" + "v"*ans_cfg['verbosity']
                else:
                    verbose = None
            if verbose is not None:
                cmd.append(verbose)

            if 'extra-vars' in ans_cfg:
                extra_vars = ans_cfg['extra-vars']
                if type(extra_vars) is str:
                    # file name (must start with '@'), or setting
                    cmd.extend(["--extra-vars", extra_vars])
                elif type(extra_vars) is list:
                    # multiple settings
                    for setting in extra_vars:
                        cmd.extend(["--extra-vars", setting])

            for option in ['tags', 'skip-tags']:
                if option in ans_cfg:
                    tags = ans_cfg[option]
                    if type(tags) is list:
                        cmd.extend([f"--{option}", ",".join(tags)])
                    elif type(tags) is str:
                        cmd.extend([f"--{option}", tags])

            logf = None
            if ans_cfg.get('logfile', None) is not None:
                logf = open(ans_cfg['logfile'], "wt")

            self.logger.info(f"running ansible playbook {playbook}")
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in process.stdout:
                if logf:
                    logf.write(line)
                else:
                    self.logger.info(line)
            process.wait()
            assert process.returncode == 0, f"ansible run for playbook {playbook} failed"
            if logf is not None:
                shutil.copy(ans_cfg['logfile'], os.path.join(self.photon_root, "var/log"))


    def _write_manifest(self):
        mf_file = self.install_config.get('manifest_file', "poi-manifest.json")
        manifest = {}

        self.logger.info(f"writing manifest file {mf_file}")

        manifest['install_time'] = str(datetime.datetime.now())

        manifest['install_config'] = self.install_config

        if 'ostree' not in self.install_config:
            retval, pkg_list = self.tdnf.run(["list", "--installed", "--disablerepo=*"])
            manifest['packages'] = pkg_list

        with open(os.path.join(self.photon_root, "etc/fstab"), "rt") as f:
            manifest['fstab'] = jc.parse("fstab", f.read())

        df = jc.parse("df", subprocess.check_output(["df"], text=True))
        df = [d for d in df if d['mounted_on'].startswith(self.photon_root)]
        for d in df:
            d['mounted_on'] = d['mounted_on'][len(self.photon_root):]
        manifest['df'] = df

        mount = jc.parse("mount", subprocess.check_output(["mount"], text=True))
        mount = [m for m in mount if m['mount_point'].startswith(self.photon_root)]
        for m in mount:
            m['mount_point'] = m['mount_point'][len(self.photon_root):]
        manifest['mount'] = mount

        with open(mf_file, "wt") as f:
            f.write(json.dumps(manifest))

        # write a copy to the image itself
        mf_dir = os.path.join(self.photon_root, "var", "log", "poi")
        os.makedirs(mf_dir, exist_ok=True)
        mf_file = os.path.join(mf_dir, "manifest.json")
        with open(mf_file, "wt") as f:
            f.write(json.dumps(manifest))
        subprocess.run(["gzip", mf_file])


    def _unmount_all(self):
        """
        Unmount partitions and special folders
        """

        partitions = self.install_config['partitions']
        for p in partitions:
            # only fstrim fs types that are supported to avoid error messages
            # instead of filtering for the fs type we could use '--quiet-unsupported',
            # but this is not implemented in older fstrim versions in Photon 3.0
            if p['filesystem'] in ['ext4', 'btrfs', 'xfs']:
                mntpoint = os.path.join(self.photon_root, p['mountpoint'].strip('/'))
                retval = self.cmd.run(["fstrim", mntpoint])

        if self.install_config.get('no_unmount', False):
            return

        while self.mounts:
            d = self.mounts.pop()
            retval = self.cmd.run(["umount", "-l", d])
            if retval != 0:
                self.logger.error(f"Failed to unmount {d}")

        self.cmd.run(['sync'])
        if os.path.exists(self.photon_root):
            shutil.rmtree(self.photon_root)

        # Deactivate LVM VGs
        for vg in self.lvs_to_detach['vgs']:
            retval = self.cmd.run(["vgchange", "-v", "-an", vg])
            if retval != 0:
                self.logger.error("Failed to deactivate LVM volume group: {}".format(vg))

        # Simulate partition hot remove to notify LVM
        for pv in self.lvs_to_detach['pvs']:
            retval = self.cmd.run(["dmsetup", "remove", pv])
            if retval != 0:
                self.logger.error("Failed to detach LVM physical volume: {}".format(pv))

        # Get the disks from partition table
        disk_ids = set(partition['disk_id'] for partition in self.install_config['partitions'])
        for disk_id in disk_ids:
            device = self.install_config['disks'][disk_id]['device']
            if 'loop' in device:
                # Uninitialize device paritions mapping
                retval = self.cmd.run(['kpartx', '-d', device])
                if retval != 0:
                    # don't raise an exception so we can continue with remaining devices
                    self.logger.error("failed to unmap partitions of device '{device}'")

                # If we have a filename then we set it up ourselves.
                # If not, it was already set up and it's not our responsibility to clean up.
                if 'filename' in self.install_config['disks'][disk_id]:
                    retval = self.cmd.run(['losetup', '-d', device])
                    if retval != 0:
                        # don't raise an exception so we can continue with remaining devices
                        self.logger.error("failed to detach loop device '{device}'")


    def _get_partuuid(self, path):
        partuuid = subprocess.check_output(['blkid', '-s', 'PARTUUID', '-o', 'value', path],
                                           universal_newlines=True).rstrip('\n')
        # Backup way to get uuid/partuuid. Leave it here for later use.
        # if partuuidval == '':
        #    sgdiskout = Utils.runshellcommand(
        #        "sgdisk -i 2 {} ".format(disk_device))
        #    partuuidval = (re.findall(r'Partition unique GUID.*',
        #                          sgdiskout))[0].split(':')[1].strip(' ').lower()
        return partuuid

    def _get_uuid(self, path):
        return subprocess.check_output(['blkid', '-s', 'UUID', '-o', 'value', path],
                                       universal_newlines=True).rstrip('\n')

    def _add_btrfs_subvolume_to_fstab(self, mnt_src, fstab_file, btrfs_partition, parent_subvol=''):
        """
        Recursive function to add btrfs subvolume and nested subvolumes to fstab
        fstab entry ex - UUID=0b56138b-6124-4ec4-a7a3-7c503516a65c   /data/projects    btrfs   subvol=projects    0   0
        """
        for subvol in btrfs_partition["subvols"]:
            if "mountpoint" in subvol:
                fstab_file.write(f"{mnt_src}\t{subvol['mountpoint']}\tbtrfs\tsubvol="+ os.path.join(parent_subvol, subvol['name']) +"\t0\t0\n")
            if "subvols" in subvol:
                self._add_btrfs_subvolume_to_fstab(mnt_src, fstab_file, subvol, os.path.join(parent_subvol, subvol['name']))

    def _create_fstab(self, fstab_path=None):
        """
        update fstab
        """
        if not fstab_path:
            fstab_path = os.path.join(self.photon_root, "etc/fstab")
        with open(fstab_path, "w") as fstab_file:
            fstab_file.write("#system\tmnt-pt\ttype\toptions\tdump\tfsck\n")

            for partition in self.install_config['partitions']:
                ptype = self._get_partition_type(partition)
                if ptype == PartitionType.BIOS:
                    continue
                if partition.get('shadow', False):
                    continue

                options = 'defaults'
                dump = 1
                fsck = 2

                if 'fs_options' in partition:
                    if type(partition['fs_options']) is str:
                        options += f",{partition['fs_options']}"
                    elif type(partition['fs_options']) is list:
                        options += "," + ",".join(partition['fs_options'])
                    else:
                        self.logger.error("fs_options must be of type str or list")
                        self.exit_gracefully()

                # Add supported options according to partition filesystem
                if partition.get('mountpoint', '') == '/':
                    part_fstype = partition.get('filesystem', '')
                    if part_fstype in ['ext4', 'ext3', 'swap', 'vfat']:
                        options += ',barrier,noatime,data=ordered'
                    elif part_fstype == 'btrfs':
                        options += ',barrier,noatime'
                    elif part_fstype == 'xfs':
                        pass
                    else:
                        self.logger.error(f"Filesystem type not supported: {part_fstype}")
                        self.exit_gracefully()
                    fsck = 1

                if ptype == PartitionType.SWAP:
                    mountpoint = 'swap'
                    dump = 0
                    fsck = 0
                else:
                    mountpoint = partition['mountpoint']

                # Use PARTUUID/UUID instead of bare path.
                # Prefer PARTUUID over UUID as it is supported by kernel
                # and UUID only by initrd.
                path = partition['path']
                mnt_src = None
                partuuid = self._get_partuuid(path)
                if partuuid != '':
                    mnt_src = "PARTUUID={}".format(partuuid)
                else:
                    uuid = self._get_uuid(path)
                    if uuid != '':
                        mnt_src = "UUID={}".format(uuid)
                if not mnt_src:
                    raise RuntimeError("Cannot get PARTUUID/UUID of: {}".format(path))

                fstab_file.write("{}\t{}\t{}\t{}\t{}\t{}\n".format(
                    mnt_src,
                    mountpoint,
                    partition['filesystem'],
                    options,
                    dump,
                    fsck
                    ))

                if partition.get('filesystem', '') == "btrfs" and "btrfs" in partition and "subvols" in partition["btrfs"]:
                    self._add_btrfs_subvolume_to_fstab(mnt_src, fstab_file, partition["btrfs"])

            # Add the cdrom entry
            fstab_file.write("/dev/cdrom\t/mnt/cdrom\tiso9660\tro,noauto\t0\t0\n")


    def _update_abupdate(self):
        if not self.ab_present:
            return

        abupdate_conf = os.path.join(self.photon_root, "etc/abupdate.conf")

        boot_map = {'efi':'EFI', 'bios':'BIOS', 'dualboot':'BOTH'}
        bootmode = self.install_config['bootmode']
        if not bootmode in boot_map:
            raise Exception(f"invalid boot mode '{bootmode}'")

        ab_map = {}
        for partition in self.install_config['partitions']:
            ptype = self._get_partition_type(partition)
            if ptype == PartitionType.BIOS:
                continue
            if partition.get('ab', False):
                mntpoint = partition['mountpoint']
                partuuid = self._get_partuuid(partition['path'])

                if mntpoint == '/boot/efi':
                    name = 'EFI'
                elif mntpoint == '/':
                    name = '_ROOT'
                else:
                    name = mntpoint[1:].upper().replace('/', '_')

                # we go through this twice - active and shadow
                # only add entry once
                if not name in ab_map:
                    ab_map[name] = {'mntpoint' : mntpoint}

                if partition.get('shadow', False):
                    ab_map[name]['shadow'] = partuuid
                else:
                    ab_map[name]['active'] = partuuid

        # assuming a virgin file with no settings, or no file
        with open(abupdate_conf, 'a') as f:
            f.write(f"BOOT_TYPE={boot_map[bootmode]}\n")

            for name, ab in ab_map.items():
                f.write(f"{name}=({ab['active']} {ab['shadow']} {ab['mntpoint']})\n")

            sets = " ".join(ab_map.keys())
            f.write(f"SETS=({sets})\n")


    def _generate_partitions_param(self, reverse=False):
        """
        Generate partition param for mount command
        """
        if reverse:
            step = -1
        else:
            step = 1
        params = []
        for partition in self.install_config['partitions'][::step]:
            if self._get_partition_type(partition) in [PartitionType.BIOS, PartitionType.SWAP]:
                continue

            params.extend(['--partitionmountpoint', partition["path"], partition["mountpoint"]])
        return params

    def _mount_partitions(self):
        for partition in self.install_config['partitions'][::1]:
            if self._get_partition_type(partition) in [PartitionType.BIOS, PartitionType.SWAP]:
                continue
            if partition.get('shadow', False):
                continue

            options = None
            if 'fs_options' in partition:
                if type(partition['fs_options']) is str:
                    options = partition['fs_options'].split(",")
                elif type(partition['fs_options']) is list:
                    options = partition['fs_options']
            self._mount(partition['path'], partition['mountpoint'], options=options, create=True)

            if partition['filesystem'] == "btrfs" and "btrfs" in partition:
                mntpoint = os.path.join(self.photon_root, partition['mountpoint'].strip('/'))
                if 'label' in partition['btrfs']:
                    self.cmd.run(f"btrfs filesystem label {mntpoint} {partition['btrfs']['label']}")
                if 'subvols' in partition["btrfs"]:
                    self._create_btrfs_subvolumes(mntpoint, partition['btrfs'], partition['path'])


    def _initialize_system(self):
        """
        Prepare the system to install photon
        """
        if self.install_config['ui']:
            self.progress_bar.update_message('Initializing system...')

        rpm_db_path = subprocess.check_output(['rpm', '-E', '%_dbpath'], universal_newlines=True).rstrip('\n')
        if not rpm_db_path:
            self.logger.error("Rpm db path empty...")
            self.exit_gracefully()
        # Initialize rpm DB
        self.cmd.run(['mkdir', '-p', os.path.join(self.photon_root, rpm_db_path[1:])])

        rpm_db_init_cmd = f"rpm --root {self.photon_root} --initdb --dbpath {rpm_db_path}"
        if self.cmd.checkIfHostRpmNotUsable():
            rpm_db_init_cmd = f"tdnf install -y rpm && {rpm_db_init_cmd}"
            retval = self.cmd.run(['docker', 'run', '--privileged', '--ulimit',  'nofile=1024:1024', '--rm',
                                  '-v', f"{self.photon_root}:{self.photon_root}",
                                   self.install_config['photon_docker_image'],
                                   '/bin/sh', '-c', rpm_db_init_cmd])
        else:
            retval = self.cmd.run(rpm_db_init_cmd)

        if retval != 0:
            self.logger.error("Failed to initialize rpm DB")
            self.exit_gracefully()

        retval, tdnf_out = self.tdnf.run(['install', 'filesystem'],
                                         repos=self.install_config['repos'])
        if retval != 0:
            self.logger.error("Failed to install filesystem rpm")
            self.exit_gracefully()

        # Create special devices. We need it when devtpmfs is not mounted yet.
        devices = {
            'console': (600, stat.S_IFCHR, 5, 1),
            'null': (666, stat.S_IFCHR, 1, 3),
            'random': (444, stat.S_IFCHR, 1, 8),
            'urandom': (444, stat.S_IFCHR, 1, 9)
        }
        for device, (mode, dev_type, major, minor) in devices.items():
            os.mknod(os.path.join(self.photon_root, "dev", device),
                     mode | dev_type, os.makedev(major, minor))


    def _mount_special_folders(self):
        for d in ["/proc", "/dev", "/dev/pts", "/sys"]:
            self._mount(d, d, bind=True)

        for d in ["/sys/fs/cgroup"]:
            self._mount(d, d, bind=True)

        for d in ["/tmp", "/run"]:
            self._mount('tmpfs', d, fstype='tmpfs')


    def _copy_additional_files(self):
        if 'additional_files' in self.install_config:
            for filetuples in self.install_config['additional_files']:
                for src, dest in filetuples.items():
                    if src.startswith('http://') or src.startswith('https://'):
                        temp_file = tempfile.mktemp()
                        result, msg = CommandUtils.wget(src, temp_file, False)
                        if result:
                            shutil.copyfile(temp_file, self.photon_root + dest)
                        else:
                            self.logger.error("Download failed URL: {} got error: {}".format(src, msg))
                    else:
                        srcpath = self.getfile(src)
                        if (os.path.isdir(srcpath)):
                            shutil.copytree(srcpath, self.photon_root + dest, True)
                        else:
                            shutil.copyfile(srcpath, self.photon_root + dest)

    def _finalize_system(self):
        """
        Finalize the system after the installation
        """
        if self.install_config['ui']:
            self.progress_bar.show_loading('Finalizing installation')

        self._copy_additional_files()

        self.cmd.run_in_chroot(self.photon_root, "/sbin/ldconfig")

        # Importing the pubkey
        self.cmd.run_in_chroot(self.photon_root, "rpm --import /etc/pki/rpm-gpg/*")


    def _cleanup_tdnf_cache(self):
        if self.install_config.get('no_clean', False):
            return

        # remove the tdnf cache directory
        if self.install_config['ui']:
            self.progress_bar.update_message('Cleaning up tdnf cache')

        cache_dir = os.path.join(self.photon_root, 'var/cache/tdnf')
        if (os.path.isdir(cache_dir)):
            shutil.rmtree(cache_dir)


    def _cleanup_install_repo(self):
        if self.install_config.get('no_clean', False):
            return

        if self.install_config['ui']:
            self.progress_bar.update_message('Cleaning up tdnf install repo configs')

        if os.path.exists(self.tdnf_conf_path):
            os.remove(self.tdnf_conf_path)
        if 'repos' in self.install_config:
            for repo in self.install_config['repos']:
                try:
                    os.remove(os.path.join(self.working_directory, f"{repo}.repo"))
                except FileNotFoundError:
                    pass


    def _setup_grub(self):
        bootmode = self.install_config['bootmode']

        if self.install_config['ui']:
            self.progress_bar.update_message('Setting up GRUB')

        device = self.install_config['disks']['default']['device']
        # Setup bios grub
        if bootmode == 'dualboot' or bootmode == 'bios':
            path = os.path.join(self.photon_root, "boot")
            retval = self.cmd.run(f"grub2-install --target=i386-pc --force --boot-directory={path} {device}")
            if retval != 0:
                retval = self.cmd.run(['grub-install', '--target=i386-pc', '--force',
                                       f"--boot-directory={path}",
                                       device])
                if retval != 0:
                    raise Exception("Unable to setup grub")

        # Setup efi grub
        if bootmode == 'dualboot' or bootmode == 'efi':
            esp_pn = '1'
            if bootmode == 'dualboot':
                esp_pn = '2'

            self.cmd.run(['mkdir', '-p', self.photon_root + '/boot/efi/boot/grub2'])
            with open(os.path.join(self.photon_root, 'boot/efi/boot/grub2/grub.cfg'), "w") as grub_cfg:
                grub_cfg.write("search -n -u {} -s\n".format(self._get_uuid(self.install_config['partitions_data']['boot'])))
                grub_cfg.write("set prefix=($root){}grub2\n".format(self.install_config['partitions_data']['bootdirectory']))
                grub_cfg.write("configfile {}grub2/grub.cfg\n".format(self.install_config['partitions_data']['bootdirectory']))

            if self.install_config.get('live', True):
                arch = self.install_config['arch']
                # 'x86_64' -> 'bootx64.efi', 'aarch64' -> 'bootaa64.efi'
                exe_name = 'boot'+arch[:-5]+arch[-2:]+'.efi'
                # Some platforms do not support adding boot entry. Thus, ignore failures
                self.cmd.run(['efibootmgr', '--create', '--remove-dups', '--disk', device,
                              '--part', esp_pn, '--loader', '/EFI/BOOT/' + exe_name, '--label', 'Photon'])

        # Create custom grub.cfg
        retval = self.cmd.run(
            [self.setup_grub_command, self.photon_root,
             self.install_config['partitions_data']['root'],
             self.install_config['partitions_data']['boot'],
             self.install_config['partitions_data']['bootdirectory']])

        if retval != 0:
            raise Exception("Bootloader (grub2) setup failed")

    def _execute_modules(self, phase):
        """
        Execute the scripts in the modules folder
        """
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "modules")))
        modules_paths = glob.glob(os.path.abspath(os.path.join(os.path.dirname(__file__), 'modules')) + '/m_*.py')
        for mod_path in modules_paths:
            module = os.path.splitext(os.path.basename(mod_path))[0]
            try:
                __import__(module)
                mod = sys.modules[module]
            except ImportError:
                self.logger.error('Error importing module {}'.format(module))
                continue

            # the module default is deactivate
            if not hasattr(mod, 'enabled') or mod.enabled is False:
                self.logger.info("module {} is not enabled".format(module))
                continue
            # check for the install phase
            if not hasattr(mod, 'install_phase'):
                self.logger.error("Error: can not defind module {} phase".format(module))
                continue
            if mod.install_phase != phase:
                self.logger.info("Skipping module {0} for phase {1}".format(module, phase))
                continue
            if not hasattr(mod, 'execute'):
                self.logger.error("Error: not able to execute module {}".format(module))
                continue
            self.logger.info("Executing: " + module)

            if self.install_config.get('ui', False):
                self.progress_bar.update_message('Setting up GRUB')

            mod.execute(self)

    def _adjust_packages_based_on_selected_flavor(self):
        """
        Install slected linux flavor only
        """
        redundant_linux_flavors = []

        def filter_packages(package):
            package = package.split('-')
            if len(package) > 1:
                flavor = package[1]
            else:
                flavor = ""
            if(package[0] != "linux"):
                return True
            elif("" in redundant_linux_flavors and flavor in self.linux_dependencies):
                return False
            elif(flavor in redundant_linux_flavors):
                return False
            else:
                return True

        for flavor in self.all_linux_flavors:
            if(flavor != self.install_config['linux_flavor']):
                flavor = flavor.split('-')
                if len(flavor) > 1:
                    flavor = flavor[1]
                else:
                    flavor = ""
                redundant_linux_flavors.append(flavor)
        self.install_config['packages'] = list(filter(filter_packages, self.install_config['packages']))

    def _add_packages_to_install(self, package):
        """
        Install packages on VMware virtual machine if requested
        """
        self.install_config['packages'].append(package)

    def _setup_install_repo(self):
        """
        Setup the tdnf repo for installation
        """
        repos = self.install_config['repos']
        for repo in repos:
            if self.insecure_installation:
                repos[repo]["sslverify"] =  0
            with open(os.path.join(self.working_directory, f"{repo}.repo"), "w") as repo_file:
                repo_file.write(f"[{repo}]\n")
                for key,value in repos[repo].items():
                    repo_file.write(f"{key}={value}\n")

        with open(self.tdnf_conf_path, "w") as conf_file:
            conf_file.writelines([
                "[main]\n",
                "gpgcheck=0\n",
                "installonly_limit=3\n",
                "clean_requirements_on_remove=true\n",
                "keepcache=0\n"])


    def _install_additional_rpms(self):
        rpms_path = self.install_config.get('additional_rpms_path', None)

        if not rpms_path:
            return

        if not os.path.exists(rpms_path):
            raise Exception(f"additional rpms path '{rpms_path}' not found")

        pkgs = glob.glob(os.path.join(rpms_path, "*.rpm"))
        retval, tdnf_out = self.tdnf.run(['install'] + pkgs,
                                         directories=[rpms_path],
                                         repos=self.install_config['repos'])

        if retval != 0:
            raise Exception(f"failed to install additional rpms from '{rpms_path}'")


    def _install_packages(self):
        """
        Install packages using tdnf command
        """
        self._adjust_packages_based_on_selected_flavor()
        selected_packages = self.install_config['packages']
        state = 0
        packages_to_install = {}
        total_size = 0
        stderr = None

        if self.install_config['ui']:
            tdnf_cmd = ("tdnf install -y --releasever {0} --installroot {1} "
                        "-c {2} --setopt=reposdir={3} "
                        "{4}").format(self.photon_release_version,
                                      self.photon_root,
                                      self.tdnf_conf_path,
                                      self.working_directory,
                                      " ".join(selected_packages))

            # run in shell to do not throw exception if tdnf not found
            process = subprocess.Popen(tdnf_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            while True:
                output = process.stdout.readline().decode()
                if output == '':
                    retval = process.poll()
                    if retval is not None:
                        stderr = process.communicate()[1]
                        break
                if state == 0:
                    if output == 'Installing:\n':
                        state = 1
                elif state == 1:  # N A EVR Size(readable) Size(in bytes)
                    if output == '\n':
                        state = 2
                        self.progress_bar.update_num_items(total_size)
                    else:
                        info = output.split()
                        package = '{0}-{1}.{2}'.format(info[0], info[2], info[1])
                        rpm_download_size = self.cmd.convertToBytes(info[5])
                        packages_to_install[package] = rpm_download_size
                        total_size += rpm_download_size
                elif state == 2:
                    output_status = ["Downloading", "Testing transaction"]
                    if output.startswith(tuple(output_status)):
                        self.progress_bar.update_message('Preparing ...')
                        state = 3
                elif state == 3:
                    self.progress_bar.update_message(output)
                    if output == 'Running transaction\n':
                        state = 4
                else:
                    self.logger.info("[tdnf] {0}".format(output))
                    prefix = 'Installing/Updating: '
                    if output.startswith(prefix):
                        package = output[len(prefix):].rstrip('\n')
                        self.progress_bar.increment(packages_to_install[package])

                    self.progress_bar.update_message(output)
        else:
            retval, tdnf_out = self.tdnf.run(['install'] + selected_packages, repos=self.install_config['repos'])

        # 0 : succeed; 137 : package already installed; 65 : package not found in repo.
        if retval != 0 and retval != 137:
            self.logger.error("Failed to install some packages")
            if stderr:
                self.logger.error(stderr.decode())
            self.exit_gracefully()

    def _eject_cdrom(self):
        """
        Eject the cdrom on request
        """
        if self.install_config.get('eject_cdrom', True):
            self.cmd.run(['eject', '-r'])

    def _enable_network_in_chroot(self):
        """
        Enable network in chroot
        """
        if os.path.exists("/etc/resolv.conf"):
            shutil.copy("/etc/resolv.conf", self.photon_root + '/etc/.')

    def _deactivate_network_in_chroot(self):
        """
        deactivate network in chroot
        """
        if os.path.exists(self.photon_root + '/etc/resolv.conf'):
            os.remove(self.photon_root + '/etc/resolv.conf')


    def partition_compare(self, p):
        if 'mountpoint' in p and p['mountpoint'] is not None:
            return (1, len(p['mountpoint']), p['mountpoint'])
        return (0, 0, "A")


    def _get_partition_path(self, disk, part_idx):
        prefix = ''
        if 'nvme' in disk or 'mmcblk' in disk or 'loop' in disk:
            prefix = 'p'

        # loop partitions device names are /dev/mapper/loopXpY instead of /dev/loopXpY
        if 'loop' in disk:
            path = '/dev/mapper' + disk[4:] + prefix + repr(part_idx)
        else:
            path = disk + prefix + repr(part_idx)

        return path

    def _get_partition_type(self, partition):
        if partition['filesystem'] == 'bios':
            return PartitionType.BIOS
        if partition['filesystem'] == 'swap':
            return PartitionType.SWAP
        if partition.get('mountpoint', '') == '/boot/efi' and partition['filesystem'] == 'vfat':
            return PartitionType.ESP
        if partition.get('lvm', None):
            return PartitionType.LVM
        return PartitionType.LINUX

    def _partition_type_to_string(self, ptype):
        if ptype == PartitionType.BIOS:
            return 'ef02'
        if ptype == PartitionType.SWAP:
            return '8200'
        if ptype == PartitionType.ESP:
            return 'ef00'
        if ptype == PartitionType.LVM:
            return '8e00'
        if ptype == PartitionType.LINUX:
            return '8300'
        raise Exception("Unknown partition type: {}".format(ptype))


    def _mount(self, device, mntpoint, bind=False, options=None, fstype=None, create=False):
        mntpoint = os.path.join(self.photon_root, mntpoint.strip("/"))

        self.logger.info(f"mounting {device} to {mntpoint}")
        assert mntpoint.startswith(self.photon_root)

        if create and not os.path.isdir(mntpoint):
            os.makedirs(mntpoint)

        cmd = ['mount', '-v']
        if fstype is not None:
            cmd.extend(['-t', fstype])
        if options is not None:
            cmd.extend(['-o', ','.join(options)])
        if bind:
            cmd.extend(['--bind'])
        cmd.extend([device, mntpoint])
        retval = self.cmd.run(cmd)
        if retval:
            self.logger.error(f"Failed to mount {device} to {mntpoint}")
            self.exit_gracefully()
        else:
            self.mounts.append(mntpoint)


    def _mount_btrfs_subvol(self, mountpoint, disk, subvol_name, fs_options=None, parent_subvol=""):
        """
        Mount btrfs subvolume if mountpoint specified.
        Create mountpoint directory inside given photon root.
        If nested subvolume then append parent subvolume to identify the given subvolume to mount.
        If fs_options provided then append fs_options to given mount options.
        """

        options = []
        if type(fs_options) is str:
            options = fs_options.split(",")
        elif type(fs_options) is list:
            options = fs_options
        options.append("subvol={}".format(os.path.join(parent_subvol, subvol_name)))
        self._mount(disk, mountpoint, options=options, create=True)


    def _create_btrfs_subvolumes(self, path, partition, disk, parent_subvol=""):
        """
        Recursive function to create btrfs subvolumes.

        Iterate over list of subvols in a given btrfs partition.
        If "mountpoint" exists inside subvolume mount the subvolume at given mountpoint.
        Label the subvolume if "label" exists in subvolume.
        Create nested subvolume if "subvols" key exists inside parent subvolume.
        """
        for subvol in partition["subvols"]:
            if subvol.get("name") is None:
                self.logger.error("Failed to get subvol 'name'")
                self.exit_gracefully()
            retval = self.cmd.run(["btrfs", "subvolume", "create", os.path.join(path, subvol["name"])])
            if retval:
                self.logger.error(f"Error: Failed to create subvolume {path}")
                self.exit_gracefully()
            if "mountpoint" in subvol:
                self._mount_btrfs_subvol(subvol["mountpoint"], disk, subvol["name"], subvol.get("fs_options", None), parent_subvol)
            if "label" in subvol:
                self.cmd.run(f"btrfs filesystem label " + os.path.join(path, subvol['name']) + f" {subvol['label']}")
            if "subvols" in subvol:
                self._create_btrfs_subvolumes(os.path.join(path, subvol["name"]), subvol, disk, os.path.join(parent_subvol, subvol["name"]))


    def _create_logical_volumes(self, physical_partition, vg_name, lv_partitions, extensible):
        """
        Create logical volumes
        """
        # Remove LVM logical volumes and volume groups if already exists
        # Existing lvs & vg should be removed to continue re-installation
        # else pvcreate command fails to create physical volumes even if executes forcefully
        retval = self.cmd.run(['bash', '-c', 'pvs | grep {}'. format(vg_name)])
        if retval == 0:
            # Remove LV's associated to VG and VG
            retval = self.cmd.run(["vgremove", "-f", vg_name])
            if retval != 0:
                self.logger.error("Error: Failed to remove existing vg before installation {}". format(vg_name))
        # if vg is not extensible (all lvs inside are known size) then make last lv
        # extensible, i.e. shrink it. Srinking last partition is important. We will
        # not be able to provide specified size because given physical partition is
        # also used by LVM header.
        extensible_logical_volume = None
        if not extensible:
            extensible_logical_volume = lv_partitions[-1]
            extensible_logical_volume['size'] = 0

        # create physical volume
        command = ['pvcreate', '-ff', '-y', physical_partition]
        retval = self.cmd.run(command)
        if retval != 0:
            raise Exception("Error: Failed to create physical volume, command : {}".format(command))

        # create volume group
        command = ['vgcreate', vg_name, physical_partition]
        retval = self.cmd.run(command)
        if retval != 0:
            raise Exception("Error: Failed to create volume group, command = {}".format(command))

        # create logical volumes
        for partition in lv_partitions:
            lv_cmd = ['lvcreate', '-y', '--zero', 'n']
            lv_name = partition['lvm']['lv_name']
            size = partition['size']
            if size == 0:
                # Each volume group can have only one extensible logical volume
                if not extensible_logical_volume:
                    extensible_logical_volume = partition
            else:
                lv_cmd.extend(['-L', '{}M'.format(size), '-n', lv_name, vg_name])
                retval = self.cmd.run(lv_cmd)
                if retval != 0:
                    raise Exception("Error: Failed to create logical volumes , command: {}".format(lv_cmd))
            if not "loop" in  partition['device']:
                partition['path'] = os.path.join("/dev", vg_name, lv_name)
            else:
                partition['path'] = os.path.join("/dev/mapper", f"{vg_name}-{lv_name}")

        # create extensible logical volume
        if not extensible_logical_volume:
            raise Exception("Can not fully partition VG: " + vg_name)

        lv_name = extensible_logical_volume['lvm']['lv_name']
        lv_cmd = ['lvcreate', '-y', '--zero', 'n']
        lv_cmd.extend(['-l', '100%FREE', '-n', lv_name, vg_name])

        retval = self.cmd.run(lv_cmd)
        if retval != 0:
            raise Exception("Error: Failed to create extensible logical volume, command = {}". format(lv_cmd))

        # remember pv/vg for detaching it later.
        self.lvs_to_detach['pvs'].append(os.path.basename(physical_partition))
        self.lvs_to_detach['vgs'].append(vg_name)

    def _get_partition_tree_view(self):
        # Tree View of partitions list, to be returned.
        # 1st level: dict of disks
        # 2nd level: list of physical partitions, with all information necessary to partition the disk
        # 3rd level: list of logical partitions (LVM) or detailed partition information needed to format partition
        ptv = {}

        # Dict of VG's per disk. Purpose of this dict is:
        # 1) to collect its LV's
        # 2) to accumulate total size
        # 3) to create physical partition representation for VG
        vg_partitions = {}

        partitions = self.install_config['partitions']

        for partition in partitions:
            device = partition['device']
            if device not in ptv:
                ptv[device] = []
            if device not in vg_partitions:
                vg_partitions[device] = {}

            if partition.get('lvm', None):
                vg_name = partition['lvm']['vg_name']
                if vg_name not in vg_partitions[device]:
                    vg_partitions[device][vg_name] = {
                        'size': 0,
                        'type': self._partition_type_to_string(PartitionType.LVM),
                        'extensible': False,
                        'lvs': [],
                        'vg_name': vg_name
                    }
                vg_partitions[device][vg_name]['lvs'].append(partition)
                if partition['size'] == 0:
                    vg_partitions[device][vg_name]['extensible'] = True
                    vg_partitions[device][vg_name]['size'] = 0
                else:
                    if not vg_partitions[device][vg_name]['extensible']:
                        vg_partitions[device][vg_name]['size'] = vg_partitions[device][vg_name]['size'] + partition['size']
            else:
                if 'type' in partition:
                    ptype_code = partition['type']
                else:
                    ptype_code = self._partition_type_to_string(self._get_partition_type(partition))

                l2entry = {
                    'size': partition['size'],
                    'type': ptype_code,
                    'partition': partition
                }
                ptv[device].append(l2entry)

        # Add accumulated VG partitions
        for device, vg_list in vg_partitions.items():
            ptv[device].extend(vg_list.values())

        return ptv


    def _insert_boot_partitions(self):

        def create_partition(size, filesystem, mountpoint):
            device = self.install_config['disks']['default']['device']
            return {'size' : size,
                    'filesystem' : filesystem,
                    'mountpoint' : mountpoint,
                    'disk_id' : 'default',
                    'device' : device}

        bios_found = False
        esp_found = False
        partitions = self.install_config['partitions']

        for partition in partitions:
            ptype = self._get_partition_type(partition)
            if ptype == PartitionType.BIOS:
                bios_found = True
            if ptype == PartitionType.ESP:
                esp_found = True
                efi_partition = partition

        # Adding boot partition required for ostree if already not present in partitions table
        if 'ostree' in self.install_config:
            mount_points = [partition['mountpoint'] for partition in partitions if 'mountpoint' in partition]
            if '/boot' not in mount_points:
                boot_partition = create_partition(300, "ext4", "/boot")
                partitions.insert(0, boot_partition)

        bootmode = self.install_config.get('bootmode', 'bios')

        if bootmode == 'dualboot' or bootmode == 'efi':
            # Insert efi special partition
            if not esp_found:
                efi_partition = create_partition(ESPSIZE, "vfat", "/boot/efi")
                partitions.insert(0, efi_partition)

            if self.ab_present:
                efi_partition['ab'] = True

        # Insert bios partition last to be very first
        if not bios_found and (bootmode == 'dualboot' or bootmode == 'bios'):
            bios_partition = create_partition(BIOSSIZE, "bios", None)
            partitions.insert(0, bios_partition)


    def __set_ab_partition_size(self, l2entries, used_size, total_disk_size):
        for l2 in l2entries:
            if l2['size'] == 0:
                l2['size'] = int((total_disk_size - (used_size * (1024**2))) / (2 * (1024**2)))


    def __ptv_update_partition_sizes(self, ptv):
        # For ab partitions, if we copied a partition with size==0, we need to
        # set the size explicitely for both to make sure their sizes are the
        # same.
        if self.ab_present:
            for disk, l2entries in ptv.items():
                total_disk_size = self.disk_sizes[disk]
                is_last_partition_ab = False
                used_size = 1 # first usable sector is 2048, 512 * 2048 = 1MB
                for l2 in l2entries:
                    used_size += l2['size']
                    if not 'lvs' in l2:
                        if l2['partition'].get('ab', False) and l2['partition'].get('shadow', False):
                            if l2['size'] == 0:
                                is_last_partition_ab = True

                if is_last_partition_ab:
                    self.__set_ab_partition_size(l2entries, used_size, total_disk_size)


    def _clear_vgs(self):
        retval, active_vg_list = self.cmd.get_vgnames()
        if retval != 0:
            self.logger.warning("no LVM volume groups to clear found")
        else:
            # clear VG names that are in use and that we care about
            for vg_name in self.vg_names:
                if vg_name not in active_vg_list:
                    continue
                retval = self.cmd.run(['vgremove', '-ff', vg_name])
                if retval == 0:
                    self.logger.info(f"Cleared volume group {vg_name} and its associated LVs")
                else:
                    self.logger.error(f"Error: Failed to remove existing VG: {vg_name} before clearing the disk")
                    self.exit_gracefully()


    def _check_device(self, device):
        with open("/proc/mounts", "rt") as f:
            for line in f:
                if line.startswith(device):
                    raise Exception("device '{device}' appears to be in use (mounted)")


    def _partition_disks(self):
        """
        Partition the disk
        """

        if self.install_config['ui']:
            self.progress_bar.update_message('Partitioning...')

        ptv = self._get_partition_tree_view()

        self.__ptv_update_partition_sizes(ptv)

        self.logger.info(json.dumps(ptv, indent=4))

        partitions = self.install_config['partitions']
        partitions_data = {}
        lvm_present = False

        # Partitioning disks
        for device, l2entries in ptv.items():
            self._check_device(device)

            # Clear the disk first
            retval = self.cmd.run(["sgdisk", "-Z", device])
            if retval != 0:
                raise Exception(f"failed clearing disk '{device}'")

            # Build partition command and insert 'part' into 'partitions'
            part_idx = 1
            partition_cmd = ['sgdisk']
            # command option for extensible partition
            last_partition = None

            for l2 in l2entries:
                if 'lvs' in l2:
                    # will be used for _create_logical_volumes() invocation
                    l2['path'] = self._get_partition_path(device, part_idx)
                else:
                    l2['partition']['path'] = self._get_partition_path(device, part_idx)

                if l2['size'] == 0:
                    last_partition = []
                    last_partition.extend(['-n{}'.format(part_idx)])
                    last_partition.extend(['-t{}:{}'.format(part_idx, l2['type'])])
                else:
                    partition_cmd.extend(['-n{}::+{}M'.format(part_idx, l2['size'])])
                    partition_cmd.extend(['-t{}:{}'.format(part_idx, l2['type'])])
                part_idx += 1

            # if extensible partition present, add it to the end of the disk
            if last_partition:
                partition_cmd.extend(last_partition)
            partition_cmd.extend(['-p', device])

            # Run the partitioning command (all physical partitions in one shot)
            retval = self.cmd.run(partition_cmd)
            if retval != 0:
                raise Exception(f"failed partition disk, command: {partition_cmd}")

            # For RPi image we used 'parted' instead of 'sgdisk':
            # parted -s $IMAGE_NAME mklabel msdos mkpart primary fat32 1M 30M mkpart primary ext4 30M 100%
            # Try to use 'sgdisk -m' to convert GPT to MBR and see whether it works.
            if self.install_config.get('partition_type', 'gpt') == 'msdos':
                # m - colon separated partitions list
                m = ":".join([str(i) for i in range(1, part_idx)])
                retval = self.cmd.run(['sgdisk', '-m', m, device])
                if retval != 0:
                    raise Exception("Failed to setup efi partition")

            # Make loop disk partitions available
            if 'loop' in device:
                retval = self.cmd.run(['kpartx', '-avs', device])
                if retval != 0:
                    raise Exception(f"failed to rescan partitions of the disk image {device}")

            # Go through l2 entries again and create logical partitions
            for l2 in l2entries:
                if 'lvs' not in l2:
                    continue
                lvm_present = True
                self._create_logical_volumes(l2['path'], l2['vg_name'], l2['lvs'], l2['extensible'])

        if lvm_present:
            # add lvm2 package to install list
            self._add_packages_to_install('lvm2')

        # Create partitions_data (needed for mk-setup-grub.sh)
        for partition in partitions:
            if 'mountpoint' in partition and not partition.get('shadow', False):
                if partition['mountpoint'] == '/':
                    partitions_data['root'] = partition['path']
                elif partition['mountpoint'] == '/boot':
                    partitions_data['boot'] = partition['path']
                    partitions_data['bootdirectory'] = '/'

        # If no separate boot partition, then use /boot folder from root partition
        if 'boot' not in partitions_data:
            partitions_data['boot'] = partitions_data['root']
            partitions_data['bootdirectory'] = '/boot/'

        # Sort partitions by mountpoint to be able to mount and
        # unmount it in proper sequence
        partitions.sort(key=lambda p: self.partition_compare(p))

        self.install_config['partitions_data'] = partitions_data

    def _format_partitions(self):
        partitions = self.install_config['partitions'].copy()
        self.logger.info(json.dumps(partitions, indent=4))

        # Format the filesystem
        for partition in partitions:
            ptype = self._get_partition_type(partition)
            # Do not format BIOS boot partition
            if ptype == PartitionType.BIOS:
                continue
            if ptype == PartitionType.SWAP:
                mkfs_cmd = ['mkswap']
            else:
                mkfs_cmd = ['mkfs', '-t', partition['filesystem']]

            # Add force option to mkfs to override previously created partition
            if partition["filesystem"] in ["btrfs", "xfs"]:
                mkfs_cmd.extend(['-f'])

            if 'mkfs_options' in partition:
                options = re.sub(r"[^\S]", " ", partition['mkfs_options']).split()
                mkfs_cmd.extend(options)

            mkfs_cmd.extend([partition['path']])
            retval = self.cmd.run(mkfs_cmd)

            if retval != 0:
                raise Exception(
                    "Failed to format {} partition @ {}".format(partition['filesystem'],
                                                                partition['path']))

    def getfile(self, filename):
        """
        Returns absolute filepath by filename.
        """
        for dirname in self.install_config['search_path']:
            filepath = os.path.join(dirname, filename)
            if os.path.exists(filepath):
                return filepath
        raise Exception("File {} not found in the following directories {}".format(filename, self.install_config['search_path']))
