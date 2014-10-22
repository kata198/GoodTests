class TestMagic(object):

    def setup_TestMagic(self):
        print "Class Constructor"

    def setup_one(self):
        print "--Setting up one"

    def test_one(self):
        assert "one" != "magic"
        assert "magic" == "magic"

    def teardown_one(self):
        print "--Tearing Down One"


    def test_WillFail(self):
        assert 2 == 3

    def teardown_WillFail(self):
        print "--Tearing Down Will Fail"
