# -*- coding: utf-8 -*-
"""
Created on Thu Dec 13 23:18:39 2018

@author: rmn
"""

import binascii
from io import BytesIO
from math import ceil
import os

import yaml


event_types_fname = os.path.join('data', 'event-types.yml')
custom_fname = os.path.join('data', 'custom-event-types.yml')
event_types = yaml.safe_load(open(event_types_fname, 'r'))

custom_event_types = yaml.safe_load(open(custom_fname, 'r'))

for key, value in event_types.items():
    if key == 'default':
        continue
    event_types[key] = {key: value}
    if key in custom_event_types.keys():
        event_types[key].update(custom_event_types[key])

keys = list(event_types.keys())
keys.remove('default')
lookahead_amount = max(v.bit_length() for v in keys)
del keys


def read_script(file, include_terminator=False):
    """
    Read from a file until reaching the 0x00000000 terminator event. Return a
    list of Event objects for each event read.

    Parameters
    ----------
    file : file-like
        Source file to read from. Must have read() and tell() methods.
    include_terminator : bool (default false)
        If true, the last Event in the list will be an End Of Script
        (terminator) event. If false, it is omitted.
    """
    script = []
    while True:
        ev = Event.from_stream(file)
        if ev is None:
            return script
#        print(ev)
        script.append(ev)
        if not ev:
            return script if include_terminator else script[:-1]
        if ev.code in [0x18, 0x1C]:  # 0x18 = return, 0x1C = goto
            return script


def iter_script(list_of_events, start_offset=0):
    offset = start_offset
    for ev in list_of_events:
        yield ev, offset
        offset += ev.length


def script_length(list_of_events):
    return sum(ev.length for ev in list_of_events)


def pointer_offsets(list_of_events, start_offset):
    pointer_offset_list = []
    for ev, offset in iter_script(list_of_events, start_offset):
        for p_offset in ev.pointers:
            if p_offset is not None and p_offset not in pointer_offset_list:
                pointer_offset_list.append(offset + p_offset)
    return pointer_offset_list


def print_script(list_of_events):
    [print(ev) for ev in list_of_events]


def script_from_bytes(bytes_like, include_terminator=False):
    io = BytesIO(bytes_like)
    return read_script(io, include_terminator)


def script_from_hex_str(hexstr, include_terminator=False):
    return script_from_bytes(binascii.unhexlify(hexstr), include_terminator)


class Event:
    """
    An event, which makes up part of a subaction script.

    Index by field name, i.e. ev['z_offset'] or by position, i.e. ev[6].
    Slice indexing is also supported.

    Parameters
    ----------
    bytestr : bytes
        Data read from the subaction script. ValueError will be raised if
        len(bytestr) is not equal to the byte count for an event with the given
        code. In most cases one of the alternate constructors will be
        preferred, such as Event.from_stream() to automatically read the
        correct number of bytes.

    """

    @property
    def code(self):
        return self._code

    @property
    def name(self):
        """Name of event type"""
        return self._evtype['name']

    @property
    def length(self):
        """Event length in bytes"""
        return self._evtype['length']

    @property
    def fields(self):
        """List of EventField namedtuples (name, bits, type)"""
        return self._evtype['fields']

    def fieldnames(self):
        """Return a list of field names."""
        return [fd['name'] for fd in self.fields]

    def str_values(self):
        """Return a list of strings representing a string value for each field.
        """
        strs = []
        types = [fd['type'] for fd in self.fields]
        for val, tp in zip(self, types):
                if tp == 'h':
                    strs.append(hex(val))
                else:
                    strs.append(val)
        return strs

    def __init__(self, bytestr):
        self._data = self._data = int.from_bytes(bytestr, byteorder='big')
        code, custom_code = self.find_code(bytestr)
        self._code = [code, custom_code]
        self._evtype = self.get_evtype(code, custom_code)

        if len(bytestr) != self.length:
            raise ValueError("Invalid input length for event '{}' (expected {}"
                             " bytes, received {})".format(self.name,
                                                           self.length,
                                                           len(bytestr)))
        self._nbits = self.length*8

        self.pointers = []  # in case of future custom event with more than 1
        p = self._evtype.get('pointer')
        if p is not None:
            try:
                self.pointers.extend(p)
            except TypeError:
                self.pointers.append(p)

    @staticmethod
    def find_code(bytestr):
        # returns code, custom_code
        # where custom_code is the same as base_code if the event is not custom
        data = int.from_bytes(bytestr, byteorder='big')

        base_code = bytestr[0] & 0xFC
        if base_code in custom_event_types.keys():
            for i in range(len(bytestr)*8 - 6):
                try_code = (data >> i)
                if try_code in custom_event_types[base_code].keys():
                    return [base_code, try_code]
        return [base_code, base_code]

    @staticmethod
    def get_evtype(code, custom_code=None):
        if custom_code is None:
            custom_code = code
        try:
            print(code)
            print(code in event_types.keys())
            base = event_types[code]
        except KeyError:  # manually rather than get() because default has no subkeys
            print('default')
            return event_types['default']
        return base[custom_code]

    # alternate constructors
    @classmethod
    def blank(cls, code, custom_code=None):
        """
        Create an Event of the specified type with all fields initialized to
        zeros.

        Parameters:
        -----------
        code : int
            Event code, ranging from 0 to 0xFC

        """
        if custom_code is None:
            custom_code = code
        length = event_types[code][custom_code]['length']
        bytestr = custom_code.to_bytes(ceil(custom_code.bit_length()/8), 'big')
        bytestr += b'\x00' * (length - len(bytestr))
        return cls(bytestr)

    @classmethod
    def from_stream(cls, file):
        """
        Create an Event by reading from the current position in file-like
        object ``file``, which must have a read() method. The number of bytes
        to read is automatically determined.

        """
        # Inefficient, fix later
        pos = file.tell()
        lookahead = file.read(lookahead_amount)
        if not lookahead:
            return None

        length = cls.get_evtype(*cls.find_code(lookahead))['length']
        print(length)
        file.seek(pos)
        bytestr = file.read(length)
        return cls(bytestr)
