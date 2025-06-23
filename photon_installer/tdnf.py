# /*
# * Copyright © 2023 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */
# pylint: disable=invalid-name,missing-docstring

import subprocess
import os
import json
import shutil
from logger import Logger


class TdnfError(Exception):
    """Base exception for tdnf-related errors"""
    pass


class TdnfBinaryNotFoundError(TdnfError):
    """Raised when tdnf binary is not found in PATH"""
    pass


class TdnfBinaryNotUsableError(TdnfError):
    """Raised when tdnf binary is found but not functional"""
    pass


class TdnfCommandError(TdnfError):
    """Raised when a tdnf command fails"""
    def __init__(self, message, return_code=None, command=None):
        super().__init__(message)
        self.return_code = return_code
        self.command = command


def create_repo_conf(repos, reposdir="/etc/yum.repos.d", insecure=False, skip_md_extras=True):
    """
    Create .repo file as per configurations passed.
    Parameters:
    - repos: Dictionary containing repo_id as key and value as dictionary containing repo configurations.
             Ex: {'repo_id1': {'baseurl': 'https://foo/bar', 'enabled': 0}, 'repo_id2': {'baseurl': '/mnt/media/RPMS', 'enabled': 1}}
    - reposdir (Optional): Parent dir where .repo needs to be placed. Default Value - /etc/yum.repos.d/{repo_name}.repo
    Returns:
    - None
    """
    os.makedirs(reposdir, exist_ok=True)
    for id, repo in repos.items():
        if insecure:
            repo['sslverify'] = 0
        if skip_md_extras:
            for key in ['skip_md_filelists', 'skip_md_updateinfo', 'skip_md_other']:
                if key not in repo:
                    repo[key] = 1
        with open(os.path.join(reposdir, f"{id}.repo"), "w", encoding="utf-8") as repo_file:
            repo_file.write(f"[{id}]\n")
            for key, value in repo.items():
                repo_file.write(f"{key}={value}\n")


class Tdnf:
    def __init__(self, **kwargs):
        kwords = [
            'logger',
            'config_file',
            'reposdir',
            'releasever',
            'installroot',
        ]

        for kw in kwords:
            attr = kwargs.get(kw, None)
            setattr(self, kw, attr)

        if self.logger is None:
            self.logger = Logger.get_logger(None, "debug", True)

        # Find and validate tdnf binary
        self.tdnf_bin = shutil.which("tdnf")
        if not self.tdnf_bin:
            raise TdnfBinaryNotFoundError("tdnf binary not found in PATH")

        # Validate tdnf binary is usable
        try:
            retval, tdnf_out = self.run(["--version"])
            if retval != 0:
                raise TdnfBinaryNotUsableError("tdnf binary returned non-zero exit code")
            self.tdnf_version = tdnf_out['Version']
            self.logger.info(f"Using tdnf version: {self.tdnf_version}")
        except TdnfError:
            # Re-raise tdnf-specific errors as-is
            raise
        except Exception as e:
            self.logger.error(f"tdnf binary found at {self.tdnf_bin} is not usable: {e}")
            raise TdnfBinaryNotUsableError(f"tdnf binary is not functional: {e}")

    def get_rpm_dbpath(self):
        if self.releasever == "4.0":
            return "/var/lib/rpm"
        else:
            return "/usr/lib/sysimage/rpm"

    def default_args(self):
        args = []
        if self.config_file:
            args += ["-c", self.config_file]
        if self.reposdir:
            args += ["--setopt", f"reposdir={self.reposdir}"]
        if self.releasever:
            args += ["--releasever", self.releasever]
        if self.installroot:
            args += ["--installroot", self.installroot]
        if self.releasever != "5.0":
            args += ["--rpmdefine", f"_dbpath {self.get_rpm_dbpath()}"]
        return args

    def get_command(self, args=None, do_json=True):
        # Fix mutable default arguments issue
        if args is None:
            args = []

        tdnf_args = []
        if do_json:
            tdnf_args.append("-j")
        if "--assumeno" not in args:
            tdnf_args.append("-y")
        tdnf_args += self.default_args() + args

        return [self.tdnf_bin] + tdnf_args

    def execute(self, args, do_json=True):
        self.logger.info(f"running {' '.join(args)}")

        if do_json:
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, err = process.communicate()
            retval = process.returncode

            out_json = None

            if err:
                self.logger.error(err.decode())

            try:
                out_json = json.loads(out)
            except json.decoder.JSONDecodeError as e:
                # try again, stopping at the pos where error happened
                # happens when packages print output from scripts
                try:
                    self.logger.info(
                        f"json decode failed at line {e.lineno}, at: '{e.doc[e.pos:]}'"
                    )
                    out_json = json.loads(out[: e.pos])
                except json.decoder.JSONDecodeError:
                    self.logger.info(
                        f"json decode failed for output: {out_json}"
                    )

            if retval != 0:
                self.logger.info(f"Command failed: {args}")
                self.logger.error(err.decode('utf-8', errors='replace'))
                if 'Error' in out_json:
                    self.logger.info(f"Error code: {out_json['Error']}")
                if out_json and 'ErrorMessage' in out_json:
                    self.logger.error(out_json['ErrorMessage'])
                else:
                    self.logger.error(f"Command output: {out_json}")

            return retval, out_json
        else:
            return subprocess.check_call(args)

    def run(self, args=None, do_json=True):
        # Fix mutable default arguments issue
        if args is None:
            args = []

        command = self.get_command(args, do_json=do_json)
        return self.execute(command, do_json=do_json)


def main():
    tdnf = Tdnf(installroot="/installroot", releasever="5.0")
    retval, out_json = tdnf.run(["repolist"])
    print(json.dumps(out_json, indent=4))


if __name__ == "__main__":
    main()
