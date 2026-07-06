# /*
#  * Copyright © 2026 VMware, Inc.
#  * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
#  */
"""Standalone entrypoint that runs only the interactive dialog flow of the
photon-os-installer (IsoConfig.configure()), with the real disk lookup
(normally backed by `lsblk`) replaced by a small set of fake devices, and
prints the resulting install_config as JSON once the dialogs complete.

This never calls Installer.execute() - no disks, packages, or network are
touched by running this. It exists so tests can drive the dialogs with
tui_driver.py the same way iso_config.py's own "for debugging" main() lets
a human do it by hand: `python3 photon_installer/iso_config.py -f ui_config.json`.

Usage: iso_config_stub_entrypoint.py <path to ui_config.json>

Fake disks can be overridden via the POI_TEST_FAKE_DISKS environment
variable: a JSON list of {"model": ..., "path": ..., "size_bytes": ...}
objects. Defaults to a single 10 GiB disk at /dev/fakea.

Besides the disk lookup, two more real-system dependencies of the dialogs
are faked out so this has no system-package requirements beyond Python
itself: password strength checking (normally python3-cracklib) and
password hashing (normally shells out to `mkpasswd` from the `whois`
package). Neither is part of what these tests are exercising - the dialog
flow is - so real cracklib/mkpasswd behavior would only add environment
dependencies without adding coverage.
"""

import curses
import json
import os
import sys
import types

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
POI_INSTALLER_DIR = os.path.join(REPO_ROOT, "photon_installer")
sys.path.insert(0, POI_INSTALLER_DIR)

# Fake out cracklib before anything imports it (iso_config.py does `import
# cracklib` at module load time). Any password is considered strong enough.
_fake_cracklib = types.ModuleType("cracklib")
_fake_cracklib.VeryFascistCheck = lambda password: password
sys.modules.setdefault("cracklib", _fake_cracklib)

import device  # noqa: E402
from commandutils import CommandUtils  # noqa: E402

# Avoid shelling out to the real `mkpasswd` binary; the dialogs only care
# that *some* string ends up in install_config['shadow_password'].
CommandUtils.generate_password_hash = staticmethod(lambda password: f"$fake-hash${password}")

# Printed right before the final install_config JSON, so the driver can
# split the curses screen output from the actual result.
RESULT_MARKER = "===INSTALL_CONFIG_JSON==="

DEFAULT_FAKE_DISKS = [
    {"model": "Fake Disk", "path": "/dev/fakea", "size_bytes": 10 * 1024 ** 3},
]


class _FakeDevice:
    def __init__(self, model, path, size):
        self.model = model
        self.path = path
        self.size = size


def _load_fake_disks():
    raw = os.environ.get("POI_TEST_FAKE_DISKS")
    if raw:
        return json.loads(raw)
    return DEFAULT_FAKE_DISKS


def _human_size(size_bytes):
    return f"{size_bytes // (1024 ** 3)}G"


def _make_fake_refresh_devices(fake_disks):
    def _fake_refresh_devices(bytes=False):
        return [
            _FakeDevice(
                disk["model"],
                disk["path"],
                str(disk["size_bytes"]) if bytes else _human_size(disk["size_bytes"]),
            )
            for disk in fake_disks
        ]
    return _fake_refresh_devices


device.Device.refresh_devices = staticmethod(_make_fake_refresh_devices(_load_fake_disks()))

from iso_config import IsoConfig  # noqa: E402


def main():
    with open(sys.argv[1]) as f:
        ui_config = json.load(f)

    install_config = curses.wrapper(IsoConfig().configure, ui_config)

    print(RESULT_MARKER)
    print(json.dumps(install_config))


if __name__ == "__main__":
    main()
