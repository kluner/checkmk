#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2019 tribe29 GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

# yapf: disable
# type: ignore

from cmk.base.plugins.agent_based.lnx_if import parse_lnx_if

checkname = 'lnx_if'

parsed = parse_lnx_if([
    [u'em0', u'376716785370 417455222 0 0 0 0 0 0 383578105955 414581956 0 0 0 0 0 0'],
    [u'tun0', u'342545566242 0 259949262 0 0 0 0 0  0 19196 0 0  0 0'],
    [u'tun1', u'2422824602 0 2357563 0 0 0 0 0  0 0 0 0  0 0'],
    [u'[em0]'],
    [u'Speed', u' 1000Mb/s'],
    [u'Duplex', u' Full'],
    [u'Auto-negotiation', u' on'],
    [u'Link detected', u' yes'],
    [u'Address', u' 00', u'AA', u'11', u'BB', u'22', u'CC'],
    [u'[tun0]'],
    [u'Link detected', u' yes'],
    [u'Address', u' 123'],
    [u'[tun1]'],
    [u'Link detected', u' yes'],
    [u'Address', u' 456'],
])

discovery = {'': [('1', "{'state': ['1'], 'speed': 1000000000}"),
                  ('2', "{'state': ['1'], 'speed': 0}"),
                  ('3', "{'state': ['1'], 'speed': 0}")]}

checks = {'': [('1',
                {'errors': (0.01, 0.1), 'speed': 1000000000, 'state': ['1']},
                [(0, '[em0] (up) MAC: 00:AA:11:BB:22:CC, 1 Gbit/s', [])]),
               ('2',
                {'errors': (0.01, 0.1), 'speed': 0, 'state': ['1']},
                [(0, '[tun0] (up) speed unknown', [])]),
               ('3',
                {'errors': (0.01, 0.1), 'speed': 0, 'state': ['1']},
                [(0, '[tun1] (up) speed unknown', [])])]}
