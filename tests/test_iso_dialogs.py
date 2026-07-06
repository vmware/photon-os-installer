# /*
#  * Copyright © 2026 VMware, Inc.
#  * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
#  */
"""Scripted walkthroughs of the interactive iso installer dialogs.

These drive photon_installer/iso_config.py's dialog flow (never
Installer.execute()) via tests/tui_driver.py + the stub entrypoint in
tests/fixtures/, so they touch no real disks/packages/network and can run
as a normal, fast part of CI. See docs/testing-interactive-installer.md.
"""

import json
import os
import shlex
import sys

from tui_driver import TuiDriver

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
STUB_ENTRYPOINT = os.path.join(FIXTURES_DIR, "iso_config_stub_entrypoint.py")
PACKAGES_OPTIONS_FILE = os.path.join(FIXTURES_DIR, "packages_options.json")

# Password strength checking is faked out in the stub entrypoint (see
# tests/fixtures/iso_config_stub_entrypoint.py), so any non-empty value works.
ROOT_PASSWORD = "xK9#mQ2$vL7pZ4w"

RESULT_MARKER = "===INSTALL_CONFIG_JSON==="


def _write_ui_config(tmp_path):
    ui_config = {
        "options_file": PACKAGES_OPTIONS_FILE,
        "eula_file_path": None,
        "license_display_title": None,
    }
    path = tmp_path / "ui_config.json"
    path.write_text(json.dumps(ui_config))
    return path


def _run_dialogs(tmp_path, on_stig_screen=None):
    """Walk through every dialog screen, accepting defaults throughout.

    `on_stig_screen(driver)`, if given, runs once the STIG screen is up
    instead of the default "press enter to accept 'No'" behavior, so tests
    can exercise non-default choices without duplicating the whole flow.
    """
    ui_config_path = _write_ui_config(tmp_path)
    command = f"{shlex.quote(sys.executable)} {shlex.quote(STUB_ENTRYPOINT)} {shlex.quote(str(ui_config_path))}"

    driver = TuiDriver(command, cwd=str(tmp_path))
    try:
        driver.expect_text("Welcome to the Photon installer")
        driver.send_key("enter")  # accept the license

        driver.expect_text("Select a disk")
        driver.send_key("enter")  # first (only) disk, auto-partition

        driver.expect_text("Select Installation")
        driver.send_key("enter")  # default (minimal) package set

        driver.expect_text("Network Configuration")
        driver.send_key("enter")  # "Configure network automatically" (DHCP)

        driver.expect_text("Select Linux kernel to install")
        driver.send_key("enter")  # Generic kernel

        driver.expect_text("Apply STIG hardening")
        if on_stig_screen:
            on_stig_screen(driver)
        else:
            driver.send_key("enter")  # "No"

        driver.expect_text("Choose the hostname")
        driver.send_key("enter")  # accept the generated random hostname

        driver.expect_text("Set up root password")
        driver.send_text(ROOT_PASSWORD)
        driver.send_key("enter")

        driver.expect_text("Confirm root password")
        driver.send_text(ROOT_PASSWORD)
        driver.send_key("enter")

        driver.expect_text("Confirm")
        driver.send_key("enter")  # "Yes", start installation

        exit_status, output = driver.close_and_get_result(timeout=15)
    finally:
        driver.terminate()

    output = output.decode(errors="replace") if isinstance(output, bytes) else output
    assert exit_status == 0, output
    _, _, payload = output.partition(RESULT_MARKER)
    return json.loads(payload)


def test_happy_path_auto_partition_dhcp(tmp_path):
    install_config = _run_dialogs(tmp_path)

    assert install_config["disk"] == "/dev/fakea"
    assert install_config["autopartition"] is True
    assert install_config["packages"] == ["minimal", "linux", "linux-rt"]
    assert install_config["linux_flavor"] == "linux"
    assert install_config["network"] == {"type": "dhcp"}
    assert install_config["hostname"].startswith("photon-")
    assert install_config["shadow_password"] == f"$fake-hash${ROOT_PASSWORD}"
    assert "ansible" not in install_config
    assert "additional_packages" not in install_config


def test_stig_hardening_enabled(tmp_path):
    def _enable_stig(driver):
        driver.send_key("down")  # move from the default "No" to "Yes"
        driver.send_key("enter")

    install_config = _run_dialogs(tmp_path, on_stig_screen=_enable_stig)

    assert install_config["ansible"]
    assert "audit" in install_config["additional_packages"]
