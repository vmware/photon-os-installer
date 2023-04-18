#!/usr/bin/env python3

#
# Copyright © 2020-2023 VMware, Inc.
# SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
#

__all__ = ('get_installer_version')

# Default Tag represents tag value in case git is not available on system.
# This need not be updated with every tag release.
defaultTag = "2.2"

import os
from subprocess import Popen, PIPE
from subprocess import call, STDOUT

def get_version():
    try:
        p = Popen(['git', 'rev-parse', '--short', 'HEAD'],
                  stdout=PIPE, stderr=PIPE)
        p.stderr.close()
        line = p.stdout.readlines()[0].decode()
        return line.strip()
    except:
        raise ValueError('Cannot get the version number!')

def get_latest_tag():
    try:
        p = Popen(['git', 'describe', '--tags', '--abbrev=0'],
                  stdout=PIPE, stderr=PIPE)
        p.stderr.close()
        line = p.stdout.readlines()[0].decode().strip()
        return line[1:]
    except:
        raise ValueError('Cannot get the latest tag!')

def is_dirty():
    try:
        p = Popen(['git', 'diff-index', '--name-only', 'HEAD'],
                  stdout=PIPE, stderr=PIPE)
        p.stderr.close()
        lines = p.stdout.readlines()
        return len(lines) > 0
    except:
        return False


def get_installer_version():
    # if not a git repo, return default tag.
    try:
        if call(['git', 'branch'], stderr=STDOUT, stdout=open(os.devnull, 'w')):
            return defaultTag
    except FileNotFoundError:
        # also return default tag when we do not have git.
        return defaultTag

    version = f"{get_latest_tag()}+{get_version()}"
    if not version:
        raise ValueError("Cannot get the version number!")

    if is_dirty():
        version += '.dirty'

    return version


if __name__ == '__main__':
    print(get_installer_version())
