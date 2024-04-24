#!/bin/bash

#/*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */

set -o errexit -o nounset +h -x

#SCRIPT_PATH="$(dirname $(realpath -s "$0"))"

BUILDROOT="$1"
ROOT_PARTITION_PATH="$2"
BOOT_PARTITION_PATH="$3"

# remove trailing '/' if present
BOOT_DIR="$(echo "$4" | sed 's/\/$//')"

USER_CFG_FN="$5"

# Install grub2.
PARTUUID="$(blkid -s PARTUUID -o value "$ROOT_PARTITION_PATH")"
BOOT_UUID="$(blkid -s UUID -o value "${BOOT_PARTITION_PATH}")"

# linux-esx tries to mount rootfs even before nvme got initialized.
# rootwait fixes this issue
EXTRA_PARAMS=""
if [[ ${ROOT_PARTITION_PATH} = *"nvme"* ]]; then
  EXTRA_PARAMS=rootwait
fi

if [ -n "$PARTUUID" ]; then
  ROOT_PARTITION_PATH="PARTUUID=${PARTUUID}"
fi

# For CVE-2021-3981, be explicit here
old_umask=$(umask)
umask 077

cp ${USER_CFG_FN} ${BUILDROOT}/boot/user.cfg || exit 1

cat > ${BUILDROOT}/boot/grub2/grub.cfg << EOF
# Begin /boot/grub2/grub.cfg

# Genereated by Photon Installer
# DO NOT OVERWRITE THIS FILE USING 'grub2-mkconfig'
# UNLESS YOU ARE ABSOULUTELY SURE

set default=0
set timeout=5
search -n -u ${BOOT_UUID} -s
loadfont ascii

insmod gfxterm
insmod vbe
insmod tga
insmod png
insmod ext2
insmod part_gpt

set gfxmode="640x480"
gfxpayload=keep

terminal_output gfxterm

set theme=${BOOT_DIR}/grub2/themes/photon/theme.txt

load_env -f ${BOOT_DIR}/photon.cfg

if [ -f ${BOOT_DIR}/user.cfg ]; then
  load_env -f ${BOOT_DIR}/user.cfg
fi

if [ -f ${BOOT_DIR}/systemd.cfg ]; then
  load_env -f ${BOOT_DIR}/systemd.cfg
else
  set systemd_cmdline=net.ifnames=0
fi

set rootpartition=${ROOT_PARTITION_PATH}

menuentry "Photon" {
  linux ${BOOT_DIR}/\$photon_linux root=\$rootpartition \$photon_cmdline \$systemd_cmdline \$user_cmdline ${EXTRA_PARAMS}

  if [ -f ${BOOT_DIR}/\$photon_initrd ]; then
    initrd ${BOOT_DIR}/\$photon_initrd
  fi
}

# End /boot/grub2/grub.cfg
EOF

umask ${old_umask}
