# -*- coding: utf-8 -*-
"""
Created on Tue Jan  8 23:01:10 2019

Goofy kinda-partially-declarative file handling.

It makes things easier to be able just assign a values in order to lessen
the file-level IO done by the GUI layer. Because a lot of the format is
unknown it would be hard to just use something like Construct.

On the to-do list: make everything less ugly. Because oh boy, some of it is.

@author: rmn
"""

from collections import namedtuple
import struct
from os import SEEK_CUR


Int = struct.Struct('>I')


class HasInPlaceTables:  # TODO: move at() here? also follow_chain()?
    """
    Mixin class
    Keeps track of in place tables and maintains them by adjusting their
    start offset whenever data is inserted earlier in the file.
    """
    def __init__(self):
        self.__tables = []

    def inplace_table(self, start_offset, length, struct):
        new = _InPlaceTable(self, start_offset, length, struct)
        self.__tables.append(new)
        return new

    def inplace_struct(self, start_offset, struct, names=None):
        new = _InPlaceStruct(self, start_offset, struct, names)
        self.__tables.append(new)
        return new

    def update_table_offsets(self, location, amount):
        for table in self.__tables:
            if table.start_offset >= location:
                table.start_offset += amount

    def remove_inplace_table(self, table):
        self.__tables.remove(table)
        del table


# TODO: make everything less ugly
def preserve_pos(f):
    """
    Decorator to make a function preserve the prior file cursor position
    """
    def decorated(self, *args, **kw):
        pos = self.f.tell()
        ret = f(self, *args, **kw)
        self.f.seek(pos)
        return ret
    return decorated


# TODO: rewrite to allow chain links to be names, passed as strings?
@preserve_pos
def follow_chain(self, chain):
    if not hasattr(chain, '__len__'):
        return chain
    self.seek(0)
    for offset in chain:
        self.seek(offset, SEEK_CUR)
        self.seek(Int.unpack(self.read(4))[0] + self.header_size)
    return self.tell()


def at(offset, fmt='I'):
    """
    Function to make an instance property that reads from the underlying file
    on get and writes to the file on set.

    TODO: use instance-level descriptors instead
    """
    @preserve_pos
    def getter(self):
        loc = follow_chain(self, offset)
        self.seek(loc)
        return struct.unpack('>'+fmt, self.read(4))[0]

    @preserve_pos
    def setter(self, value):
        loc = follow_chain(self, offset)
        self.seek(loc)
        self.write(struct.pack('>'+fmt, value))
    return property(getter, setter)


class _InPlaceTable:
    """
    Index by position in the table. [key, subkey] indexing can be used to
    index into the struct at that position. subkey can be positional index or
    a string corresponding to an attribute name

    """
    def __init__(self, f, offset, length, struct):
        self.f = f
        self.start_offset = int(offset)
        self.length = int(length)
        self.item_size = struct.size
        self.struct = struct

    def insert_sorted(self, value):
        """for pointer table"""
        for i, val in enumerate(self):
            if val > value:
                break
        self.insert(i, value)

    @preserve_pos
    def append(self, value):
        if not hasattr(value, '__len__'):
            value = (value, )
        self.f.insert(self.get_offset(len(self)-1)+self.item_size,
                      data=self.struct.pack(*value))
        self.length += 1

    @preserve_pos
    def insert(self, key, value):
        key = self._process_key(key)
        self._length_check(key)
        if not hasattr(value, '__len__'):
            value = (value, )
        self.f.insert(self.get_offset(key), data=self.struct.pack(*value))
        self.length += 1

    def delete_by_value(self, value):
        """Delete the first instance of `value`. Used for pointer table."""
        for i, val in enumerate(self):
            if val == value:
                del self[i]
                return
        raise ValueError(f"{value} not found in table")

    def get_offset(self, key):
        return self.start_offset + key*self.item_size

    def _process_key(self, key, allow_subkey=False):
        try:
            key, subkey = key
        except TypeError:
            subkey = None
        if key < 0:
            key = len(self) + key
        self._length_check(key)
        if not allow_subkey:
            return key
        return key, subkey

    def _length_check(self, key):
        if key > self.length - 1 or key < 0:
            raise IndexError(f"Index out of range: {key}")

    @preserve_pos
    def __getitem__(self, key):
        key, subkey = self._process_key(key, True)
        self.f.seek(self.get_offset(key))
        val = self.struct.unpack(self.f.read(self.item_size))
        if subkey is not None:
            try:
                return val[subkey]
            except TypeError:
                return getattr(val, subkey)
        return val[0] if len(val) == 1 else val

    @preserve_pos
    def __setitem__(self, key, value):
        key, subkey = self._process_key(key, True)
        if not hasattr(value, '__len__'):
            value = (value, )
        if subkey is not None:
            old_value = self[key]
            try:
                subkey = list(old_value._asdict().keys()).index(subkey)
            except (AttributeError, ValueError):
                pass
            before = tuple(old_value[:subkey])
            try:
                after = tuple(old_value[subkey+1:])
            except KeyError:
                after = ()
            value = before + value + after
        self.f.seek(self.get_offset(key))
        self.f.write(self.struct.pack(*value))

    # TODO: fix argument out of range error
    def __delitem__(self, key):
        """use with care: does not update pointers"""

        print(hex(self.start_offset))
        pos = self.f.tell()
        self.f.seek(0x420c)
        print(hex(Int.unpack(self.f.read(4))[0]))
        self.f.seek(pos)


        print(hex(self.start_offset))
        key = self._process_key(key)
        print(hex(self.get_offset(key)))
        self.f.insert(self.get_offset(key), amount=-self.item_size)
        self.length -= 1


        print(hex(self.start_offset))
        pos = self.f.tell()
        self.f.seek(0x420c)
        print(hex(Int.unpack(self.f.read(4))[0]))
        self.f.seek(pos)

    def __str__(self):
        return '[' + ', '.join(str(val) for val in self) + ']'

    def __repr__(self):
        return (self.__class__.__name__ + ' at ' + hex(self.start_offset) +
                ' of ' + str(self.f) + ':\n' + str(self))

    def __len__(self):
        return self.length

    @property
    def end_offset(self):
        return self.start_offset + len(self)*self.item_size


