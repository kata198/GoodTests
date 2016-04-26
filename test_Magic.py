#!/usr/bin/env GoodTests.py

import os
import subprocess
import sys

DO_PRINT = int(os.environ.get('DO_PRINT', 0))

class TestMagic(object):

    def setup_TestMagic(self):
        if DO_PRINT:
            print("Class Constructor")

    def setup_one(self):
        if DO_PRINT:
            print("--Setting up one")

    def test_one(self):
        assert "one" != "magic"
        assert "magic" == "magic"

    def teardown_one(self):
        if DO_PRINT:
            print("--Tearing Down One")


    def test_WillFail(self):
        assert 2 == 3

    def test_popularity(self):
        tim = 'abcsdfsd'
        cool = 'abcsdfsd'
        assert tim is cool

    def teardown_WillFail(self):
        if DO_PRINT:
            print("--Tearing Down Will Fail")


if __name__ == '__main__':
    sys.exit(subprocess.Popen(['GoodTests.py', sys.argv[0]], shell=False).wait())
