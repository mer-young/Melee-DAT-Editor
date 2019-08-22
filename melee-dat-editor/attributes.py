# -*- coding: utf-8 -*-
"""
Created on Wed Jan  9 20:41:47 2019

@author: rmn
"""

import os
import yaml


common_folder = os.path.join('data', 'attributes', 'common')
unique_folder = os.path.join('data', 'attributes', 'unique')


def article_info(character_short_name):
    try:
        fname = os.path.join(unique_folder, character_short_name + '.yml')
        return yaml.safe_load(open(fname, 'r'))['articles']
    except OSError:
        raise
    except IndexError:
        return None


def common_table(dat_type):
    try:
        fname = os.path.join(common_folder, dat_type + '.yml')
        return get_table(fname)
    except FileNotFoundError:
        fname = os.path.join(common_folder, '_default.yml')
        return get_table(fname)


def unique_table(character_short_name):
    try:
        fname = os.path.join(unique_folder, character_short_name + '.yml')
        return get_table(fname, key='unique attributes')
    except FileNotFoundError:
        fname = os.path.join(unique_folder, '_default.yml')
        return get_table(fname, key='unique attributes')


def get_table(fname, key=None):
    data = yaml.safe_load(open(fname, 'r'))
    if key is not None:
        data = data[key]
    try:
        length = data.pop('length')
    except KeyError:
        # no length specified, assume the table ends with the last listed
        length = max(data.keys()) + 4
    return table_names_and_fmt(data, length)


def table_names_and_fmt(info, length):
    names = []
    fmt = '>'
    for offset in range(0, length, 4):
        entry = info.get(offset, _default_attribute)
        names.append(entry['name'])
        fmt += entry['type']
    return names, fmt


_default_attribute = {
        'name': 'Unknown',
        'type': 'f'
        }
