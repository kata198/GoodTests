#!/usr/bin/env python
'''
    Copyright 2011, 2015, 2016, 2017 (c) Timothy Savannah under LGPLv2.1, All Rights Reserved.
  
        If a LICENSE file was not included in this distribution, the license can be found

          at https://github.com/kata198/GoodTests/blob/master/LICENSE

'''
# vim: set ts=4 sw=4 st=4 expandtab


import glob
import multiprocessing
import os
import inspect
import re
import shutil
import signal
import sys
import time
import traceback
import types

from collections import deque

DEFAULT_MAX_RUNNERS = multiprocessing.cpu_count()

try:
    xrange
except NameError:
    xrange = range

COLOUR_RE = re.compile('\033\[[\d]+[m]')

VERSION_MAJOR = 2
VERSION_MINOR = 2
VERSION_PATCH = 0

__version__ = "2.2.0"

__version_tuple__ = (2, 2, 0)

VERSION = "%d.%d.%d" %(VERSION_MAJOR, VERSION_MINOR, VERSION_PATCH)

class GoodTests(object):
    '''
       GoodTests - Runs tests well.
    '''

    def __init__(self, maxRunners=DEFAULT_MAX_RUNNERS, printFailuresOnly=False, extraTimes=False, useColour=True, specificTestPattern=None):
        '''
            __init__ - Create a GoodTests object.

                @param maxRunner <int> Default DEFAULT_MAX_RUNNERS (number of cpus on system) - 

                    Set this to the number of concurrent processes you want to run. For tests without any blocking whatsoever,
                       you may find it faster to leave maxRunners=1, as there is a minor overhead to using >1.

                       Also, required to be =1 when doPdb=True (if not, a warning will be printed and it will be forced to 1)

                @param printFailuresOnly <bool> Default False, if True will only print the Failures and the summary.

                    If True, then every method which passes will print a line

                @param extraTimes <bool> default False. If True, the time each test method, setup, and teardown function takes will be printed.

                @param useColour <bool> default True. If True, will use colour output (works on POSIX/Linux/Unix/Mac terminals). False will not include colours.

                @param specificTestPattern <str/None> default None - If a string is provided, this pattern will be compiled and mathced against functions. Only test functions which match this pattern will be run.

                    For example, specificTestPattern="smoke" will only run test methods which contain 'smoke' in the name.

        '''

        # communcationLock - This is a lock used for transferring data between the parent process
        #                        and children. 
        #         Before writing an object to the parent, this lock is obtained.
        #         When the parent notices an object waiting in the queue, it will read it then
        #           release this lock.
        #         This ensures that one item is transferred at a time to the parent
        #      
        self.communicationLock = multiprocessing.Lock()

        # communicationPipe - A pipe used for sending data from the child back to the parent.
        #                       This is how the child communicates which tests have been ran and the result
        self.communicationPipe = multiprocessing.Pipe(False)

        # runningProcesses - List of running processes, number of elements is number of runners.
        #   Contents is tuple of (multiprocessing.Process, testName)
        self.runningProcesses = [ [None, None] for x in xrange(maxRunners) ]

        # If only to show failures
        self.printFailuresOnly = printFailuresOnly
        if printFailuresOnly is True:
            devnull = open(os.devnull, 'w')
            sys.stdout = devnull

        # List of testNames left to run
        self.testQueue = deque()
        self.extraTimes = extraTimes
        self.noFork = (maxRunners == 1)

        self.useColour = useColour

        self.specificTestPattern = specificTestPattern
        if specificTestPattern is not None:
            try:
                re.compile(specificTestPattern)
            except:
                raise ValueError('Cannot compile pattern: ' + specificTestPattern)

    @staticmethod
    def _getTestClasses(module):
        '''
            _getTestClasses - Return a dict of test classes extracted from a module

                @param module <module> - A module

                @return dict < className : classObj > - A dict of test class names to test class object

                    as found in #module.  A test class begins or ends with "Test"
        '''

        return { inspectInfo[0] : inspectInfo[1]
                    for inspectInfo in
                        inspect.getmembers(module, predicate=inspect.isclass)
                    if inspectInfo[0].startswith('Test') or inspectInfo[0].endswith('Test')
        }

    @staticmethod
    def _getTestMethodsNewStyle(testClass):
        '''
            _getTestMethodsNewStyle - Get test methods which follow the "new style" of names (i.e. begins with "test_")

                @param testClass <class object> - The class to scan

                @return dict < functionName : functionObj > - A dict of test method names to the test methods on #testClass
        '''
        return { inspectInfo[0] : inspectInfo[1]
                    for inspectInfo in
                        inspect.getmembers(testClass, predicate=inspect.ismethod)
                    if inspectInfo[0].startswith('test_')
        }


    @staticmethod
    def _getTestMethodsOldStyle(testClass):
        '''
            _getTestMethodsOldStyle - Get test methods which follow the "old style" of names (i.e. begins with "test")

                @param testClass <class object> - The class to scan

                @return dict < functionName : functionObj > - A dict of test method names to the test methods on #testClass
        '''
        return { inspectInfo[0] : inspectInfo[1]
                    for inspectInfo in
                        inspect.getmembers(testClass, predicate=inspect.ismethod)
                    if inspectInfo[0].startswith('test')
        }


    def output(self, text):
        '''
            output - Called to output text to stderr, optionally stripping colour if disabled

                @param text <str> - Text to send out
        '''
        if self.useColour is False:
            text = COLOUR_RE.sub('', text)
        sys.stderr.write(text + '\n')

    def terminate(self):
        '''
            terminate - Kill all running processes
        '''
        for (process, testName) in self.runningProcesses:
            try:
                process.terminate()
            except:
                pass

        time.sleep(.2)
        for (process, testName) in self.runningProcesses:
            try:
                os.kill(process.pid, 9)
            except:
                pass
        time.sleep(.5)

    def _childObjToParent(self, obj):
        '''
            _childObjToParent - 

               Writes an object to the communication pipe (child->parent).

           This gains the lock, but does not release. (Parent process must read for release)
        '''
        self.communicationLock.acquire()
        try:
            self.communicationPipe[1].send(obj)
        except:
            self.output('>>FAILED TO COMMUNICATE WITH PARENT PROCESS!')

    def _readChildObj(self):
        '''
           _readChildObj - Checks the queue and if there is an item waiting, reads the object and releases

                                the communication lock
        '''
        if not self.communicationPipe[0].poll():
            return None
        obj = self.communicationPipe[0].recv()
        self.communicationLock.release()
        return obj

    def _cleanupProcesses(self):
        '''
           _cleanupProcesses - Cleanup any "finished" processes
        '''
        runningProcesses = self.runningProcesses

        for i in xrange(len(runningProcesses)):
            runningProcess = runningProcesses[i]
            if runningProcess[0] and not runningProcess[0].is_alive():
                runningProcess[0].join()
                runningProcesses[i] = [None, None]

    def _getAvailableData(self):
        '''
           _getAvailableData - Gets any available data from child processes. cleans up processes.

            @return <list> - A list of objects received
        '''
        ret = []

        # Give a little time in between each available thread
