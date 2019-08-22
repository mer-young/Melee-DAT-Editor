# -*- coding: utf-8 -*-
"""
Created on Wed Jan 23 19:16:10 2019

@author: rmn
"""

import os

from PyQt5.QtWidgets import QComboBox
import yaml


id_list_fname = os.path.join('data', 'id-lists.yml')
id_lists = yaml.safe_load(open(id_list_fname, 'r'))


class id_combobox (QComboBox):
    def __init__(self, id_list_name, bit_width=None, parent=None):
        super().__init__(parent)


        self.id_list = id_lists[id_list_name]
        if bit_width is not None:
            max_value = 2**bit_width - 1
            keys = self.id_list.keys()
            if max(keys) > max_value:
                raise ValueError('Max value in ID list is too large for '
                                 'the specified bit field width.')
            for i in range(max_value + 1):
                if i not in keys:
                    self.id_list[i] = ''

        for key, val in self.id_list.items():
            display_string = hex(key)
            if val:
                display_string += f': {val}'
            self.addItem(display_string, key)

    def value(self):
        return self.currentData()

    def set_value(self, value):
        self.setCurrentIndex(self.findData(value))
