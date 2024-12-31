#/*
# * Copyright © 2020-2023 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */
from os.path import dirname, join
from argparse import ArgumentParser
import sys
import traceback
from commandutils import CommandUtils
import yaml


def main():
    parser = ArgumentParser()
    parser.add_argument("-i", "--image-type", dest="image_type")
    parser.add_argument("-c", "--install-config", dest="install_config_file")
    parser.add_argument("-u", "--ui-config", dest="ui_config_file")
    # comma separated paths to rpms
    parser.add_argument("-r", "--repo-paths", dest="repo_paths", default=None)
    parser.add_argument("-o", "--options-file", dest="options_file")
    parser.add_argument("-w", "--working-directory", dest="working_directory")
    parser.add_argument("-l", "--log-path", dest="log_path", default="/var/log")
    parser.add_argument("-e", "--eula-file", dest="eula_file_path", default=None)
    parser.add_argument("-t", "--license-title", dest="license_display_title", default=None)
    parser.add_argument("-v", "--photon-release-version", dest="photon_release_version", required=True)
    parser.add_argument("-p", "--param", dest='params', action='append', default=[])

    options = parser.parse_args()

    params = {}
    for p in options.params:
        k,v = p.split('=', maxsplit=1)
        params[k] = yaml.safe_load(v)

    try:
        if options.image_type == 'iso':
            from isoInstaller import IsoInstaller
            IsoInstaller(options, params=params)
        else:
            from installer import Installer
            import json
            install_config = None
            if options.install_config_file:
                with open(options.install_config_file) as f:
                    install_config = CommandUtils.readConfig(f, params=params)
            else:
                raise Exception('install config file not provided')
            if options.repo_paths is None and "repos" not in install_config:
                raise Exception('No repo available! Specify repo via "--repo-paths" or "repos" in install_config')
            if not options.working_directory:
                raise Exception('Please provide "--working-directory"')

            installer = Installer(working_directory=options.working_directory, repo_paths=options.repo_paths,
                                log_path=options.log_path, photon_release_version=options.photon_release_version)
            installer.configure(install_config)
            installer.execute()
    except Exception as err:
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

