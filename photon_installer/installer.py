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
import json
from logger import Logger
from commandutils import CommandUtils
from jsonwrapper import JsonWrapper
from progressbar import ProgressBar
from window import Window
from networkmanager import NetworkManager
from enum import Enum
from collections import abc

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
        'arch',
        'autopartition',
        'bootmode',
        'disk',
        'eject_cdrom',
        'hostname',
        'install_linux_esx',
        'linux_flavor',
        'live',
        'log_level',
        'ostree',
        'packages',
        'packagelist_file',
        'partition_type',
        'partitions',
        'network',
        'password',
        'postinstall',
        'postinstallscripts',
        'preinstall',
        'preinstallscripts',
        'public_key',
        'photon_docker_image',
        'search_path',
        'setup_grub_script',
        'shadow_password',
        'type',
        'ui'
    }

    default_partitions = [{"mountpoint": "/", "size": 0, "filesystem": "ext4"}]
    all_linux_flavors = ["linux", "linux-esx", "linux-aws", "linux-secure", "linux-rt"]
    linux_dependencies = ["devel", "drivers", "docs", "oprofile", "dtb"]

    def __init__(self, working_directory="/mnt/photon-root",
                 rpm_path=os.path.dirname(__file__)+"/../stage/RPMS", log_path=os.path.dirname(__file__)+"/../stage/LOGS",
                 insecure_installation=False, photon_release_version='4.0'):
        self.exiting = False
        self.interactive = False
        self.install_config = None
        self.rpm_path = rpm_path
        self.log_path = log_path
        self.logger = None
        self.cmd = None
        self.working_directory = working_directory
        self.insecure_installation = insecure_installation
        self.photon_release_version = photon_release_version
        self.ab_present = False

        if os.path.exists(self.working_directory) and os.path.isdir(self.working_directory) and working_directory == '/mnt/photon-root':
            shutil.rmtree(self.working_directory)
        if not os.path.exists(self.working_directory):
            os.mkdir(self.working_directory)

        self.installer_path = os.path.dirname(os.path.abspath(__file__))

        self.photon_root = self.working_directory + "/photon-chroot"
        self.tdnf_conf_path = self.working_directory + "/tdnf.conf"
        self.tdnf_repo_path = self.working_directory + "/photon-local.repo"

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

        # run preinstall scripts before installation begins
        if install_config:
            self._load_preinstall(install_config)

        # run UI configurator iff install_config param is None
        if not install_config and ui_config:
            from iso_config import IsoConfig
            self.interactive = True
            config = IsoConfig()
            install_config = curses.wrapper(config.configure, ui_config)

        self._add_defaults(install_config)

        issue = self._check_install_config(install_config)
        if issue:
            self.logger.error(issue)
            raise Exception(issue)

        self.install_config = install_config

        self.ab_present = self._is_ab_present()

        self._insert_boot_partitions()

        self._add_shadow_partitions()


    def execute(self):
        if 'setup_grub_script' in self.install_config:
            self.setup_grub_command = self.install_config['setup_grub_script']

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
                        else:
                            raise Exception("Install configuration has dynamic value=\"{}\" for key=\"{}\" \
                                            \n which is not exported in preinstall script. \
                                            \n Please export dynamic values in preinstall script in ks file as below: \
                                            \n export {}=\"<my-val>\"".format(value,key,value[1:]))


    def _load_preinstall(self, install_config):
        self.install_config = install_config
        self._execute_modules(modules.commons.PRE_INSTALL)
        for fill_values in self._fill_dynamic_conf(install_config):
            print(fill_values)


    def _add_defaults(self, install_config):
        """
        Add default install_config settings if not specified
        """
        # set arch to host's one if not defined
        arch = subprocess.check_output(['uname', '-m'], universal_newlines=True).rstrip('\n')
        if 'arch' not in install_config:
            install_config['arch'] = arch

        # 'bootmode' mode
        if 'bootmode' not in install_config:
            if "x86_64" in arch:
                install_config['bootmode'] = 'dualboot'
            else:
                install_config['bootmode'] = 'efi'

        # extend 'packages' by 'packagelist_file' and 'additional_packages'
        packages = []
        if 'packagelist_file' in install_config:
            plf = install_config['packagelist_file']
            if not plf.startswith('/'):
                plf = os.path.join(os.getcwd(), plf)
            json_wrapper_package_list = JsonWrapper(plf)
            package_list_json = json_wrapper_package_list.read()
            if "packages_" + install_config['arch'] in package_list_json:
                packages.extend(package_list_json["packages"] + package_list_json["packages_"+install_config['arch']])
            else:
                packages.extend(package_list_json["packages"])

        if 'additional_packages' in install_config:
            packages.extend(install_config['additional_packages'])

        # add bootloader packages after bootmode set
        if install_config['bootmode'] in ['dualboot', 'efi']:
            packages.append('grub2-efi-image')

        if 'packages' in install_config:
            install_config['packages'] = list(set(packages + install_config['packages']))
        else:
            install_config['packages'] = packages

        # live means online system, and it's True be default. When you create an image for
        # target system, live should be set to False.
        if 'live' not in install_config:
            if 'loop' in install_config['disk']:
                install_config['live'] = False

        # default partition
        if 'partitions' not in install_config:
            install_config['partitions'] = Installer.default_partitions

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

        if 'linux_flavor' not in install_config:
            if install_config.get('install_linux_esx', False):
                install_config['linux_flavor'] = "linux-esx"
            else:
                available_flavors = []
                for flavor in self.all_linux_flavors:
                    if flavor in install_config['packages']:
                        available_flavors.append(flavor)
                if len(available_flavors) == 1:
                    install_config['linux_flavor'] = available_flavors[0]

        install_config['install_linux_esx'] = False

        # Default Photon docker image
        if 'photon_docker_image' not in install_config:
            install_config['photon_docker_image'] = "photon:latest"

    def _check_install_config(self, install_config):
        """
        Sanity check of install_config before its execution.
        Return error string or None
        """

        unknown_keys = install_config.keys() - Installer.known_keys
        if len(unknown_keys) > 0:
            return "Unknown install_config keys: " + ", ".join(unknown_keys)

        if 'disk' not in install_config:
            return "No disk configured"

        # For Ostree install_config['packages'] will be empty list, because ostree
        # uses preinstalled tree ostree-repo.tar.gz for installation
        if 'ostree' not in install_config and 'linux_flavor' not in install_config:
            return "Attempting to install more than one linux flavor"

        # Perform following checks here:
        # 1) Only one extensible partition is allowed per disk
        # 2) /boot can not be LVM
        # 3) / must present
        # 4) Duplicate mountpoints should not be present
        has_extensible = {}
        has_root = False
        mountpoints = []
        default_disk = install_config['disk']
        for partition in install_config['partitions']:
            disk = partition.get('disk', default_disk)
            mntpoint = partition.get('mountpoint', '')
            if disk not in has_extensible:
                has_extensible[disk] = False
            size = partition['size']
            if size == 0:
                if has_extensible[disk]:
                    return "Disk {} has more than one extensible partition".format(disk)
                else:
                    has_extensible[disk] = True
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

        if install_config['arch'] not in ["aarch64", 'x86_64']:
            return "Unsupported target architecture {}".format(install_config['arch'])

        # No BIOS for aarch64
        if install_config['arch'] == 'aarch64' and install_config['bootmode'] in ['dualboot', 'bios']:
            return "Aarch64 targets do not support BIOS boot. Set 'bootmode' to 'efi'."

        if 'age' in install_config.get('password', {}):
            if install_config['password']['age'] < -1:
                return "Password age should be -1, 0 or positive"

        for partition in install_config['partitions']:
            if partition.get('ab', False):
                if partition.get('lvm', None):
                    return "ab partition cannot be LVM"

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
            self._cleanup_install_repo()
            self._setup_grub()
            self._create_fstab()
            self._update_abupdate()
        self._execute_modules(modules.commons.POST_INSTALL)
        self._deactivate_network_in_chroot()
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
        nm = NetworkManager(self.install_config['network'], self.photon_root)
        if not nm.setup_network():
            self.logger.error("Failed to setup network!")
            self.exit_gracefully()
        nm.set_perms()

        # Configure network when in live mode (ISO)
        if (self.install_config.get('live', True)):
            nm.restart_networkd()


    def _unmount_all(self):
        """
        Unmount partitions and special folders
        """
        for d in ["/tmp", "/run", "/sys", "/dev/pts", "/dev", "/proc"]:
            if os.path.exists(self.photon_root + d):
                retval = self.cmd.run(['umount', '-l', self.photon_root + d])
                if retval != 0:
                    self.logger.error("Failed to unmount {}".format(d))

        for partition in self.install_config['partitions'][::-1]:
            if self._get_partition_type(partition) in [PartitionType.BIOS, PartitionType.SWAP]:
                continue
            if partition.get('shadow', False):
                continue

            mountpoint = self.photon_root + partition["mountpoint"]
            if os.path.exists(mountpoint):
                retval = self.cmd.run(['umount', '-l', mountpoint])
                if retval != 0:
                    self.logger.error("Failed to unmount partition {}".format(mountpoint))

        # need to call it twice, because of internal bind mounts
        if 'ostree' in self.install_config:
            if os.path.exists(self.photon_root):
                retval = self.cmd.run(['umount', '-R', self.photon_root])
                retval = self.cmd.run(['umount', '-R', self.photon_root])
                if retval != 0:
                    self.logger.error("Failed to unmount disks in photon root")

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
        disks = set(partition.get('disk', self.install_config['disk']) for partition in self.install_config['partitions'])
        for disk in disks:
            if 'loop' in disk:
                # Uninitialize device paritions mapping
                retval = self.cmd.run(['kpartx', '-d', disk])
                if retval != 0:
                    self.logger.error("Failed to unmap partitions of the disk image {}". format(disk))
                    return None


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

                # Add supported options according to partition filesystem
                if partition.get('mountpoint', '') == '/' and partition.get('filesystem','') != 'xfs':
                    options = options + ',barrier,noatime'
                    if partition.get('filesystem','') != 'btrfs':
                        options += ',data=ordered'
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
            mountpoint = self.photon_root + partition["mountpoint"]
            self.cmd.run(['mkdir', '-p', mountpoint])
            mount_cmd = ['mount', '-v']
            if "fs_options" in partition:
                mount_cmd.extend(['-o', partition['fs_options']])
            mount_cmd.extend([partition["path"], mountpoint])
            retval = self.cmd.run(mount_cmd)
            if retval != 0:
                self.logger.error("Failed to mount partition {}".format(partition["path"]))
                self.exit_gracefully()
            if partition['filesystem'] == "btrfs" and "btrfs" in partition:
                if "label" in partition["btrfs"]:
                    self.cmd.run(f"btrfs filesystem label {mountpoint} {partition['btrfs']['label']}")
                if "subvols" in partition["btrfs"]:
                    self._create_btrfs_subvolumes(mountpoint, partition["btrfs"], partition["path"])

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
            retval = self.cmd.run(['docker', 'run', '--ulimit',  'nofile=1024:1024', '--rm',
                                  '-v', f"{self.photon_root}:{self.photon_root}",
                                   self.install_config['photon_docker_image'],
                                   '/bin/sh', '-c', rpm_db_init_cmd])
        else:
            retval = self.cmd.run(rpm_db_init_cmd)

        if retval != 0:
            self.logger.error("Failed to initialize rpm DB")
            self.exit_gracefully()

        # Install filesystem rpm
        tdnf_cmd = ("tdnf install -y filesystem --releasever {0} "
                    "--installroot {1} -c {2} "
                    "--setopt=reposdir={3}").format(self.photon_release_version,
                                                    self.photon_root,
                                                    self.tdnf_conf_path,
                                                    self.working_directory)
        retval = self.cmd.run(tdnf_cmd)
        if retval != 0:
            retval = self._run_tdnf_in_docker(tdnf_cmd)
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
            retval = self.cmd.run(['mount', '-o', 'bind', d, self.photon_root + d])
            if retval != 0:
                self.logger.error("Failed to bind mount {}".format(d))
                self.exit_gracefully()

        for d in ["/tmp", "/run"]:
            retval = self.cmd.run(['mount', '-t', 'tmpfs', 'tmpfs', self.photon_root + d])
            if retval != 0:
                self.logger.error("Failed to bind mount {}".format(d))
                self.exit_gracefully()

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

    def _cleanup_install_repo(self):
        # remove the tdnf cache directory
        cache_dir = os.path.join(self.photon_root, 'var/cache/tdnf')
        if (os.path.isdir(cache_dir)):
            shutil.rmtree(cache_dir)
        if os.path.exists(self.tdnf_conf_path):
            os.remove(self.tdnf_conf_path)
        if os.path.exists(self.tdnf_repo_path):
            os.remove(self.tdnf_repo_path)

    def _setup_grub(self):
        bootmode = self.install_config['bootmode']

        # Setup bios grub
        if bootmode == 'dualboot' or bootmode == 'bios':
            retval = self.cmd.run('grub2-install --target=i386-pc --force --boot-directory={} {}'.format(self.photon_root + "/boot", self.install_config['disk']))
            if retval != 0:
                retval = self.cmd.run(['grub-install', '--target=i386-pc', '--force',
                                      '--boot-directory={}'.format(self.photon_root + "/boot"),
                                      self.install_config['disk']])
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
                self.cmd.run(['efibootmgr', '--create', '--remove-dups', '--disk', self.install_config['disk'],
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
        with open(self.tdnf_repo_path, "w") as repo_file:
            repo_file.write("[photon-local]\n")
            repo_file.write("name=VMware Photon OS Installer\n")

            if self.rpm_path.startswith('/'):
                repo_file.write("baseurl=file://{}\n".format(self.rpm_path))
            else:
                repo_file.write("baseurl={}\n".format(self.rpm_path))

            repo_file.write("gpgcheck=0\nenabled=1\n")
            if self.insecure_installation:
                repo_file.write("sslverify=0\n")
        with open(self.tdnf_conf_path, "w") as conf_file:
            conf_file.writelines([
                "[main]\n",
                "gpgcheck=0\n",
                "installonly_limit=3\n",
                "clean_requirements_on_remove=true\n",
                "keepcache=0\n"])

    def _install_additional_rpms(self):
        rpms_path = self.install_config.get('additional_rpms_path', None)

        if not rpms_path or not os.path.exists(rpms_path):
            return

        if self.cmd.run(['rpm', '--root', self.photon_root, '-U', rpms_path + '/*.rpm']) != 0:
            self.logger.info('Failed to install additional_rpms from ' + rpms_path)
            self.exit_gracefully()


    def _run_tdnf_in_docker(self, tdnf_cmd):
        docker_args = ['docker', 'run', '--rm', '--ulimit',  'nofile=1024:1024']
        docker_args.extend(['-v', f'{self.working_directory}:{self.working_directory}'])

        rpm_path = self.rpm_path
        if rpm_path.startswith('file://'):
            rpm_path = rpm_path[7:]
        if rpm_path.startswith('/'):
            docker_args.extend(['-v', f'{rpm_path}:{rpm_path}'])
        docker_args.extend([self.install_config["photon_docker_image"], "/bin/sh", "-c", tdnf_cmd])
        self.logger.info(' '.join(docker_args))
        return self.cmd.run(docker_args)


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
        tdnf_cmd = ("tdnf install -y --releasever {0} --installroot {1} "
                    "-c {2} --setopt=reposdir={3} "
                    "{4}").format(self.photon_release_version,
                                  self.photon_root,
                                  self.tdnf_conf_path,
                                  self.working_directory,
                                  " ".join(selected_packages))
        self.logger.debug(tdnf_cmd)

        # run in shell to do not throw exception if tdnf not found
        process = subprocess.Popen(tdnf_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if self.install_config['ui']:
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
            stdout, stderr = process.communicate()
            self.logger.info(stdout.decode())
            retval = process.returncode
            # image creation. host's tdnf might not be available or can be outdated (Photon 1.0)
            # retry with docker container
            if retval != 0 and retval != 137:
                self.logger.error(stderr.decode())
                stderr = None
                self.logger.info("Retry 'tdnf install' using docker image")
                retval = self._run_tdnf_in_docker(tdnf_cmd)

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
        if 'mountpoint' in p:
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

    def _mount_btrfs_subvol(self, mountpoint, disk, subvol_name, fs_options=None, parent_subvol=""):
        """
        Mount btrfs subvolume if mountpoint specified.
        Create mountpoint directory inside given photon root.
        If nested subvolume then append parent subvolume to identify the given subvolume to mount.
        If fs_options provided then append fs_options to given mount options.
        """
        self.logger.info(self.photon_root + mountpoint)
        mountpt = self.photon_root + mountpoint
        self.cmd.run(["mkdir", "-p", mountpt])
        mount_cmd = ['mount', '-v', disk]
        options = "subvol=" + os.path.join(parent_subvol, subvol_name)
        if fs_options:
            options += f",{fs_options}"
        mount_cmd.extend(['-o', options, mountpt])
        retval = self.cmd.run(mount_cmd)
        if retval:
            self.logger.error(f"Failed to mount subvolume {parent_subvol}/{subvol_name} to {mountpt}")
            self.exit_gracefully()

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
            lv_cmd = ['lvcreate', '-y']
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
            partition['path'] = '/dev/' + vg_name + '/' + lv_name

        # create extensible logical volume
        if not extensible_logical_volume:
            raise Exception("Can not fully partition VG: " + vg_name)

        lv_name = extensible_logical_volume['lvm']['lv_name']
        lv_cmd = ['lvcreate', '-y']
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

        # /dev/disk/by-path/pci-* -> ../../dev/sd* is symlink to device file
        # To handle the case for ex:
        # 'disk' : '/dev/disk/by-path/pci-0000:03:00.0-scsi-0:0:0:0'
        self.install_config['disk'] = os.path.realpath(self.install_config['disk'])

        default_disk = self.install_config['disk']
        partitions = self.install_config['partitions']
        for partition in partitions:
            if 'disk' in partition:
                partition['disk'] = os.path.realpath(partition['disk'])
            disk = partition.get('disk', default_disk)
            if disk not in ptv:
                ptv[disk] = []
            if disk not in vg_partitions:
                vg_partitions[disk] = {}

            if partition.get('lvm', None):
                vg_name = partition['lvm']['vg_name']
                if vg_name not in vg_partitions[disk]:
                    vg_partitions[disk][vg_name] = {
                        'size': 0,
                        'type': self._partition_type_to_string(PartitionType.LVM),
                        'extensible': False,
                        'lvs': [],
                        'vg_name': vg_name
                    }
                vg_partitions[disk][vg_name]['lvs'].append(partition)
                if partition['size'] == 0:
                    vg_partitions[disk][vg_name]['extensible'] = True
                    vg_partitions[disk][vg_name]['size'] = 0
                else:
                    if not vg_partitions[disk][vg_name]['extensible']:
                        vg_partitions[disk][vg_name]['size'] = vg_partitions[disk][vg_name]['size'] + partition['size']
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
                ptv[disk].append(l2entry)

        # Add accumulated VG partitions
        for disk, vg_list in vg_partitions.items():
            ptv[disk].extend(vg_list.values())

        return ptv


    def _insert_boot_partitions(self):
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
                boot_partition = {'size': 300, 'filesystem': 'ext4', 'mountpoint': '/boot'}
                partitions.insert(0, boot_partition)

        bootmode = self.install_config.get('bootmode', 'bios')

        if bootmode == 'dualboot' or bootmode == 'efi':
            # Insert efi special partition
            if not esp_found:
                efi_partition = {'size': ESPSIZE, 'filesystem': 'vfat', 'mountpoint': '/boot/efi'}
                partitions.insert(0, efi_partition)

            if self.ab_present:
                efi_partition['ab'] = True

        # Insert bios partition last to be very first
        if not bios_found and (bootmode == 'dualboot' or bootmode == 'bios'):
            bios_partition = {'size': BIOSSIZE, 'filesystem': 'bios'}
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
                retval, total_disk_size = CommandUtils.get_disk_size_bytes(disk)
                if retval != 0:
                    self.logger.info("Error code: {}".format(retval))
                    raise Exception("Failed to get disk {0} size".format(disk))
                total_disk_size = int(total_disk_size)
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
        for disk, l2entries in ptv.items():

            # Clear the disk first
            retval = self.cmd.run(['sgdisk', '-o', '-g', disk])
            if retval != 0:
                raise Exception("Failed clearing disk {0}".format(disk))

            # Build partition command and insert 'part' into 'partitions'
            part_idx = 1
            partition_cmd = ['sgdisk']
            # command option for extensible partition
            last_partition = None

            for l2 in l2entries:
                if 'lvs' in l2:
                    # will be used for _create_logical_volumes() invocation
                    l2['path'] = self._get_partition_path(disk, part_idx)
                else:
                    l2['partition']['path'] = self._get_partition_path(disk, part_idx)

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
            partition_cmd.extend(['-p', disk])

            # Run the partitioning command (all physical partitions in one shot)
            retval = self.cmd.run(partition_cmd)
            if retval != 0:
                raise Exception("Failed partition disk, command: {0}".format(partition_cmd))

            # For RPi image we used 'parted' instead of 'sgdisk':
            # parted -s $IMAGE_NAME mklabel msdos mkpart primary fat32 1M 30M mkpart primary ext4 30M 100%
            # Try to use 'sgdisk -m' to convert GPT to MBR and see whether it works.
            if self.install_config.get('partition_type', 'gpt') == 'msdos':
                # m - colon separated partitions list
                m = ":".join([str(i) for i in range(1, part_idx)])
                retval = self.cmd.run(['sgdisk', '-m', m, disk])
                if retval != 0:
                    raise Exception("Failed to setup efi partition")

            # Make loop disk partitions available
            if 'loop' in disk:
                retval = self.cmd.run(['kpartx', '-avs', disk])
                if retval != 0:
                    raise Exception("Failed to rescan partitions of the disk image {}". format(disk))

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
            if 'filesystem' in partition and not partition.get('shadow', False):
                if partition['filesystem'] == "xfs":
                    self._add_packages_to_install('xfsprogs')
                elif partition['filesystem'] == "btrfs":
                    self._add_packages_to_install('btrfs-progs')

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
