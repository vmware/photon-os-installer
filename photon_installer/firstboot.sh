#!/bin/bash
#
# script installed by photon-os-installer
#

SCRIPT_DIR=/etc/firstboot.d

[ -d "${SCRIPT_DIR}" ] || exit 0

for script in "${SCRIPT_DIR}"/*.sh ; do
    if [ -x "${script}" ] ; then
        echo "Running ${script} ..."
        ${script} || echo "${script} failed with $?"
    fi
done

exit 0
