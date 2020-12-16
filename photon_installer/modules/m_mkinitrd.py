import os
import commons

install_phase = commons.POST_INSTALL
enabled = True

def execute(installer):
    ''' If we are building cloud-image/ova, we need to generic initrd '''
    if os.environ.get('REGENERATE_INITRD', '') == 'TRUE':
        installer.logger.info('--- Regenerating initrd ---')
        installer.cmd.run_in_chroot(installer.photon_root, 'mkinitrd -q --no-host-only')
