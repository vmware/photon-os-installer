# /*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */
# pylint: disable=invalid-name,missing-docstring
import subprocess
import os
import re
import glob
import crypt
import shutil
import ssl
import requests
import copy
import json
from urllib.parse import urlparse
from urllib.request import urlopen
from OpenSSL.crypto import load_certificate, FILETYPE_PEM
import yaml


class CommandUtils(object):
    def __init__(self, logger):
        self.logger = logger
        self.hostRpmIsNotUsable = -1

    def run(self, cmd, update_env=False):
        self.logger.debug(cmd)
        use_shell = not isinstance(cmd, list)
        process = subprocess.Popen(
            cmd, shell=use_shell, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        out, err = process.communicate()
        retval = process.returncode
        if out != b"":
            self.logger.info(out.decode())
            if update_env:
                os.environ.clear()
                os.environ.update(
                    dict(
                        line.partition("=")[::2]
                        for line in out.decode("utf8").split("\0")
                        if line
                    )
                )
        if retval != 0:
            self.logger.info("Command failed: {}".format(cmd))
            self.logger.info("Error code: {}".format(retval))
            self.logger.error(err.decode())
        return retval

    def run_in_chroot(self, chroot_path, cmd, update_env=False):
        # Use short command here. Initial version was:
        # chroot "${BUILDROOT}" \
        #   /usr/bin/env -i \
        #   HOME=/root \
        #   TERM="$TERM" \
        #   PS1='\u:\w\$ ' \
        #   PATH=/bin:/usr/bin:/sbin:/usr/sbin \
        #   /usr/bin/bash --login +h -c "cd installer;$*"
        return self.run(["chroot", chroot_path, "/bin/bash", "-c", cmd], update_env)

    @staticmethod
    def is_vmware_virtualization():
        """Detect vmware vm"""
        process = subprocess.Popen(["systemd-detect-virt"], stdout=subprocess.PIPE)
        out, err = process.communicate()
        if err is not None and err != 0:
            return False
        return out.decode() == "vmware\n"

    @staticmethod
    def generate_password_hash(password):
        """Generate hash for the password"""
        return crypt.crypt(password)

    @staticmethod
    def _requests_get(url, verify):
        try:
            r = requests.get(url, verify=verify, stream=True, timeout=5.0)
        except Exception as e:
            return None
        return r

    @staticmethod
    def exists_in_file(target_string, file_path):
        """
        Check if a given string exists in a file.
        If the file doesn't exists return False.

        Parameters:
        - file_path (str): The path to the file to search in.
        - target_string (str): The string to search for in the file.

        Returns:
        - bool: True if the string exists in the file, False otherwise.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                for line in file:
                    if target_string in line:
                        return True
                return False
        except FileNotFoundError:
            return False

    # check if url is a URL (note: a file path is not a URL)
    @staticmethod
    def is_url(url):
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False

    # read json from a file or URL
    @staticmethod
    def load_json(url):
        if CommandUtils.is_url(url):
            with urlopen(url) as f:
                data = json.load(f)
        else:
            if url.startswith("file://"):
                url = url[7:]
            with open(url, "rt") as f:
                data = json.load(f)
        return data

    @staticmethod
    def wget(url, out, enforce_https=True, ask_fn=None, fingerprint=None):
        # Check URL
        try:
            u = urlparse(url)
        except:
            return False, "Failed to parse URL"
        if not all([u.scheme, u.netloc]):
            return False, "Invalid URL"
        if enforce_https:
            if u.scheme != "https":
                return False, "URL must be of secure origin (HTTPS)"
        r = CommandUtils._requests_get(url, True)
        if r is None:
            if fingerprint is None and ask_fn is None:
                return False, "Unable to verify server certificate"
            port = u.port
            if port is None:
                port = 443
            try:
                pem = ssl.get_server_certificate((u.netloc, port))
                cert = load_certificate(FILETYPE_PEM, pem)
                fp = cert.digest("sha1").decode()
            except:
                return False, "Failed to get server certificate"
            if ask_fn is not None:
                if not ask_fn(fp):
                    return False, "Aborted on user request"
            else:
                if fingerprint != fp:
                    return (
                        False,
                        "Server fingerprint did not match provided. Got: " + fp,
                    )
            # Download file without validation
            r = CommandUtils._requests_get(url, False)
            if r is None:
                return False, "Failed to download file"
        r.raw.decode_content = True
        with open(out, "wb") as f:
            shutil.copyfileobj(r.raw, f)

        return True, None

    def checkIfHostRpmNotUsable(self):
        if self.hostRpmIsNotUsable >= 0:
            return self.hostRpmIsNotUsable

        # if rpm doesn't have zstd support
        # if host rpm doesn't support sqlite backend db
        cmds = [
            "rpm --showrc | grep -qw 'rpmlib(PayloadIsZstd)'",
            "rpm -E %{_db_backend} | grep -qw 'sqlite'",
        ]

        for cmd in cmds:
            if self.run(cmd):
                self.hostRpmIsNotUsable = 1
                break

        if self.hostRpmIsNotUsable < 0:
            self.hostRpmIsNotUsable = 0

        return self.hostRpmIsNotUsable

    @staticmethod
    def jsonread(filename):
        with open(filename) as f:
            data = json.load(f)
            return data

    @staticmethod
    def _yaml_param(loader, node):
        params = loader.app_params
        default = None
        key = node.value

        assert type(key) is str, f"param name must be a string"

        if "=" in key:
            key, default = [t.strip() for t in key.split("=")]
            default = yaml.safe_load(default)
        value = params.get(key, default)

        assert value is not None, f"no param set for '{key}', and there is no default"

        return value

    @staticmethod
    def readConfig(stream, params={}):
        config = None

        yaml_loader = yaml.SafeLoader
        yaml_loader.app_params = params
        yaml.add_constructor("!param", CommandUtils._yaml_param, Loader=yaml_loader)
        config = yaml.load(stream, Loader=yaml_loader)

        return config

    def convertToBytes(self, size):
        if not isinstance(size, str):
            return int(size)
        if not size[-1].isalpha():
            return int(size)
        conv = {'k': 1024, 'm': 1024**2, 'g': 1024**3, 't': 1024**4}
        return int(float(size[:-1]) * conv[size.lower()[-1]])

    @staticmethod
    def get_disk_size_bytes(disk):
        cmd = ["blockdev", "--getsize64", disk]
        process = subprocess.Popen(
            cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        out, err = process.communicate()
        retval = process.returncode
        return retval, copy.copy(out.decode())

    def get_vgnames(self):
        vg_list = []
        try:
            cmd = ["vgdisplay", "-c"]
            process = subprocess.Popen(
                cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            out, err = process.communicate()
            retval = process.returncode
            if retval == 0:
                vgdisplay_output = out.decode().split("\n")
                for vg in vgdisplay_output:
                    if vg == "":
                        break
                    vg_list.append(vg.split(":")[0].strip())
        except Exception as e:
            retval = e.args[0]
        self.logger.info(f"VG's list {vg_list}")
        return retval, vg_list

    @staticmethod
    def write_pkg_list_file(file_path, packages_list):
        with open(file_path, "w") as json_file:
            json.dump(packages_list, json_file, indent=4)
        return file_path

    def replace_in_file(self, file_path, pattern, replacement):
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                file_contents = file.read()

            modified_contents = re.sub(pattern, replacement, file_contents)

            with open(file_path, "w", encoding="utf-8") as file:
                file.write(modified_contents)

            self.logger.info(f"Replacement completed in {file_path}")

        except FileNotFoundError:
            self.logger.error(f"File '{file_path}' not found.")
        except Exception as e:
            raise Exception(f"An error occurred during replacement: {str(e)}")

    def remove_files(self, file_list):
        """
        Remove all files in a directory that match a given file pattern.

        Parameters:
        - file_path (list[str]): list of file paths containing full path to a file
                                 including file pattern for removal (e.g., "*.txt" to remove all .txt files).

        Returns:
        - None
        """
        try:
            for file_path in file_list:
                for file in glob.glob(file_path):
                    if os.path.isfile(file):
                        os.remove(file)
                    elif os.path.islink(file):
                        os.unlink(file)
                    elif os.path.isdir(file):
                        shutil.rmtree(file)
                    else:
                        self.logger.info(f"File format not identified for: {file_path}")
        except FileNotFoundError:
            self.logger.info(f"File path not found: {file_path}")
            pass
        except Exception as e:
            raise Exception(f"Error removing {file_path}: {e}")

    def acquire_file_map(self, map, dest_dir):
        """
        map is a dictionary that maps source files to destinations
        the sources can be URLs or files.
        The destinations are paths under dest_dir. Any directories in the
        paths will be created if needed.
        If the basename of the destination is just a directory, the basename
        of the source will be used.
        """
        for src, dest in map.items():
            if dest.startswith("/"):
                dest = dest[1:]
            if os.path.basename(dest) == "":
                dest = os.path.join(os.path.dirname(dest), os.path.basename(src))
            dest = os.path.join(dest_dir, dest)
            os.makedirs(os.path.dirname(dest), exist_ok=True)

            if src.startswith("file://"):
                src = src[7:]
            if CommandUtils.is_url(src):
                self.logger.info(f"downloading {src} to {dest}")
                ret, _ = CommandUtils.wget(src, dest)
                assert ret, f"downloading {src} failed"
            else:
                self.logger.info(f"copying {src} to {dest}")
                shutil.copyfile(src, dest)
