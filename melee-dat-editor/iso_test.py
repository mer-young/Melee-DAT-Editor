# -*- coding: utf-8 -*-
"""
Created on Sun Dec  9 21:32:17 2018

@author: rmn
"""

from collections import namedtuple
import struct
from io import BytesIO
import os
import re

from test1 import HasInPlaceTables

iso_fname = 'd:/ssb/melee iso/mcm/melee 1.02 testing iso (GALEzz).iso'

Int = struct.Struct('>I')

File = namedtuple('File', 'name, offset, length')
Directory = namedtuple('Directory', 'name, parent_offset, next_offset')
Root = namedtuple('Root', 'n_entries')


def read_string(f, strip_terminator=True):
    s = b''
    while True:
        c = f.read(1)
        s += c
        if c == b'\x00' or not c:
            break
    if strip_terminator:
        s = s.replace(b'\x00', b'')
    return s.decode('ascii')


def read_entry(fst, string_table_offset):
#    print(hex(fst.tell()))
    flag = struct.unpack('>B', fst.read(1))[0]
#    print('flag:', flag)
    fst.seek(-1, os.SEEK_CUR)
    (name_offset, val1, val2) = struct.unpack('>III', fst.read(0xC))

#    print(name_offset)
    name_offset = name_offset & 0xFFFFFF
#    print(name_offset)
    pos = fst.tell()
    fst.seek(name_offset + string_table_offset)
    name = read_string(fst)
    fst.seek(pos)

    if flag:
        return Directory(name, val1, val2)
    else:
        return File(name, val1, val2)


total_size = 0
with open(iso_fname, 'rb') as iso_f:
    iso_f.seek(0x424)
    fst_start_offset = Int.unpack(iso_f.read(4))[0]
    fst_size = Int.unpack(iso_f.read(4))[0]

    iso_f.seek(fst_start_offset)
    fst = BytesIO(iso_f.read(fst_size))

    fst.seek(0x8)
    n_entries = Int.unpack(fst.read(0x4))[0]
    string_table_start = n_entries*0xC
    entries = []
    for i in range(n_entries - 1):
        e = read_entry(fst, string_table_start)
        entries.append(e)
        if isinstance(e, Directory):
            print(f'Directory at i = {i}, pos = {hex(fst.tell())}')
            print('   ', e)
        else:
            print('       ', e)
            total_size += e.length

for e in entries:
    if re.match(r'Pl\w{2}.dat', e.name) and e.name != 'PlCo.dat':
        print(e.name)