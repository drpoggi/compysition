#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  setup.py
#
#  Copyright 2014 Adam Fiebig <fiebig.adam@gmail.com>
#  Originally based on "wishbone" project by smetj
#  
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#
#

from setuptools import setup, find_packages
import re

PROJECT = 'compysition'
try:
    with open('compysition/__init__.py') as init:
        VERSION = re.search("__version__\s*=\s*'(.*)'", init.read(), re.M).group(1)
except (AttributeError, IndexError, OSError, IOError) as e:
    VERSION = ''

REQUIRES = [
            "gevent",
            "greenlet",
            "pyzmq",
            "amqp",
            "pycrypto",
            "configobj",
            "lxml",
            "Pillow==6.2.1",
            "blockdiag",
            "bottle",
            "xmltodict",
            "jsonschema==2.6.0",
            "apscheduler",
            "mimeparse",
            "requests",
            "future"
            ]

try:
     with open('README.rst', 'rt') as readme:
        long_description = readme.read()
except (OSError, IOError) as e:
    long_description = ''

setup(
    name=PROJECT,
    version=VERSION,
    description='Build event pipeline servers with minimal effort.',
    long_description=long_description,
    author='Integrations Team',
    author_email='integrations@cuanswers.com',
    classifiers=['Development Status :: 5 - Production/Stable',
                 'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
                 'Programming Language :: Python',
                 'Programming Language :: Python :: 2',
                 'Programming Language :: Python :: 2.7',
                 'Programming Language :: Python :: 3.6',
                 'Intended Audience :: Developers',
                 'Intended Audience :: System Administrators'],
    platforms=['Linux'],
    install_requires=REQUIRES,
    namespace_packages=[],
    test_suite="tests",
    packages=find_packages(include=('compysition*',)),
    package_data={'': ['*.txt', '*.rst', '*.xml', '*.xsl', '*.conf']},
    zip_safe=False)