#        try:
#            return cls(bytestr)
#        except ValueError:
#            raise EOFError("End of file reached at {} after "
#                           " reading '{}'".format(file.tell(), bytestr))

    @classmethod
    def from_hex(cls, hexstr):
        """
        Create an Event from a string of hex digits, such as
        ``'0x2c02080d0578000000000000b4990013078c000b'``. The '0x' prefix may
        be omitted if desired.

        """
        return cls(binascii.unhexlify(hexstr.replace('0x', '')))

    @classmethod
    def from_fields(cls, code, *args, **kwargs):
        """
        Create an Event and initialize each field to the values given.
        Accepts fields in order or by passing the field names (with any spaces
        either omitted or replaced with underscores) as keyword arguments.

        """
        new = cls.blank(code)
        for i, val in enumerate(args):
            new[i] = val
        if kwargs:
            for key, val in kwargs.items():
                new[key] = val
        return new

    def copy(self):
        return self.__class__(bytes(self))

    # indexing
    def _try_fieldname_to_index(self, name):
        """Allow indexing fields by position or by name"""
        def remove_spaces(s):
            return s.lower().replace('-', '').replace(' ', '').replace('_', '')
        if isinstance(name, str):
            try:
                names = [remove_spaces(s) for s in self.fieldnames()]
                return names.index(remove_spaces(name))
            except ValueError:
                raise ValueError("Field '{}' does not exist for "
                                 "event {}".format(name, self.name))
        else:
            return name

    def __setitem__(self, key, val):
        # Slice indexing
        if isinstance(key, slice):
            indices = range(*key.indices(len(self)))
            if len(indices) != len(val):
                raise ValueError("Attempted slice assignment with an unequal "
                                 "number of values")
            for k, v in zip(indices, val):
                self[k] = v
            return
        # list-like and dict-like indexing
        key = self._try_fieldname_to_index(key)

        low, high = self.fields[key]['bits']
        mask = 2**(1+high-low) - 1
        shift = self._nbits - 1 - high
        self._data &= ~(mask << shift)
        self._data |= (min(val, mask) & mask) << (shift)

    def __getitem__(self, key):
        if isinstance(key, slice):
            return [self[k] for k in range(*key.indices(len(self)))]
        key = self._try_fieldname_to_index(key)
        low, high = self.fields[key]['bits']
        mask = 2**(1+high-low) - 1
        return (self._data >> (self._nbits - 1 - high)) & mask

    def __len__(self):
        return len(self.fields)

    def __eq__(self, other):
        if isinstance(other, (bytes, bytearray)):
            return bytes(self) == other
        else:
            return self._data == other

    def __bool__(self):
        return self._data != 0

    def __bytes__(self):
        return self._data.to_bytes(self.length, byteorder='big')

    def __index__(self):
        return self._data

    def __int__(self):
        return int(self._data)

    def __str__(self, offset=None):
        offset_str = '' if offset is None else f'  ({hex(offset)})'
        s = self.name + offset_str + ':\n'
        strs = self.str_values()
        L = [f'  {name}: {s}' for name, s in zip(self.fieldnames(), strs)]
        if not L:
            L = ['  ' + binascii.hexlify(bytes(self)).decode('ascii'), ]
        return s + '\n'.join(L)

    def compact_str(self, offset=None):
        offset_str = '' if offset is None else f'  ({hex(offset)})'
        s = self.name + offset_str + ':\n  '
        strs = self.str_values()
        L = [f'{name}: {s}' for name, s in zip(self.fieldnames(), strs)]
        if not L:
            L = [binascii.hexlify(bytes(self)).decode('ascii'), ]
        return s + ', '.join(L)

    def __repr__(self):
        return f'{self.__class__.__qualname__}({bytes(self)})'
