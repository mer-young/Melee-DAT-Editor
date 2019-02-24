# -*- coding: utf-8 -*-
"""
Created on Tue Oct  9 11:43:43 2018

@author: rmn
"""

from collections import namedtuple
from os import SEEK_CUR
import struct
from tempfile import TemporaryFile

import attributes
from inplace_tables import (HasInPlaceTables, preserve_pos, follow_chain, at,
                            NamedStruct)
import script


Int = struct.Struct('>I')

ALIGN_PADDING = 0xDEADBEEF

def moveset_datfile(fname, mode='r+b', copy=True):
    new = MovesetDatFile(fname, mode, copy)
    if new.char_short_name() == 'Kirby':
        new.close()
        new = MovesetDatFile_Kirby(fname, mode, copy)
    return new


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
        self.aligned_offsets = []
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
            if not self.pointer_table.start_offset < location < self.pointer_table.end_offset:
                # this "am I in the pointer table" check is here to prevent
                # a bug where __delitem__ on the pointer table would
                # decrement the pointer in the data section by 4 as it was
                # removed from the pointer list
                self.seek(p + self.header_size)
                val = Int.unpack(self.read(4))[0]
                if val + self.header_size >= location:
                    self.seek(-4, SEEK_CUR)
                    self.write(Int.pack(val + amount))
        for table in (self.root_nodes, self.ref_nodes):
            for i, node in enumerate(table):
                if node[0] > location:
                    table[i, 0] += amount

#    def next_pointer(self, location):
#        """
#        Returns the next offset greater than `location` that is a pointer, or
#        None if no greater pointer is found.
#        Does not assume the pointer table is sorted in strictly ascending
#        order, because with hand-edited dat files it may not be.
#        """
#        found = None
#        for p in self.pointer_table:
#            if p > location and (found is None or p < found):
#                found = p
#        return found

    @preserve_pos
    def next_target(self, location):
        """Returns the next offset greater than `location` that is the target
        of a pointer. Returns a raw file offset, not a data section offset."""
        found = None
        for p in self.pointer_table:
            self.seek(self.pointer(p))
            val = self.pointer(self.read_int())
            if val > location and (found is None or val < found):
                found = val
        return found

    @preserve_pos
    def insert(self, location, amount=None, data=None):
        if amount is not None:
            if data is not None:
                raise ValueError("Received both an amount and a value")
            else:
                data = b'\x00'*amount
        else:
            amount = len(data)
        if amount == 0:
            return
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
        self.update_aligned_offsets(location, amount)

    def set_offset_aligned(self, offset, alignment):
        self.aligned_offsets.append((offset, alignment))
        self.aligned_offsets.sort(key=lambda entry: entry[0])

    def update_aligned_offsets(self, location, amount):
#        print([(hex(a), hex(b)) for a, b in self.aligned_offsets])
        for i, (offset, alignment) in enumerate(self.aligned_offsets):
            if offset >= location:
                self.aligned_offsets[i] = (offset+amount, alignment)
        for i, (offset, alignment) in enumerate(self.aligned_offsets):
            if offset-amount >= location:
                self.seek(location)
                padding_start = None
                for lookbehind in range(4, location, 4):
                    self.seek(offset-lookbehind)
#                    print(hex(self.tell()), lookbehind)
                    checked_value = self.read_int()
#                    print(hex(checked_value))
                    if checked_value != ALIGN_PADDING:
                        padding_start = self.tell()
#                        print(f'padding starts at {hex(padding_start)}')
                        break
                required_padding_amount = alignment - (padding_start % alignment)
                if required_padding_amount == alignment:
                    required_padding_amount = 0
                prev_padding_amount = offset - padding_start
#                print(required_padding_amount, prev_padding_amount)
                padding_delta = required_padding_amount - prev_padding_amount
