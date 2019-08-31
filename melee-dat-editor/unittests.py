# -*- coding: utf-8 -*-
"""
Unit tests for Melee Dat Editor. Incomplete so far but better than nothing;
intend to improve them over time.
"""

import os
import os.path as osp
import unittest
import re

import datfiles


iso_dump_directory = osp.expanduser(r'~/SSB/melee-hacks/iso-dump/root')  # change as needed


class TestVanillaDatLoading (unittest.TestCase):
    def test_load_files(self):
        """
        Test loading each vanilla dat file and make sure no errors occur.
        """
        moveset_dat_re = re.compile(r'Pl[a-zA-z]{2}.dat')
        filenames = filter(lambda fn: moveset_dat_re.match(fn),
                           os.listdir(iso_dump_directory)
                           )
        for fn in filenames:
            if fn in ['PlCo.dat', 'PlMh.dat', 'PlCh.dat', 'PlGk.dat', 'PlSb.dat']:
                # skip unsupported files
                continue
            with self.subTest(file=fn):
                f = datfiles.moveset_datfile(osp.join(iso_dump_directory, fn))


if __name__ == '__main__':
    unittest.main()