#        for i in xrange(len(self.runningProcesses)):
#            obj = self._readChildObj()
#            if obj:
#                ret.append(obj)
#            time.sleep(.0004)
        obj = self._readChildObj()
        if obj:
            ret.append(obj)

        self._cleanupProcesses()
        return ret

    def _getNumberOfTasksRemaining(self):
        '''
           Returns how many tasks are left to run

           @return <int> - number of tasks left to process
        '''
        runningProcesses = self.runningProcesses
        return len(self.testQueue) + len([x for x in runningProcesses if x[0] is not None])

    def _runNextTasks(self):
        '''
           _runNextTasks - Actually puts tasks into the queue.

           @return <int> - number of tasks left to process
        '''
        testQueue = self.testQueue

        if len(testQueue) == 0:
            return self._getNumberOfTasksRemaining()

        if self.noFork:
            nextTest = testQueue.popleft()
            self.runTest(nextTest, self.specificTestPattern)
        else:
            runningProcesses = self.runningProcesses
            runTest = self.runTest
            specificTestPattern = self.specificTestPattern

            for i in xrange(len(runningProcesses)):
                if runningProcesses[i][0] is None:
                    # Nothing running in this slot, queue something
                    nextTest = testQueue.popleft()
                    childProcess = multiprocessing.Process(target=runTest, args=(nextTest, specificTestPattern))
                    childProcess.start()
                    runningProcesses[i][0] = childProcess
                    runningProcesses[i][1] = nextTest

                    if len(testQueue) == 0:
                        # Nothing left to queue, return running count
                        return self._getNumberOfTasksRemaining()

        return self._getNumberOfTasksRemaining()


    @staticmethod
    def _cleanDirectoryNames(directories):
        '''
            _cleanDirectoryNames - Cleanup directory names ( unroll to the real path )

            @param directories list<str> - A list of directory names to cleanup

            @return list<str> - Cleaned up directory names
        '''
        ret = []
        for directory in directories:
            ret.append(os.path.realpath(directory))
        return ret

    @staticmethod
    def removePycacheDir(directory):
        '''
            removePycacheDir - Removes the pycache dir from a directory.

            @param directory <str> - A cleaned-up directory name (no trailing sep)
        '''
        pycacheDir = directory + os.sep + '__pycache__'

        try:
            if os.path.isdir(pycacheDir):
                shutil.rmtree(pycacheDir, ignore_errors=True)
        except:
            print ( "Warning: Failed to remove pycache dir: " + pycacheDir )
            pass


    def getTestsForDirectory(self, directory):
        '''
            getTestsForDirectory - Gather all tests in a given directory.

            A test begins with test_ and ends with .py

            @param directory <str> - A path to a directory. This should be cleaned up first ( #_cleanDirectoryNames )

            @return list ( tuple<str, str/None>  ) - A list of all test files found, coupled potentially with a specific test
        '''

        sys.path += [directory]
        testFiles = glob.glob(directory + os.sep + 'test_*.py')
        testFiles.sort()

        return testFiles

    def runTests(self, directories, files):
        '''
           runTests - Run all tests in directories

            @param directories list<str> - A list of directories to process

            @param files<str> - A list of filenames to process
        '''
        directories = self._cleanDirectoryNames(directories)

        for directory in directories:
            self.removePycacheDir(directory)
            self.testQueue += self.getTestsForDirectory(directory)

        self.testQueue += files

        testResults = {} # Keyed by testFilename, values are return of runTest

        # START IT

        totalTimeStart = time.time()

        numTasksRemaining = 1
        while numTasksRemaining > 0:
            numTasksRemaining = self._runNextTasks()
            time.sleep(.0001)
            data = self._getAvailableData()
            for testName, dataObj in data:
                testResults[testName] = dataObj


        totalTimeEnd = time.time()



        self.output('\n\n' + '=' * 50 + '\nSummary:\n')
        self.output('Test results (%d of %d PASS) Took %f total seconds to run.\n\n' %(sum([int(x[1]) for x in testResults.values()]), sum([int(x[2]) for x in testResults.values()]), totalTimeEnd - totalTimeStart ) )
        self.output('Failing Tests:')

        for filename in testResults.keys():
            failedResults = testResults[filename]
            totalFailed = len(failedResults[0].values())
            if not totalFailed:
                continue
            self.output('%s (%d FAILED):' %(filename, totalFailed))
            for testClassName in failedResults[0].keys():
                testFailures = failedResults[0][testClassName]
                self.output('\t%s (%d FAILED):' %(testClassName, len(testFailures)))
                for functionName, failureTxt in testFailures:
                    self.output('\t   ' + functionName + ' - \033[91m\n\t\t' + '\n\t\t'.join(failureTxt.split('\n')) + '\033[0m')


        self.output('\n\n' + '=' * 50 + '\nSummary:\n')
        self.output('Test results (%d of %d PASS) Took %f total seconds to run.\n\n' %(sum([int(x[1]) for x in testResults.values()]), sum([int(x[2]) for x in testResults.values()]), totalTimeEnd - totalTimeStart ) )


    def runTest(self, testFile, specificTestPattern=None):
        '''
           runTest - Run a specific test file (where testFile is an importable python name [i.e. test_Something.py]).
           All classes beginning with 'Test' are going to be tested.

           setup_(testClassName) or setup_class and teardown_(testClassName) or teardown_class are run at approperate times

           Returns tuple (failedResults<testClassName>(testFunctionName, message), testsPassedCount, totalTestsRun)

           Passes to parent (testFile, return value)

                @param testFile <str> - The filename to run

                @param specificTestPattern <str/None> default None - If provided, will only run methods matching

                        this pattern.
        '''
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        oldDir = os.getcwd()
        if os.sep in testFile:
            (testFileDir, testFile) = os.path.split(testFile)
            os.chdir(testFileDir)

        moduleName = re.sub('.py$', '', testFile)
        try:
            timeStart = time.time()
            module = __import__(moduleName)
            timeEnd = time.time()
            if self.extraTimes is True:
                self.output("Import of " + moduleName + " took " + str(timeEnd-timeStart) + " seconds")
        except Exception as e:
            failedResults = {}
            exc_type, exc_value, exc_traceback = sys.exc_info()
            tracebackInfo = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            failedResults[moduleName] = [('FAIL', 'Failed to compile.\n' + tracebackInfo)]
            ret = (failedResults, 0, 0)
            os.chdir(oldDir)
            self._childObjToParent((testFile, ret))
            return ret

        testClasses = GoodTests._getTestClasses(module)

        failedResults = {} # Keyed by testClassName, contains tuple of testFunctionName and traceback status
        passCount = 0
        testsRunCount = 0

        for testClassName, TestClass in testClasses.items():

            oldStyle = bool(testClassName.endswith('Test') and not testClassName.startswith('Test'))

            try:
                instantiatedTestClass = TestClass()
            except:
                # This is an import beginning with 'Test'
                continue

            if not oldStyle:
                testFunctions = GoodTests._getTestMethodsNewStyle(instantiatedTestClass)
            else:
                testFunctions = GoodTests._getTestMethodsOldStyle(instantiatedTestClass)

            if specificTestPattern:
                specificTestPatternRE = re.compile(specificTestPattern)

                # Filter out test functions
                testFunctionsFiltered = { functionName : funcObj for functionName, funcObj in testFunctions.items() if specificTestPatternRE.match(functionName) }

                if not testFunctionsFiltered:
                    # If we didn't get any matches, try .* on either side
                    specificTestPatternRE = re.compile('.*' + specificTestPattern + '.*')
                    testFunctionsFiltered = { functionName : funcObj for functionName, funcObj in testFunctions.items() if specificTestPatternRE.match(functionName) }

                testFunctions = testFunctionsFiltered

            # General setup_class
            setupSuccess = True
            try:
                timeStart = time.time()

                functionName = 'setup_class'
                if hasattr(instantiatedTestClass, 'setup_class'):
                    getattr(instantiatedTestClass, 'setup_class')()
                timeEnd = time.time()
                if self.extraTimes is True:
                    self.output("setup_class took " + str(timeEnd - timeStart) + " seconds")

                # Old school python unittest general setup for class
                functionName = 'setUp'
                if hasattr(instantiatedTestClass, 'setUp'):
                    getattr(instantiatedTestClass, 'setUp')()

                # Module-specific class-level setup
                functionName = 'setup_' + testClassName
                if hasattr(instantiatedTestClass, functionName):
                    getattr(instantiatedTestClass, functionName)()
            except Exception as e:
                # Exception while running test
                exc_type, exc_value, exc_traceback = sys.exc_info()
                tracebackInfo = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback.tb_next))
                theTuple = self._getTestLineStart(instantiatedTestClass, testFile, functionName) + (tracebackInfo,)
                self.output("\n\033[93m%s - %s.%s \033[91mFAIL \033[93m*****General Exception During Class Setup*****\n\033[91m%s\033[0m" % theTuple)

                if testClassName not in failedResults:
                    failedResults[testClassName] = []
                failedResults[testClassName].append((functionName, tracebackInfo))


                setupSuccess = False


            if setupSuccess is True:
                # Run test methods (and method-specific setup/teardown)
                for testFunctionName, testFunction in testFunctions.items():
                    timeStart = time.time()
                    (status, message) = self.runTestMethod(instantiatedTestClass, testFile, testFunction)
                    timeEnd = time.time()
                    if self.extraTimes is True:
                        self.output(testFunctionName + " took " + str(timeEnd - timeStart) + " seconds")
                    if status == 'FAIL':
                        if testClassName not in failedResults:
                            failedResults[testClassName] = []
                        failedResults[testClassName].append((testFunctionName, message))
                    else:
                        passCount += 1
                    testsRunCount += 1
            else:
                # Mark all tests failed, we could not complete class setup
                testsRunCount += len(testFunctionNames)

            try:
                # Module-specific tear-down
                functionName = 'teardown_' + testClassName
                if hasattr(instantiatedTestClass, functionName):
                    getattr(instantiatedTestClass, functionName)()

                # Old school python unittest general teardown for class
                functionName = 'tearDown'
                if hasattr(instantiatedTestClass, 'tearDown'):
                    getattr(instantiatedTestClass, 'tearDown')()

                # General teardown_class
                functionName = 'teardown_class'
                if hasattr(instantiatedTestClass, 'teardown_class'):
                    getattr(instantiatedTestClass, 'teardown_class')()
            except Exception as e:
                # Exception while running test
                exc_type, exc_value, exc_traceback = sys.exc_info()
                tracebackInfo = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback.tb_next))
                theTuple = self._getTestLineStart(instantiatedTestClass, testFile, functionName) + (tracebackInfo,)
                self.output("\n\033[93m%s - %s.%s \033[91mFAIL \033[93m*****General Exception During Class Teardown*****\n\033[91m%s\033[0m" % theTuple)

                if testClassName not in failedResults:
                    failedResults[testClassName] = []
                failedResults[testClassName].append((functionName, tracebackInfo))

        ret = (failedResults, passCount, testsRunCount)
        self._childObjToParent((testFile, ret))

        os.chdir(oldDir)
        return ret


    @staticmethod
    def _getTestLineStart(instantiatedTestClass, testFile, testFunctionName):
        '''
           _getTestLineStart - Gets the beginning of every log statement.

                @param instantiatedTestClass - module that has been initted

                @paramtestFile - string of python file

                @param testFunctionName - string of test function name
        '''
        return (testFile, str(instantiatedTestClass.__class__.__name__), testFunctionName)

    def runTestMethod(self, instantiatedTestClass, testFile, testFunction):
        '''
           runTestMethod - Run a specific method in a specific test.

           setup_(methodName) will be run for paticular methodName, as well as setup_method (old school).

           teardown_(methodName) will be run after method, or teardown_method (old school).

           
               @param instantiatedTestClass - module that has been initted

               @param testFile - string name of origin file

               @param testFunction <method/str> - string of test function name, or the function method itself


           @return tuple<str, str> - Returns a tuple of execution status

               first value is 'PASS' or 'FAIL'
               second value is function's traceback or empty string
        '''
        if isinstance(testFunction, types.MethodType):
            testFunctionName = testFunction.__name__
        else:
            testFunctionName = testFunction
            testFunction = getattr(instantiatedTestClass, testFunctionName)

        try:
            # General method setup
            if hasattr(instantiatedTestClass, 'setup_method'):
                getattr(instantiatedTestClass, 'setup_method')(getattr(instantiatedTestClass, testFunctionName))

            testSetupFuncName = re.sub('^test_', 'setup_', testFunctionName)
            # Specific method setup
            if hasattr(instantiatedTestClass, testSetupFuncName):
                getattr(instantiatedTestClass, testSetupFuncName)()
        except Exception as e:
            # Exception while running test
            exc_type, exc_value, exc_traceback = sys.exc_info()
            tracebackInfo = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback.tb_next))
            theTuple = self._getTestLineStart(instantiatedTestClass, testFile, testFunctionName) + (tracebackInfo,)
            self.output("\n\033[93m%s - %s.%s \033[91mFAIL \033[93m*****General Exception During Method Setup*****\n\033[91m%s\033[0m" % theTuple)
            return ('FAIL', tracebackInfo)

        try:

            # Execute Test
            testFunction()


        except AssertionError as e:
            # Test failure
            exc_type, exc_value, exc_traceback = sys.exc_info()
            tracebackInfo = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback.tb_next))
            theTuple = self._getTestLineStart(instantiatedTestClass, testFile, testFunctionName) +  (tracebackInfo,)
            self.output("\n\033[93m%s - %s.%s \033[91mFAIL \033[93m*****Assertion Error*****\n\033[91m%s\033[0m" % theTuple)
            ret = ('FAIL', tracebackInfo)
        except Exception as e:
            # Exception while running test
            exc_type, exc_value, exc_traceback = sys.exc_info()
            tracebackInfo = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback.tb_next))
            theTuple = self._getTestLineStart(instantiatedTestClass, testFile, testFunctionName) + (tracebackInfo,)
            self.output("\n\033[93m%s - %s.%s \033[91mFAIL \033[93m*****General Exception During Execution*****\n\033[91m%s\033[0m" % theTuple)
            ret = ('FAIL', tracebackInfo)
        else:
            # PASS
            if not self.printFailuresOnly:
                self.output("\033[93m%s - %s.%s \033[96mPASS\033[0m" % self._getTestLineStart(instantiatedTestClass, testFile, testFunctionName))
            ret = ('PASS', '')

        try:
            # Specific method teardown

            testTeardownFuncName = re.sub('^test_', 'teardown_', testFunctionName)
            if hasattr(instantiatedTestClass, testTeardownFuncName):
                getattr(instantiatedTestClass, testTeardownFuncName)()

            # General method teardown
            if hasattr(instantiatedTestClass, 'teardown_method'):
                getattr(instantiatedTestClass, 'teardown_method')(getattr(instantiatedTestClass, testFunctionName))
        except Exception as e:
            # Exception while running test
            exc_type, exc_value, exc_traceback = sys.exc_info()
            tracebackInfo = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback.tb_next))
            theTuple = self._getTestLineStart(instantiatedTestClass, testFile, testFunctionName) + (tracebackInfo,)
            self.output("\n\033[93m%s - %s.%s \033[91mFAIL \033[93m*****General Exception During Method Teardown*****\n\033[91m%s\033[0m" % theTuple)
            return ('FAIL', tracebackInfo)

        return ret



