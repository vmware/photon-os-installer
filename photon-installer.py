#/*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */
from os.path import dirname, join
from argparse import ArgumentParser

if __name__ == '__main__':
    usage = "Usage: %prog [options]"
    parser = ArgumentParser(usage)
    parser.add_argument("-i", "--image-type", dest="image_type")
    parser.add_argument("-c", "--install-config", dest="install_config_file")
    parser.add_argument("-u", "--ui-config", dest="ui_config_file")
    parser.add_argument("-r", "--repo-path", dest="repo_path")
    parser.add_argument("-o", "--options-file", dest="options_file")
    parser.add_argument("-w", "--working-dir", dest="working_dir")
    parser.add_argument("-p", "--rpm-path", dest="rpm_path")
    parser.add_argument("-l", "--log-path", dest="log_path")
    parser.add_argument("-e", "--eula-file", dest="eula_file_path", default=None)
    parser.add_argument("-t", "--license-title", dest="license_display_title", default=None)

    options = parser.parse_args()

    if options.image_type == 'iso':
        from isoInstaller import IsoInstaller
        IsoInstaller(options)

    else:
        from installer import Installer
        import json
        install_config = None
        if options.install_config_file:
            with open(options.install_config_file) as f:
                install_config = json.load(f)
        else:
            raise Exception('install config file not provided')

        installer = Installer(working_directory=working_directory, rpm_path=options.rpm_path,log_path=options.log_path)
        installer.configure(install_config)
        installer.execute()
