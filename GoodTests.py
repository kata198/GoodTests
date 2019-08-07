#!/usr/bin/env python
'''
    Copyright 2011, 2015, 2016, 2017, 2018 (c) Timothy Savannah under LGPLv2.1, All Rights Reserved.
  
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

import pdb

BdbQuit = pdb.bdb.BdbQuit

from collections import deque


__all__ = ( 'GoodTests', 'printUsage', 'main', )


DEFAULT_MAX_RUNNERS = multiprocessing.cpu_count()

try:
    xrange
except NameError:
    xrange = range

COLOUR_RE = re.compile('\033\[[\d]+([;][\d]+){0,1}[m]')

VERSION_MAJOR = 3
VERSION_MINOR = 0
VERSION_PATCH = 5

__version__ = "3.0.5"

__version_tuple__ = (3, 0, 5)

VERSION = "%d.%d.%d" %(VERSION_MAJOR, VERSION_MINOR, VERSION_PATCH)

# CHILD_CLEANUP_DELAY - The number of seconds we sleep before attempting
#            to cleanup done/dead children
CHILD_CLEANUP_DELAY = .002


class GoodTests(object):
    '''
       GoodTests - Runs tests well.
    '''

    def __init__(self, maxRunners=DEFAULT_MAX_RUNNERS, printFailuresOnly=False, extraTimes=False, useColour=True, specificTestPattern=None, usePdb=False):
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
        
        self.usePdb = usePdb
        if usePdb and maxRunners > 1:
            sys.stderr.write('WARNING: pdb mode enabled, but maxRunners (number of processes, -n) was > 1 (%d). Setting to 1 to support pdb.\n\n')
            maxRunners = 1


        # communicationPipe - A pipe used for sending data from the child back to the parent.
        #                       This is how the child communicates which tests have been ran and the result
        self.communicationPipe = multiprocessing.Pipe(False)

        # runningProcesses - List of running processes, number of elements is number of runners.
        #   Contents is tuple of (multiprocessing.Process, testName)
        self.runningProcesses = [ [None, None] for x in xrange(maxRunners) ]

        # doneRunning - Since there is a large cost to running through and polling all children for
        #                  .is_alive, we rely on the child to self-report when it is done via setting
        #                   their index to "1" in this array.
        #
        #       49/50 checks we only use this self-reporting and join that process.
        #        1/50 we fallback to the "full" check wherein each child is polled, to cover issues
        #        like running out of memory and a subprocess crashing.
        self.doneRunning = multiprocessing.Array('b', maxRunners)

        # If only to show failures
        self.printFailuresOnly = printFailuresOnly
        if printFailuresOnly is True:
            self.origStdout = sys.stdout
            self.devnull = open(os.devnull, 'wt')

        # List of testNames left to run
        self.testQueue = deque()
        self.extraTimes = extraTimes

        # self.runDirect - bool, if True we will run right in the current process ( maxRunners==1 ),
        #                        if False, this will become the parent and children will run tests
        self.runDirect = (maxRunners == 1)

        self.useColour = useColour

        self.specificTestPattern = specificTestPattern
        if specificTestPattern is not None:
            try:
                re.compile(specificTestPattern)
            except:
                raise ValueError('Cannot compile pattern: ' + specificTestPattern)

        # thisRunnerIdx - Set after starting a child to the runnerIdx this is
        self.thisRunnerIdx = None

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


    def _disableStdoutIfQuiet(self):
        '''
            _disableStdoutIfQuiet - If printFailuresOnly=True ( aka -q or "quiet mode" ), then disable stdout

                @see _enableStdoutIfQuiet to re-enable
        '''
        if self.printFailuresOnly:
            sys.stdout = self.devnull

    def _enableStdoutIfQuiet(self):
        '''
            _enableStdoutIfQuiet - If printFailuresOnly=True (aka -q or "quiet mode" ), then re-enable stdout

                @see _enableStdoutIfQuiet to disable
        '''
        if self.printFailuresOnly:
            sys.stdout = self.origStdout

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

                 This is called when a child completes its test set, and passes the results back
                   up to the parent for the final aggregation of results.
        '''
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

        return obj


    def _markThisRunnerDone(self):
        '''
            _markThisRunnerDone - Self-report that we have completed our set to alert the parent

                    that we are ready to be joined and our slot given to a new worker
        '''
        runnerIdx = self.thisRunnerIdx

        # If we are running with parent->child
        if runnerIdx != None:
            self.doneRunning[runnerIdx] = 1

    def _cleanupChildrenDone(self):
        '''
           _cleanupChildrenDone - Cleanup any "finished" child processes.

              This is the "fast-path" function, and relies on the self-reporting of completion
                of the child processes (@see self.doneRunning).

              This should be called the majority of the time, but occasionally call self._cleanupChildrenLong
                which will poll every child in the self.runningProcesses array, catching the case for like segfault or OOM, etc.


              Will join the completed child, 
                and mark its entry in self.runningProcesses as [None, None],
                and reset the self.doneRunning[runnerIdx] to 0
        '''

        runningProcesses = self.runningProcesses
        doneRunning = list(self.doneRunning)

        for runnerIdx in range(len(doneRunning)):

            if doneRunning[runnerIdx] == 1:
                runningProcessObj = runningProcesses[runnerIdx][0]
                runningProcessObj.join()

                self.doneRunning[runnerIdx] = 0

                runningProcesses[runnerIdx] = [None, None]



    def _cleanupChildrenLong(self):
        '''
            _cleanupChildrenLong - Iterate through every entry in the self.runningProcesses list of children,
               
                                        and poll them to see if they have stopped running.

                There is a significant overhead to polling child processes, so this should only be called

                   "once in a while", whilst #_cleanupChildrenDone should be the primary "cleanup" call done.

              Will join the completed child, 
                and mark its entry in self.runningProcesses as [None, None],
                and reset the self.doneRunning[runnerIdx] to 0
        '''

        runningProcesses = self.runningProcesses

        for runnerIdx in xrange(len(runningProcesses)):
            runningProcessObj = runningProcesses[runnerIdx][0]
            if runningProcessObj and not runningProcessObj.is_alive():
                runningProcessObj.join()
                self.doneRunning[runnerIdx] = 0
                runningProcesses[runnerIdx] = [None, None]


    def _getAvailableData(self):
        '''
           _getAvailableData - Gets any available data from child processes. cleans up processes.

            @return <list> - A list of objects received
        '''
        ret = []

        # Read all available data on the pipe
        while True:
            nextItem = self._readChildObj()
            if nextItem is None:
                break
            ret.append(nextItem)

        # Give a little time in between each available thread