def printUsage():
        sys.stderr.write("""Usage:  GoodTests.py (options) [filesnames or directories]

         Options:

           -n [number]              - Specifies number of simultaneous executions 
                                        Default = # of processors (%d).
                                       You must use "-n 1" if using pdb
                                      

           -m [regexp]              - Run methods matching a specific pattern
           -q                       - Quiet (only print failures)
           -t                       - Print extra timing information

           --no-colour              - Strip out colours from output
           --no-color

           --help                   - Show this message


""" %(DEFAULT_MAX_RUNNERS,))



def main(args):

    global isTerminating
    isTerminating = False

    def handle_sigTerm(a, b):
        global isTerminating
        if isTerminating:
            return
        isTerminating = True

        sys.stderr.write ( "\nTerminating GoodTests.py...\n" )
        global tester
        tester.terminate()
        sys.exit(1)


    # Parse args
    maxRunners = DEFAULT_MAX_RUNNERS
    printFailuresOnly = False
    specificTestPattern = None
    extraTimes = False
    useColour = True


    if sys.platform == 'win32':
        # Don't try colour if running on dos
        useColour = False
    
    numArgs = len(args)
    i = 0
    
    argPaths = []

    helpArgs = ('--help', '-h', '-?')
    versionArgs = ('--version', '-v')

    while i < numArgs:
        arg = args[i]

        if arg in helpArgs:
            printUsage()
            sys.exit(0)
        elif arg in versionArgs:
            sys.stdout.write('GoodTests.py version %s by Timothy Savannah (c) 2011 - 2017 LGPL version 2.1\n' %(VERSION,))
            sys.exit(0)
        elif arg.startswith('-n'):
            if arg[2:].strip().isdigit():
                maxRunners = int(arg[2:].strip())
                i += 1
            else:
                if i+1 == numArgs or args[i+1].isdigit() is False:
                    sys.stderr.write('-n requires a numeric argument\n')
                    sys.exit(1)
                maxRunners = int(args[i+1])
                i += 2
        elif arg == '-q':
            printFailuresOnly = True
            i += 1
        elif arg.startswith('-m'):
            if arg == '-m':
                if i+1 == numArgs:
                    sys.stderr.write('-m needs a value\n')
                    sys.exit(1)
                specificTestPattern = args[i+1]
                i += 2
            else:
                specificTestPattern = arg[2:]
                i += 1
        elif arg == '-t':
            extraTimes = True
            i += 1
        elif arg in ('--no-colour', '--no-color'):
            useColour = False
            i += 1
        else:
            argPaths.append(arg)
            i += 1

    sys.path += ['.']

    # init tester
    global tester
    try:
        tester = GoodTests(maxRunners=maxRunners, printFailuresOnly=printFailuresOnly, extraTimes=extraTimes, useColour=useColour, specificTestPattern=specificTestPattern)
    except ValueError as e:
        sys.stderr.write(str(e) + '\n')
        sys.exit(1)

    signal.signal(signal.SIGTERM, handle_sigTerm)
    signal.signal(signal.SIGINT, handle_sigTerm)

    # Find directory to run
    if len(argPaths) == 0:
        directories = ['.']
        files = []
    else:
        directories = []
        files = []
        for filename in argPaths:
            if not os.path.exists(filename):
                sys.stderr.write("Invalid filename or directory. '%s' does not exist.\n\n" %(filename,))
                printUsage()
                sys.exit(1)

            if os.path.isdir(filename):
                directories.append(filename)
            else:
                files.append(filename)

    # Run directory
    try:
        tester.runTests(directories, files)
    except KeyboardInterrupt:
        handle_sigTerm(None, None)


if __name__ == "__main__":
    main(sys.argv[1:])

# vim: set ts=4 sw=4 st=4 expandtab
