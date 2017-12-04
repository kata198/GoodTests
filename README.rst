
GoodTests
=========
GoodTests is a fast python 2/3 compatible unit testing framework which I wrote to work around the shortcomings of other existing frameworks (like py.test and py unit test). It can serve as a drop-in replacement, without the need to modify any existing testcases (or very minimal modification).

It supports parallel execution, regular expression filtering, and provides class-level encapsulation such that a corrupted python environment (such as mocking out DB function calls and whatnot) does not propigate to other tests. This was one of the issues I had found in py.test. And teardown didn't get called if the test failed, so catching cleanup was impossible. It supports both setup/teardown for an entire class, and per method.

Each class runs as a separate process, which can save a lot of time in data generation, and early failure prediction.

Some Features:
--------------

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

*  Supports pdb mode (enabled via --pdb). See "Interactive Debugging" section below.

GoodTests supports auto discovery of tests given a directory, by looking for files and classes that match the pattern (compatible with py.test)

Each file should be in the form of test\_$$CLASSNAME$$.py (where $$CLASSNAME$$ is the name, e.g. "Magic"). The class within the file should either be prefixed or suffixed with the word "Test" (e.g: "TestMagic" or "MagicTest").

Supports old unit-test style (teardown\_method and setup\_method called for each method, and setup\_class, teardown\_class for each class) Also supports more modern forms, setup/teardown\_[CLASSNAME] and setup/teardown\_[METHOD]

The setup and teardown functions run REGARDLESS of whether the method itself was a success (contrary to some other unit testing frameworks).

Assertions should use the "assert" keyword in python (example: assert 1 != 2)

See "test\_Magic.py" for an example:

Usage
-----

	Usage:  GoodTests.py (options) [filesnames or directories]

		Options:

		\-n [number]              \- Specifies number of simultaneous executions 

									 Default = # of processors (2).

									You must use "\-n 1" if using pdb

		\-\-pdb                    \- When an assertion fails, drop to a pdb shell within

									 the test code at the point of failure  ( forces \-n1 )


		\-m [regexp]              \- Run methods matching a specific pattern

		\-q                       \- Quiet (only print failures)

									  This will also disable stdout during test execution

		\-t                       \- Print extra timing information


		\-\-no\-colour              \- Strip out colours from output

		\-\-no\-color


		\-\-version                \- Print version and copyright information

		\-\-help                   \- Show this message



GoodTests can be used with -n to do multiple simultaneous executions (one process per test class)

-m will use a regular expression pattern to execute only methods matching the name -q will only print failures

GoodTests.py can be pointed toward any directory, and will load all files prefixed with test\_ (example: test\_Something.py)

Output will contain colours, and lists all the failures (or passes) as they happen, and a consolidated list at the end:


Interactive Debugging (pdb)
---------------------------

GoodTests.py supports an "interactive debugging" mode, which is toggled by passing "--pdb" as an argument on the commandline.

When in "pdb mode" or "interactive debugging" mode, if an AssertionError (failed assertion) is raised, or another uncaught Exception during test execution, the following will occur:

* A pdb shell is started in the frame at which the exception was raised. So if you had an assertion that failed, the shell would drop you at that point in the code, allowing you to inspect variables, etc. to help diagnose why the failure occured and correct the situation.

* Once you enter "next" [n] or "continue" [c], the setup (if any) will be ran again, and you will be dropped into a pdb interactive shell starting at the top of the test function. This will allow you to walk through the code, change variables, call functions, and print values to understand and attempt to correct the situation inline. If, during this session, you correct the issue and the formerly failing assertion now passes, it will be marked as "PASS (debugger)" in the results. The original Traceback will be printed in the aggregate summary at the bottom of test results, noting that it did pass upon retry due to actions executed during your debug session.


You may also choose to put a "pdb.set\_trace()" directly within your test or code somewhere. In order for this to work, you must ensure that maxRunners == 1 ( i.e. pass "-n1" as an argument ).


Example
-------

Example Test test\_Magic.py:

	import os

	DO\_PRINT = int(os.environ.get('DO\_PRINT', 0))

	class TestMagic(object):

		def setup\_TestMagic(self):

			if DO\_PRINT:

				print("Class Constructor")

		def setup\_one(self):

			if DO\_PRINT:

				print("\-\-Setting up one")

		def test\_one(self):

			assert "one" != "magic"

			assert "magic" == "magic"

		def teardown\_one(self):

			if DO\_PRINT:

				print("\-\-Tearing Down One")


		def test\_WillFail(self):

			assert 2 == 3, 'Expected two to equal three'

		def test\_popularity(self):

			tim = 'abcsdfsd'

			cool = 'abcsdfsd'

			assert tim is cool

		def teardown\_WillFail(self):

			if DO\_PRINT:

				print("\-\-Tearing Down Will Fail")


Results:

	$ GoodTests.py test\\\_Magic.py

	test\_Magic.py \- TestMagic.test\_WillFail FAIL \*\*\*\*\*Assertion Error\*\*\*\*\*

	Traceback (most recent call last):

		File "/home/media/work/github/GoodTests/test\_Magic.py", line 25, in test\_WillFail

		assert 2 == 3

	AssertionError: Expected two to equal three

	test\_Magic.py \- TestMagic.test\_one PASS

	test\_Magic.py \- TestMagic.test\_popularity PASS


	\==================================================

	Summary:

	Test results (2 of 3 PASS) Took 0.000650 total seconds to run.


	Failing Tests:

	test\_Magic.py (1 FAILED):

		TestMagic (1 FAILED):

			test\_WillFail \-

			Traceback (most recent call last):

				File "/home/media/work/github/GoodTests/test\_Magic.py", line 25, in test\_WillFail

				assert 2 == 3

			AssertionError: Expected two to equal three



	\==================================================

	Summary:

	Test results (2 of 3 PASS) Took 0.006250 total seconds to run.


Including In Project
--------------------

I recommend bundling the provided "distrib/runTests.py" with your projects to support GoodTests.

runTests.py will download the latest GoodTests.py into the local directory if it is not installed, and will ensure the local copy of source is used when running tests, which saves the step of running "setup.py install" each change to run tests.

