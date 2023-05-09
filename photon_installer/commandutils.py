#/*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */
#pylint: disable=invalid-name,missing-docstring
import subprocess
import os
import crypt
import string
import random
import shutil
import ssl
import requests
import copy
import json
from urllib.parse import urlparse
from OpenSSL.crypto import load_certificate, FILETYPE_PEM
import yaml


class CommandUtils(object):
    def __init__(self, logger):
        self.logger = logger
        self.hostRpmIsNotUsable = -1

    def run(self, cmd, update_env = False):
        self.logger.debug(cmd)
        use_shell = not isinstance(cmd, list)
        process = subprocess.Popen(cmd, shell=use_shell, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out,err = process.communicate()
        retval = process.returncode
        if out != b'':
            self.logger.info(out.decode())
            if update_env:
                os.environ.clear()
                os.environ.update(dict(line.partition('=')[::2] for line in out.decode('utf8').split('\0') if line))
        if retval != 0:
            self.logger.info("Command failed: {}".format(cmd))
            self.logger.info("Error code: {}".format(retval))
            self.logger.error(err.decode())
        return retval

    def run_in_chroot(self, chroot_path, cmd, update_env = False):
        # Use short command here. Initial version was:
        # chroot "${BUILDROOT}" \
        #   /usr/bin/env -i \
        #   HOME=/root \
        #   TERM="$TERM" \
        #   PS1='\u:\w\$ ' \
        #   PATH=/bin:/usr/bin:/sbin:/usr/sbin \
        #   /usr/bin/bash --login +h -c "cd installer;$*"
        return self.run(['chroot', chroot_path, '/bin/bash', '-c', cmd], update_env)

    @staticmethod
    def is_vmware_virtualization():
        """Detect vmware vm"""
        process = subprocess.Popen(['systemd-detect-virt'], stdout=subprocess.PIPE)
        out, err = process.communicate()
        if err is not None and err != 0:
            return False
        return out.decode() == 'vmware\n'

    @staticmethod
    def generate_password_hash(password):
        """Generate hash for the password"""
        return crypt.crypt(password)

    @staticmethod
    def _requests_get(url, verify):
        try:
            r = requests.get(url, verify=verify, stream=True, timeout=5.0)
        except:
            return None
        return r

    @staticmethod
    def wget(url, out, enforce_https=True, ask_fn=None, fingerprint=None):
        # Check URL
        try:
            u = urlparse(url)
        except:
            return False, "Failed to parse URL"
        if not all([ u.scheme, u.netloc ]):
            return False, 'Invalid URL'
        if enforce_https:
            if u.scheme != 'https':
                return False, 'URL must be of secure origin (HTTPS)'
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
                fp = cert.digest('sha1').decode()
            except:
                return False, "Failed to get server certificate"
            if ask_fn is not None:
                if not ask_fn(fp):
                    return False, "Aborted on user request"
            else:
                if fingerprint != fp:
                    return False, "Server fingerprint did not match provided. Got: " + fp
            # Download file without validation
            r = CommandUtils._requests_get(url, False)
            if r is None:
                return False, "Failed to download file"
        r.raw.decode_content = True
        with open(out, 'wb') as f:
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

        if '=' in key:
            key, default = [t.strip() for t in key.split('=')]
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
        conv = {'k': 1024, 'm':1024**2, 'g':1024**3, 't':1024**4}
        return int(float(size[:-1]) * conv[size.lower()[-1]])


    @staticmethod
    def get_disk_size_bytes(disk):
        cmd = ['blockdev', '--getsize64', disk]
        process = subprocess.Popen(cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out,err = process.communicate()
        retval = process.returncode
        return retval, copy.copy(out.decode())

    def get_vgnames(self):
        vg_list=[]
        try:
            cmd = ['vgdisplay', '-c']
            process = subprocess.Popen(cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out,err = process.communicate()
            retval = process.returncode
            if retval==0:
                vgdisplay_output=out.decode().split("\n")
                for vg in vgdisplay_output:
                    if vg=="":
                        break
                    vg_list.append(vg.split(":")[0].strip())
        except Exception as e:
            retval=e.args[0]
        self.logger.info(f"VG's list {vg_list}")
        return retval, vg_list
