# Kickstart Features

The kickstart config file is a json format file with the following possible parameters:


### _"additional_files":_ (optional)

- Contains list of pairs { source file (or directory), destination file
(or directory) } to copy to the target system. Source file
(directory) will be looked up in "search_path" list.

  Example:
  ```json
  {
     "additional_files": [
                           {"resizefs.sh": "/usr/local/bin/resizefs.sh"},
                           {"resizefs.service": "/lib/systemd/system/resizefs.service"}
                         ]
  }
  ```
### _"additional_packages":_
- Same as _"packages"_

### _"additional_rpms_path":_ (optional)
- Provide a path containing additional RPMS that are to be bundled into the image.


### _"arch":_ (optional)
- Target system architecture. Should be set if target architecture is
different from host one, for instance x86_64 machine building RPi
image.

  - ***Acceptable values:*** _"x86_64"_, _"aarch64"_

  - ***Default value:*** autodetected host architecture

  Example:
  ```json
  {
    "arch": "aarch64"
  }
  ```

### _"bootmode":_ (optional)
- Sets the boot type to suppot: EFI, BIOS or both.

  - ***Acceptable values:*** _"bios"_, _"efi"_, _"dualboot"_
  - ***Default value:*** _"dualboot"_ for x86_64 and _"efi"_ for aarch64

- _"bios"_ will add special partition (very first) for first stage grub.
- _"efi"_ will add ESP (Efi Special Partition), format is as FAT and copy
there EFI binaries including grub.efi
- _"dualboot"_ will add two extra partitions for "bios" and "efi" modes.
  - This target will support both modes that can be switched in bios
settings without extra actions in the OS.

  Example:
  ```json
  {
    "bootmode": "bios"
  }
  ```

### _"disk":_ (required)

- Target"s disk device file path to install into, such as "/dev/sda".
Loop device is also supported.

  Example:
  ```json
  {
    "disk": "/dev/sdb"
  }
  ```
- /dev/disk/by-path is also supported.

  Example:
  ```json
  {
    "disk": "/dev/disk/by-path/pci-0000:03:00.0-scsi-0:0:1:0"
  }
  ```
### _"eject_cdrom":_ (optional)
- Eject or not cdrom after installation completed.
  - **Boolean:** _true_ or _false_
  - **Default value:** true

  Example:
  ```json
  {
    "eject_cdrom": false
  }
  ```

### _"hostname":_ (optional)
- Set target host name.
  - **Default value:** "photon-<randomized string>"

  Example:
  ```json
  {
    "hostname": "photon-machine"
  }
  ```
### _"live":_ (optional)
- Should be set to false if target system will not be run on
 host machine. When it set to false, installer will not add EFI boot
 entries, and will not generate unique machine-id.
  - **Boolean:** _false_ if "disk" is /dev/loop and _true_ otherwise.

  Example:
   ```json
  {
    "live": false
  }
   ```
### _"log_level":_ (optional)
- Set installer logging level.
  - **Acceptable values:** _"error"_, _"warning"_, _"info"_, _"debug"_
  - **Default value:** _"info"_

    Example:
    ```json
    {
      "log_level": "debug"
    }
    ```
### _"ostree":_ (optional)
- Atomic flavour of Photon OS.
- Define the type of repo data used for installing the OS
- There are two type:
  1. Default Repo(comes with ISO)
  2. Custom Repo (Remote server)
  - _"default_repo":_ (required)
    - **Boolean:** _true_ or _false_
      - _true_ : Default Repo is selected
      - _false_: Custom Repo is selected
    - **Default value:** _true_
   Example:
   ```json
   {
     "ostree": {
                  "default_repo": true
               }
   }
   ```
  - _"repo_url":_ (Required, Only If Custom Repo is selected)
    - **Supported Values:** Valid "repo" URL of remote server where repo data exists
  - _"repo_ref":_ (Required, Only If Custom Repo is selected)
    - **Supported Value:** Valid "ref" path which was mentioned for
                           creation of Base Tree on remote server

   Example:
   ```json
   {
     "ostree": {
                 "default_repo": false,
                 "repo_url": "http://<ip>:<port>/repo",
                 "repo_ref": "photon/4.0/x86_64/minimal"
               }
   }
   ```

