# POI in a Container

The container needs to be run as root, at least if using `create-image` because we need access to the loop device for creating disk images. Rootless docker does not work.

## Create Image

```
sudo docker buildx build -t photon/installer .
```

To build with local changes in photon-os-installer:
```
sudo docker buildx build --build-context poi-helper=/home/okurth/projects/photon-os-installer -t poi-debug .
```

## Usage

The builder makes heavy use of the kickstart config files, please see https://github.com/vmware/photon-os-installer/blob/master/docs/ks_config.md for documentation. Example config files are in the `examples/` folder.

Configuration files are expected to be in `/workdir`, ideally it is mounted to the current working directory with `-v(pwd):/workdir`.

There are 3 scripts integrated into the container: `create-repo`, `create-image`, and `create-ova`. All of these print out usage information when invoked with `-h`. Example:
```
$ sudo docker run --rm poi-debug create-image -h
[sudo] password for okurth:
Usage: /usr/bin/create-image
          [-c|--config <config-file>] (required)
          [-v|--releasever <version>] (default is 5.0)
          [--repo-paths] (default /repo)
```

## Create a Local Repository

This is not strictly need, but useful to save downloads when creating images repeatedly. This will scan the config file for all needed packages, download with their dependencies and create a repository. The repo is assumed to be mounted to `/repo` in the container.

Usage:
```
Usage: /usr/bin/create-repo
          [-c|--config <config-file>] (required)
          [-v|--releasever <version>] (default is 5.0)
          [--repo-paths] (default )
```

Example:
```
sudo docker run --rm --privileged -v/dev:/dev -v$(pwd):/workdir -v /home/okurth/poi/repo/4.0:/repo poi-debug create-repo -c ami_40_ks.yaml -v 4.0
```

## Create an Image
The container needs to be invoked with the arguments `--privileged -v/dev:/dev` to be able to access the loop device. The repository is expected to be mounted to `/repo`, but can be overridden with `--repo-paths`.

Usage:
```
Usage: /usr/bin/create-image
          [-c|--config <config-file>] (required)
          [-v|--releasever <version>] (default is 5.0)
          [--repo-paths] (default /repo)
```

Examples:
```
sudo docker run --rm --privileged -v/dev:/dev -v$(pwd):/workdir -v /home/okurth/poi/repo/5.0:/repo poi-debug create-image -c minimal_ks.yaml -v 5.0
```

```
sudo docker run --rm --privileged -v/dev:/dev -v$(pwd):/workdir -v /home/okurth/poi/repo/4.0:/repo poi-debug create-image -c ami_40_ks.yaml -v 4.0
```

## Create an OVA

This will create an OVA image, using open-vmdk, see https://github.com/vmware/open-vmdk

Usage:
```
Usage: /usr/bin/create-ova
          [--installer-config <config-file>]
          [--raw-image <image-file>]
          [--ova-name <name>]
          [--ova-config <ova-config-file>] (required)
```

Example:
```
sudo docker run -ti --rm --privileged -v/dev:/dev -v$(pwd):/workdir -v /home/okurth/poi/repo/:/repo poi-debug create-ova --installer-config minimal_ks.yaml --ova-config minimal.yaml --ova-name minimal --raw-image minimal.img
```

## Examples

### Create an AMI image

There are example files in `examples/ami`. Edit the files `ami_ks.yaml`, `packages_ami.json` and others as needed.

Create the repository first (optional):
```
sudo docker run --rm --privileged -v/dev:/dev -v$(pwd):/workdir -v /home/okurth/poi/repo/5.0:/repo poi-debug create-repo -c ami_ks.yaml -v 5.0
```
Then create the image:
```
sudo docker run --rm --privileged -v/dev:/dev -v$(pwd):/workdir -v /home/okurth/poi/repo/5.0:/repo poi-debug create-image -c ami_ks.yaml -v 5.0
```
This will result in a raw disk image, the name of the file is configured in the file `ami_ks.yaml` with `disks.default.filename`.

Note that the raw image may be large (same size as the disk), but most of the space will be unused (zero). This can be simply compressed, for example into a tar file:
```
tar zcf tar zcf photon-ami.tar.gz photon-ami.raw
```

### Create an RPi image

