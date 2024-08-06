#/*
# * Copyright © 2020-2023 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */

import getopt
import json
import os
import re
import subprocess
import shutil
import sys


SYSTEMD_NETWORK_DIR = "etc/systemd/network"
HOSTS_FILE = "etc/hosts"
HOSTNAME_FILE = "etc/hostname"


"""
Useful links:
Netplan: https://netplan.io/reference
systemd-networkd: https://www.freedesktop.org/software/systemd/man/systemd-networkd.service.html
"""

"""
Example config:

    "network":{
        "version": "2",
        "hostname" : "photon-machine",
        "ethernets": {
            "id0":{
                "match":{
                    "name" : "eth0"
                },
                "dhcp4" : false,
                "addresses":[
                    "192.168.2.58/24"
                ],
                "gateway": "192.168.2.254",
                "nameservers":{
                    "addresses" : ["8.8.8.8", "8.8.4.4"],
                    "search" : ["vmware.com", "eng.vmware.com"]
                }
            }
        },
        "vlans": {
            "vlan0": {
                "id": 100,
                "link": "id0",
                "addresses":[
                    "192.168.100.58/24"
                ]
            }
        }
    }
"""


"""
Writes systemd-networkd config file

Input (config) is a simple two level dict:
first level is the section name,
second level is the options.
If an option occurs more than once it's represented as an list with the
individual values, otherwise it's a string or int.

Example:
[Network]
DHCP = yes
DNS = 8.8.8.8
DNS = 8.8.4.4

is represented as:

{'Network' : {'DNS':["8.8.8.8", "8.8.4.4"], 'DHCP':'yes'}}
"""
def write_systemd_config(fout, config):
    for sname, section in config.items():
        fout.write(f"[{sname}]\n")
        for option in section:
            if type(section[option]) in [str, int]:
                fout.write(f"{option}={section[option]}\n")
            elif type(section[option]) == list:
                for val in section[option]:
                    fout.write(f"{option}={val}\n")
        fout.write("\n")


# should we allow '_' ?
def is_valid_hostname(hostname):
    if len(hostname) > 255:
        return False
    allowed = re.compile("(?!-)[A-Z\d_-]{1,63}(?<!-)$", re.IGNORECASE)
    return allowed.match(hostname)


def netmask_to_cidr(netmask):
    # param: netmask ip addr (eg: 255.255.255.0)
    # return: equivalent cidr number to given netmask ip (eg: 24)
    return sum([bin(int(x)).count('1') for x in netmask.split('.')])


