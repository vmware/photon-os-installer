# /*
# * Copyright © 2023 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */
# pylint: disable=invalid-name,missing-docstring

import subprocess
import os
import json
from logger import Logger


def find_binary_in_path(binary_name):
    path_dirs = os.environ.get("PATH").split(os.pathsep)

    for dir in path_dirs:
        binary_path = os.path.join(dir, binary_name)
        if os.path.isfile(binary_path) and os.access(binary_path, os.X_OK):
            return binary_path

    return None


def create_repo_conf(repos, reposdir="/etc/yum.repos.d", insecure=False):
    """
    Create .repo file as per configurations passed.
    Parameters:
    - repos: Dictionary containing repo_id as key and value as dictionary containing repo configurations.
             Ex: {'repo_id1': {'baseurl': 'https://foo/bar', 'enabled': 0}, 'repo_id2': {'basurl': '/mnt/media/RPMS', 'enabled': 1}}
    - reposdir (Optional): Parent dir where .repo needs to be placed. Default Value - /etc/yum.repos.d/{repo_name}.repo
    Returns:
    - None
    """
    os.makedirs(reposdir, exist_ok=True)
    for repo in repos:
        if insecure:
            repos[repo]["sslverify"] =  0
        with open(os.path.join(reposdir, f"{repo}.repo"), "w", encoding="utf-8") as repo_file:
            repo_file.write(f"[{repo}]\n")
            for key,value in repos[repo].items():
                repo_file.write(f"{key}={value}\n")


class Tdnf:
    DOCKER_ARGS = ["--rm", "--privileged", "--ulimit", "nofile=1024:1024"]
    DEFAULT_CONTAINER = "photon:latest"

    def __init__(self, force_docker=False, **kwargs):
        kwords = [
            'logger',
            'config_file',
            'reposdir',
            'releasever',
            'installroot',
            'docker_image',
        ]

        for kw in kwords:
            attr = kwargs.get(kw, None)
            setattr(self, kw, attr)

        if self.logger is None:
            self.logger = Logger.get_logger(None, "debug", True)

        self.tdnf_bin = None

        if not force_docker:
            self.tdnf_bin = find_binary_in_path("tdnf")

            if self.tdnf_bin:
                try:
                    retval, tdnf_out = self.run(["--version"])
                    assert retval == 0
                    self.tdnf_version = tdnf_out['Version']
                except Exception:
                    self.logger.error(
                        f"tdnf binary found at {self.tdnf_bin} is not usable."
                    )
                    self.tdnf_bin = None

        self.docker_bin = find_binary_in_path("docker")

        if self.tdnf_bin is None:
            if self.docker_bin:
                assert (
                    self.docker_image is not None
                ), "local tdnf binary not found, try setting a docker image that contains tdnf"
                try:
                    retval, tdnf_out = self.run(["--version"])
                    assert retval == 0
                    self.tdnf_version = tdnf_out["Version"]
                except Exception as e:
                    self.logger.error(
                        f"tdnf binary on docker image {self.docker_image} is not usable - maybe provide another image?"
                    )
                    self.tdnf_bin = None
                    raise e
            else:
                raise Exception("No usable tdnf or docker binary found")

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

    def get_command(self, args=[], directories=[], repos={}):
        tdnf_args = ["-j", "-y"] + self.default_args() + args
        if self.tdnf_bin:
            return [self.tdnf_bin] + tdnf_args
        elif self.docker_bin:
            dirs = set(directories)
            if self.installroot:
                dirs.add(self.installroot)
            if self.config_file:
                dirs.add(os.path.dirname(self.config_file))
            if self.reposdir:
                dirs.add(os.path.dirname(self.reposdir))

            for repoid, repo in repos.items():
                if repo['baseurl'].startswith("file://"):
                    dirs.add(repo['baseurl'][7:])

            dir_args = []
            for d in dirs:
                dir_args.append("-v")
                dir_args.append(f"{d}:{d}")

            return (
                [self.docker_bin, "run"]
                + self.DOCKER_ARGS
                + dir_args
                + [self.docker_image, "tdnf"]
                + tdnf_args
            )
        else:
            raise Exception("no usable tdnf or docker binary found")

    def execute(self, args):
        self.logger.info(f"running {' '.join(args)}")
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        retval = process.returncode

        out_json = None
        try:
            out_json = json.loads(out)
        except json.decoder.JSONDecodeError as e:
            # try again, stopping at the pos where error happened
            # happens when packages print output from scripts
            out_json = json.loads(out[: e.pos])
            self.logger.info(
                f"json decode failed at line {e.lineno}, at: '{e.doc[e.pos:]}'"
            )

        if retval != 0:
            self.logger.info(f"Command failed: {args}")
            self.logger.error(err.decode())
            if 'Error' in out_json:
                self.logger.info(f"Error code: {out_json['Error']}")
            if 'ErrorMessage' in out_json:
                self.logger.error(out_json['ErrorMessage'])
            else:
                print(out_json)

        return retval, out_json

    def run(self, args=[], directories=[], repos={}):
        args = self.get_command(args, directories, repos)
        return self.execute(args)


def main():
    tdnf = Tdnf(installroot="/installroot", releasever="5.0")
    retval, out_json = tdnf.run(["repolist"])
    print(json.dumps(out_json, indent=4))


if __name__ == "__main__":
    main()