The container image supports multiple architectures (`arm64` and `x86_64`), and can be built with another architecture to build disk images for another architecture:

Note: It also required following packages need to be installed in host for cross platform docker images.
```
qemu binfmt-support qemu-user-static
```
```
sudo docker buildx build --build-context poi-helper=/home/okurth/projects/photon-os-installer --platform=linux/arm64 -t arm64/poi-debug .
```

This can be used to create Photon images for a Raspberry Pi. Example config files are in `examples/rpi`.

Creating the repo and building an image is very similar to building AMI, just use the `arm64` container instead:
```
sudo docker run --rm --privileged -v/dev:/dev -v$(pwd):/workdir -v /home/okurth/poi/repo/5.0:/repo arm64/poi-debug create-image -c rpi_ks.yaml -v 5.0
sudo docker run --rm --privileged -v/dev:/dev -v$(pwd):/workdir -v /home/okurth/poi/repo/5.0:/repo arm64/poi-debug create-image -c rpi_ks.yaml -v 5.0
```

### Create an OVA

Building an OVA involves creating a raw image just like other images, but requires the additional step of converting the raw disk image to a `vmdk` file and package it into an OVA.

Example config files are in `examples/ova`. It includes a config file to create the OVA (`minimal.yaml`), which is used by `ova-compose`, which ships as part of the container. Please see https://github.com/vmware/open-vmdk for documentation.

Example:
```
sudo docker run --rm --privileged -v/dev:/dev -v$(pwd):/workdir -v /home/okurth/poi/repo/5.0:/repo poi-debug create-image -c minimal_ks.yaml -v 5.0
sudo docker run -ti --rm --privileged -v/dev:/dev -v$(pwd):/workdir -v /home/okurth/poi/repo/:/repo poi-debug create-ova --installer-config minimal_ks.yaml --ova-config minimal.yaml --ova-name minimal --raw-image minimal.img
```

### Create an AZURE image

There are example files in `examples/azure`. Edit the files `azure_ks.yaml`, `packages_azure.json` and others as needed.

Create the repository first (optional):
```
sudo docker run --rm --privileged -v/dev:/dev -v$(pwd):/workdir -v ${REPO_PATH}:/repo poi-debug create-repo -c azure_ks.yaml -v 5.0
```
Then create the image:
```
sudo docker run --rm --privileged -v/dev:/dev -v$(pwd):/workdir -v ${REPO_PATH}:/repo poi-debug create-image -c azure_ks.yaml -v 5.0
```
This will result in a raw disk image, the name of the file is configured in the file `azure_ks.yaml` with `disks.default.filename`.

Then create the azure image:
```
sudo docker run -ti --rm --privileged -v/dev:/dev -v$(pwd):/workdir -v ${REPO_PATH}:/repo poi-debug create-azure --raw-image ${RAW_IMAGE}
```
This will result in a azure image with  `azure_ks.yaml` with `disks.default.filename`.vhd.tar.gz.

## Create an ISO Image

Example:

```
sudo docker run --rm --privileged -v/dev:/dev -v$(pwd):/workdir -v /home/okurth/poi/repo/5.0:/repo photon/installer photon-iso-builder -f build-iso -v 5.0 -p packages_minimal.json
```
Or using a config file:
```
function: build-iso

photon_release_version: "5.0"

packageslist_file: packages_minimal.json

initrd_pkgs_list_file: packages_installer_initrd.json

kickstart_path: minimal_ks.yaml

# uncomment for non-interactive install
#boot_cmdline_param: ks=minimal_ks.yaml

repo_paths:
    - /repo
    - /poi

iso_files:
    minimal_ks.yaml: isolinux/
    "https://raw.githubusercontent.com/vmware/photon/5.0/support/image-builder/iso/sample_ks.cfg": isolinux/
    "https://raw.githubusercontent.com/vmware/photon/5.0/EULA.txt": ""
    "https://raw.githubusercontent.com/vmware/photon/5.0/NOTICE-Apachev2": ""
    "https://raw.githubusercontent.com/vmware/photon/5.0/NOTICE-GPL2.0": ""
    "https://github.com/vmware/photon/raw/5.0/support/image-builder/iso/open_source_license.tar.gz": ""

initrd_files:
    minimal_ks.yaml: installer/
    packages_minimal.json: installer/
    "https://raw.githubusercontent.com/vmware/photon/5.0/support/image-builder/iso/sample_ui.cfg": installer/
    "https://raw.githubusercontent.com/vmware/photon/5.0/EULA.txt": installer/
```
Use the config file as (`iso.yaml`) with:
```
sudo docker run --rm --privileged -v/dev:/dev -v$(pwd):/workdir -v /home/okurth/poi/repo/5.0:/repo photon/installer photon-iso-builder -y iso.yaml
```

