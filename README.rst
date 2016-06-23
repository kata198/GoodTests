
GoodTests
=========
GoodTests is a fast python 2/3 compatible unit testing framework which I wrote to work around the shortcomings of other existing frameworks (like py.test and py unit test). It can serve as a drop-in replacement, without the need to modify any existing testcases (or very minimal modification).

It supports parallel execution, regular expression filtering, and provides class-level encapsulation such that a corrupted python environment (such as mocking out DB function calls and whatnot) does not propigate to other tests. This was one of the issues I had found in py.test. And teardown didn't get called if the test failed, so catching cleanup was impossible. It supports both setup/teardown for an entire class, and per method.

Each class runs as a separate process, which can save a lot of time in data generation, and early failure prediction.

**Some Features:**


*  It makes use of the "assert" keyword instead of other frameworks which have obtuse methods (like self.assertEquals)
*  Colour output
*  Because "assert" keyword is used, failures can have associated messages. e.x. assert len(items) == 2, 'Expected 2 items, got %d' %(len(items),)
*  It supports running only methods that match a given regular expression.
*  It supports discovery of all tests within a directory.
*  Drop-in replacement for existing py.test/unit tests
*  Tests extend "object". The tests themselves don't actually import any part of GoodTests.
*  License is LGPL
*  Supports python 2 and python 3.
*  Runs tests in parallel
*  Each test class (should have one per file) runs in the same process. This allows you to get more performance by not setting up and tearing down similar data for each function, and allows sharing of state and knowledge (like if test\_constructor fails on a class, you know everything else is going to fail, so you can mark a flag "self.xWillFail" and assert at the beginning of functions.) Other advantages too


GoodTests supports auto discovery of tests given a directory, by looking for files and classes that match the pattern (compatible with py.test)

Each file should be in the form of test_$$CLASSNAME$$.py (where $$CLASSNAME$$ is the name, e.g. "Magic"). The class within the file should either be prefixed or suffixed with the word "Test" (e.g: "TestMagic" or "MagicTest").

Supports old unit-test style (teardown_method and setup_method called for each method, and setup_class, teardown_class for each class) Also supports more modern forms, setup/teardown_[CLASSNAME] and setup/teardown_[METHOD]

The setup and teardown functions run REGARDLESS of whether the method itself was a success (contrary to some other unit testing frameworks).

Assertions should use the "assert" keyword in python (example: assert 1 != 2)

See "test_Magic.py" for an example:


	$ python GoodTests.py --help

	Usage:  GoodTests.py (options) [filesnames or directories]



	Options:



		\-n [number]              - Specifies number of simultanious executions (default: 1)

		\-m [regexp]              - Run methods matching a specific pattern

		\-q                       - Quiet (only print failures)

		\-t                       - Print extra timing information

		\-\-no\-colour              - Strip out colours from output

		\-\-no\-color



		\-\-help                   - Show this screen




GoodTests can be used with -n to do multiple simultaneous executions (one process per test class)

-m will use a regular expression pattern to execute only methods matching the name -q will only print failures

GoodTests.py can be pointed toward any directory, and will load all files prefixed with test\_ (example: test_Something.py)

Output will contain colours, and lists all the failures (or passes) as they happen, and a consolidated list at the end:

**Example**

Example Test test_Magic.py:


	import os



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

			assert 2 == 3, 'Expected two to equal three'



		def test_popularity(self):

			tim = 'abcsdfsd'

			cool = 'abcsdfsd'

			assert tim is cool



		def teardown_WillFail(self):

			if DO_PRINT:

				print("--Tearing Down Will Fail")




Results:


	$ GoodTests.py test\_Magic.py



	test_Magic.py - TestMagic.test_WillFail FAIL *****Assertion Error*****

	Traceback (most recent call last):

		File "./GoodTests.py", line 371, in runTestMethod

		getattr(instantiatedTestClass, testFunctionName)()

		File "/home/media/work/github/GoodTests/test_Magic.py", line 25, in test_WillFail

		assert 2 == 3

	AssertionError: Expected two to equal three



	test_Magic.py - TestMagic.test_one PASS

	test_Magic.py - TestMagic.test_popularity PASS





	\==================================================

	Summary:



	Test results (2 of 3 PASS) Took 0.000650 total seconds to run.





	Failing Tests:

	test_Magic.py (1 FAILED):

		TestMagic (1 FAILED):

			test_WillFail -

			Traceback (most recent call last):

				File "./GoodTests.py", line 371, in runTestMethod

				getattr(instantiatedTestClass, testFunctionName)()

				File "/home/media/work/github/GoodTests/test_Magic.py", line 25, in test_WillFail

				assert 2 == 3

			AssertionError: Expected two to equal three







	\==================================================

	Summary:



	Test results (2 of 3 PASS) Took 0.006250 total seconds to run.




**Including In Project**

I recommend bundling the provided "distrib/runTests.py" with your projects to support GoodTests.

runTests.py will download the latest GoodTests.py into the local directory if it is not installed, and will ensure the local copy of source is used when running tests, which saves the step of running "setup.py install" each change to run tests.
