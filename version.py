#!/usr/bin/env python3

#
# Copyright © 2020-2021 VMware, Inc.
# SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
#

__all__ = ('get_installer_version')

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
    # if not a git repo return empty string
    if call(['git', 'branch'], stderr=STDOUT, stdout=open(os.devnull, 'w')):
        return ''

    version = get_version()
    if is_dirty():
        version += '.dirty'

    if not version:
        raise ValueError('Cannot get the version number!')

    return version


if __name__ == '__main__':
    print(get_installer_version())
