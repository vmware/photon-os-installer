# What is kickstart
Kickstart is a json format file use to configure installer to deploy OS as per user requirements.

# Ways to provide Kickstart path:

### 1. Remote kickstart

    ks=http://<kickstart-link>

### 2. Kickstart from cdrom attched with iso

    ks=cdrom:/isolinux/sample_ks.cfg

### 3. Secondary Device Kickstart

    ks=<device-path>:<path-referential-to-device>
    Example:
    ks=/dev/sr1:/isolinux/sample_ks.cfg

Please refer [ks_config.md](https://github.com/vmware/photon-os-installer/docs/ks_config.md) to explore more about kickstart features.
