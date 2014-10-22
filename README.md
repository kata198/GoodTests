GoodTests
============

Supports python2 and python3

A fast python unit-testing framework which supports safe, encapsulated parallel execution of tests, unlike other frameworks (like py.tests, which shares state between tests), and intuitive setup/teardown methodology

Supports old unit-test style (teardown\_method and setup\_method called for each method, and setup\_class, teardown\_class for each class)
Also supports more modern forms, setup/teardown\_[CLASSNAME] and setup/teardown\_[METHOD]

The setup and teardown functions run REGARDLESS of whether the method itself was a success (contrary to some other unit testing frameworks).

All Test classes must begin or end with the word "Test" (example: TestMagic)

Assertions should use the "assert" keyword in python (example: assert 1 != 2)

See "test\_Magic.py" for an example.



	$ python GoodTests.py --help
	Usage:  GoodTests.py (options) [filesnames or directories]

        Options:

		-n [number]              - Specifies number of simultanious executions (default: 1)
		-m [regexp]              - Run methods matching a specific pattern
		-q                       - Quiet (only print failures)
		-t                       - Print extra timing information
		--help                   - Show this screen

GoodTests can be used with -n to do multiple simultanious executions (one process per test class)

-m will use a regular expression pattern to execute only methods matching the name
-q will only print failures


GoodTests.py can be pointed toward any directory, and will load all files prefixed with test\_ (example: test\_Something.py)



Output will contain colours, and lists all the failures (or passes) as they happen, and a consolidated list at the end:

Example:

	$ python2 GoodTests.py test_Magic.py 
	Class Constructor

	test_Magic.py - TestMagic.test_WillFail FAIL *****Assertion Error*****
	Traceback (most recent call last):
	  File "GoodTests.py", line 364, in runTestMethod
	    getattr(instantiatedTestClass, testFunctionName)()
	  File "/home/media/work/GoodTests/test_Magic.py", line 18, in test_WillFail
	    assert 2 == 3
	AssertionError

	--Tearing Down Will Fail
	--Setting up one
	test_Magic.py - TestMagic.test_one PASS
	--Tearing Down One


	==================================================
	Summary:

	Test results (1 of 2 PASS) Took 0.000977 total seconds to run.


	Failing Tests:
	test_Magic.py (1 FAILED):
		TestMagic (1 FAILED):
		   test_WillFail - 
			Traceback (most recent call last):
			  File "GoodTests.py", line 364, in runTestMethod
			    getattr(instantiatedTestClass, testFunctionName)()
			  File "/home/media/work/GoodTests/test_Magic.py", line 18, in test_WillFail
			    assert 2 == 3
			AssertionError



	==================================================
	Summary:

	Test results (1 of 2 PASS) Took 0.000977 total seconds to run.


