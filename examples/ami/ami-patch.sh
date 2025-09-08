#!/bin/bash

cd /lib/systemd/system/multi-user.target.wants/ || exit 1

ln -s ../docker.service docker.service

echo "127.0.0.1 localhost" >> /etc/hosts

echo "DNS=169.254.169.253" >> /etc/systemd/resolved.conf
echo "Domains=ec2.internal" >> /etc/systemd/network/99-dhcp-en.network

# Add a DHCP section, but comment out the MTU setting that enables
# jumbo frames (9001 byte MTU) on AWS. Users who have the right
# overall setup (eg: who have configured the necessary ICMP rules in
# their security group to handle large MTUs correctly for
# internet-bound traffic) can then choose to enable jumbo frames on
# the system by simply uncommenting this line.
echo -e "\n[DHCP]\n#UseMTU=true" >> /etc/systemd/network/99-dhcp-en.network

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
PubkeyAuthentication yes
PasswordAuthentication no
PermitRootLogin without-password
PermitTunnel no
AllowTcpForwarding yes
X11Forwarding no
ClientAliveInterval 420
UseDNS no
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
ServerAliveInterval 420
EOF

sed -i 's/net.ifnames=0//' /boot/grub/grub.cfg

# shellcheck disable=SC2016
sed -i 's/$photon_cmdline/init=\/lib\/systemd\/systemd loglevel=3 ro console=ttyS0 earlyprintk=ttyS0 nvme_core.io_timeout=4294967295/' /boot/grub/grub.cfg

# Disable loading/unloading of modules
#echo "kernel.modules_disabled = 1" > /etc/sysctl.d/modules_disabled.conf

# Remove kernel symbols
rm -f /boot/System.map*

# Added as a part of rpm db migration from BDB to sqlite
# No harm in cross checking here
if [ -f /var/lib/rpm/Packages ]; then
  if ! rpmdb --rebuilddb; then
    echo "WARNING: Failed rebuild rpmdb" 1>&2
  fi
fi