### _"packagelist_file":_ (optional if _"packages"_ set)
- Contains file name which has list of packages to install.

  Example:
  ```json
  {
    "packagelist_file": "packages_minimal.json"
  }
  ```

### _"packages":_ (optional if _"packagelist_file"_ set)
- Contains list of packages to install.

  Example:
  ```json
  {
    "packages": ["minimal", "linux", "initramfs"]
  }
  ```

### _"partition_type":_ (optional)
- Set partition table type. Supported values are: "gpt", "msdos".
 - **Default value:** _"gpt"_

  Example:
  ```json
  {
    "partition_type": "msdos"
  }
  ```

### _"partitions":_ (optional)
- Contains list of partitions to create.
- Each partition is a dictionary of the following items:
 - _"filesystem":_ (required)
  - Filesystem type.
      - **Supported values:** _"swap"_, _"ext4"_, _"vfat"_, _"xfs"_, _"btrfs"_.

  - _"disk":_ (_optional_ if single disk device is available,
             _required_ if multiple disk devices are available)
    - Target disk device will have the defined partition
    - **Supported values:**
      - _"/dev/loop":_ loop devices
      - _"/dev/sdX"_ : scsi drives based devices
      - _"/dev/hdX"_ : IDE drives based devices
  - _"mountpoint":_ (required for non "swap" partitions)
    - Mount point for the partition.
  - _"size":_
    - Exactly one of "size" or "sizepercent" (see below) is required.
    - Size of the partition in MB. If 0 then partition is considered
  as expansible to fill rest of the disk. Only one expansible
  partition is allowed.
  - _"sizepercent":_
    - Size of the partition in percent of the total disk space.
    - Only one of "size" and "sizepercent" can be set per partition.

    Example - `/boot` has a fixed size of 128 MB, swap has 5 percent of
    the total disk size and the root fs gets the remaining space:
    ```json
    "partitions": [
    {
      "mountpoint": "/",
      "size": 0,
      "filesystem": "ext4"
    },
    {
      "mountpoint": "/boot",
      "size": 128,
      "filesystem": "ext4"
    },
    {
      "sizepercent": 5,
      "filesystem": "swap"
    }
    ```
  - _"mkfs_options":_ (optional)
    - Additional parameters for the mkfs command as a string
  - _"fs_options":_ (optional)
    -fs options to be passed to mount command as a string

    Example:
    ```json
    "fs_options": "nodev,noexec,nosuid"
    ```
  - _"btrfs":_ (optional)
    - Creates btrfs volumes and subvolumes.
    - Value is a dictionary with 1 required and 1 optional key.
    - _"label"_ (optional)
      - Name of the parent volume label.
    - _"subvols"_ (optional)
      - Subvolumes inside parent volume.

    Example:
    ```json
    {
      "disk": "/dev/sda",
      "partitions": [
                      {
                        "mountpoint": "/",
                        "size": 0,
                        "filesystem": "btrfs"
                      }
                    ]
    }
    ```
    Example to create subvols:
    ```json
    {
      "partitions" : [
                        {
                          "mountpoint": "/",
                          "size": 2048,
                          "filesystem": "btrfs",
                          "btrfs" : {
                                      "label" : "main",
                                      "subvols" : [
                                                    {
                                                      "name": "rootfs",
                                                      "mountpoint": "/root"
                                                    },
                                                    {
                                                      "name": "home",
                                                      "mountpoint": "/home",
                                                      "subvols": [
                                                                   {
                                                                      "name": "dir1",
                                                                      "mountpoint": "/dir1"
                                                                   }
                                                                 ]
                                                    }
                                                  ]
                                     }
                        }
                    ]
    }
    ```
  - _"lvm":_ (optional)
    - Will logical volume (LVM) for this partition.
    - Value is a dictionary with 2 required keys:
    - _"vg_name"_ (required)
      - Name of a virtual group to put current partition into.
      - Several partitions may have same "vg_name"
    - _"lv_name"_ (required)
      - Unique logical volume name of the partition.

    Example:
    ```json
    {
      "partitions" : [
                             {
                               "mountpoint": "/",
                               "size": 0,
                               "filesystem": "ext4",
                               "lvm": {
                                        "vg_name": "VirtualGroup1",
                                        "lv_name": "root"
                                      }
                             },
                             {
                               "mountpoint": "/boot/efi",
                               "size": 12,
                               "filesystem": "vfat",
                               "fs_options": "-n EFI"
                             },
                             {
                               "size": 128,
                               "filesystem": "swap"
                             }
                     ]
    }
    ```
    Example: Multiple Disk device partition table
    ```json
    {
      "partitions": [
       {
         "disk": "/dev/sda",
         "mountpoint": "/",
         "size": 0,
         "filesystem": "ext4"
       },
       {
         "disk": "/dev/sdb",
         "mountpoint": "/sdb",
         "size": 0,
         "filesystem": "ext4"
       },
       {
         "disk": "/dev/sdc",
         "mountpoint": "/sdc",
         "size": 0,
         "filesystem": "ext4"
       },
     ]
    }
    ```
  - _"ab":_ (optional)
    - This feature enables the system to create a shadow partition
  (snapshot of user-defined partition) of a user defined partition.
    - This is required to support the system upgrade/rollback functionality via
  AB System Upgrade mechanism.
    - **Acceptable values:** _true_, _false_
    - **Default value:** _false_
    - Note that the space set is per individual partition. So if the size is
      for example set to 128 MB, a total of 256 MB will be used.
    - Example: If given the partition table below, the "/" partition will have
  a shadow partition but the "/sda" partition will not have a shadow partition:
    ```json
    {
      "partitions": [
                      {
                        "disk": "/dev/sda",
                        "mountpoint": "/",
                        "size": 0,
                        "filesystem": "ext4",
                        "ab": true
                      },
                      {
                        "disk": "/dev/sda",
                        "mountpoint": "/sda",
                        "size": 100,
                        "filesystem": "ext4"
                      }
                    ]
    }
    ```