#        for i in xrange(len(self.runningProcesses)):
#            obj = self._readChildObj()
#            if obj:
#                ret.append(obj)
#            time.sleep(.0004)

#        # Old one-at-a-time read
#        obj = self._readChildObj()
#        if obj:
#            ret.append(obj)

        #self._cleanupProcesses()
        return ret

    def _getNumberOfActiveRunningProcesses(self):
        '''
            _getNumberOfActiveRunningProcesses - Get the number of active running processes

            @return <int> - Number of active running processes
        '''
        runningProcesses = self.runningProcesses
        return len([x for x in runningProcesses if x[0] is not None])


    def _getNumberOfTasksRemaining(self):
        '''
           Returns how many tasks are left to run

           @return <int> - number of tasks left to process
        '''
        runningProcesses = self.runningProcesses
        return len(self.testQueue) + len([x for x in runningProcesses if x[0] is not None])

    def _runNextTasks(self):
        '''
           _runNextTasks - Actually puts tasks into the queue, filling any empty slots.

           @return <int> - number of tasks left to process
        '''
        testQueue = self.testQueue

        if len(testQueue) == 0:
            return self._getNumberOfActiveRunningProcesses()

        if self.runDirect:
            nextTest = testQueue.popleft()
            self.runTest(nextTest, self.specificTestPattern)
        else:
            runningProcesses = self.runningProcesses
            runTest = self.runTest
            specificTestPattern = self.specificTestPattern


            testQueueLen = len(testQueue)

            for runnerIdx in xrange(len(runningProcesses)):
                if runningProcesses[runnerIdx][0] is None:
                    # Nothing running in this slot, queue something
                    nextTest = testQueue.popleft()
                    testQueueLen -= 1

                    childProcess = multiprocessing.Process(target=runTest, args=(nextTest, specificTestPattern, runnerIdx))
                    childProcess.start()
                    runningProcesses[runnerIdx][0] = childProcess
                    runningProcesses[runnerIdx][1] = nextTest

                    if testQueueLen == 0:
                        # Nothing left to queue, return running count
                        return self._getNumberOfActiveRunningProcesses()

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
        childCleanupDelay = CHILD_CLEANUP_DELAY

        directories = self._cleanDirectoryNames(directories)

        for directory in directories:
            self.removePycacheDir(directory)
            self.testQueue += self.getTestsForDirectory(directory)

        self.testQueue += files

        testResults = {} # Keyed by testFilename, values are return of runTest

        # START IT

        totalTimeStart = time.time()

        numTasksRemaining = 1

        # i - a counter we use to walk the fast path most of the time, but still
        #       occasionally fall back to the long path
        i = 0
        while numTasksRemaining > 0:
            numTasksRemaining = self._runNextTasks()

            # Rest a little bit to not interrupt the children too often
            time.sleep(childCleanupDelay)
            i += 1
            if i >= 50:
                # Every 50th run do the "Long" cleanup process method, which will
                #    catch any processes that have died unexpectedly (like out of memory)
                #  And clear any pending data on the pipe so it doesn't fill
                i = 0

                self._cleanupChildrenLong()

                # Perform some data collection here, so that the our pipe doesn't fill up
                data = self._getAvailableData()
                for testName, dataObj in data:
                    testResults[testName] = dataObj
            else:
                # For the most part, cleanup the processes that have self-reported being
                #    done
                self._cleanupChildrenDone()

        totalTimeEnd = time.time()

        # Save data collection until the end
        data = self._getAvailableData()
        for testName, dataObj in data:
            testResults[testName] = dataObj


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

        totalPassCount = 0
        totalTestCount = 0
        totalDebugPassCount = 0

        for filename, testResult in testResults.items():
            totalPassCount += int(testResult[1])

            numTests = int(testResult[2])
            if numTests == -1:
                # If -1, we failed to run the test. Log error in the summary
                #  and set numTests to 1 (just so we don't get 100%)
                self.output("FAILED TO RUN TEST %s (syntax error?)\n\n" %(filename, ))
                numTests = 1
            totalTestCount += numTests
            totalDebugPassCount += int(testResult[3])

        if totalTestCount > 0:
            passedPct = ( float(totalPassCount) / float(totalTestCount) ) * 100.0
        else:
            passedPct = 0

        if totalDebugPassCount > 0:
            if totalTestCount > 0:
                passedAfterDebugPct = ( float(totalDebugPassCount) / float(totalTestCount) ) * 100.0
            else:
                passedAfterDebugPct = 0.0
            passedAfterDebugStr = " + ( %d PASSED after interactive debug [%.2f%%]) " %(totalDebugPassCount, passedAfterDebugPct )
        else:
            passedAfterDebugStr = ""


        self.output('Test results (%d of %d PASS) [%.2f%%] %s Took %f total seconds to run.\n\n' % \
            (totalPassCount, totalTestCount, passedPct, passedAfterDebugStr, totalTimeEnd - totalTimeStart ) 
        )


    def runTest(self, testFile, specificTestPattern=None, runnerIdx=None):
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
        # Mark this "rjunner index." In the multiprocess scenario, this method is called with its index
        #    in the self.runningProcesses list as #runnerIdx, and is used to self-mark when we are done.
        #  For single-threaded scenario, this value is not used.
        self.thisRunnerIdx = runnerIdx

        # Disable stdout if in quiet mode
        self._disableStdoutIfQuiet()

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
            ret = (failedResults, 0, -1, 0)
            os.chdir(oldDir)
            self._childObjToParent((testFile, ret))
            self._markThisRunnerDone()
            return ret

        testClasses = GoodTests._getTestClasses(module)

        failedResults = {} # Keyed by testClassName, contains tuple of testFunctionName and traceback status
        passCount = 0
        debugPassCount = 0
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

            # If we did not match any test functions, do not call setup_class
            if not testFunctions:
                return (0, 0, 0, 0)
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
                    elif message:
                        if testClassName not in failedResults:
                            failedResults[testClassName] = []
                        failedResults[testClassName].append((testFunctionName, message))
                        debugPassCount += 1
                    else:
                        passCount += 1
                    testsRunCount += 1
            else:
                # Mark all tests failed, we could not complete class setup
                testsRunCount += len(testFunctions)

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

        ret = (failedResults, passCount, testsRunCount, debugPassCount)
        self._childObjToParent((testFile, ret))

        os.chdir(oldDir)

        # re-enable stdout if quiet mode
        self._enableStdoutIfQuiet()

        self._markThisRunnerDone()
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

    def runTestMethod(self, instantiatedTestClass, testFile, testFunction, runUnderDebugger=False):
        '''
           runTestMethod - Run a specific method in a specific test.

           setup_(methodName) will be run for paticular methodName, as well as setup_method (old school).

           teardown_(methodName) will be run after method, or teardown_method (old school).

           
               @param instantiatedTestClass - module that has been initted

               @param testFile - string name of origin file

               @param testFunction <method/str> - string of test function name, or the function method itself

               @param runUnderDebugger <bool> default False - If True, will execute this method under the debugger

                            This is called when self.usePdb = True and an Exception is raised during test execution


           @return tuple<str, str> - Returns a tuple of execution status

               first value is 'PASS' or 'FAIL'
               second value is function's traceback or empty string
        '''
        if runUnderDebugger is False:
            self.lastTracebackMsg = ''

            # Disable stdout if we are in "quiet" mode, and NOT re-running this method
            #   under the debugger
            self._disableStdoutIfQuiet()

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
            if not runUnderDebugger:
                testFunction()
            else:
                pdb.runcall(testFunction)


        except AssertionError as e:
            # Test failure
            excInfo = sys.exc_info()
            exc_type, exc_value, exc_traceback = excInfo
            tracebackInfo = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback.tb_next))
            theTuple = self._getTestLineStart(instantiatedTestClass, testFile, testFunctionName) +  (tracebackInfo,)
            self.output("\n\033[93m%s - %s.%s \033[91mFAIL \033[93m*****Assertion Error*****\n\033[91m%s\033[0m" % theTuple)

            # TODO: Should trap setup / teardown?
            if not runUnderDebugger and self.usePdb:
                self.lastTracebackMsg = "Was corrected in interactive debugger session.\n\nOriginal Traceback:\n\n" + tracebackInfo
                return self.runTestMethodDebugFailure(instantiatedTestClass, testFile, testFunction, excInfo)

            ret = ('FAIL', tracebackInfo)
        except BdbQuit as be:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            tracebackInfo = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback.tb_next))
            theTuple = self._getTestLineStart(instantiatedTestClass, testFile, testFunctionName) + (tracebackInfo,)
            self.output("\n\033[93m%s - %s.%s \033[91mFAIL \033[93m*****Debugger Aborted During Execution*****\n\033[91m%s\033[0m" % theTuple)
            ret = ('FAIL', tracebackInfo)
            
        except Exception as e:
            # Exception while running test
            excInfo = sys.exc_info()
            exc_type, exc_value, exc_traceback = excInfo
            tracebackInfo = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback.tb_next))
            theTuple = self._getTestLineStart(instantiatedTestClass, testFile, testFunctionName) + (tracebackInfo,)
            self.output("\n\033[93m%s - %s.%s \033[91mFAIL \033[93m*****General Exception During Execution*****\n\033[91m%s\033[0m" % theTuple)
            if not runUnderDebugger and self.usePdb:
                self.lastTracebackMsg = "Was corrected in interactive debugger session.\n\nOriginal Traceback:\n\n" + tracebackInfo
                return self.runTestMethodDebugFailure(instantiatedTestClass, testFile, testFunction, excInfo)

            ret = ('FAIL', tracebackInfo)
        else:
            # PASS
            if runUnderDebugger:
                passStrOutput = 'PASS \033[97m(debugger)\033[0m'
                passStrRet = 'PASS (debugger)'
            else:
                passStrRet = passStrOutput = 'PASS'

            if not self.printFailuresOnly:
                outputStr = "\033[93m%s - %s.%s \033[96m" % self._getTestLineStart(instantiatedTestClass, testFile, testFunctionName)
                if runUnderDebugger:
                    outputStr += 'PASS \033[97m(debugger)'
                else:
                    outputStr += 'PASS'

                outputStr += "\033[0m"
                self.output(outputStr)

            if runUnderDebugger:
                ret = ( 'PASS (debugger)', self.lastTracebackMsg )
            else:
                ret = ('PASS', '')

        if runUnderDebugger:
            # If we re-enabled stdout for the debugger, go ahead and disable it again before running teardown
            self._disableStdoutIfQuiet()
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


    def runTestMethodDebugFailure(self, instantiatedTestClass, testFile, testFunction, excInfo):
        '''
            runTestMethodDebugFailure - Resume a test method at a failure point.

                @see runTestMethod

                Additional:

                    @param excInfo - The sys.exc_info() tuple at time of exception
        '''

        # Turn stdout back on when debugging, to see pdb prompt and any debug prints
        self._enableStdoutIfQuiet()

        (orig_exc_type, orig_exc_value, orig_exc_traceback) = excInfo
        origTracebackInfo = ''.join(traceback.format_exception(orig_exc_type, orig_exc_value, orig_exc_traceback.tb_next))

        if isinstance(testFunction, types.MethodType):
            testFunctionName = testFunction.__name__
        else:
            testFunctionName = testFunction
            testFunction = getattr(instantiatedTestClass, testFunctionName)

        # TODO: This always says "ASSERTION FAILED", but we could have dropped in for a different kind of error
        self.output("\033[93;1m============================================================\033[0m\n")
        self.output("\n\033[94mASSERTION FAILED AND PDB ENABLED: DROPPING INTO DEBUGGER ---\033[0m\n")

        self.output("\033[94mGoodTests ==> Loading at failing assertion\n" \
            "\tEnter 'locals()' (without quotes) to access a dict of local variables.\n" \
            "\tEnter 'print ( someVar )' (without quotes) to print the value of a variable.\n" \
            "\tEnter 'n' or 'c' (without quotes) to restart execution at beginning of test method." \
            "\033[0m\n\n"
        )
        self.output("\033[93;1m============================================================\033[0m\n")

        pdb.post_mortem(orig_exc_traceback.tb_next)

        self.output("\033[93;1m============================================================\033[0m\n")
        self.output("\n\033[94mGoodTests ==> Restarting the method '%s' under debugger control.\033[0m\n" %(testFunction.__func__.__qualname__, ))

        self.output("\033[94m  (type 'help' followed by return for assistance with debugger)\033[0m\n")
        self.output("\033[94m Quick Ref (commands listed within square-brackets; enter commands without the bracket):\n\n" \
            "\t[n]\t\t  - Execute current line and proceed to next line\n" \
            "\t[s]\t\t  - Step into current line\n" \
            "\t[c]\t\t  - Continue Execution\n" \
            "\t[up/down]\t  - Move up or down in current stack\n" \
            "\t[print ( X )]\t  - Print the variable 'X' in current context.\n" \
            "\t[locals()]\t  - Print local variables in this scope\n" \
            "\t[arbitrary code]  - Execute arbitrary code at current level\033[0m\n"
        )
        self.output("\033[93;1m============================================================\033[0m\n")

        return self.runTestMethod(instantiatedTestClass, testFile, testFunction, runUnderDebugger=True)



