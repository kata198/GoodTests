#!/usr/bin/env python
#Copyright 2011, 2015, 2016 (c) Timothy Savannah under LGPLv2, All Rights Reserved. See LICENSE for more information

import glob
import multiprocessing
import os
import re
import signal
import sys
import time
import traceback
import types

DEFAULT_MAX_RUNNERS = multiprocessing.cpu_count()

try:
    xrange
except NameError:
    xrange = range

COLOUR_RE = re.compile('\033\[[\d]+[m]')

VERSION_MAJOR = 1
VERSION_MINOR = 2
VERSION_PATCH = 1

__version__ = "1.2.1"

__version_tuple__ = (1, 2, 1)

VERSION = "%d.%d.%d" %(VERSION_MAJOR, VERSION_MINOR, VERSION_PATCH)

class GoodTests(object):
    '''
       Runs tests well.
    '''

    def __init__(self, maxRunners=DEFAULT_MAX_RUNNERS, printFailuresOnly=False, extraTimes=False, useColour=True):
        '''
            maxRunners is how many tests to execute simultaniously.
        '''
        self.communicationLock = multiprocessing.Lock()
        self.communicationPipe = multiprocessing.Pipe(False)

        # List of running processes, number of elements is number of runners. Contents is tuple of (multiprocessing.Process, testName)
        self.runningProcesses = [ [None, None] for x in xrange(maxRunners) ]

        # If only to show failures
        self.printFailuresOnly = printFailuresOnly
        if printFailuresOnly is True:
            devnull = open('/dev/null', 'w')
            sys.stdout = devnull

        # List of testNames left to run
        self.testQueue = []
        self.extraTimes = extraTimes
        self.noFork = (maxRunners == 1)

        self.useColour = useColour


    def output(self, text):
        if self.useColour is False:
            text = COLOUR_RE.sub('', text)
        sys.stderr.write(text + '\n')

    def terminate(self):
        for (process, testName) in self.runningProcesses:
            os.kill(process.pid, 9)
        time.sleep(.5)

    def _childObjToParent(self, obj):
        '''
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
           Reads object from a child
        '''
        if not self.communicationPipe[0].poll():
            return None
        obj = self.communicationPipe[0].recv()
        self.communicationLock.release()
        return obj

    def _cleanupProcesses(self):
        '''
           Cleanup any "finished" processes
        '''
        for i in xrange(len(self.runningProcesses)):
            runningProcess = self.runningProcesses[i]
            if runningProcess[0] and not runningProcess[0].is_alive():
                runningProcess[0].join()
                self.runningProcesses[i] = [None, None]

    def _getAvailableData(self):
        '''
           Gets any available data from child processes. cleans up processes.
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

    def _tasksLeft(self):
        '''
           Returns how many tasks are left to run
        '''
        return len(self.testQueue) + len([x for x in self.runningProcesses if x[0] is not None])

    def _runNextTasks(self):
        '''
           Actually puts tasks into the queue.

           Returns number of tasks left to process
        '''
        if len(self.testQueue) == 0:
            return self._tasksLeft()

        if self.noFork:
            (nextTest, specificTest) = self.testQueue.pop(0)
            self.runTest(nextTest, specificTest)
        else:
            for i in xrange(len(self.runningProcesses)):
                if self.runningProcesses[i][0] is None:
                    # Nothing running in this slot, queue something
                    (nextTest, specificTest) = self.testQueue.pop(0)
                    childProcess = multiprocessing.Process(target=self.runTest, args=(nextTest, specificTest))
                    childProcess.start()
                    self.runningProcesses[i][0] = childProcess
                    self.runningProcesses[i][1] = nextTest

                    if len(self.testQueue) == 0:
                        # Nothing left to queue, return running count
                        return self._tasksLeft()

        return self._tasksLeft()



    def getTestsForDirectory(self, directory, specificTest=None):
        ''' Run all tests in a directory, where a test is any file that begins with test_ and ends in .py '''
        if directory.endswith('/'):
            directory = directory[:-1]
        sys.path += [directory]
        testFiles = glob.glob(directory + '/test_*.py')
        testFiles.sort()


        return [(testFile, specificTest) for testFile in testFiles]

    def runTests(self, directories, files, specificTest=None):
        '''
           Run all tests in directories
        '''
        for directory in directories:
            self.testQueue += self.getTestsForDirectory(directory, specificTest)
        for file in files:
            self.testQueue.append( (file, specificTest) )

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


    def runTest(self, testFile, specificTest=None):
        '''
           Run a specific test file (where testFile is an importable python name [i.e. test_Something.py]).
           All classes beginning with 'Test' are going to be tested.

           setup_(testClassName) or setup_class and teardown_(testClassName) or teardown_class are run at approperate times

           Returns tuple (failedResults<testClassName>(testFunctionName, message), testsPassedCount, totalTestsRun)

           Passes to parent (testFile, return value)
        '''
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        oldDir = os.getcwd()
        if '/' in testFile:
            (testFileDir, testFile) = os.path.split(testFile)
            os.chdir(testFileDir)

        moduleName = testFile.replace('.py', '')
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

        testClassNames = [testClassName for testClassName in dir(module) if testClassName.startswith('Test') or testClassName.endswith('Test')]

        failedResults = {} # Keyed by testClassName, contains tuple of testFunctionName and traceback status
        passCount = 0
        testsRunCount = 0

        for testClassName in testClassNames:
            TestClass = getattr(module, testClassName)

            oldStyle = bool(testClassName.endswith('Test'))

            try:
                instantiatedTestClass = TestClass()
            except:
                # This is an import beginning with 'Test'
                continue

            if specificTest:
                testFunctionNames = [memberName for memberName in dir(instantiatedTestClass) if re.match(specificTest, memberName) and memberName.startswith('test') and type(getattr(instantiatedTestClass, memberName)) == types.MethodType]
                if not testFunctionNames:
                    # Try .* on either side
                    specificTest = '.*' + specificTest + '.*'
                    testFunctionNames = [memberName for memberName in dir(instantiatedTestClass) if re.match(specificTest, memberName) and memberName.startswith('test') and type(getattr(instantiatedTestClass, memberName)) == types.MethodType]
            else:
                if not oldStyle:
                    testFunctionNames = [memberName for memberName in dir(instantiatedTestClass) if memberName.startswith('test_') and type(getattr(instantiatedTestClass, memberName)) == types.MethodType]
                else:
                    testFunctionNames = [memberName for memberName in dir(instantiatedTestClass) if memberName.startswith('test') and type(getattr(instantiatedTestClass, memberName)) == types.MethodType]

            # General setup_class
            timeStart = time.time()
            if hasattr(instantiatedTestClass, 'setup_class'):
                getattr(instantiatedTestClass, 'setup_class')()
            timeEnd = time.time()
            if self.extraTimes is True:
                self.output("setup_class took " + str(timeEnd - timeStart) + " seconds")

            # Old school python unittest general setup for class
            if hasattr(instantiatedTestClass, 'setUp'):
                getattr(instantiatedTestClass, 'setUp')()

            # Module-specific class-level setup
            if hasattr(instantiatedTestClass, 'setup_' + testClassName):
                getattr(instantiatedTestClass, 'setup_' + testClassName)()


            # Run test methods (and method-specific setup/teardown)
            for testFunctionName in testFunctionNames:
                timeStart = time.time()
                (status, message) = self.runTestMethod(instantiatedTestClass, testFile, testFunctionName)
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

            # Module-specific tear-down
            if hasattr(instantiatedTestClass, 'teardown_' + testClassName):
                getattr(instantiatedTestClass, 'teardown_' + testClassName)()

            # Old school python unittest general teardown for class
            if hasattr(instantiatedTestClass, 'tearDown'):
                getattr(instantiatedTestClass, 'tearDown')()

            # General teardown_class
            if hasattr(instantiatedTestClass, 'teardown_class'):
                getattr(instantiatedTestClass, 'teardown_class')()

        ret = (failedResults, passCount, testsRunCount)
        self._childObjToParent((testFile, ret))

        os.chdir(oldDir)
        return ret


    @staticmethod
    def _getTestLineStart(instantiatedTestClass, testFile, testFunctionName):
        '''
           Gets the beginning of every log statement.

           instantiatedTestClass - module that has been initted
           testFile - string of python file
           testFunctionName - string of test function name
        '''
        return (testFile, str(instantiatedTestClass.__class__.__name__), testFunctionName)

    def runTestMethod(self, instantiatedTestClass, testFile, testFunctionName):
        '''
           Run a specific method in a specific test.

           setup_(methodName) will be run for paticular methodName, as well as setup_method (old school).

           teardown_(methodName) will be run after method, or teardown_method (old school).

           instantiatedTestClass - module that has been initted
           testFile - string name of origin file
           testFunctionName - string of test function name


           Returns a tuple of execution status

           first value is 'PASS' or 'FAIL'
           second value is function's traceback or empty string
        '''
        try:
            # General method setup
            if hasattr(instantiatedTestClass, 'setup_method'):
                getattr(instantiatedTestClass, 'setup_method')(getattr(instantiatedTestClass, testFunctionName))

            # Specific method setup
            if hasattr(instantiatedTestClass, testFunctionName.replace('test_', 'setup_')):
                getattr(instantiatedTestClass, testFunctionName.replace('test_', 'setup_'))()
        except Exception as e:
            # Exception while running test
            exc_type, exc_value, exc_traceback = sys.exc_info()
            tracebackInfo = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            theTuple = self._getTestLineStart(instantiatedTestClass, testFile, testFunctionName) + (tracebackInfo,)
            self.output("\n\033[93m%s - %s.%s \033[91mFAIL \033[93m*****General Exception During Setup*****\n\033[91m%s\033[0m" % theTuple)
            return ('FAIL', tracebackInfo)

        try:

            # Execute Test
            getattr(instantiatedTestClass, testFunctionName)()


        except AssertionError as e:
            # Test failure
            exc_type, exc_value, exc_traceback = sys.exc_info()
            tracebackInfo = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            theTuple = self._getTestLineStart(instantiatedTestClass, testFile, testFunctionName) +  (tracebackInfo,)
            self.output("\n\033[93m%s - %s.%s \033[91mFAIL \033[93m*****Assertion Error*****\n\033[91m%s\033[0m" % theTuple)
            ret = ('FAIL', tracebackInfo)
        except Exception as e:
            # Exception while running test
            exc_type, exc_value, exc_traceback = sys.exc_info()
            tracebackInfo = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
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
            if hasattr(instantiatedTestClass, testFunctionName.replace('test_', 'teardown_')):
                getattr(instantiatedTestClass, testFunctionName.replace('test_', 'teardown_'))()

            # General method teardown
            if hasattr(instantiatedTestClass, 'teardown_method'):
                getattr(instantiatedTestClass, 'teardown_method')(getattr(instantiatedTestClass, testFunctionName))
        except Exception as e:
            # Exception while running test
            exc_type, exc_value, exc_traceback = sys.exc_info()
            tracebackInfo = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            theTuple = self._getTestLineStart(instantiatedTestClass, testFile, testFunctionName) + (tracebackInfo,)
            self.output("\n\033[93m%s - %s.%s \033[91mFAIL \033[93m*****General Exception During Teardown*****\n\033[91m%s\033[0m" % theTuple)
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

           --pdb                    - When an assertion fails, begin a pdb session at
                                       that point. Requires n=1

           --no-colour              - Strip out colours from output
           --no-color

           --help                   - Show this message


""" %(DEFAULT_MAX_RUNNERS,))


if __name__ == "__main__":

    def handle_sigTerm(a, b):
        global tester
        tester.terminate()
        sys.exit(1)
    signal.signal(signal.SIGTERM, handle_sigTerm)
    signal.signal(signal.SIGINT, handle_sigTerm)

    # Parse args
    maxRunners = DEFAULT_MAX_RUNNERS
    printFailuresOnly = False
    specificTest = None
    extraTimes = False
    useColour = True


    if sys.platform == 'win32':
        # Don't try colour if running on dos
        useColour = False
    
    numArgs = len(sys.argv)
    i = 1
    
    argPaths = []

    helpArgs = ('--help', '-h', '-?')
    versionArgs = ('--version', '-v')

    while i < numArgs:
        arg = sys.argv[i]

        if arg in helpArgs:
            printUsage()
            sys.exit(0)
        elif arg in versionArgs:
            sys.stdout.write('GoodTests.py version %s by Timothy Savannah (c) 2011 LGPL version 2.1\n' %(VERSION,))
            sys.exit(0)
        elif arg.startswith('-n'):
            if arg[2:].strip().isdigit():
                maxRunners = int(arg[2:].strip())
                i += 1
            else:
                if i+1 == numArgs or sys.argv[i+1].isdigit() is False:
                    sys.stderr.write('-n requires a numeric argument\n')
                    sys.exit(1)
                maxRunners = int(sys.argv[i+1])
                i += 2
        elif arg == '-q':
            printFailuresOnly = True
            i += 1
        elif arg == '-m':
            if i+1 == numArgs:
                sys.stderr.write('-m needs a value\n')
                sys.exit(1)
            specificTest = sys.argv[i+1]
            i += 2
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
    tester = GoodTests(maxRunners=maxRunners, printFailuresOnly=printFailuresOnly, extraTimes=extraTimes, useColour=useColour)

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
    tester.runTests(directories, files, specificTest=specificTest)
