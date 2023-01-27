#!/bin/bash

set -ex

SCRIPT_PATH=$(dirname $(realpath -s $0))
WORKINGDIR=$1
PACKAGES=$2
RPMS_PATH=$3
PHOTON_RELEASE_VER=$4
CUSTOM_PKG_LIST_FILE=$5
PACKAGE_LIST_FILE_BASE_NAME="build_install_options_custom.json"
CUSTOM_PKG_LIST_FILE_BASE_NAME=$(basename "${CUSTOM_PKG_LIST_FILE}")
INITRD=$WORKINGDIR/photon-chroot
LICENSE_TEXT="VMWARE $PHOTON_RELEASE_VER"

mkdir -m 755 -p $INITRD

if ! eval "$(grep -m 1 -w 'BETA LICENSE AGREEMENT' $WORKINGDIR/EULA.txt)"; then
  LICENSE_TEXT+=" BETA"
fi

LICENSE_TEXT+=" LICENSE AGREEMENT"

cat > ${WORKINGDIR}/photon-local.repo <<EOF
[photon-local]
name=VMware Photon Linux
baseurl=file://${RPMS_PATH}
gpgcheck=0
enabled=1
skip_if_unavailable=True
EOF

cat > ${WORKINGDIR}/tdnf.conf <<EOF
[main]
gpgcheck=0
installonly_limit=3
clean_requirements_on_remove=true
repodir=${WORKINGDIR}
EOF

rpmdb_init_cmd="rpm --root ${INITRD} --initdb --dbpath /var/lib/rpm"
echo "${rpmdb_init_cmd}"
if [ "$(rpm -E %{_db_backend})" != "sqlite" ]; then
  rpmdb_init_cmd="docker run --rm -v ${INITRD}:${INITRD} photon:$PHOTON_RELEASE_VER /bin/bash -c \"tdnf install -y rpm && ${rpmdb_init_cmd}\""
fi

if ! eval "${rpmdb_init_cmd}"; then
  echo "ERROR: failed to initialize rpmdb" 1>&2
  exit 1
fi

TDNF_CMD="tdnf install -qy \
          --releasever $PHOTON_RELEASE_VER \
          --installroot $INITRD \
          --rpmverbosity 10 \
          -c ${WORKINGDIR}/tdnf.conf \
          ${PACKAGES}"

echo $TDNF_CMD

$TDNF_CMD || docker run --rm -v $RPMS_PATH:$RPMS_PATH -v $WORKINGDIR:$WORKINGDIR photon:$PHOTON_RELEASE_VER /bin/bash -c "$TDNF_CMD"

#mkdir -p $WORKINGDIR/isolinux
#cp -r ${INITRD}/usr/share/photon-isolinux/* $WORKINGDIR/isolinux/

chroot ${INITRD} /usr/sbin/pwconv
chroot ${INITRD} /usr/sbin/grpconv

chroot ${INITRD} /bin/systemd-machine-id-setup || chroot ${INITRD} date -Ins | md5sum | cut -f1 -d' ' > /etc/machine-id

echo "LANG=en_US.UTF-8" > $INITRD/etc/locale.conf
echo "photon-installer" > $INITRD/etc/hostname

rm -rf ${INITRD}/var/cache/tdnf

# Move entire /boot from initrd to ISO
mv ${INITRD}/boot ${WORKINGDIR}/

mkdir -p $INITRD/installer
cp $SCRIPT_PATH/sample_ui.cfg ${INITRD}/installer
mv ${WORKINGDIR}/EULA.txt ${INITRD}/installer

# TODO: change minimal to custom.json
cat > ${INITRD}/installer/build_install_options_custom.json << EOF
{
    "custom" : {
        "title" : "Photon Custom",
        "packagelist_file" : "${CUSTOM_PKG_LIST_FILE_BASE_NAME}",
        "visible" : false
    }
}
EOF


if [ -f "$CUSTOM_PKG_LIST_FILE" ]; then
  cp ${CUSTOM_PKG_LIST_FILE} ${INITRD}/installer/packages_minimal.json
  cp ${CUSTOM_PKG_LIST_FILE} ${INITRD}/installer
fi

mkfifo ${INITRD}/dev/initctl
mknod ${INITRD}/dev/ram0 b 1 0
mknod ${INITRD}/dev/ram1 b 1 1
mknod ${INITRD}/dev/ram2 b 1 2
mknod ${INITRD}/dev/ram3 b 1 3
mknod ${INITRD}/dev/sda b 8 0

mkdir -p ${INITRD}/etc/systemd/scripts

mkdir -p ${INITRD}/etc/yum.repos.d
cat > ${INITRD}/etc/yum.repos.d/photon-iso.repo << EOF
[photon-iso]
name=VMWare Photon Linux (x86_64)
baseurl=file:///mnt/media/RPMS
gpgkey=file:///etc/pki/rpm-gpg/VMWARE-RPM-GPG-KEY
gpgcheck=1
enabled=1
skip_if_unavailable=True
EOF

