# Testing the interactive (curses) installer

The interactive installer's dialog flow (`photon_installer/iso_config.py`
and the screens under `photon_installer/`) is covered by an automated,
scripted walkthrough in `tests/test_iso_dialogs.py`. This doc explains how
that works and how to extend it.

Out of scope here: booting the real ISO end-to-end in a VM. That's handled
separately, and there's already coverage for installing from an ISO image
via other tests/tooling.

## Why this is possible

`Installer.configure()` (`photon_installer/installer.py`) cleanly separates
gathering answers from acting on them:

- The curses dialogs (driven by `IsoConfig.configure()` in
  `photon_installer/iso_config.py`) only build up an `install_config` dict.
- `Installer.execute()` is the part that actually partitions disks, installs
  packages, etc., and is a separate call that these tests never make.

`iso_config.py` also has a `main()` ("for debugging") that runs just the
dialog flow standalone via `curses.wrapper(IsoConfig.configure, ui_config)`
and prints the resulting JSON:

```
cd photon_installer
python3 iso_config.py -f sample_ui_config.json
```

`photon_installer/sample_ui_config.json` is a minimal working ui_config
(`eula_file_path`/`license_display_title` set to `null`, picking up the
defaults). Both keys are required — `add_ui_pages()` reads them with plain
dict indexing (`ui_config['eula_file_path']`), so a `ui_config.json` missing
either one raises a `KeyError` before the first screen even renders; the
debug `main()` doesn't fill in defaults for them itself. This run uses your
machine's *real* disks (`SelectDisk` isn't stubbed here — only the
automated tests stub it) but is still safe: this path only ever calls
`IsoConfig.configure()`, never `Installer.execute()`, so nothing is written
to disk regardless of what you select.

That's the manual, human-drivable way to click through the screens for a
quick sanity check. `tests/test_iso_dialogs.py` automates the same idea.

Only one screen touches the real system: `SelectDisk` /
`CustomPartition` call `Device.refresh_devices()`
(`photon_installer/device.py`), which shells out to `lsblk`. That's stubbed
out for the tests (see below). `NetworkConfigure` does **not** probe real
network interfaces — it only ever offers a fixed menu of DHCP/static/VLAN
options — so it needs no stubbing.

## Driving the TUI with `pexpect`

`tests/tui_driver.py` wraps `pexpect`: it spawns the dialog process in a
pty and lets tests `expect()` known marker text (window titles, prompts)
and `send()` key sequences (arrows, tab, enter, plain text) in response —
no terminal-emulation/screen-buffer library needed. Each curses screen
renders distinctive, literal strings (e.g. `"Select a disk"`, `"Choose the
hostname for your system"`) that survive being interleaved with
ANSI/cursor-movement bytes, so sequential `expect()` calls reliably confirm
which screen is up before the next batch of keys is sent.

Known limitation: `pexpect` has no screen model, so it can't tell which
menu item currently has the highlight (that's conveyed via color/reverse
video, not text). Tests work around this by scripting a fixed, known-good
key sequence per screen (e.g. "press Down once, then Enter" to move off the
default choice) instead of reading back highlight state.

`TERM` is pinned to `"linux"` in `tui_driver.py` rather than left to the
environment: the `"linux"` terminfo entry maps arrow keys to the plain
`ESC [ A/B/C/D` byte sequences, whereas e.g. `"xterm"`'s terminfo uses
`ESC O A/B/C/D` — an easy way to get silently-ignored keystrokes if `TERM`
varies by environment.

## Fixtures/stubs (`tests/fixtures/`)

`tests/fixtures/iso_config_stub_entrypoint.py` is what `pexpect` actually
spawns. Before calling `IsoConfig().configure()` it patches out three real
external dependencies the dialogs would otherwise pull in, so the tests
have no system-package requirements and no dependence on the machine
they're running on:

- `Device.refresh_devices` → returns a small fixed list of fake disks
  (default: one 10 GiB disk at `/dev/fakea`), overridable via the
  `POI_TEST_FAKE_DISKS` env var (JSON list of
  `{"model", "path", "size_bytes"}`).
- `cracklib.VeryFascistCheck` → faked to accept any password. Password
  strength policy isn't what these tests exercise.
- `CommandUtils.generate_password_hash` → faked to avoid shelling out to
  the real `mkpasswd` binary (from the `whois` package). The dialogs only
  care that *some* string ends up in `install_config['shadow_password']`.

`tests/fixtures/packages_options.json` is a package-options file (the
format normally passed as `--options-file`/`ui_config['options_file']`)
with two visible options, both including `"linux"` and `"linux-rt"` in
their package lists. Two visible options keeps the package-selection screen
active (a single-option file gets silently auto-skipped by
`PackageSelector`), and having two non-conflicting kernel flavors present
keeps the linux-kernel-selection screen active too (`LinuxSelector`
auto-skips itself when fewer than two flavors are available). This makes
both screens deterministically part of the flow regardless of what
environment the test runs in.

## The tests: `tests/test_iso_dialogs.py`

`_run_dialogs()` walks the full screen sequence — license, disk selection,
packages, network, kernel flavor, STIG, hostname, root password (x2),
final confirmation — accepting the default choice at each screen unless a
test overrides one step (currently only the STIG screen, via the
`on_stig_screen` callback). It returns the final `install_config` as a
parsed dict for assertions.

Two tests today:

- `test_happy_path_auto_partition_dhcp` — every default accepted.
- `test_stig_hardening_enabled` — same flow, but presses Down+Enter on the
  STIG screen and asserts `ansible`/`additional_packages` show up.

To add another variant (e.g. static IP networking, custom partitioning),
add a new test that calls `_run_dialogs()` with an override callback for
the relevant screen, following the `on_stig_screen` pattern — or extend
`_run_dialogs()` with another optional callback parameter if the new
variant needs to diverge earlier/later in the sequence.

Since this only ever calls `IsoConfig.configure()` (never
`Installer.execute()`), these tests touch no real disks/packages/network
and run in ~1s each — a normal, fast part of CI
(`.github/workflows/photon-os-installer.yml`), unlike a real install.

## Dependency

- `pexpect` (installed in CI via `pip install pytest pexpect`; not added to
  `requirements.txt` since it's test-only, not a runtime dependency of the
  installer itself).

## Explicitly not covered here

- Booting the actual ISO in QEMU/a VM and driving the installer over a
  serial console for a true end-to-end interactive install. This is handled
  separately; there's already coverage for installing from an ISO image via
  other tests/tooling.
