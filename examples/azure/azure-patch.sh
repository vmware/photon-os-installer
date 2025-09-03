#!/bin/bash

cd /lib/systemd/system/multi-user.target.wants/ || exit 1

# Create links in multi-user.target to auto-start these scripts and services.

ln -s ../docker.service docker.service
ln -s ../waagent.service waagent.service
ln -s ../sshd-keygen.service sshd-keygen.service

# Remove ssh host keys and add script to regenerate them at boot time.

rm -f /etc/ssh/ssh_host_*

sudo groupadd docker
sudo groupadd sudo

rm /root/.ssh/authorized_keys

# ssh server config
# Override old values
rm /etc/ssh/sshd_config

cat <<'EOF' >> /etc/ssh/sshd_config
AuthorizedKeysFile .ssh/authorized_keys
PasswordAuthentication no
PermitRootLogin without-password
PermitTunnel no
AllowTcpForwarding yes
X11Forwarding no
ClientAliveInterval 180
ChallengeResponseAuthentication no
UsePAM yes
EOF

# ssh client config
# Override old values

rm /etc/ssh/ssh_config

cat <<'EOF' >> /etc/ssh/ssh_config
Host *
Protocol 2
ForwardAgent no
ForwardX11 no
HostbasedAuthentication no
StrictHostKeyChecking no
Ciphers aes128-ctr,aes192-ctr,aes256-ctr,aes128-cbc,3des-cbc
Tunnel no
ServerAliveInterval 180
EOF

# shellcheck disable=SC2016
sed -i 's/$photon_cmdline $systemd_cmdline/init=\/lib\/systemd\/systemd loglevel=3 ro console=tty1 console=ttyS0,115200n8 earlyprintk=ttyS0,115200 fsck.repair=yes rootdelay=300/' /boot/grub/grub.cfg


# Remove kernel symbols
rm /boot/system.map*

waagent -force -deprovision+user
export HISTSIZE=0