### _"network":_ (optional)
- Used to configure network in live/installed system.

- Set  _"version":_ _"2"_ or the legacy config will be used, see below.

- The syntax roughly follows the cloud-init or netplan configuration,
    but not all options are supported.

 - _"hostname":_ set the host name.

 - _"ethernets":_ Settings for ethernet interfaces. Each interface has an 'id',
    which can be any name which may be referenced for example for VLANs. Can
    be the interface name.

    - Within any _'id'_:

      - _"match"_ : set a way to match this interface. Can be 'name' or 'macaddress'.

      - _"dhcp4"_ : boolean, set to true or false

      - _"dhcp6"_ : boolean, set to true or false

      - _"accept-ra"_ : boolean, set to true or false. Whether to accept
    Router Advertisement for IPv6.

      - _"addresses"_ : a list of ip addresses (IPv4 or IPv6) with cidr netmask.

      - _"gateway"_ : the default gateway.

      - _"nameservers"_ : a dictionary with "addresses" containing a list of name servers,
    and "search" with a list of search domains.

 - _"vlans":_ Settings for VLAN interfaces. Similar to _"ethernets"_ above,
    but with these additional required settings:

   - _"id"_ : the VLAN id (integer in the range 1..4094)

   - _"link"_ : the id of the ethernet interface to use, from the "ethernets"
    configured.

  Example:
  ```json
  {
    "network":{
                "version": "2",
                "hostname" : "photon-machine",
                "ethernets": {
                                "id0": {
                                          "match": {
                                                    "name" : "eth0"
                                                   },
                                          "dhcp4" : false,
                                          "addresses": ["192.168.2.58/24"],
                                          "gateway": "192.168.2.254",
                                          "nameservers": {
                                                            "addresses" : ["8.8.8.8", "8.8.4.4"],
                                                            "search" : ["vmware.com", "eng.vmware.com"]
                                                          }
                                       }
                             },
                "vlans": {
                            "vlan0": {
                                        "id": 100,
                                        "link": "id0",
                                        "addresses":["192.168.100.58/24"]
                                     }
                         }
              }
  }
  ```

 - Legacy network configuration:
  - _"type"_ (required)
    - String: must be one of _dhcp_/_static_/_vlan_. Indicates how the network
  is being configured.
  - _"hostname"_ (optional; when _type_ == _dhcp_)
    - String: DHCP client hostname
  - _"ip_addr"_ (required; when _type_ == _static_)
    - IP String: IP address to be configured
  - _"netmask"_ (required; when _type_ == _static_)
    - IP String: Netmask to be configured
  - _"gateway"_ (required; when _type_ == _static_)
    - IP String: Gateway IP address to be configured
  - _"nameserver"_ (required; when _type_ == _static_)
    - IP String: Name server IP address to be configured
  - _"vlan_id"_ (required; when _type_ == _vlan_)
    - ID String: (1-4094); VLAN ID number expressed as string