class _InPlaceStruct:
    __slots__ = ('f', 'start_offset', 'struct', 'names')

    def __init__(self, f, offset, struct, names=None):
        object.__setattr__(self, 'f', f)
        object.__setattr__(self, 'start_offset', int(offset))
        object.__setattr__(self, 'struct', struct)
        object.__setattr__(self, 'names', names)

    @preserve_pos
    def __getitem__(self, key):
        self.f.seek(self.start_offset)
        return self.struct.unpack(self.f.read(self.struct.size))[key]

    @preserve_pos
    def __setitem__(self, key, value):
        vals = list(self[:])
        vals[key] = value
        self.f.seek(self.start_offset)
        self.f.write(self.struct.pack(*vals))

    # get and set attr are for use with NamedStruct
    @preserve_pos
    def __getattr__(self, name):
        self.f.seek(self.start_offset)
        return getattr(self.struct.unpack(self.f.read(self.struct.size)), name)

    def __setattr__(self, name, value):
        if name in self.__slots__:
            return object.__setattr__(self, name, value)
        else:
            key = self.struct.ntuple._fields.index(name)
            self[key] = value

    def get_relative_offset(self, index):
        try:
            fmt = self.struct.format.decode('ascii')
        # Some Python versions return str rather than bytes
        except AttributeError:
            fmt = self.struct.format
        for c in '@-<>!':
            fmt = fmt.replace(c, '')
        return struct.calcsize(fmt[:index])

    def get_offset(self, index):
        return self.start_offset + self.get_relative_offset(index)

    def __del__(self):
        try:
            self.f.remove_inplace_table(self)
        except ValueError:
            pass

    @preserve_pos
    def raw(self, index):
        try:
            fmt = self.struct.format.decode('ascii')
        # Some Python versions return str rather than bytes
        except AttributeError:
            fmt = self.struct.format
        for c in '@-<>!':
            fmt = fmt.replace(c, '')
        self.f.seek(self.get_offset(index))
        return self.f.read(struct.calcsize(fmt[index]))


# this one doesn't fit in with the rest really, but it gets used in
# conjunction with in-place tables for the subaction table and probably
# will be used for some extended-dat stuff later
class NamedStruct (struct.Struct):
    def __init__(self, fmt, name, fields):
        super().__init__(fmt)
        self.ntuple = namedtuple(name, fields)
        for c in '@-<>!':
            fmt = fmt.replace(c, '')
        if len(self.ntuple._fields) != len(fmt):
            raise ValueError("Length of struct does not match number of field "
                             "names")

    def pack(self, *args, **kw):
        return super().pack(*self.ntuple(*args, **kw))

    def unpack(self, bytes_):
        return self.ntuple(*super().unpack(bytes_))
