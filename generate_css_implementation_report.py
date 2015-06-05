#!/usr/bin/env python

import argparse
import logging
import os
import re
import sys
import urllib2

log = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description='Generate CSS WG implementation reports from Blink repository.')
    parser.add_argument('--verbose', '-v', action='store_true')
    parser.add_argument('dir', nargs='?', default='~/src/chromium/src/third_party/WebKit/LayoutTests/imported/csswg-test/css-writing-modes-3')
    parser.add_argument('template', nargs='?', default='http://test.csswg.org/suites/css-writing-modes-3_dev/nightly-unstable/implementation-report-TEMPLATE.data')
    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)
    args.dir = os.path.expanduser(args.dir)
    generator = W3CImplementationReportGenerator()
    generator.load_test_results(args.dir)
    generator.write_report(args.template, sys.stdout)
    generator.get_stats()

class W3CImplementationReportGenerator(object):
    def __init__(self):
        pass

    class Test(object):
        def __init__(self, dir):
            self.dir = dir
            self.is_failed = False
            self.is_reported = False

    def load_test_results(self, directory):
        tests = {}
        for root, filename in self.find_test_files(directory):
            if filename in tests:
                log.warn("File name conflicts: %s", filename)
            tests[filename] = W3CImplementationReportGenerator.Test(root)

        expectations = os.path.join(directory, '../../../TestExpectations')
        for path in self.read_test_expectations(expectations):
            filename = os.path.basename(path)
            if not filename in tests:
                log.warn("Failure test not found: %s", filename)
                continue
            tests[filename].is_failed = True

        self.tests = tests

    def find_test_files(self, directory):
        dirs_to_skip = ('support',)
        for root, dirs, files in os.walk(directory):
            for d in dirs_to_skip:
                if d in dirs:
                    dirs.remove(d)

            for file in files:
                name, ext = os.path.splitext(file)
                if name.endswith('-expected'):
                    continue
                log.debug("Test file found: %s %s", root, file)
                yield (root, file)

    def read_test_expectations(self, path):
        pattern = re.compile(r'([^\[]+)(\[[^\]]+])?\s+(\S+)\s+\[\s*([^\]]+)]$')
        with open(path) as file:
            for line in file:
                line = line.strip()
                if not line or line[0] == '#':
                    continue
                match = pattern.match(line)
                if match:
                    condition, path, results = match.group(2, 3, 4)
                    if not path.startswith('imported/csswg-test/css-writing-modes-3/'):
                        continue
                    results = results.rstrip().split()
                    if 'Pass' in results:
                        log.info("Flaky as Pass: %s", line)
                        continue
                    if condition:
                        log.info("Conditional as Pass: %s", line)
                        continue
                    log.debug("Expectation found: %s %s %s", condition, path, results)
                    yield path
                    continue
                log.warn("Line unknown: %s", line)

    def write_report(self, input, output):
        input = urllib2.urlopen(input).read()
        for line in input.splitlines():
            line = self.get_report_line(line)
            if line is not None:
                output.write(line + '\n')

    def get_report_line(self, line):
        if not line or line[0] == '#':
            return line
        values = line.split('\t')
        if len(values) == 3 and values[1] == '?' and values[2] == '':
            filename = os.path.basename(values[0])
            test = self.find_test(filename)
            if not test:
                return None
            if test.is_failed:
                values[1] = 'fail'
            else:
                values[1] = 'pass'
            test.is_reported = True
            return '\t'.join(values)
        if line != 'testname    result  comment':
            log.warn("Unrecognized line in template: %s", values)
        return line

    def find_test(self, filename):
        test = self.tests.get(filename, None)
        if test:
            return test
        name, ext = os.path.splitext(filename)
        if ext == '.htm':
            test = self.tests.get(filename + 'l', None)
            if test:
                return test
        if re.search(r'-\d{3}[a-z]$', name): # if affix, find the combo test
            return self.find_test(name[0:-1] + ext)
        return None

    def get_stats(self):
        passed = 0
        failed = 0
        for filename, test in self.tests.iteritems():
            if not test.is_reported:
                log.warn('Not found in template: %s', filename)
            elif test.is_failed:
                failed += 1
            else:
                passed += 1
        log.info("Total = %d, Passed = %d, Failed = %d", passed + failed, passed, failed)

main()
