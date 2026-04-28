# /*
# * Copyright © 2026 Broadcom, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */

import os

import commons

install_phase = commons.POST_INSTALL
enabled = True


def execute(installer):
    default_services = {}

    # Get user-defined services from config
    user_services = installer.install_config.get('services', {})

    # Merge configurations, prioritizing user_services
    services = default_services.copy()
    services.update(user_services)

    if not services:
        return

    # Map states to systemctl verbs
    verb_map = {
        'enabled': 'enable',
        'disabled': 'disable',
        'masked': 'mask'
    }

    for service, state in services.items():
        verb = verb_map.get(state)
        if not verb:
            installer.logger.warning(f"Invalid state '{state}' for service '{service}'")
            continue

        if state in ['enabled', 'disabled']:
            # Check if it's masked first
            service_link = os.path.join(installer.photon_root, f"etc/systemd/system/{service}.service")
            if os.path.islink(service_link) and os.readlink(service_link) == "/dev/null":
                installer.logger.info(f"Unmasking service '{service}' before setting state to '{state}'")
                installer.cmd.run_in_chroot(installer.photon_root, f"systemctl unmask {service}")

        installer.logger.info(f"Setting service '{service}' to '{state}'")
        retval = installer.cmd.run_in_chroot(installer.photon_root, f"systemctl {verb} {service}")
        if retval != 0:
            raise Exception(f"Failed to set service '{service}' to '{state}' (exit code: {retval})")
