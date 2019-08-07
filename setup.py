#!/usr/bin/env python
'''
    setup.py - Used to install GoodTests.py.

        While GoodTests.py is licensed under the LGPL v2.1, this setup.py file specifically is Public Domain
           or the nearest equivilant in your jurisdiction.
'''

from setuptools import setup


summary = "A fast, parallel, featured python unit-testing framework"

try:
    with open('README.rst', 'rt') as f:
        long_description = f.read()
except:
    long_description = summary

if __name__ == '__main__':

    setup(name='GoodTests',
            version='3.0.5',
            scripts=['GoodTests.py'],
            author='Tim Savannah',
            author_email='kata198@gmail.com',
            maintainer='Tim Savannah',
            maintainer_email='kata198@gmail.com',
            url="https://github.com/kata198/GoodTests",
            description=summary,
            long_description=long_description,
            license='LGPLv2',
            provides=['GoodTests'],
            keywords=['unit test', 'python', 'good tests', 'parallel', 'fast', 'framework', 'testing', 'py.test', 'nose', 'unit'],
            classifiers=['Development Status :: 6 - Mature',
                         'Programming Language :: Python',
                         'License :: OSI Approved :: GNU Lesser General Public License v2 (LGPLv2)',
                         'Programming Language :: Python :: 2',
                          'Programming Language :: Python :: 2',
                          'Programming Language :: Python :: 2.6',
                          'Programming Language :: Python :: 2.7',
                          'Programming Language :: Python :: 3',
                          'Programming Language :: Python :: 3.4',
                          'Programming Language :: Python :: 3.5',
                          'Programming Language :: Python :: 3.6',
                          'Programming Language :: Python :: 3.7',
                          'Topic :: Software Development :: Testing',
            ]
    )