### _"password":_ (optional)
- Set root password. It is dictionary of the following items:
  - _"text"_ (required) password plain text (_"crypted"_ : _false_)
  or encrypted (_"crypted"_: _true_)
  - _"crypted"_ (required) Hint on how to interpret "text" content.
  - _"age"_ (optional) Set password expiration date. If not set, then
  used Photon OS default password aging value.
  - **Value:** integer. Meanings:
    - Any positive number - password will be expired in
    so many days from today.
    - Zero (0) - marks password as already expired. root
    will be asked to change current password during the
    first login.
    - Minus one (-1) - removes root password expiration date.
  - **Default value:**
  ```json
  {
    "crypted": true,
    "text": "*"
  }
  ```
  which means root is not allowed to login.

  Example:
  ```json
  {
    "password": {
                  "crypted": false,
                  "text": "changeme",
                  "age": 0
                }
  }
  ```

### _"postinstall":_ (optional)
- Contains list of lines to be executed as a single script on
 the target after installation.

  Example:
  ```json
  {
    "postinstall": [
                     "#!/bin/sh",
                     "echo \"Hello World\" > /etc/postinstall"
                   ]
  }
  ```
 ### _"postinstallscripts":_ (optional)
- Contains list of scripts to execute on the target after installation.
- Scripts will be looked up in _"search_path"_ list.

  Example:
  ```json
  {
    "postinstallscripts": ["rpi3-custom-patch.sh"]
  }
  ```

### _"preinstall":_ (optional)
- Contains list of lines to be executed as a single script on
 the target before installation starts.
- if ks file defines any value($VALUE) that need to be populated dynamically
 during runtime then it should be determined and exported in preinstall script.

  Example:
  ```json
  {
    "disk": "$DISK"
    "preinstall": [
                    "#!/bin/sh",
                    "ondisk=$(ls -lh /dev/disk/by-path/ | grep 'scsi-0:0:1:0' | cut -d' ' -f 9)",
                    "export DISK=\"/dev/disk/by-path/$ondisk\""
                  ]
  }
  ```
### _"preinstallscripts":_ (optional)
- Contains list of scripts to execute on the target before installation starts.
- Scripts will be looked up in _"search_path"_ list.

  Example:
  ```json
  {
    "preinstallscripts": ["find_disk.sh"]
  }
  ```

### _"public_key":_ (optional)
- To inject entry to authorized_keys as a string. Setting this variable
 enables root login in sshd config.

### _"search_path":_ (optional)
- List of directories to search for additional files and scripts.

  Example:
  ```json
  {
    "search_path": ["/home/user", "/tmp"]
  }
  ```

### _"shadow_password":_ (optional)
- Contains encrypted root password <encrypted password here>.
- Short form of:
  ```json
  {
    "password": {
                  "crypted": true,
                  "text": "<encrypted password here>"
                }
  }
  ```

### _"ui":_ (optional)
- Installer will show UI for progress status if it set to true.
 Or logging output will be printed to console - default behavior.
  - **Boolean:** _true_ or _false_
  - **Default value:** _false_

   Example:
   ```json
   {
     "ui": true
   }
   ```

### _"linux_flavor":_ (optional)
- Contains the flavor of linux to install, if multiple linux flavors
 are present in _"packages"_ or _"packagelist_file"_
  - **Acceptable values:** _"linux"_, _"linux-esx"_, _"linux-rt"_, _"linux-aws"_, and _"linux-secure"_

  Example:
  ```json
  {
    "linux_flavor": "linux-esx"
  }
  ```

### _"photon_docker_image":_ (optional)
- Contains the docker image <name:tag>
 are present in _"packages"_ or _"packagelist_file"_
  - **Acceptable values:** _"photon:1.0"_, _"photon:2.0"_, _"photon:3.0"_, _"photon:4.0"_, _"photon:latest"_ etc.
  - **Default value:** _"photon:latest"_

  Example:
  ```json
  {
    "photon_docker_image": "photon:4.0"
  }
  ```

For reference, look at [sample_ks.cfg](../sample_ks/sample_ks.cfg) file
