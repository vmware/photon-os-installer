# What is kickstart
Kickstart is a json format file use to configure installer to deploy OS as per user requirements.

# Ways to provide Kickstart path:

## Installing as ESXi VM

For an unattended installation, the kickstart configuration needs to be passed to the installer. For installing as ESXi VMs, we provide an easy way through VM extra settings:

    guestinfo.kickstart.data=<base64 encoded kickstart file content>

Or

    guestinfo.kickstart.url=<URL to kickstart configuration file>

The supported URL schemes are described below.

## Generic installation

If installing on other platforms or you'd rather prefer the generic kickstart installation path, the `ks=<URL to config_file>` parameter can be appended to the kernel command line, and the installer will take it up.

The supported URL schemes are: `cdrom:/`, `<abs-device-path>:<abs-file-path>`, `http://`, `https://` and `https+insecure://`

### 1. Kickstart from cdrom attched with iso

    ks=cdrom:/isolinux/sample_ks.cfg

### 2. Secondary Device Kickstart

    ks=<abs-device-path>:<abs-path-referential-to-device>
    Example:
    ks=/dev/sr1:/isolinux/sample_ks.cfg

### 3. Remote kickstart

    ks=[http|https|https+insecure]://<kickstart-link>

For https+insecure://, it's like https://, except that server certificate validation will be skipped.

Please refer [ks_config.md](https://github.com/vmware/photon-os-installer/docs/ks_config.md) to explore more about kickstart features.
