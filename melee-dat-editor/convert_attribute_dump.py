# -*- coding: utf-8 -*-
"""
Created on Wed Jan 16 20:51:58 2019

@author: rmn
"""

import os

import yaml

from datfiles import moveset_datfile


attribs_folder = 'data/attributes/unique'
# wip.txt scraped by regexes from crazy hand v1.0 github source
ch_dump_data = yaml.safe_load(open(os.path.join(attribs_folder, 'wip.txt'), 'r'))

iso_folder = 'D:/SSB/melee mods/dat files/iso dump/root'
dat_names = {
        "falcon": "PlCa",
        "younglink": "PlCl",
        "dk": "PlDk",
        "doctorMario": "PlDr",
        "falco": "PlFc",
        "roy": "PlFe",
        "fox": "PlFx",
        "ganondorf": "PlGn",
        "gnw": "PlGw",
        "kirby": "PlKb",
        "bowser": "PlKp",
        "luigi": "PlLg",
        "link": "PlLk",
        "mario": "PlMr",
        "marth": "PlMs",
        "mewtwo": "PlMt",
        "ness": "PlNs",
        "pichu": "PlPc",
        "peach": "PlPe",
        "pikachu": "PlPk",
        "iceclimbers": "PlPp",
        "jigglypuff": "PlPr",
        "sheik": "PlSk",
        "samus": "PlSs",
        "yoshi": "PlYs",
        "zelda": "PlZd"
        }

for character, attributes in ch_dump_data.items():
    if attributes == {'None': 'None'}:
        continue
    dat_fname = os.path.join(iso_folder, dat_names[character] + '.dat')
    with moveset_datfile(dat_fname) as dat_f:
        character_name = dat_f.char_short_name()
        start_offset = dat_f.unique_attributes_table.start_offset
        next_pointer = 99999999999999999999999
        for p in dat_f.pointer_table:
            dat_f.seek(dat_f.pointer(p))
            pointed = dat_f.pointer(dat_f.read_int())
            if start_offset < pointed < next_pointer:
                next_pointer = pointed
        length = next_pointer - start_offset

    with open(os.path.join(attribs_folder, character_name + '.yml'), 'w') as f:
        f.write('length: ' + hex(length) + '\n\n')

        for offset in sorted(attributes.keys()):
            attribute = attributes[offset]
            name = attribute['name']
            type_ = attribute['type']
            relative_offset = offset - start_offset
            if 0 <= relative_offset < length:
                f.write(hex(relative_offset) + ':\n')
                f.write('    name: "' + name + '"\n')
                f.write('    type: ' + type_ + '\n\n')
