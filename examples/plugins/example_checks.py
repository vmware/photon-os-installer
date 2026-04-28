import os


def pre_install(installer):
    installer.logger.info("Executing pre_install hook from poi_plugins...")


def pre_pkgs_install(installer):
    installer.logger.info("Executing pre_pkgs_install hook from poi_plugins...")


def post_install(installer):
    installer.logger.info("Executing post_install hook from poi_plugins...")


def final_check(installer):
    """
    Run custom validation checks on the installed system.

    :param installer: The Installer instance, providing access to:
                      - installer.photon_root (path to the chroot)
                      - installer.cmd (CommandUtils for running commands)
                      - installer.logger (for logging output)
                      - installer.install_config (the parsed ks config)
    """
    installer.logger.info("Starting custom validation checks...")

    # ---------------------------------------------------------
    # Example 1: Run a command INSIDE the chroot
    # ---------------------------------------------------------
    installer.logger.info("Checking if SSH is enabled...")

    # run_in_chroot executes the command inside the new system and returns the exit code
    retval = installer.cmd.run_in_chroot(
        installer.photon_root,
        "systemctl is-enabled sshd"
    )

    if retval == 0:
        installer.logger.info("Check passed: SSH is enabled.")
    else:
        # You can log a warning, or raise an exception to fail the installation
        installer.logger.warn("Check failed: SSH is NOT enabled.")
        # raise Exception("SSH must be enabled!")

    # ---------------------------------------------------------
    # Example 2: Run a command to check a package
    # ---------------------------------------------------------
    installer.logger.info("Checking if 'vim' is installed...")
    retval = installer.cmd.run_in_chroot(
        installer.photon_root,
        "rpm -q vim"
    )
    if retval == 0:
        installer.logger.info("Check passed: vim is installed.")
    else:
        installer.logger.warn("Check failed: vim is not installed.")

    # ---------------------------------------------------------
    # Example 3: Check a file directly from the host side
    # ---------------------------------------------------------
    installer.logger.info("Checking GRUB configuration...")
    grub_cfg_path = os.path.join(installer.photon_root, "boot/grub2/grub.cfg")

    if os.path.exists(grub_cfg_path):
        with open(grub_cfg_path, 'r') as f:
            content = f.read()
            if 'password' in content:
                installer.logger.info("Check passed: GRUB password is set.")
            else:
                installer.logger.warn("Check failed: GRUB password is NOT set.")
    else:
        installer.logger.warn(f"GRUB config not found at {grub_cfg_path}")

    installer.logger.info("Custom validation checks completed.")
