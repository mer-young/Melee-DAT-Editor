# -*- coding: utf-8 -*-
"""
Created on Wed Jan 23 00:31:12 2019

Support for UnclePunch's datfile version of Magus's FSM engine

@author: rmn
"""

import binascii
from io import BytesIO
import struct

from datfiles import BaseDatFile
from widgets import id_combobox


Float = struct.Struct('>f')
Int = struct.Struct('>I')


def read_fsm_table(file):
    fsm_list = []
    while True:
        fsm = FSM.from_stream(file)
        if not fsm:
            return fsm_list
        fsm_list.append(fsm)


def write_fsm_table(file, fsm_list):
    for fsm in fsm_list:
        file.write(bytes(fsm))


def fsm_list_from_bytes(bytes_like):
    io = BytesIO(bytes_like)
    return read_fsm_table(io)


def fsm_list_from_hex_str(hexstr):
    return fsm_list_from_bytes(binascii.unhexlify(hexstr))


class FSM:
    # TODO: write an "unaligned struct" base class for FSM and Event classes

    _byte_length = 8
    _nbits = _byte_length*8

    def __init__(self, bytestr):
        self._data = int.from_bytes(bytestr, byteorder='big')

    @classmethod
    def from_fields(cls, character_ext_id, sub_flag, asid, start_frame, speed):
        new = cls.blank()
        new.character = int(character_ext_id)
        new.asid = int(asid)
        new.start_frame = int(start_frame)
        new.sub_flag = bool(sub_flag)
        new.speed = float(speed)
        return new

    @classmethod
    def blank(cls):
        return cls(b'\x00'*cls._byte_length)

    @classmethod
    def from_stream(cls, file_like):
        return cls(file_like.read(cls._byte_length))

    @classmethod
    def from_hex(cls, hexstr):
        return cls(binascii.unhexlify(hexstr.replace('0x', '')))

    @property
    def character(self):
        return self._get([0, 7])

    @character.setter
    def character(self, val):
        self._set([0, 7], val)

    @property
    def start_frame(self):
        return self._get([8, 15])

    @start_frame.setter
    def start_frame(self, val):
        self._set([8, 15], val)

    @property
    def sub_flag(self):
        return self._get([16, 16])

    @sub_flag.setter
    def sub_flag(self, val):
        self._set([16, 16], val)

    @property
    def asid(self):
        return self._get([20, 31])

    @asid.setter
    def asid(self, val):
        self._set([20, 31], val)

    @property
    def speed(self):
        return Float.unpack(Int.pack(self._get([32, 63])))[0]

    @speed.setter
    def speed(self, val):
        if isinstance(val, int):
            self._set([32, 63], val)  # set raw data
        else:
            self._set([32, 63], Int.unpack(Float.pack(float(val)))[0])

    def _set(self, bits, val):
        low, high = bits
        mask = 2**(1+high-low) - 1
        shift = self._nbits - 1 - high
        self._data &= ~(mask << shift)
        self._data |= (min(val, mask) & mask) << (shift)

    def _get(self, bits):
        low, high = bits
        mask = 2**(1+high-low) - 1
        return (self._data >> (self._nbits - 1 - high)) & mask

    def __bytes__(self):
        return self._data.to_bytes(self._byte_length, byteorder='big')

    def __bool__(self):
        return self._data != 0

    def __index__(self):
        return self._data

    def __str__(self):
        return (f'FSM: character={self.character}, asid={self.asid}, '
                f'frame={self.start_frame}, speed={self.speed}, '
                f'sub_flag={self.sub_flag}')

    def __repr__(self):
        return f'{self.__class__.__qualname__}({bytes(self)})'


class FSMDatFile (BaseDatFile):
    def __init__(self, fname, mode='r+b', copy=True, fixed_size=None):
        super().__init__(fname, mode, copy)

        # True for trophy method (always leave file size the same)
        # False for FSM.dat method
        self._fixed_size = fixed_size
        if self._fixed_size is None:
            if self.title() == 'FSMDataStandalone':
                self._fixed_size = False
            elif self.title() == 'FSMDataTrophy':
                self._fixed_size = True
            else:
                raise ValueError('Could not determine FSM datfile type from '
                                 'root node string')

    def get_fsm_list(self):
        self.seek(self.header_size)
        return read_fsm_table(self)

    def replace_fsm_list(self, list_of_fsm):
        prev_len = len(self.get_fsm_list())
        added_entries = len(list_of_fsm) - prev_len
        if self._fixed_size:
            if added_entries < 0:
                list_of_fsm.extend([FSM.blank()] * -added_entries)
            if len(list_of_fsm) * FSM._byte_length > self.data_size:
                raise ValueError('FSM list is too long for this trophy file')
        else:
            self.insert(self.header_size, added_entries*FSM._byte_length)
        self.seek(self.header_size)
        write_fsm_table(self, list_of_fsm)


if __name__ == '__main__':
    x = FSMDatFile('data/fsm-templates/FSM.dat')
    y = FSMDatFile('data/fsm-templates/TyMnView.dat', fixed_size=True)

#    import sys
#    from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout
#
#    app = QApplication.instance()
#    if app is None:
#        app = QApplication([])
#
#    mw = QWidget()
#    vb = QVBoxLayout(mw)
#    box = id_combobox('Character External', bit_width=8)
#    vb.addWidget(box)
#    mw.show()
#
#    sys.exit(app.exec_())
