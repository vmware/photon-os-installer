# Photon OS Installer

### What is Photon Installer

Photon OS Installer Project aims to seperate out installer source code from [Photon project](https://github.com/vmware/photon/tree/master) and use it as a python library. This Project can be used to create a photon-installer binary that can be used to install Photon OS when invoked with appropriate arguments.

### Features

 - Generates Photon Installer executable.
 - Creates Photon Images(ISO, GCE, AMI, AZURE, OVA...).
 - Makes Photon Installer Source code installable through pip interface and use it as a python library.

### Dependencies

 `python3, python3-pyinstaller, python3-setuptools`

### Building from source.

 Building Photon Installer Executable on Photon OS
```bash
➜  ~ tdnf install -y python3 python3-setuptools python3-pyinstaller
➜  ~ git clone https://github.com/vmware/photon-os-installer.git
➜  ~ cd photon-os-installer
➜  ~ pyinstaller --onefile photon-installer.spec
```
 Building Photon Installer Executable on Other distros
```bash
➜  ~ pip3 install setuptools pyinstaller
➜  ~ git clone https://github.com/vmware/photon-os-installer.git
➜  ~ cd photon-os-installer
➜  ~ pyinstaller --onefile photon-installer.spec
```

The executable generated can be found inside dist directory created.

Building Photon Cloud images using Photon OS Installer
```bash
➜  ~ pip3 install git+https://github.com/vmware/photon-os-installer.git
➜  ~ git clone https://github.com/vmware/photon.git
➜  ~ cd photon
➜  ~ make image IMG_NAME=<img-name>
```

Using Photon OS Installer as python library
install config mentioned below can be referred from [Photon Project](https://github.com/vmware/photon/blob/master/support/image-builder/azure/config_azure.json)
```python
import photon_installer
from photon_installer.installer import Installer
installer = Installer(working_directory='/root/photon/stage/ova', rpm_path='/root/photon/stage/RPMS', log_path='/root/photon/stage/LOGS')
installer.configure(install_config)
installer.execute()
```

### Contributing

The Photon OS Installer project team welcomes contributions from the community. If you wish to contribute code and you have not signed our contributor license agreement (CLA), our bot will update the issue when you open a Pull Request. For any questions about the CLA process, please refer to our [FAQ](https://cla.vmware.com/faq).

License
----

[Apache-2.0](https://spdx.org/licenses/Apache-2.0.html)
[GPL-2.0](https://github.com/vmware/photon-os-installer/blob/master/LICENSE-GPL2.0)