## create-image-util tool

This is an alternative tool to build images using single command instead of running multiple commands. This tool is a wrapper for all the commands need to trigger in a sequence to build an image on container.

Following are the examples to build an image with different flavor like, ova, ovf, azure, ami and rpi using create-image-util.
Note: This tool does not support for multiple local repo.

Usage:
```
Usage: ./create-image-util
          [--raw-image <image-file>] (required)
          [--config-file <ks-config-file>] (required)
          [--local-repo-path <local-repo-path>] (required)
          [--poi-path <poi-path>] (required)
          [--src-repo-url <src-repo-url>] (optional, use this parameter in case of public repo)
          [--flavor <image-flavor>] (required)
          [--ova-config <ova-config>] (required in case of ova)
          [--ova-name <ova-name>] (required in case of ova)
          [--ovf <set true>] (optional parameter for ova flavor, required in case of building ovf cant use along with --vmdk-only)
          [--mf <set true>] (optional parameter for ova flavor, required in case of building manifest file)
          [--vmdk-only <set true>] (optional parameter for ova flavor, required in case of building vmdk cant use along with --ovf)
          [--arch <arch-type>] (optional parameter for building aarch64 or x86_64 images. accept aarch64 or x86_64 as value by default uses system arch)
          [--releasever <release-version>] (optional parameter by default image build for 5.0)
```

Examples:

create 5.0 azure image using local repo
```
./create-image-util --raw-image photon-azure.raw --config-file azure_ks.yaml --local-repo-path /home/dbx/poi/repo/5.0 --poi-path /home/dbx/workspace/poi_gitlab/photon-os-installer/ --flavor azure
```
create 4.0 azure image using local repo
```
./create-image-util --raw-image photon-azure-4.0.raw --config-file azure_40_ks.yaml --local-repo-path /home/dbx/poi/repo/4.0 --poi-path /home/dbx/workspace/poi_gitlab/photon-os-installer/ --flavor azure --releasever 4.0
```
create 4.0 azure image using remote repo
```
./create-image-util --raw-image photon-azure-4.0.raw --config-file azure_40_ks.yaml --local-repo-path /home/dbx/poi/repo/4.0 --poi-path /home/dbx/workspace/poi_gitlab/photon-os-installer/ --flavor azure --releasever 4.0 --src-repo-url=https://packages.vmware.com/photon/4.0/photon_updates_4.0_x86_64/
```
create 5.0 ova image using local repo
```
./create-image-util --raw-image minimal.img --config-file minimal_ks.yaml --local-repo-path /home/dbx/poi/repo/5.0 --poi-path /home/dbx/workspace/poi_gitlab/photon-os-installer/ --flavor ova --ova-config minimal.yaml --ova-name minimal
```
create 4.0 ova image using local repo
```
./create-image-util --raw-image minimal.img --config-file minimal_ks.yaml --local-repo-path /home/dbx/poi/repo/4.0 --poi-path /home/dbx/workspace/poi_gitlab/photon-os-installer/ --flavor ova --ova-config minimal.yaml --ova-name minimal --releasever 4.0
```
create 4.0 ova image using remote repo
```
./create-image-util --raw-image minimal.img --config-file minimal_ks.yaml --local-repo-path /home/dbx/poi/repo/4.0 --poi-path /home/dbx/workspace/poi_gitlab/photon-os-installer/ --flavor ova --ova-config minimal.yaml --ova-name minimal --releasever 4.0 --src-repo-url=https://packages.vmware.com/photon/4.0/photon_updates_4.0_x86_64/
```
create 5.0 vmdk image using local repo
```
./create-image-util --raw-image minimal.img --config-file minimal_ks.yaml --local-repo-path /home/dbx/poi/repo/5.0 --poi-path /home/dbx/workspace/poi_gitlab/photon-os-installer/ --flavor ova --ova-config minimal.yaml --ova-name minimal --vmdk-only
```
create 4.0 vmdk image using local repo
```
./create-image-util --raw-image minimal.img --config-file minimal_ks.yaml --local-repo-path /home/dbx/poi/repo/4.0 --poi-path /home/dbx/workspace/poi_gitlab/photon-os-installer/ --flavor ova --ova-config minimal.yaml --ova-name minimal --vmdk-only --releasever 4.0
```
create 4.0 vmdk image using remote repo
```
./create-image-util --raw-image minimal.img --config-file minimal_ks.yaml --local-repo-path /home/dbx/poi/repo/4.0 --poi-path /home/dbx/workspace/poi_gitlab/photon-os-installer/ --flavor ova --ova-config minimal.yaml --ova-name minimal --vmdk-only --releasever 4.0 --src-repo-url=https://packages.vmware.com/photon/4.0/photon_updates_4.0_x86_64/
```
create 5.0 ovf and manifest file using local repo
Note: Creating OVF required to first build VMDK from above command line
```
./create-image-util --raw-image minimal.img --config-file minimal_ks.yaml --local-repo-path /home/dbx/poi/repo/5.0 --poi-path /home/dbx/workspace/poi_gitlab/photon-os-installer/ --flavor ova --ova-config minimal.yaml --ova-name minimal --ovf --mf
```
create 4.0 ovf and manifest file using local repo
```
./create-image-util --raw-image minimal.img --config-file minimal_ks.yaml --local-repo-path /home/dbx/poi/repo/4.0 --poi-path /home/dbx/workspace/poi_gitlab/photon-os-installer/ --flavor ova --ova-config minimal.yaml --ova-name minimal --ovf --mf --releasever 4.0
```
create 4.0 ovf and manifest file using remote repo
```
./create-image-util --raw-image minimal.img --config-file minimal_ks.yaml --local-repo-path /home/dbx/poi/repo/4.0 --poi-path /home/dbx/workspace/poi_gitlab/photon-os-installer/ --flavor ova --ova-config minimal.yaml --ova-name minimal --ovf --mf --releasever 4.0 --src-repo-url=https://packages.vmware.com/photon/4.0/photon_updates_4.0_x86_64/
```
create 5.0 ami image using local repo
```
./create-image-util --config-file ami_ks.yaml --local-repo-path /home/dbx/poi/repo/5.0 --poi-path /home/dbx/workspace/poi_gitlab/photon-os-installer/ --flavor ami
```
create 4.0 ami image using local repo
```
./create-image-util --config-file ami_40_ks.yaml --local-repo-path /home/dbx/poi/repo/4.0 --poi-path /home/dbx/workspace/poi_gitlab/photon-os-installer/ --flavor ami --releasever 4.0
```
create 4.0 ami image using remote repo
```
./create-image-util --config-file ami_40_ks.yaml --local-repo-path /home/dbx/poi/repo/4.0/ --poi-path /home/dbx/workspace/poi_gitlab/photon-os-installer/ --flavor ami --releasever 4.0 --src-repo-url=https://packages.vmware.com/photon/4.0/photon_updates_4.0_x86_64/
```
create 5.0 rpi image using local repo
```
./create-image-util --config-file rpi_ks.yaml --local-repo-path /home/dbx/poi/repo/5.0 --poi-path /home/dbx/workspace/poi_gitlab/photon-os-installer/ --flavor rpi --arch aarch64
```
create 4.0 ami image using local repo
```
./create-image-util --config-file rpi_ks.yaml --local-repo-path /home/dbx/poi/repo/4.0 --poi-path /home/dbx/workspace/poi_gitlab/photon-os-installer/ --flavor rpi --arch aarch64 --releasever 4.0
```
create 4.0 ami image using remote repo
```
./create-image-util --config-file rpi_ks.yaml --local-repo-path /home/dbx/poi/repo/4.0 --poi-path /home/dbx/workspace/poi_gitlab/photon-os-installer/ --flavor rpi --arch aarch64 --releasever 4.0 --src-repo-url=https://packages.vmware.com/photon/4.0/photon_updates_4.0_x86_64/
```
