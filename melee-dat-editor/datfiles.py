# -*- coding: utf-8 -*-
"""
Created on Tue Oct  9 11:43:43 2018

@author: rmn
"""

from os import SEEK_CUR
import struct
from tempfile import TemporaryFile

import attributes
from inplace_tables import (HasInPlaceTables, preserve_pos, follow_chain, at,
                            NamedStruct)
import script


Int = struct.Struct('>I')


class BaseDatFile (HasInPlaceTables):
    """Parent to all HAL dat file types"""

    header_size = 0x20

    # header values. These are magical and will read from the file whenever
    # accessed, and will write to the file whenever modified.
    file_size = at(0)
    data_size = at(4)
    n_pointers = at(8)
    root_node_count = at(0xC)
    ref_node_count = at(0x10)

    @property
    def index_offset(self):
        """
        'index' pointed to by the root node
        """
        return follow_chain(self, (4, 4*self.n_pointers))

    def __init__(self, fname, mode='r+b', copy=True):
        super().__init__()
        if copy:
            with open(fname, 'rb') as file:
                self.f = TemporaryFile()
                self.f.write(file.read())
                self.f.seek(0)
        else:
            self.f = open(fname, mode)
        self.pointer_table = self.inplace_table(
                self.data_size+self.header_size,
                self.n_pointers,
                Int)
        Node = NamedStruct('>II', 'Node', 'pointer str_pointer')
        self.root_nodes = self.inplace_table(
                self.header_size + self.data_size + 4*self.n_pointers,
                self.root_node_count,
                Node)
        self.ref_nodes = self.inplace_table(
                self.root_nodes.end_offset,
                self.ref_node_count,
                Node)

    def pointer(self, offset):
        return offset + self.header_size

    def seek_pointer(self, offset):
        return self.seek(self.pointer(offset))

    @preserve_pos
    def peek(self, amount):
        return self.read(amount)

    def __getattr__(self, name):
        # delegate to the internal file object
        return getattr(self.f, name)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.f.close()

    def delete_pointer(self, pointer_value):
        self.pointer_table.delete_by_value(pointer_value)
        self.n_pointers -= 1

    def add_pointer(self, pointer_value):
        self.pointer_table.insert_sorted(pointer_value)
        self.n_pointers += 1

    @preserve_pos
    def adjust_pointers(self, location, amount):
        for i, p in enumerate(self.pointer_table):
            if p + self.header_size >= location:
                self.pointer_table[i] += amount
            self.seek(p + self.header_size)
            val = Int.unpack(self.read(4))[0]
            if val + self.header_size >= location:
                self.seek(-4, SEEK_CUR)
                self.write(Int.pack(val + amount))
        for table in (self.root_nodes, self.ref_nodes):
            for i, node in enumerate(table):
                if node[0] > location:
                    table[i, 0] += amount

    @preserve_pos
    def insert(self, location, amount=None, data=None):
        if amount is not None:
            if data is not None:
                raise ValueError("Received both an amount and a value")
            else:
                data = b'\x00'*amount
        else:
            amount = len(data)
        self.adjust_pointers(location, amount)

        self.seek(0)
        before = self.read(location)
        if amount < 0:
            self.seek(-amount, SEEK_CUR)
        after = self.read()
        data = before + data + after
        self.seek(0)
        self.truncate()
        self.write(data)
        self.file_size += amount
        self.update_table_offsets(location, amount)
        if location <= self.data_size + self.header_size:
            self.data_size += amount

    @preserve_pos
    def save(self, fname):
        self.seek(0)
        with open(fname, 'wb') as f:
            f.write(self.read())

    def read_string(self, strip_terminator=False):
        s = b''
        while True:
            c = self.read(1)
            s += c
            if c == b'\x00' or not c:
                break
        if strip_terminator:
            s = s.replace(b'\x00', b'')
        return s.decode('ascii')

    def read_int(self):
        return Int.unpack(self.read(4))[0]

    @preserve_pos
    def title(self, root_node=0):
        self.seek(self.ref_nodes.end_offset
                  + self.root_nodes[root_node].str_pointer
                  )
        return self.read_string(strip_terminator=True)


