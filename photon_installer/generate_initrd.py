#
# Copyright © 2023 VMware, Inc.
# SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# pylint: disable=invalid-name,missing-docstring,no-member
import os
import stat
import shutil
import subprocess

from tdnf import Tdnf, create_repo_conf
from commandutils import CommandUtils


INITRD_FSTAB = """# Begin /etc/fstab for a bootable CD

# file system  mount-point  type   options         dump  fsck
#                                                        order
#/dev/EDITME     /            EDITME  defaults        1     1
#/dev/EDITME     swap         swap   pri=1           0     0
proc           /proc        proc   defaults        0     0
sysfs          /sys         sysfs  defaults        0     0
devpts         /dev/pts     devpts gid=4,mode=620  0     0
tmpfs          /dev/shm     tmpfs  defaults        0     0
tmpfs          /run         tmpfs  defaults        0     0
devtmpfs       /dev         devtmpfs mode=0755,nosuid 0   0
# End /etc/fstab
"""


class IsoInitrd:
    def __init__(self, **kwargs):
        known_kw = [
            "logger",
            "working_dir",
            "initrd_pkgs",
            "rpms_path",
            "photon_release_version",
            "pkg_list_file",
            "install_options_file",
            "ostree_iso",
        ]
        for key in kwargs:
            if key not in known_kw:
                raise KeyError("Not a known keyword")
            else:
                attr = kwargs.get(key, None)
                setattr(self, key, attr)

        self.cmd_util = CommandUtils(self.logger)
        self.initrd_path = os.path.join(self.working_dir, "photon-chroot")
        self.license_text = f"VMWARE {self.photon_release_version} LICENSE AGREEMENT"
        if CommandUtils.exists_in_file(
            "BETA LICENSE AGREEMENT", os.path.join(self.working_dir, "EULA.txt")
        ):
            self.license_text = (
                f"VMWARE {self.photon_release_version} BETA LICENSE AGREEMENT"
            )
        self.tdnf = Tdnf(
            logger=self.logger,
            reposdir=self.working_dir,
            releasever=self.photon_release_version,
            installroot=self.initrd_path,
            docker_image=f"photon:{self.photon_release_version}",
        )

    def create_installer_script(self):
        script_content = f"""#!/bin/bash
            cd /installer
            ACTIVE_CONSOLE="$(< /sys/devices/virtual/tty/console/active)"
            install() {{
            LANG=en_US.UTF-8 photon-installer -i iso -o {self.install_options_file} -e EULA.txt -t "{self.license_text}" -v {self.photon_release_version} && shutdown -r now
            }}
            try_run_installer() {{
            if [ "$ACTIVE_CONSOLE" == "tty0" ]; then
                [ "$(tty)" == '/dev/tty1' ] && install
            else
                [ "$(tty)" == "/dev/$ACTIVE_CONSOLE" ] && install
            fi
            }}
            try_run_installer || exec /bin/bash
            """

        with open(
            f"{self.initrd_path}/bin/bootphotoninstaller", "w", encoding="utf-8"
        ) as f:
            f.write(script_content)
        os.chmod(f"{self.initrd_path}/bin/bootphotoninstaller", 0o755)

    def create_init_script(self):
        with open(f"{self.initrd_path}/init", "w", encoding="utf-8") as init_script:
            init_script.writelines(
                ["mount -t proc proc /proc\n", "/lib/systemd/systemd"]
            )
        os.chmod(f"{self.initrd_path}/init", 0o755)

    def strip_if_needed(self, file_path):
        try:
            output = subprocess.check_output(["file", file_path], text=True)
            stripped_files = [
                line.split(":")[0]
                for line in output.splitlines()
                if "ELF" in line and "not stripped" in line
            ]
            for stripped_file in stripped_files:
                self.cmd_util.run(["strip", stripped_file])
        except Exception as err:
            raise Exception(f"Failed to strip {file_path} with err: {err}")

    def process_files(self):
        try:
            lib_directory = os.path.join(self.initrd_path, "usr/lib/")

            for file in os.listdir(lib_directory):
                if os.path.isfile(file):
                    self.strip_if_needed(
                        os.path.join(self.initrd_path, "usr/lib", file)
                    )
        except subprocess.CalledProcessError as err:
            print(f"Error processing {file}: {err}")

    def clean_up(self):
        exclusions = ["terminfo", "cracklib", "grub", "factory", "dbus-1"]
        dir_to_list = ["usr/share", "usr/sbin"]
        listed_contents = []

        files_to_remove = [
            "/home/*",
            "/var/cache",
            "/var/lib/rpm*",
            "/var/lib/.rpm*",
            "/usr/lib/sysimage/rpm*",
            "/usr/lib/sysimage/.rpm",
            "/usr/lib/sysimage/tdnf",
            "/boot",
            "/usr/include",
            "/usr/sbin/sln",
            "/usr/bin/iconv",
            "/usr/bin/oldfind",
            "/usr/bin/localedef",
            "/usr/bin/sqlite3",
            "/usr/bin/grub2-*",
            "/usr/bin/bsdcpio",
            "/usr/bin/bsdtar",
            "/usr/bin/networkctl",
            "/usr/bin/machinectl",
            "/usr/bin/pkg-config",
            "/usr/bin/openssl",
            "/usr/bin/timedatectl",
            "/usr/bin/localectl",
            "/usr/bin/systemd-cgls",
            "/usr/bin/systemd-analyze",
            "/usr/bin/systemd-nspawn",
            "/usr/bin/systemd-inhibit",
            "/usr/bin/systemd-studio-bridge",
            "/usr/lib/python*/lib2to3",
            "/usr/lib/python*/lib-tk",
            "/usr/lib/python*/ensurepip",
            "/usr/lib/python*/distutils",
            "/usr/lib/python*/pydoc_data",
            "/usr/lib/python*/idlelib",
            "/usr/lib/python*/unittest",
            "/usr/lib/librpmbuild.so*",
            "/usr/lib/libdb_cxx*",
            "/usr/lib/libnss_compat*",
            "/usr/lib/grub/i386-pc/*.module",
            "/usr/lib/grub/x86_64-efi/*.module",
            "/usr/lib/grub/arm64-efi/*.module",
            "/usr/lib/libmvec*",
            "/usr/lib/gconv",
        ]

        for directory in dir_to_list:
            contents = os.listdir(os.path.join(self.initrd_path, directory))
            listed_contents.extend(contents)

        for file_name in listed_contents:
            if file_name not in exclusions:
                files_to_remove.append(os.path.join("/usr/share", file_name))
            if file_name.startswith("grub2") and file_name != "grub2-install":
                files_to_remove.append(os.path.join("/usr/sbin", file_name))

        files_to_remove = [
            os.path.join(self.initrd_path, file[1:]) for file in files_to_remove
        ]

        self.cmd_util.remove_files(files_to_remove)

    def install_initrd_packages(self):
        tdnf_args = ["install"] + self.initrd_pkgs
        mount_dirs = []
        if self.ostree_iso:
            self.tdnf.config_file = None
            self.tdnf.reposdir = None
        else:
            mount_dirs = [self.rpms_path, self.working_dir]

        self.tdnf.run(tdnf_args, directories=mount_dirs)

    def prepare_installer_dir(self):
        installer_dir = f"{self.initrd_path}/installer"

        if not os.path.exists(installer_dir):
            os.mkdir(installer_dir)

        files_to_move = ["sample_ui.cfg", "EULA.txt", self.install_options_file]
        for file_name in files_to_move:
            source_path = f"{self.working_dir}/{file_name}"
            destination_path = f"{self.initrd_path}/installer/{file_name}"

            try:
                shutil.move(source_path, destination_path)
                self.logger.info(f"Moved {file_name} successfully.")
            except Exception as err:
                raise Exception(f"Error moving {file_name}: {err}")

        # Copy provided pkg list file into installer
        file_to_copy = (
            f"{self.initrd_path}/installer/{os.path.basename(self.pkg_list_file)}"
        )
        if not os.path.exists(file_to_copy):
            shutil.copyfile(self.pkg_list_file, file_to_copy)

    def build_initrd(self):
        os.makedirs(self.initrd_path, exist_ok=True)

        # Explicitly set permission to 755 as it is ignored when passed through mode= in os.makedirs
        os.chmod(self.initrd_path, 0o755)

        if not self.ostree_iso:
            # Create Local Repo
            create_repo_conf(
                {
                    "photon-local": {
                        "name": "VMWare Photon Linux (x86_64)",
                        "baseurl": f"file://{self.rpms_path}",
                        "gpgcheck": 0,
                        "enabled": 1,
                        "skip_if_unavailable": True,
                    }
                },
                reposdir=self.working_dir,
            )
        self.install_initrd_packages()

        with open(
            f"{self.initrd_path}/etc/locale.conf", "w", encoding="utf-8"
        ) as locale_conf:
            locale_conf.write("LANG=en_US.UTF-8")

        with open(
            f"{self.initrd_path}/etc/hostname", "w", encoding="utf-8"
        ) as hostname:
            hostname.write("photon-installer\n")

        self.cmd_util.remove_files([f"{self.initrd_path}/var/cache/tdnf"])
        shutil.move(f"{self.initrd_path}/boot", self.working_dir)

        # Move nessecary files for installer
        self.prepare_installer_dir()

        retval = self.cmd_util.run_in_chroot(
            self.initrd_path, "/bin/systemd-machine-id-setup"
        )

        if retval:
            alt_cmd = f"chroot {self.initrd_path} date -Ins | md5sum | cut -f1 -d' '"
            hash_value = subprocess.check_output(
                alt_cmd, shell=True, stderr=subprocess.STDOUT, text=True
            )
            with open(
                f"{self.initrd_path}/etc/machine-id", "w", encoding="utf-8"
            ) as machine_id:
                machine_id.write(hash_value)

        self.cmd_util.run_in_chroot(self.initrd_path, "/usr/sbin/pwconv")
        self.cmd_util.run_in_chroot(self.initrd_path, "/usr/sbin/grpconv")

        # Make nessacery devices
        os.mkfifo(f"{self.initrd_path}/dev/initctl")
        for idx in range(0, 4):
            os.mknod(
                f"{self.initrd_path}/dev/ram{idx}",
                mode=stat.S_IFBLK | 0o660,
                device=os.makedev(1, idx),
            )
        os.mknod(
            f"{self.initrd_path}/dev/sda",
            mode=stat.S_IFBLK | 0o660,
            device=os.makedev(8, 0),
        )

        if not os.path.exists(f"{self.initrd_path}/etc/systemd/scripts"):
            os.makedirs(f"{self.initrd_path}/etc/systemd/scripts")

        # Create iso repo
        create_repo_conf(
            {
                "photon-iso": {
                    "name": "VMWare Photon Linux (x86_64)",
                    "baseurl": "file:///mnt/media/RPMS",
                    "gpgkey": "file:///etc/pki/rpm-gpg/VMWARE-RPM-GPG-KEY",
                    "gpgcheck": 1,
                    "enabled": 1,
                    "skip_if_unavailable": True,
                }
            },
            reposdir=f"{self.initrd_path}/etc/yum.repos.d",
        )
        self.create_installer_script()
        self.create_init_script()

        with open(f"{self.initrd_path}/etc/fstab", "w", encoding="utf-8") as fstab:
            fstab.write(INITRD_FSTAB)

        self.cmd_util.replace_in_file(
            f"{self.initrd_path}/lib/systemd/system/getty@.service",
            "ExecStart.*",
            "ExecStart=-/sbin/agetty --autologin root --noclear %I linux",
        )
        self.cmd_util.replace_in_file(
            f"{self.initrd_path}/lib/systemd/system/serial-getty@.service",
            "ExecStart.*",
            "ExecStart=-/sbin/agetty --autologin root --keep-baud 115200,38400,9600 %I screen",
        )
        self.cmd_util.replace_in_file(
            f"{self.initrd_path}/etc/passwd",
            "root:.*",
            "root:x:0:0:root:/root:/bin/bootphotoninstaller",
        )

        os.makedirs(f"{self.initrd_path}/mnt/photon-root/photon-chroot", exist_ok=True)
        self.process_files()
        self.clean_up()

        # Set password expiry of initrd image to MAX
        self.cmd_util.run_in_chroot(self.initrd_path, "chage -M 99999 root")

        self.logger.info(f"Generating initrd img: {self.working_dir}/initrd.img")

        cur_dir = os.getcwd()
        os.chdir(self.initrd_path)
        self.cmd_util.run(
            f"(find . | cpio -o -H newc --quiet | gzip -9) > {self.working_dir}/initrd.img"
        )
        os.chdir(cur_dir)

        self.logger.info("Cleaning initrd directory and installer initrd json...")
        self.cmd_util.remove_files(
            [self.initrd_path, f"{self.working_dir}/packages_installer_initrd.json"]
        )
