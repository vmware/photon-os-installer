# -*- mode: python ; coding: utf-8 -*-
#/*
# * Copyright © 2020 VMware, Inc.
# * SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
# */
block_cipher = None

added_files = [
	('./photon_installer/*', '.'),
	('./photon_installer/modules/*', 'modules')
       ]

a = Analysis(['photon-installer.py'],
             pathex=['./photon_installer', './photon_installer/modules'],
             binaries=[],
             datas=added_files,
             hiddenimports=['isoInstaller', 'modules'],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          [],
          name='photon-installer',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          upx_exclude=[],
          runtime_tmpdir=None,
          console=True )