class MovesetDatFile (BaseDatFile):

    dat_kind = 'default'  # will be used to differentiate DatEx files

    INDEX_LENGTH = 0x18
    SUBACTION_DIVIDER = 0x155

    SubactionTableEntry = NamedStruct('>IIIIII', 'SubactionTableEntry', [
                                        'name_pointer',
                                        'animation_offset',
                                        'animation_filesize',
                                        'script_pointer',
                                        'flags',
                                        'empty_'
                                        ])

    Hurtbox = NamedStruct('>IIIfffffff', 'Hurtbox', [
                                'bone',
                                'unk_int1',
                                'unk_int2',
                                'x1',
                                'y1',
                                'z1',
                                'x2',
                                'y2',
                                'z2',
                                'scale'
                                ])

    def __init__(self, *args):
        super().__init__(*args)
        self.index = self.inplace_table(
                self.pointer(self.root_nodes[0].pointer),
                self.INDEX_LENGTH,
                Int
                )

        self.subaction_table = self.inplace_table(
                self.pointer(self.index[3]),
                (self.index[5] - self.index[3])/self.SubactionTableEntry.size,
                self.SubactionTableEntry
                )

        self.seek(self.pointer(self.index[7]))
        self.seek(self.pointer(self.read_int()))
        self.seek(4, SEEK_CUR)
        subaction_table_end = self.pointer(self.read_int())
        L = subaction_table_end - self.pointer(self.index[5])
        self.nonlocal_subaction_table = self.inplace_table(
                self.pointer(self.index[5]),
                L/self.SubactionTableEntry.size,
                self.SubactionTableEntry
                )

        names, fmt = attributes.common_table(self.dat_kind)
        self.common_attributes_table = self.inplace_struct(
                self.pointer(self.index[0]),
                struct.Struct(fmt),
                names=names
                )

        names, fmt = attributes.unique_table(self.char_short_name())
        self.unique_attributes_table = self.inplace_struct(
                self.pointer(self.index[1]),
                struct.Struct(fmt),
                names=names
                )

        self.hurtbox_header = self.inplace_struct(
                self.pointer(self.index[12]),
                NamedStruct('>II', 'HurtboxHeader',
                            ['n_hurtboxes', 'hurtbox_table_pointer']
                            )
                )

        self.hurtbox_table = self.inplace_table(
                self.pointer(self.hurtbox_header.hurtbox_table_pointer),
                self.hurtbox_header.n_hurtboxes,
                self.Hurtbox
                )

        self.ledge_grab_data = self.inplace_struct(
                self.pointer(self.index[17]),
                struct.Struct('>IIIIfff'),
                names=['Unknown', 'Unknown', 'Unknown', 'Unknown',
                       'Horizontal Scale', 'Vertical Offset', 'Vertical Scale']
                )

    def append_subaction(self):
        insert_offset = self.subaction_table.end_offset
        self.subaction_table.append([*self.subaction_table[0x3e]])  # hardcoded for now, don't use this
        self.pointer_table.insert_sorted(insert_offset-self.header_size)
        self.pointer_table.insert_sorted(insert_offset+0xC-self.header_size)
        self.n_pointers += 2
        return len(self.subaction_table)

    def get_subaction(self, subaction_number):
        """Locate the given subaction, whether it is in the main table or the
        'nonlocal animations' table"""
        L = len(self.subaction_table)
        if subaction_number < self.SUBACTION_DIVIDER:
            if subaction_number < L:
                return self.subaction_table[subaction_number]
            else:
                raise ValueError(f'Subaction {subaction_number} does not '
                                 f'exist (local subaction table range is '
                                 f'length is 0-{L-1})'
                                 )
        else:
            return self.nonlocal_subaction_table[subaction_number - self.SUBACTION_DIVIDER]

    def subaction_short_name(self, subaction_number):
        s = self.subaction_name(subaction_number)
        if not s:
            return ''
        return s[(s.find('ACTION')+7):s.find('_figatree')]

    def subaction_name(self, subaction_number):
        self.seek_pointer(self.get_subaction(subaction_number).name_pointer)
        return self.read_string()[:-1]

    def subaction_script(self, subaction_number):
        return self.script_at(self.pointer(
                self.get_subaction(subaction_number).script_pointer))

    def iter_subactions(self):
        for i in range(self.SUBACTION_DIVIDER
                       + len(self.nonlocal_subaction_table)):
            try:
                yield i, self.get_subaction(i)
            except ValueError:
                pass

    def script_at(self, start_offset):
        self.seek(start_offset)
        return script.read_script(self, True)

    def replace_subaction_script(self, subaction_number, new_script):
        start_offset = self.pointer(
                self.get_subaction(subaction_number).script_pointer)
        self.replace_script_at(start_offset, new_script)

    def replace_script_at(self, start_offset, new_script):
        old_script = self.script_at(start_offset)
        end_offset = self.tell()
        self.insert(end_offset,
                    script.script_length(new_script)
                    - script.script_length(old_script)
                    )
        self.seek(start_offset)
        for ev in new_script:
            self.write(bytes(ev))
        # update pointer table for any subaction calls or gotos
        for p in script.pointer_offsets(old_script, start_offset):
            self.delete_pointer(p - self.header_size)
        for p in script.pointer_offsets(new_script, start_offset):
            self.add_pointer(p - self.header_size)

    def find_subroutines(self, max_recursion_depth=5):
        """
        Finds subroutine and goto events and returns a list of the locations
        they jump to.

        Recursively searches for nested calls, up to `max_recursion_depth`
        layers deep.
        """
        def check_and_append(pointer_list):
            changed = False
            for p in pointer_list:
                self.seek(p)
                offset = self.pointer(Int.unpack(self.read(4))[0])
                if offset not in subroutine_locations:
                    subroutine_locations.append(offset)
                    changed = True
            return changed

        subroutine_locations = []
        for i, entry in enumerate(self.subaction_table):
            pointer_list = script.pointer_offsets(
                    self.subaction_script(i),
                    self.pointer(entry.script_pointer)
                    )
            check_and_append(pointer_list)
        for _ in range(max_recursion_depth):
            for script_offset in subroutine_locations:
                pointer_list = script.pointer_offsets(
                        self.script_at(script_offset),
                        script_offset
                        )
            if not check_and_append(pointer_list):
                break
        return sorted(subroutine_locations)

    def char_short_name(self):
        return self.title().replace('ftData', '')