#- Step 7 - Create installer script
cat >> ${INITRD}/bin/bootphotoninstaller << EOF
#!/bin/bash
cd /installer
ACTIVE_CONSOLE="\$(< /sys/devices/virtual/tty/console/active)"
install() {
  LANG=en_US.UTF-8 photon-installer -i iso -o $PACKAGE_LIST_FILE_BASE_NAME -e EULA.txt -t "$LICENSE_TEXT" -v $PHOTON_RELEASE_VER && shutdown -r now
}
try_run_installer() {
  if [ "\$ACTIVE_CONSOLE" == "tty0" ]; then
      [ "\$(tty)" == '/dev/tty1' ] && install
  else
      [ "\$(tty)" == "/dev/\$ACTIVE_CONSOLE" ] && install
  fi
}
try_run_installer || exec /bin/bash
EOF

chmod 755 ${INITRD}/bin/bootphotoninstaller

cat >> ${INITRD}/etc/fstab << EOF
# Begin /etc/fstab for a bootable CD

# file system  mount-point  type   options         dump  fsck
#                                                        order
#/dev/EDITME     /            EDITME  defaults        1     1
#/dev/EDITME     swap         swap   pri=1           0     0
proc           /proc        proc   defaults        0     0
sysfs          /sys         sysfs  defaults        0     0
devpts         /dev/pts     devpts gid=4,mode=620  0     0
tmpfs          /dev/shm     tmpfs  defaults        0     0
tmpfs          /run         tmpfs  defaults        0     0
devtmpfs       /dev         devtmpfs mode=0755,nosuid 0   0
# End /etc/fstab
EOF

cat >> ${INITRD}/init << EOF
mount -t proc proc /proc
/lib/systemd/systemd
EOF
chmod 755 ${INITRD}/init

#adding autologin to the root user
# and set TERM=linux for installer
sed -i "s/ExecStart.*/ExecStart=-\/sbin\/agetty --autologin root --noclear %I linux/g" ${INITRD}/lib/systemd/system/getty@.service
sed -i "s/ExecStart.*/ExecStart=-\/sbin\/agetty --autologin root --keep-baud 115200,38400,9600 %I screen/g" ${INITRD}/lib/systemd/system/serial-getty@.service

#- Step 7 - Create installer script
sed -i "s/root:.*/root:x:0:0:root:\/root:\/bin\/bootphotoninstaller/g" ${INITRD}/etc/passwd

mkdir -p ${INITRD}/mnt/photon-root/photon-chroot
rm -rf ${INITRD}/RPMS
rm -rf ${INITRD}/LOGS

find ${INITRD}/usr/lib/ -maxdepth 1 -mindepth 1 -type f | xargs -i sh -c "grep ELF {} >/dev/null 2>&1 && strip {} || :"

rm -rf ${INITRD}/home/*         \
        ${INITRD}/var/lib/rpm*  \
        ${INITRD}/var/lib/.rpm* \
        ${INITRD}/cache         \
        ${INITRD}/boot          \
        ${INITRD}/usr/include   \
        ${INITRD}/usr/sbin/sln  \
        ${INITRD}/usr/bin/iconv \
        ${INITRD}/usr/bin/oldfind       \
        ${INITRD}/usr/bin/localedef     \
        ${INITRD}/usr/bin/sqlite3       \
        ${INITRD}/usr/bin/grub2-*       \
        ${INITRD}/usr/bin/bsdcpio       \
        ${INITRD}/usr/bin/bsdtar        \
        ${INITRD}/usr/bin/networkctl    \
        ${INITRD}/usr/bin/machinectl    \
        ${INITRD}/usr/bin/pkg-config    \
        ${INITRD}/usr/bin/openssl       \
        ${INITRD}/usr/bin/timedatectl   \
        ${INITRD}/usr/bin/localectl     \
        ${INITRD}/usr/bin/systemd-cgls  \
        ${INITRD}/usr/bin/systemd-analyze       \
        ${INITRD}/usr/bin/systemd-nspawn        \
        ${INITRD}/usr/bin/systemd-inhibit       \
        ${INITRD}/usr/bin/systemd-studio-bridge \
        ${INITRD}/usr/lib/python*/lib2to3     \
        ${INITRD}/usr/lib/python*/lib-tk      \
        ${INITRD}/usr/lib/python*/ensurepip   \
        ${INITRD}/usr/lib/python*/distutils   \
        ${INITRD}/usr/lib/python*/pydoc_data  \
        ${INITRD}/usr/lib/python*/idlelib     \
        ${INITRD}/usr/lib/python*/unittest    \
        ${INITRD}/usr/lib/librpmbuild.so*       \
        ${INITRD}/usr/lib/libdb_cxx*            \
        ${INITRD}/usr/lib/libnss_compat*        \
        ${INITRD}/usr/lib/grub/i386-pc/*.module \
        ${INITRD}/usr/lib/grub/x86_64-efi/*.module \
        ${INITRD}/lib64/libmvec*        \
        ${INITRD}/usr/lib64/gconv

find "${INITRD}/usr/sbin" -mindepth 1 -maxdepth 1 -name "grub2*" \
                        ! -name grub2-install -exec rm -rvf {} \;

find "${INITRD}/usr/share" -mindepth 1 -maxdepth 1 \
                        ! -name terminfo \
                        ! -name cracklib \
                        ! -name grub    \
                        ! -name factory \
                        ! -name dbus-1 -exec rm -rvf {} \;

# Set password max days to 99999 (disable aging)
chroot ${INITRD} /bin/bash -c "chage -M 99999 root"

# Generate the initrd
pushd $INITRD
(find . | cpio -o -H newc --quiet | gzip -9) > ${WORKINGDIR}/initrd.img
popd
rm -rf $INITRD ${WORKINGDIR}/packages_installer_initrd.json
