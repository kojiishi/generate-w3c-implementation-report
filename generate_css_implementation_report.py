#!/usr/bin/env python
# https://wiki.csswg.org/test/implementation-report

import argparse
import logging
import os
import re
import sys
import urllib2

log = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description='Generate CSS WG implementation reports from Blink repository.')
    parser.add_argument('--output', '-o', action='store', default='implementation-report.txt')
    parser.add_argument('--verbose', '-v', action='count')
    parser.add_argument('dir', nargs='?', default='~/src/chromium/src/third_party/WebKit/LayoutTests/imported/csswg-test/css-writing-modes-3')
    parser.add_argument('template', nargs='?', default='http://test.csswg.org/suites/css-writing-modes-3_dev/nightly-unstable/implementation-report-TEMPLATE.data')
    args = parser.parse_args()
    if args.verbose > 1:
        logging.basicConfig(level=logging.DEBUG)
    elif args.verbose:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)
    args.dir = os.path.expanduser(args.dir)
    generator = W3CImplementationReportGenerator()
    generator.load_test_results(args.dir)
    if not args.output or args.output == '-':
        generator.write_report(args.template, sys.stdout)
    else:
        with open(args.output, 'w') as output:
            generator.write_report(args.template, output)
    generator.get_stats()

class W3CImplementationReportGenerator(object):
    def __init__(self):
        pass

    class Test(object):
        def __init__(self, dir):
            self.dir = dir
            self.is_failed = False
            self.is_in_template = False
            self.comment = None

    def load_test_results(self, directory):
        tests = {}
        for root, filename in self.find_test_files(directory):
            if filename in tests:
                log.warn("File name conflicts: %s", filename)
            tests[filename] = W3CImplementationReportGenerator.Test(root)

        expectations = os.path.join(directory, '../../../TestExpectations')
        for path, is_pass, comment in self.read_test_expectations(expectations):
            filename = os.path.basename(path)
            if not filename in tests:
                log.warn("Failure test not found: %s", filename)
                continue
            test = tests[filename]
            test.is_failed = not is_pass
            test.comment = comment

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
        comment = None
        is_actually_pass = False
        with open(path) as file:
            for line in file:
                line = line.strip()
                if not line:
                    comment = None
                    is_actually_pass = False
                    continue
                if line[0] == '#':
                    comment = line[1:].strip()
                    is_actually_pass = 'pass but' in comment
                    continue
                match = pattern.match(line)
                if match:
                    conditions, path, results = match.group(2, 3, 4)
                    if not path.startswith('imported/csswg-test/css-writing-modes-3/'):
                        continue
                    results = results.rstrip().split()
                    if 'Pass' in results:
                        log.info("Flaky as Pass: %s", line)
                        continue
                    if conditions:
                        log.info("Conditional as Pass: %s", line)
                        yield (path, True, conditions + (' ' + comment if comment else ''))
                        continue
                    log.debug("Expectation found: %s %s %s", conditions, path, results)
                    if is_actually_pass:
                        log.info("Fail as pass: %s # %s", line, comment)
                        yield (path, True, comment)
                        continue
                    yield (path, False, None)
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
            if not values[2] and test.comment:
                values[2] = test.comment
            test.is_in_template = True
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
            if not test.is_in_template:
                log.warn('Not found in template: %s', filename)
            elif test.is_failed:
                failed += 1
            else:
                passed += 1
        log.info("Total = %d, Passed = %d, Failed = %d", passed + failed, passed, failed)

main()