#                prev_padding_amount = offset - padding_start
#                padding_delta = padding_amount - prev_padding_amount
#                print(padding_amount, prev_padding_amount, padding_delta)
#                if padding_delta:
#                    print(f'inserting {padding_delta} at {offset}')
#                    self.aligned_offsets[i] = (offset+padding_delta, alignment)
#                    padding_to_insert = Int.pack(ALIGN_PADDING)*(padding_delta//4)
#                    self.insert(padding_start, data=padding_to_insert)

#                self.aligned_offsets[i] = (offset+amount+padding_delta, alignment)
#                for i_, (o, a) in enumerate(self.aligned_offsets):
#                    if o >= offset:
#                        self.aligned_offsets[i_] = (o+padding_delta+amount, a)
#                print(f'inserting {hex(padding_delta)} bytes of padding at {hex(offset+amount)})')
                if padding_delta > 0:
                    padding_data = Int.pack(ALIGN_PADDING)*(padding_delta//4)
                    self.insert(padding_start, data=padding_data)
                else:
                    self.insert(padding_start, amount=padding_delta)


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

    def __init__(self, fname, mode='r+b', copy=True):
        super().__init__(fname, mode, copy)
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

        self.articles = []
        article_list_start = self.index[18]
        print('creating articles')
        if article_list_start:
            article_info_list = attributes.article_info(self.char_short_name())
            for i, article_info in enumerate(article_info_list):
                try:
                    name = article_info['name']
                except IndexError:
                    name = 'UNKNOWN'
                if name.lower != '(empty)':
                    self.seek(self.pointer(article_list_start))
                    self.seek(4*i, SEEK_CUR)
                    article_offset = self.pointer(self.read_int())
                    self.articles.append(self.Article(self, article_offset, article_info, name))

        self.jobjdesc_set_textures_aligned(self.pointer(self.index[23]))

        self.seek(0)

    def jobjdesc_set_textures_aligned(self, jobjdesc_offset, debug_print=False):
        """
        Walk JObj to find tetures and set them as 32-byte aligned.
        Not saving hierarchy info about any of these, need to write
        a more in depth object oriented system for JObj, DObj, etc
        """
        root_jobj = self.inplace_struct(jobjdesc_offset, JObjDesc)
        jobj_list = [root_jobj]
        dobj_list = []
        mobj_list = []
        tobj_list = []
        imageheader_list = []
        image_offsets = []
        for jobj in jobj_list:
            # This adds to the list as it goes, processing in FIFO order
            if jobj.next_sibling_pointer:
                offset = self.pointer(jobj.next_sibling_pointer)
                if not any(j.start_offset == offset for j in jobj_list): # don't add a duplicate
                    jobj_list.append(self.inplace_struct(offset, JObjDesc))
                    if debug_print:
                        if debug_print: print('jobj at', hex(offset))
            if jobj.child_pointer:
                offset = self.pointer(jobj.child_pointer)
                if not any(j.start_offset == offset for j in jobj_list):
                    jobj_list.append(self.inplace_struct(offset, JObjDesc))
                    if debug_print:
                        if debug_print: print('jobj at', hex(offset))
            if jobj.dobj_pointer:
                offset = self.pointer(jobj.dobj_pointer)
                if not any(d.start_offset == offset for d in dobj_list):
                    dobj_list.append(self.inplace_struct(offset, DObjDesc))
                    if debug_print: print('dobj at', hex(offset))
        for dobj in dobj_list:
            if dobj.next_sibling_pointer:
                offset = self.pointer(dobj.next_sibling_pointer)
                if not any(d.start_offset == offset for d in dobj_list):
                    dobj_list.append(self.inplace_struct(offset, DObjDesc))
                    if debug_print: print('dobj at', hex(offset))
            if dobj.mobj_pointer:
                offset = self.pointer(dobj.mobj_pointer)
                if not any(m.start_offset == offset for m in mobj_list):
                    mobj_list.append(self.inplace_struct(offset, MObjDesc))
                    if debug_print: print('mobj at', hex(offset))
        for mobj in mobj_list:
            if mobj.tobj_pointer:
                offset = self.pointer(mobj.tobj_pointer)
                if not any(t.start_offset == offset for t in tobj_list):
                    tobj_list.append(self.inplace_struct(offset, TObjDesc))
                    if debug_print: print('tobj at', hex(offset))
        for tobj in tobj_list:
            if tobj.next_sibling_pointer:
                offset = self.pointer(tobj.next_sibling_pointer)
                if not any(t.start_offset == offset for t in tobj_list):
                    tobj_list.append(self.inplace_struct(offset, TObjDesc))
                    if debug_print: print('tobj at', hex(offset))
            if tobj.image_header_pointer:
                offset = self.pointer(tobj.image_header_pointer)
                if not any(h.start_offset == offset for h in imageheader_list):
                    imageheader_list.append(self.inplace_struct(offset, ImageHeader))
                    if debug_print: print('image header at', hex(offset))
        for ih in imageheader_list:
            if ih.image_data_pointer:
                offset = self.pointer(ih.image_data_pointer)
                if offset not in image_offsets:
                    image_offsets.append(offset)
                    if debug_print: print('image data at', hex(offset))
                    self.set_offset_aligned(offset, 32)
        # cleanup
        for item in jobj_list+dobj_list+mobj_list+tobj_list+imageheader_list:
            self.remove_inplace_table(item)
        return image_offsets

    class Article ():
        ArticleData = NamedStruct('>IIIIII', 'ArticleData', [
                                  'header_pointer',
                                  'attributes_pointer',
                                  'hurtbox_header_pointer',
                                  'variants_pointer',
                                  'jobj_pointer_pointer',
                                  'unk0x14'
                                  ])
        Variant = NamedStruct('>IIII', 'Variant', [
                              'unk0x0',
                              'unk0x4',
                              'un0x8',
                              'script_pointer'
                              ])
        Header = struct.Struct('>' + 'f'*0x21)  # probably not all floats, haven't looked closely
        def __init__(self, parent, offset, info, name=None):
            print('creating article from offset', hex(offset))
            self.f = parent
            self.base_offset = offset
            if name is None:
                self.name = 'UNNAMED ARTICLE'
            else:
                self.name = name
            variant_names = []
            if 'variants' in info.keys():
                variant_names = info['variants']
            self.data = self.f.inplace_struct(self.base_offset, self.ArticleData)
            self.header = self.f.inplace_struct(
                    self.f.pointer(self.data.header_pointer),
                    self.Header)

            # unique attributes table
            self.f.seek(self.f.pointer(self.data.attributes_pointer))
            pos = self.f.tell()
            attribs_size = self.f.next_target(pos) - pos
            if 'attributes' not in info.keys():
                info['attributes'] = dict()
            self.attribute_names, fmt = attributes.table_names_and_fmt(info['attributes'], attribs_size)
            self.attributes = self.f.inplace_struct(pos, struct.Struct(''.join(fmt)))

            # Set up variants to access scripts
            variants_start = self.f.pointer(self.data.variants_pointer)
            variants_end = self.f.next_target(variants_start)
            n_variants = (variants_end - variants_start)
            self.variants = []
            for offset in range(variants_start, variants_end, 0x10):
                self.variants.append(
                        self.f.inplace_struct(offset, self.Variant)
                        )

            self.f.seek(self.f.pointer(self.data.jobj_pointer_pointer))
            root_jobj_pointer = self.f.read_int()
            self.image_offsets = []
            if root_jobj_pointer:
                print('root jobj at', hex(root_jobj_pointer))
                self.image_offsets = self.f.jobjdesc_set_textures_aligned(self.f.pointer(root_jobj_pointer))

        def script(self, variant_number):
            script_offset_raw = self.variants[variant_number].script_pointer
            if not script_offset_raw:
                return None
            script_offset = self.f.pointer(script_offset_raw)
            return self.f.script_at(script_offset, script_type=script.ARTICLE)

        def __str__(self):
            return f'Article "{self.name}" at {hex(self.base_offset)} of {self.parent.title()}'

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

    def script_at(self, start_offset, script_type=script.FIGHTER):
        self.seek(start_offset)
        return script.read_script(self, include_terminator=True, script_type=script_type)

    def replace_subaction_script(self, subaction_number, new_script):
        start_offset = self.pointer(
                self.get_subaction(subaction_number).script_pointer)
        self.replace_script_at(start_offset, new_script)

    def replace_script_at(self, start_offset, new_script):
        old_script = self.script_at(start_offset)
        end_offset = self.tell()
        insert_length = script.script_length(new_script) - script.script_length(old_script)
        if insert_length < 0:
                manual_pointer_delta = insert_length
                for _ in range((-insert_length)//4):
                    self.insert(start_offset+4, amount=-4)
        else:
            manual_pointer_delta = 0
            self.insert(end_offset, insert_length)
        self.seek(start_offset)
        for ev in new_script:
            self.write(bytes(ev))
        # update pointer table for any subaction calls or gotos
        for p in script.pointer_offsets(old_script, start_offset):
            self.delete_pointer(p + manual_pointer_delta - self.header_size)
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


class MovesetDatFile_Kirby (MovesetDatFile):
    # temporary hardcoded fix
    SUBACTION_DIVIDER = 0x1DF


JObjDesc = NamedStruct('>IIIIIfffffffffII',
                       'JObjDesc',
                       ['name_pointer',
                        'flags0x4',
                        'child_pointer',
                        'next_sibling_pointer',
                        'dobj_pointer',  # display object
                        'x_rotation',
                        'y_rotation',
                        'z_rotation',
                        'x_scale',
                        'y_scale',
                        'z_scale',
                        'x_translation',
                        'y_translation',
                        'z_translation',
                        'inverse_matrix_pointer',
                        'robj_pointer'
                        ]
                       )


DObjDesc = NamedStruct('>IIII',
                       'DObjDesc',
                       ['name_pointer',
                        'next_sibling_pointer',
                        'mobj_pointer',  # material object
                        'pobj_pointer'  # polygon object
                        ]
                       )


MObjDesc = NamedStruct('>IIIIII',
                       'MObjDesc',
                       ['name_pointer',
                        'flags0x4',
                        'tobj_pointer',  # texture object
                        'material_pointer',
                        'unk0x10',
                        'unk0x14'
                        ]
                       )


TObjDesc = NamedStruct('>' + 'IIIIfffffffffIIBBHIfIIIII',
                       'TObjDesc',
                       ['name_pointer',
                        'next_sibling_pointer',
                        'GXTexMapID',
                        'GXTexGenSrc',
                        'x_rotation',
                        'y_rotation',
                        'z_rotation',
                        'x_scale',
                        'y_scale',
                        'z_scale',
                        'x_translation',
                        'y_translation',
                        'z_translation',
                        'GXTexWrapMode_t',
                        'GXTexWrapMode_s',
                        'repeat_s',
                        'repeat_t',
                        'padding',
                        'flags0x40',
                        'blending',
                        'GXTexFilter',
                        'image_header_pointer',
                        'palette_header_pointer',
                        'lod_struct_pointer',
                        'tev_struct_pointer'
                        ]
                       )


ImageHeader = NamedStruct('>IHHI',
                          'ImageHeader',
                          ['image_data_pointer',
                           'width',
                           'height',
                           'image_format'
                           ]
                          )

if __name__ == '__main__':
    x = moveset_datfile(r'D:\SSB\melee mods\dat files\1.02\1 - Moveset\Sheik\PlSk.dat')
#    image_offsets = []
#    for a in x.articles:
#        image_offsets.extend(a.image_offsets)
#    for offset in image_offsets:
#        print(hex(offset))
    for offset, align in x.aligned_offsets:
        print(hex(offset))