"""
Keep ext[234] file systems compatible with the target's e2fsprogs.

The file systems are created with the mke2fs of the build host, but are
checked (fsck) at boot by the e2fsprogs installed in the target. If the host
mke2fs is newer, it may enable features by default that the target's
e2fsprogs does not know, and the target fails to boot. For example
e2fsprogs 1.47.0 enables 'orphan_file', which 1.46.x cannot handle.

For every such feature, this plugin disables it in 'mkfs_options' of the
ext[234] partitions, unless the partition already mentions the feature.
"""

import copy
import os
import re
import subprocess
import tempfile

import tdnf

EXTFS_TYPES = ["ext2", "ext3", "ext4"]

# feature -> first e2fsprogs version that supports it
FEATURES = {
    'orphan_file': (1, 47, 0),
}


def _parse_version(version):
    # strip epoch and release, "1:1.47.4-1.ph5" -> (1, 47, 4)
    version = version.split(":")[-1].split("-")[0]
    return tuple(int(n) for n in re.findall(r"\d+", version))


def _version_str(version):
    return ".".join(str(n) for n in version)


def _get_host_version(installer):
    try:
        result = subprocess.run(["mke2fs", "-V"], capture_output=True, text=True)
    except FileNotFoundError:
        return None
    # prints "mke2fs 1.47.0 (5-Feb-2023)" to stderr
    match = re.search(r"mke2fs\s+(\d[\d.]*)", result.stderr + result.stdout)
    if not match:
        installer.logger.warning(f"could not parse mke2fs version from: {result.stderr}")
        return None
    return _parse_version(match.group(1))


def _get_target_version(installer):
    install_config = installer.install_config

    # explicitly pinned, like "e2fsprogs-1.46.5"
    for pkg in install_config.get('packages', []):
        match = re.match(r"e2fsprogs-(\d.*)", pkg)
        if match:
            return _parse_version(match.group(1))

    # otherwise the latest available from the install repos
    with tempfile.TemporaryDirectory(prefix="extfs-compat-") as tmpdir:
        tdnf.create_repo_conf(copy.deepcopy(install_config['repos']),
                              reposdir=tmpdir,
                              insecure=install_config.get('insecure_repo', False))
        config_file = os.path.join(tmpdir, "tdnf.conf")
        with open(config_file, "wt") as f:
            f.write("[main]\ngpgcheck=0\nkeepcache=0\n")
        installroot = os.path.join(tmpdir, "root")
        os.makedirs(installroot)

        tdnf_inst = tdnf.Tdnf(logger=installer.logger,
                              config_file=config_file,
                              arch=install_config['arch'],
                              reposdir=tmpdir,
                              releasever=installer.photon_release_version,
                              installroot=installroot)
        retval, pkgs = tdnf_inst.run(["list", "e2fsprogs"])

    if retval != 0 or not pkgs:
        return None

    versions = [_parse_version(p['Evr']) for p in pkgs if p.get('Name') == "e2fsprogs"]
    return max(versions) if versions else None


def _feature_names(options):
    """ feature names in mkfs_options, as (enabled, disabled) sets """
    enabled = set()
    disabled = set()
    for opt in options:
        opt = opt.strip()
        if opt.startswith("-O"):
            opt = opt[2:].strip()
        if opt.startswith("^"):
            disabled.add(opt[1:])
        else:
            enabled.add(opt)
    return enabled, disabled


def add_defaults(installer):
    partitions = [p for p in installer.install_config['partitions']
                  if p.get('filesystem') in EXTFS_TYPES]
    if not partitions:
        return

    host_version = _get_host_version(installer)
    if host_version is None:
        installer.logger.info("mke2fs version unknown, skipping ext fs compatibility check")
        return

    # only features the host mke2fs knows can be disabled
    candidates = [f for f, v in FEATURES.items() if host_version >= v]
    if not candidates:
        return

    target_version = _get_target_version(installer)
    if target_version is None:
        installer.logger.info("e2fsprogs not found for target, skipping ext fs compatibility check")
        return

    unsupported = [f for f in candidates if target_version < FEATURES[f]]
    if not unsupported:
        return

    for partition in partitions:
        options = partition.get('mkfs_options', [])
        # will be normalized by the installer later
        if isinstance(options, str):
            options = options.split(",")
        enabled, disabled = _feature_names(options)

        # explicitly enabled, keep it as an override
        for f in unsupported:
            if f in enabled:
                installer.logger.warning(
                    f"WARNING: {f} explicitly enabled for {partition['filesystem']} partition "
                    f"{partition.get('mountpoint') or ''}, but target e2fsprogs "
                    f"{_version_str(target_version)} does not support it "
                    f"(needs e2fsprogs >= {_version_str(FEATURES[f])})")

        disabled = [f for f in unsupported if f not in enabled and f not in disabled]
        if disabled:
            partition['mkfs_options'] = options + [f"^{f}" for f in disabled]
            reasons = ", ".join(f"{f} (needs e2fsprogs >= {_version_str(FEATURES[f])})" for f in disabled)
            installer.logger.warning(
                f"NOTE: target e2fsprogs {_version_str(target_version)} does not support "
                f"{reasons}, disabling for {partition['filesystem']} partition "
                f"{partition.get('mountpoint') or ''}")
