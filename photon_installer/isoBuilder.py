#!/usr/bin/env python3
#
# Copyright © 2023 VMware, Inc.
# SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
#


import glob
import json
import os
import platform
import shutil
import tempfile
from argparse import ArgumentParser

import yaml
from commandutils import CommandUtils
from generate_initrd import IsoInitrd
from logger import Logger
from tdnf import Tdnf, create_repo_conf

DEFAULT_INSTALL_OPTIONS_FILE = "build_install_options_custom.json"
SUPPORTED_RELEASES = ["4.0", "5.0"]
DEV_RELEASES = ["6.0"]


class IsoBuilder(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.pkg_list = []
        self.working_dir = tempfile.mkdtemp(prefix="photon-", dir=self.artifact_path)

        if self.iso_name is None:
            self.iso_name = os.path.join(
                self.artifact_path, f"photon-{self.photon_release_version}.iso"
            )
        else:
            if not self.iso_name.startswith("/"):
                self.iso_name = os.path.join(
                    self.artifact_path, self.iso_name
                )

        if self.initrd_pkg_list_file is None:
            self.initrd_pkg_list_file = os.path.join(os.path.dirname(__file__), "packages_installer_initrd.json")

        self.rpms_path = os.path.join(self.working_dir, "RPMS")
        self.initrd_path = os.path.join(self.working_dir, "photon-chroot")
        self.photon_docker_image = f"photon:{self.photon_release_version}"
        self.logger = Logger.get_logger(
            os.path.join(self.artifact_path, "LOGS"), self.log_level, True
        )
        self.cmdUtil = CommandUtils(self.logger)
        self.arch = platform.machine()
        self.additional_files = []
        self.yum_repos_dir = os.path.join(self.working_dir, "yum.repos.d")

        self.tdnf = Tdnf(
            logger=self.logger,
            releasever=self.photon_release_version,
            reposdir=self.yum_repos_dir,
        )

    def runCmd(self, cmd):
        retval = self.cmdUtil.run(cmd)
        if retval:
            raise Exception(f"Following command failed to execute: {cmd}")

    def addPkgsToList(self, pkg_list_file):
        if os.path.exists(pkg_list_file):
            pkg_data = CommandUtils.jsonread(pkg_list_file)
            self.pkg_list.extend(pkg_data["packages"])
            if f"packages_{self.arch}" in pkg_data:
                self.pkg_list.extend(pkg_data[f"packages_{self.arch}"])

    def addGrubConfig(self):
        self.logger.info(f"Adding grub config: {self.working_dir}/boot/grub2")
        os.makedirs(f"{self.working_dir}/boot/grub2", exist_ok=True)
        with open(f"{self.working_dir}/boot/grub2/grub.cfg", "w") as conf_file:
            conf_file.writelines(
                [
                    "set default=0\n",
                    "set timeout=3\n",
                    "loadfont ascii\n",
                    'set gfxmode="1024x768"\n',
                    "gfxpayload=keep\n",
                    "set theme=/boot/grub2/themes/photon/theme.txt\n",
                    "terminal_output gfxterm\n",
                    "probe -s photondisk -u ($root)\n\n",
                    'menuentry "Install" {\n',
                    f"linux /isolinux/vmlinuz root=/dev/ram0 loglevel=3 photon.media=UUID=$photondisk {self.boot_cmdline_param}\n",
                    "initrd /isolinux/initrd.img\n}",
                ]
            )

    def createInstallOptionJson(self):
        install_option_key = "custom"
        additional_files = [os.path.basename(file) for file in self.additional_files]
        install_option_data = {
            install_option_key: {
                "title": "Photon Custom",
                "packagelist_file": os.path.basename(self.packageslist_file),
                "visible": False,
                "additional-files": additional_files,
            }
        }
        with open(
            f"{self.working_dir}/{DEFAULT_INSTALL_OPTIONS_FILE}", "w"
        ) as json_file:
            json_file.write(json.dumps(install_option_data))

    def setupReposDir(self):
        self.logger.info(f"setting up repo files in {self.yum_repos_dir}")
        os.makedirs(self.yum_repos_dir, exist_ok=True)

        # copy repo files from host
        if not self.repo_paths:
            if os.path.isdir("/etc/yum.repos.d"):
                for repo_file in glob.glob("/etc/yum.repos.d/*.repo"):
                    shutil.copy(repo_file, self.yum_repos_dir)
        else:
            for i, url in enumerate(self.repo_paths):
                if url.startswith("/"):
                    url = f"file://{url}"
                create_repo_conf(
                    {
                        f"_repo{i}": {
                            "baseurl": url,
                            "enabled": 1,
                            "gpgcheck": 0,
                            "name": f"VMWare Photon Linux ({self.arch})",
                            "skip_if_unavailable": True,
                        }
                    },
                    reposdir=self.yum_repos_dir,
                )

        # additional repos
        if self.additional_repos:
            for repo_file in self.additional_repos:
                shutil.copy(repo_file, self.yum_repos_dir)

    def generateInitrd(self):
        """
        Generate custom initrd
        """

        if self.install_options_file is None:
            self.createInstallOptionJson()
            self.install_options_file = os.path.join(self.working_dir, DEFAULT_INSTALL_OPTIONS_FILE)

        self.logger.info("Starting to generate initrd.img...")
        iso_initrd = IsoInitrd(
            logger=self.logger,
            working_dir=self.working_dir,
            initrd_pkgs=self.initrd_pkgs,
            rpms_path=self.rpms_path,
            photon_release_version=self.photon_release_version,
            pkg_list_file=self.packageslist_file,
            install_options_file=self.install_options_file,
            initrd_files=self.initrd_files,
        )
        iso_initrd.build_initrd()

    def copyRPMs(self):
        """
        copies packages as set by a list of RPM paths
        there is no dependency check
        """
        # TODO: deal with source pkgs which go to SRPMS
        self.logger.info(f"Creating RPMS directory: {self.rpms_path}")
        os.makedirs(self.rpms_path, exist_ok=True)

        for f in self.rpms_list:
            # list is a plain list of files with absolute paths, we need to
            # put them into their arch specific directory
            # arch is the second to last word in the file name separated by dots:
            arch = f.split(".")[-2]
            arch_dir = os.path.join(self.rpms_path, arch)
            if not os.path.isdir(arch_dir):
                os.makedirs(arch_dir)
            shutil.copy(f, arch_dir)

        self.logger.info("Creating repodata for copied packages")
        self.createRepo()

    def downloadPkgs(self):
        """
        downloads packages as set by packages list files,
        including their dependencies by using tdnf
        """
        self.logger.info(f"Creating RPMS directory: {self.rpms_path}")
        os.makedirs(self.rpms_path, exist_ok=True)

        # Add installer initrd and custom packages to package list..
        self.addPkgsToList(self.initrd_pkg_list_file)
        self.addPkgsToList(self.packageslist_file)

        linux_flavors = [
            "linux",
            "linux-esx",
            "linux-rt",
            "linux-aws",
            "linux-secure",
        ]
        if not any(flavor in self.pkg_list for flavor in linux_flavors):
            self.pkg_list.append("linux")

        # Include additional packages if mentioned in kickstart.
        if self.kickstart_path:
            with open(self.kickstart_path, "rt") as f:
                kickstart_data = CommandUtils.readConfig(f)
            if "packages" in kickstart_data:
                self.pkg_list.extend(kickstart_data["packages"])

        pkg_list = " ".join(self.pkg_list)
        self.logger.info(f"List of packages to download: {pkg_list}")

        # skip downloading if repo already exists
        if not os.path.isdir(os.path.join(self.rpms_path, "repodata")):
            self.logger.info("downloading packages...")
            retval = self.tdnf.run(
                [
                    "--nogpgcheck",  # work around for installing locally built packages, like photon-os-installer
                    "--alldeps",
                    "--downloadonly",
                    "--downloaddir", self.rpms_path,
                    "install",
                ]
                + self.pkg_list,
                do_json=False
            )
            if retval != 0:
                raise Exception("tdnf failed")
            self.logger.info("...done.")

        # Separate out packages downloaded into arch specific directories.
        # Run createrepo on the rpm download path once downloaded.
        os.makedirs(f"{self.rpms_path}/{self.arch}", exist_ok=True)
        os.makedirs(f"{self.rpms_path}/noarch", exist_ok=True)
        for file in os.listdir(f"{self.working_dir}/RPMS"):
            if file.endswith(f".{self.arch}.rpm"):
                shutil.move(
                    f"{self.rpms_path}/{file}",
                    f"{self.rpms_path}/{self.arch}/{file}",
                )
            elif file.endswith(".noarch.rpm"):
                shutil.move(
                    f"{self.rpms_path}/{file}",
                    f"{self.rpms_path}/noarch/{file}",
                )
        self.logger.info("Creating repodata for downloaded packages...")
        self.createRepo()

    def createRepo(self):
        repoDataDir = f"{self.rpms_path}/repodata"
        self.runCmd(f"createrepo --database --update {self.rpms_path}")
        if os.path.exists(repoDataDir):
            primary_xml_gz = glob.glob(os.path.join(repoDataDir, "*-primary.xml.gz"))
            if len(primary_xml_gz) > 0:
                # use basename because symlink should be relative to make ISO relocatable
                primary_xml_gz = os.path.basename(primary_xml_gz[0])
                os.symlink(primary_xml_gz, f"{repoDataDir}/primary.xml.gz")
            else:
                raise Exception(f"no file matching '*-primary.xml.gz' found in {self.rpms_path}/repodata")
        else:
            raise Exception("no repodata folder found in {self.rpms_path}")

    def cleanUp(self, temp_file):
        if temp_file:
            os.remove(temp_file)
        try:
            shutil.rmtree(self.working_dir)
        except FileNotFoundError:
            pass

    def createEfiImg(self):
        """
        create efi image
        """
        self.logger.info("Creating EFI image...")
        self.efi_img = "boot/grub2/efiboot.img"
        efi_dir = os.path.join(self.artifact_path, "efiboot")
        self.runCmd(
            f"dd if=/dev/zero of={self.working_dir}/{self.efi_img} bs=3K count=1024"
        )
        self.runCmd(f"mkdosfs {self.working_dir}/{self.efi_img}")

        try:
            shutil.rmtree(efi_dir)
        except FileNotFoundError:
            pass
        os.makedirs(efi_dir)

        self.runCmd(f"mount -o loop {self.working_dir}/{self.efi_img} {efi_dir}")
        shutil.move(f"{self.working_dir}/boot/efi/EFI", efi_dir)
        self.runCmd(f"umount {efi_dir}")

        self.cmdUtil.remove_files([efi_dir])

    def createIsolinux(self):
        """
        Install photon-iso-config rpm in working dir.
        """
        os.makedirs(f"{self.working_dir}/isolinux", exist_ok=True)
        shutil.move(f"{self.working_dir}/initrd.img", f"{self.working_dir}/isolinux")

        self.logger.info(
            "Installing photon-iso-config and syslinux in working directory..."
        )
        os.makedirs(f"{self.working_dir}/isolinux-temp")
        pkg_list = ["photon-iso-config"]
        if self.arch == "x86_64":
            pkg_list.append("syslinux")

        self.logger.info("installing packages for isolinux...")
        isolinux_dir = os.path.join(self.working_dir, "isolinux-temp")
        retval, tdnf_out = self.tdnf.run(
            ["install", "--installroot", isolinux_dir] + pkg_list,
        )
        if retval != 0:
            raise Exception(f"tdnf failed: {tdnf_out}")
        self.logger.info("...done.")

        for file in os.listdir(
            f"{self.working_dir}/isolinux-temp/usr/share/photon-iso-config"
        ):
            shutil.copyfile(
                f"{self.working_dir}/isolinux-temp/usr/share/photon-iso-config/{file}",
                f"{self.working_dir}/isolinux/{file}",
            )
        if self.arch == 'x86_64':
            for file in [
                "isolinux.bin",
                "libcom32.c32",
                "libutil.c32",
                "vesamenu.c32",
                "ldlinux.c32",
            ]:
                shutil.copyfile(
                    f"{self.working_dir}/isolinux-temp/usr/share/syslinux/{file}",
                    f"{self.working_dir}/isolinux/{file}",
                )

        self.cmdUtil.remove_files([f"{self.working_dir}/isolinux-temp"])
        for file in ["tdnf.conf", "photon-local.repo"]:
            if os.path.exists(f"{self.working_dir}/{file}"):
                os.remove(f"{self.working_dir}/{file}")

        if self.kickstart_path:
            self.logger.info(
                f"Moving {self.kickstart_path} to {self.working_dir}/isolinux..."
            )
            shutil.copy(f"{self.kickstart_path}", f"{self.working_dir}/isolinux")

        if self.boot_cmdline_param:
            self.logger.info("adding Boot command line parameters to isolinux menu")
            with open(f"{self.working_dir}/isolinux/menu.cfg", "rt") as fin:
                with open(f"{self.working_dir}/isolinux/menu.cfg.tmp", "wt") as fout:
                    for line in fin:
                        if line.lstrip().startswith("append"):
                            append = f"{line.rstrip()} {self.boot_cmdline_param}\n"
                            self.logger.info(f"boot cmdline: {append}")
                            fout.write(append)
                        else:
                            fout.write(line)
            os.rename(f"{self.working_dir}/isolinux/menu.cfg.tmp", f"{self.working_dir}/isolinux/menu.cfg")

    def copyAdditionalFiles(self):
        for file in self.additional_files:
            output_file = f"{self.working_dir}/{os.path.basename(file)}"
            if not os.path.exists(output_file):
                shutil.copy(file, output_file)

    def build(self):
        """
        Create Custom Iso
        """
        # Create isolinux dir inside iso.
        self.createIsolinux()

        # Copy Additional Files
        self.copyAdditionalFiles()

        self.createEfiImg()
        self.runCmd(
            f"mv {self.working_dir}/boot/vmlinuz* {self.working_dir}/isolinux/vmlinuz"
        )

        # ID in the initrd.gz now is PHOTON_VMWARE_CD . This is how we recognize that the cd is actually ours. touch this file there.
        self.runCmd(f"touch {self.working_dir}/PHOTON_VMWARE_CD")

        self.addGrubConfig()

        # Clean up yum repos dir before creating iso
        if os.path.exists(self.yum_repos_dir):
            self.cmdUtil.remove_files([self.yum_repos_dir])

        self.logger.info(f"Generating Iso: {self.iso_name}")
        build_iso_cmd = f"cd {self.working_dir} && "
        build_iso_cmd += (
            "mkisofs -R -l -L -D -c isolinux/boot.cat "
        )

        # important:
        # * the order of options matters
        # * flags apply to previous boot image (given with -b or -e)
        # * 'eltorito-alt-boot' functions as separator
        # * if options appear twice it's because they apply to different boot
        #   images

        # BIOS, x86_64 only
        if self.arch == "x86_64":
            build_iso_cmd += "-b isolinux/isolinux.bin "
            build_iso_cmd += "-no-emul-boot -boot-load-size 4 -boot-info-table "
            build_iso_cmd += "-eltorito-alt-boot "

        # EFI boot
        build_iso_cmd += f"-e {self.efi_img} -no-emul-boot "
        build_iso_cmd += (
            f'-V "PHOTON_$(date +%Y%m%d)" -o {self.iso_name} {self.working_dir}'
        )
        self.runCmd(build_iso_cmd)

    def validate_options(self):
        assert self.photon_release_version is not None, "the Photon release version is required"
        assert isinstance(self.photon_release_version, str), "the Photon relase version must be a string"
        assert self.photon_release_version != "", "the Photon release version must not be empty"
        assert self.photon_release_version in (SUPPORTED_RELEASES + DEV_RELEASES), f"Photon release {self.photon_release_version} is not supported"

        path = f"{self.initrd_path}/installer"
        os.makedirs(path)

    def read_pkglist_file(self, plf):
        packages = []
        arch = self.arch

        plf_json = self.cmdUtil.load_json(plf)

        if 'packages' in plf_json:
            packages.extend(plf_json['packages'])
        if f'packages_{arch}' in plf_json:
            packages.extend(plf_json[f'packages_{arch}'])

        return packages

    def setup(self):
        # create working directory
        if not os.path.exists(self.working_dir):
            self.logger.info(f"Creating working directory: {self.working_dir}")
            os.makedirs(self.working_dir)

        # read list of RPMs from file, if given
        self.rpms_list = None
        if self.rpms_list_file is not None:
            self.rpms_list = []
            with open(self.rpms_list_file, "rt") as f:
                for line in f:
                    self.rpms_list.append(line.strip())

        self.cmdUtil.acquire_file_map(self.iso_files, self.working_dir)

        # merge initrd pkg list
        if self.initrd_pkg_list_file is not None:
            self.initrd_pkgs.extend(self.read_pkglist_file(self.initrd_pkg_list_file))
        self.initrd_pkgs = list(set(self.initrd_pkgs))

        # merge pkg list for list of packages to be installed in target
        if self.packageslist_file is not None:
            self.packages_list.extend(self.read_pkglist_file(self.packageslist_file))
        self.packages_list = list(set(self.packages_list))

        # create packages.json file from packages_list
        self.packageslist_file = os.path.join(self.working_dir, "packages.json")
        with open(self.packageslist_file, "wt") as f:
            pkg_json = {'packages': self.packages_list}
            json.dump(pkg_json, f, indent=4)

        # Download all packages before installing them during initrd generation.
        self.setupReposDir()
        # if we have a list of RPMs to ship with the iso, use that
        # (generic ISO use case)
        if self.rpms_list is not None:
            self.copyRPMs()
        # otherwise, use the packages list, which will also be used for
        # installation
        # (custom ISO use case)
        else:
            self.downloadPkgs()


def main():
    usage = "Usage: %prog [options]"
    parser = ArgumentParser(usage)
    parser.add_argument("-l", "--log-level", dest="log_level", default="info")

    parser.add_argument(
        "-f",
        "--function",
        dest="function",
        default="",
        help="<Required> Building Options",
        choices=["build-iso", "build-initrd"],
    )
    parser.add_argument(
        "-v",
        "--photon-release-version",
        dest="photon_release_version",
        default=None,
        help="<Required> Photon release version to build custom iso/initrd.",
    )
    parser.add_argument(
        "-i",
        "--initrd-pkgs-list-file",
        dest="initrd_pkgs_list_file",
        default=None,
        help="<Optional> package list file or URL for the initrd",
    )
    parser.add_argument(
        "-I",
        "--initrd-pkgs",
        dest="initrd_pkgs",
        type=str,
        default="",
        help="<Optional> list of packages to be installed in the initrd, separated by commas",
    )
    parser.add_argument(
        "-r",
        "--additional_repos",
        action="append",
        default=None,
        help="<Optional> Pass repo file as input to download rpms from external repo",
    )
    parser.add_argument(
        "-p",
        "--packageslist-file",
        dest="packageslist_file",
        default="",
        help="Custom package list file or URL",
    )
    parser.add_argument(
        "-P",
        "--packages",
        dest="packages_list",
        default="",
        help="<Optional> list of packages to be installed in the target, separated by commas",
    )
    parser.add_argument(
        "-k",
        "--kickstart-path",
        dest="kickstart_path",
        default=None,
        help="<Optional> Path to custom kickstart file.",
    )
    parser.add_argument(
        "-b",
        "--boot-cmdline-param",
        dest="boot_cmdline_param",
        default="",
        help="<Optional> Extra boot commandline parameter to pass.",
    )
    parser.add_argument(
        "-a",
        "--artifact-path",
        dest="artifact_path",
        default=os.getcwd(),
        help="<Optional> Path to generate iso in.",
    )
    parser.add_argument(
        "-R",
        "--repo-paths",
        dest="repo_paths",
        action="append",
        default=[],
        help="<Optional> repo paths or urls to download rpms from",
    )
    parser.add_argument(
        "--rpms-list-file",
        dest="rpms_list_file",
        type=str,
        default=None,
        help="<Optional> rpm list file that contains list of rpms paths to copy",
    )
    parser.add_argument(
        "-m",
        "--param",
        dest="params",
        action="append",
        default=[],
        help="Specify a parameter value. This option can be used multiple times to provide multiple parameter values.",
    )
    parser.add_argument(
        "-y",
        "--config",
        dest="config",
        type=str,
        help="Path to the configuration YAML file",
        default="",
    )
    parser.add_argument(
        "-n",
        "--name",
        dest="iso_name",
        type=str,
        help="Name of the iso file",
        default=None
    )
    parser.add_argument(
        "--install-options-file",
        dest="install_options_file",
        type=str,
        help="the install options file for the installer",
        default=None
    )

    # Parse the command-line arguments
    options = parser.parse_args()

    # no commandd line equiv for these, but we need to initialize them:
    options.iso_files = {}
    options.initrd_files = {}

    temp_file_path = ""
    if options.config and not os.path.isfile(options.config):
        _, temp_file_path = tempfile.mkstemp(prefix="isoBuilder-", suffix="-config")
        var = CommandUtils.wget(options.config, temp_file_path, False)
        if not var[0]:
            raise Exception(f"Error - {var[1]}")
        options.config = temp_file_path

    if os.path.exists(options.config):
        params = {}
        for p in options.params:
            k, v = p.split("=", maxsplit=1)
            params[k] = yaml.safe_load(v)

        # Load config from YAML file
        with open(options.config, "r") as f:
            config = CommandUtils.readConfig(f, params=params)
            # Override YAML values with command-line arguments
            for dest, value in vars(options).items():
                if value and dest in config:
                    config[dest] = value
        # Add config arguments to options
        options.__dict__.update(config)

    print(f"initrd_pkg_list_file={options.initrd_pkgs_list_file}")

    isoBuilder = IsoBuilder(
        function=options.function,
        packageslist_file=options.packageslist_file,
        kickstart_path=options.kickstart_path,
        photon_release_version=options.photon_release_version,
        log_level=options.log_level,
        initrd_pkg_list_file=options.initrd_pkgs_list_file,
        initrd_pkgs=options.initrd_pkgs.split(",") if options.initrd_pkgs else [],
        additional_repos=options.additional_repos,
        boot_cmdline_param=options.boot_cmdline_param,
        artifact_path=options.artifact_path,
        packages_list=options.packages_list.split(",") if options.packages_list else [],
        repo_paths=options.repo_paths,
        rpms_list_file=options.rpms_list_file,
        iso_name=options.iso_name,
        iso_files=options.iso_files,
        initrd_files=options.initrd_files,
        install_options_file=options.install_options_file,
    )

    isoBuilder.validate_options()

    isoBuilder.logger.info(
        f"Starting to generate photon {isoBuilder.photon_release_version} initrd.img..."
    )

    isoBuilder.setup()
    isoBuilder.generateInitrd()

    if options.function == "build-iso":
        isoBuilder.logger.info(
            f"Starting to generate photon {isoBuilder.photon_release_version} iso..."
        )
        isoBuilder.build()
    elif options.function == "build-initrd":
        isoBuilder.logger.debug(
            f"Moving {isoBuilder.working_dir}/initrd.img to {options.artifact_path}"
        )
        shutil.move(f"{isoBuilder.working_dir}/initrd.img", options.artifact_path)
    else:
        raise Exception(f"{options.function} not supported...")

    # Clean Up Working Directory and temp config file
#    isoBuilder.cmdUtil.remove_files([isoBuilder.working_dir, temp_file_path])


if __name__ == "__main__":
    main()