def printUsage():
    '''
        printUsage - Print  a "--help" listing of all supported arguments
    '''
    sys.stderr.write("""Usage:  GoodTests.py (options) [filesnames or directories]

  Options:

    -n [number]              - Specifies number of simultaneous executions 
                                 Default = # of processors (%d).
                                You must use "-n 1" if using pdb

    --pdb                    - When an assertion fails, drop to a pdb shell within
                                 the test code at the point of failure  ( forces -n1 )


    -m [regexp]              - Run methods matching a specific pattern

    -q                       - Quiet (only print failures)
                                  This will also disable stdout during test execution

    -t                       - Print extra timing information


    --no-colour              - Strip out colours from output
    --no-color

    --version                - Print version and copyright information
    --help                   - Show this message


""" %(DEFAULT_MAX_RUNNERS,))



def main(args):
    '''
        main - Begin execution of GoodTests.py with given list of arguments.

            This is called when you run "GoodTests.py [someDir]"

          @param args list<str> - A list of arguments ( sys.argv[1:] ) 

          @return <int> - The exitcode for this execution (for use with sys.exit)

            # TODO: We currently exit with code "0" if tests fail. Should this be changed to "1"?

    '''

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
    usePdb = False


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
            return 0
        elif arg in versionArgs:
            sys.stdout.write('GoodTests.py version %s by Timothy Savannah (c) 2011 - 2017 LGPL version 2.1\n' %(VERSION,))
            return 0
        elif arg.startswith('-n'):
            if arg[2:].strip().isdigit():
                maxRunners = int(arg[2:].strip())
                i += 1
            else:
                if i+1 == numArgs or args[i+1].isdigit() is False:
                    sys.stderr.write('-n requires a numeric argument\n')
                    return 1
                maxRunners = int(args[i+1])
                i += 2
        elif arg == '-q':
            printFailuresOnly = True
            i += 1
        elif arg.startswith('-m'):
            if arg == '-m':
                if i+1 == numArgs:
                    sys.stderr.write('-m needs a value\n')
                    return 1
                specificTestPattern = args[i+1]
                i += 2
            else:
                specificTestPattern = arg[2:]
                i += 1
        elif arg == '--pdb':
            usePdb = True
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
        tester = GoodTests(maxRunners=maxRunners, printFailuresOnly=printFailuresOnly, extraTimes=extraTimes, useColour=useColour, specificTestPattern=specificTestPattern, usePdb=usePdb)
    except ValueError as e:
        sys.stderr.write(str(e) + '\n')
        return 1

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
                return 1

            if os.path.isdir(filename):
                directories.append(filename)
            else:
                files.append(filename)

    # Run directory
    try:
        tester.runTests(directories, files)
    except KeyboardInterrupt:
        handle_sigTerm(None, None)

    return 0

if __name__ == "__main__":
    exitcode = main(sys.argv[1:])
    sys.exit(exitcode)
# vim: set ts=4 sw=4 st=4 expandtab