class NetworkManager:

    IFACE_TYPE_ETHERNET = 0
    IFACE_TYPE_VLAN = 1

    SYSTEMD_NETWORKD_PREFIX = "50-"

    # hard coded values in Photon
    SYSTEMD_NETWORK_UID = 76
    SYSTEMD_NETWORK_GID = 76

    # world has no perms
    SYSTEMD_NETWORK_MODE = 0o660

    def __init__(self, config, root_dir="/"):

        self.root_dir = root_dir
        self.systemd_network_dir = os.path.join(self.root_dir, SYSTEMD_NETWORK_DIR)

        """
        Use new config by default, and if explicitely forced with version
        set to '2'.
        Fall back to legacy if either there is a 'type' field or version
        is forced to '1'.
        """
        if config.get('version') != '2':
            if 'type' in config or config.get('version') == '1':
                config = self._convert_legacy_config(config)

        self.config = config


    # convert legacy config to new one
    def _convert_legacy_config(self, old_config):
        if not 'type' in old_config:
            raise Exception (f"property 'type' must be set for legacy network configuration, or use 'version':'2'")

        config = {'version' : '2'}

        if 'hostname' in old_config:
            config['hostname'] = old_config['hostname']

        type = old_config['type']
        if type == 'dhcp':
            config['ethernets'] = {'dhcp-en' :
                {'match' : {'name' : 'e*'}, 'dhcp4' : True }
            }
        elif type == 'static':
            config['ethernets'] = {'static-en':
                {'match' : {'name' : 'eth0'}}
            }

            if not 'ip_addr' in old_config:
                raise Exception("need 'ip_addr' property for static network configuration")
            address = old_config['ip_addr']

            if 'netmask' in old_config:
                cidr = netmask_to_cidr(old_config['netmask'])
                address = f'{address}/{cidr}'

            if_cfg = config['ethernets']['static-en']

            if_cfg['addresses'] = [address]

            if 'gateway' in old_config:
                if_cfg['gateway'] = old_config['gateway']
            if 'nameserver' in old_config:
                nameserver = old_config['nameserver']
                if_cfg['nameservers'] = {'addresses' : [nameserver]}

        elif type == 'vlan':
            # phys iface same as for type 'dhcp', but 'eth0' instead of 'e*'
            config['ethernets'] = {'dhcp-en' :
                {'match' : {'name' : 'eth0'}, 'dhcp4' : True }
            }

            # '99-dhcp-en.vlan_' + vlan + '.network'
            if not 'vlan_id' in old_config:
                raise Exception("need 'vlan_id' property for VLAN configuration")
            vlan_id = old_config['vlan_id']
            if_id = f'dhcp-en.vlan_{vlan_id}'
            if_name = f'eth0.{vlan_id}'
            config['vlans'] = {if_id :
                {
                    'match' : {'name' : if_name},
                    'dhcp4' : True,
                    'link' : 'dhcp-en',
                    'id' : int(vlan_id)
                }
            }
        else:
            raise Exception (f"unknown network type '{type}")

        return config


    def prepare_filesystem(self):
        os.makedirs(os.path.join(self.root_dir, SYSTEMD_NETWORK_DIR), exist_ok=True)


    # find if if_id is in any VLAN, return list of ids that match
    def _find_vlan_configs(self, if_id):
        vif_ids = []
        if 'vlans' in self.config:
            for vif_id, vif_cfg in self.config['vlans'].items():
                if 'link' in vif_cfg and vif_cfg['link'] == if_id:
                    vif_ids.append(vif_id)

        return vif_ids


    # construct name for VLAN interface from physical iface name and id
    def _get_vlan_iface_name(self, vif_id):
        vif_cfg = self.config['vlans'][vif_id]
        if 'link' in vif_cfg:
            link = vif_cfg['link']
            pif_cfg = self.config['ethernets'][link]
            if not 'name' in pif_cfg['match']:
                raise Exception("physical interface configuration needs a name to set for VLAN")
            if 'id' in vif_cfg:
                name = f"{pif_cfg['match']['name']}.{vif_cfg['id']}"
            else:
                raise Exception("need 'id' property for vlan configuration")
        else:
            raise Exception("need 'link' property for vlan configuration")

        return name


    # type is "network" or "netdev" (maybe "link" in the future)
    def _get_iface_filename(self, if_id, type):
        return os.path.join(self.root_dir,
                            SYSTEMD_NETWORK_DIR,
                            f"{self.SYSTEMD_NETWORKD_PREFIX}{if_id}.{type}")


    # write the "*.network" file for the interface
    def write_network_file(self, if_id, iface_config, type=IFACE_TYPE_ETHERNET):
        sysdict = {}
        name = None

        if type == self.IFACE_TYPE_VLAN:
            name = self._get_vlan_iface_name(if_id)
            sysdict['Match'] = {}
            sysdict['Match']['Name'] = name

        elif type == self.IFACE_TYPE_ETHERNET:
            if 'match' in iface_config:
                sysdict['Match'] = {}
                if 'macaddress' in iface_config['match']:
                    sysdict['Match']['MACAddress'] = iface_config['match']['macaddress']
                if 'name' in iface_config['match']:
                    name = iface_config['match']['name']
                    sysdict['Match']['Name'] = name

        else:
            raise Exception(f"unknown interface type {type}")

        sysdict['Network'] = {}

        if 'dhcp4' in iface_config or 'dhcp6' in iface_config:
            if iface_config.get('dhcp4', False):
                if iface_config.get('dhcp6', False):
                    sysdict['Network']['DHCP'] = 'yes'
                else:
                    sysdict['Network']['DHCP'] = 'ipv4'
            else:
                if iface_config.get('dhcp6', False):
                    sysdict['Network']['DHCP'] = 'ipv6'
                else:
                    sysdict['Network']['DHCP'] = 'no'

        sysdict['Network']['IPv6AcceptRA'] = \
            'yes' if iface_config.get('accept-ra', False) else 'no'

        if 'addresses' in iface_config:
            sysdict['Network']['Address'] = []
            for addr in iface_config['addresses']:
                sysdict['Network']['Address'].append(addr)

        if 'nameservers' in iface_config:
            sysdict['Network']['DNS'] = []
            nss = iface_config['nameservers']
            for entry in nss:
                if entry == 'addresses':
                    for addr in nss['addresses']:
                        sysdict['Network']['DNS'].append(addr)
                elif entry == 'search':
                    domains = ' '.join(nss['search'])
                    sysdict['Network']['Domains'] = domains

        if 'gateway' in iface_config:
            sysdict['Network']['Gateway'] = iface_config['gateway']

        if type == self.IFACE_TYPE_ETHERNET:
            # see if we can find iface id in VLANs
            for vif_id in self._find_vlan_configs(if_id):
                vname = self._get_vlan_iface_name(vif_id)
                sysdict['Network']['VLAN'] = vname

        with open(self._get_iface_filename(if_id, "network"), "w") as f:
            write_systemd_config(f, sysdict)


    # write the "*.netdev" file for the interface
    def write_netdev_file(self, if_id, iface_config, type):
        sysdict = {}

        if type == self.IFACE_TYPE_VLAN:
            name = self._get_vlan_iface_name(if_id)

            sysdict['NetDev'] = {'Name': name, 'Kind':'vlan'}

            if not 'id' in iface_config:
                raise Exception("need 'id' property for vlan configuration")
            id = iface_config['id']
            if not 1 <= id <= 4094:
                raise Exception("'id' must be in range 1..4094")
            sysdict['VLAN'] = {'Id': id}

        with open(self._get_iface_filename(if_id, "netdev"), "w") as f:
            write_systemd_config(f, sysdict)


    # write all network config files
    def write_interfaces(self):
        ethernets = self.config['ethernets']
        for if_id, if_cfg in self.config['ethernets'].items():
            self.write_network_file(if_id, if_cfg)

        if 'vlans' in self.config:
            for if_id, if_cfg in self.config['vlans'].items():
                if if_cfg['link'] not in self.config['ethernets']:
                    raise Exception("'link' property in VLAN config must be one of the ids set in 'ethernets'")

                self.write_network_file(if_id, if_cfg, type=self.IFACE_TYPE_VLAN)
                self.write_netdev_file(if_id, if_cfg, type=self.IFACE_TYPE_VLAN)


    # set the hostname in /etc/hostname and add it to /etc/hosts
    def set_hostname(self):
        if 'hostname' in self.config:
            hostname = self.config['hostname']

            if not is_valid_hostname(hostname):
                raise Exception(f"hostname '{hostname}' is invalid")

            hosts_file = os.path.join(self.root_dir, HOSTS_FILE)
            found = False

            # check if hostname already there:
            if os.path.exists(hosts_file):
                with open(hosts_file, 'r') as fin:
                    for line in fin.readlines():
                        if line.startswith('#'):
                            continue
                        if line.startswith('127.0.0.1') and len(line.split()) > 1:
                            if line.split()[1] == hostname:
                                found = True
                                break

            # append to file:
            if not found:
                with open(hosts_file, 'a') as fout:
                    fout.write(f'\n127.0.0.1 {hostname}\n')

            hostname_file = os.path.join(self.root_dir, HOSTNAME_FILE)
            with open(hostname_file, 'w') as fout:
                fout.write(hostname)


    def exec_cmd(self, cmd):
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, shell=True)
        retval = process.wait()
        if retval != 0:
            return False
        return True


    def restart_networkd(self):
        if self.root_dir != "/":
            return
        if not self.exec_cmd('systemctl restart systemd-networkd'):
            raise Exception('Failed to restart networkd')


    def setup_network(self, do_clean=True):
        if do_clean and os.path.isdir(self.systemd_network_dir):
            for filename in os.listdir(self.systemd_network_dir):
                filepath = os.path.join(self.systemd_network_dir, filename)
                if os.path.isfile(filepath):
                    os.remove(filepath)

        self.prepare_filesystem()
        self.write_interfaces()
        self.set_hostname()

        # we'd have thrown an exception on error:
        return True


    def set_perms(self, uid=SYSTEMD_NETWORK_UID, gid=SYSTEMD_NETWORK_UID, mode=SYSTEMD_NETWORK_MODE):
        try:
            for filename in os.listdir(self.systemd_network_dir):
                filepath = os.path.join(self.systemd_network_dir, filename)
                if os.path.isfile(filepath):
                    os.chmod(filepath, mode)
                    os.chown(filepath, uid, gid)
        except PermissionError:
            # pass if we are debugging as unprivileged user
            pass


def main():
    config_file = None
    dest_dir = "/"
    do_perms = False

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'D:f:p')
    except:
        print ("invalid option")
        sys.exit(2)

    for o, a in opts:
        if o == '-D':
            dest_dir = a
        elif o == '-f':
            config_file = a
        elif o == '-p':
            do_perms = True
        else:
            assert False, "unhandled option 'o'"

    if config_file != None:
        f = open(config_file, 'r')
    else:
        f = sys.stdin

    config = json.load(f)
    if f != sys.stdin:
        f.close()

    nm = NetworkManager(config, dest_dir)
    nm.setup_network()
    if do_perms:
        nm.set_perms()


if __name__ == "__main__":
    main()
