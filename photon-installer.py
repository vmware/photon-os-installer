from os.path import dirname, join
from argparse import ArgumentParser

if __name__ == '__main__':
    usage = "Usage: %prog [options]"
    parser = ArgumentParser(usage)
    parser.add_argument("-i", "--image-type", dest="image_type")
    parser.add_argument("-c", "--install-config", dest="install_config")
    parser.add_argument("-u", "--ui-config", dest="ui_config")
    parser.add_argument("-r", "--repo-path", dest="repo_path")
    parser.add_argument("-o", "--options-file", dest="options_file")
    parser.add_argument("-w", "--working-dir", dest="working_dir")
    parser.add_argument("-p", "--rpm-path", dest="rpm_path")
    parser.add_argument("-l", "--log-path", dest="log_path")

    options = parser.parse_args()

    if options.image_type == 'iso':
        from isoInstaller import IsoInstaller
        IsoInstaller(options.install_config, options.ui_config, options.repo_path, options.options_file)

    else:
        from installer import Installer
        installer = Installer(working_directory=working_directory, rpm_path=options.rpm_path,log_path=options.log_path)
        installer.configure(install_config)
        installer.execute()
