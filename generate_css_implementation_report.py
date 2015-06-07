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
    parser.add_argument('--output', '-o', action='store', default='css-writing-modes-3.txt')
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
    generator.load_test_files(args.dir)
    generator.load_test_results(os.path.join(args.dir, '../../../TestExpectations'))
    if not args.output or args.output == '-':
        generator.write_report(args.template, sys.stdout)
    else:
        with open(args.output, 'w') as output:
            generator.write_report(args.template, output)

class W3CImplementationReportGenerator(object):
    def __init__(self):
        self.tests = {}

    class Test(object):
        def __init__(self, name):
            self.combo = None
            self._comment = None
            self.import_dir = None
            self.import_ext = None
            self._is_fail = False
            self._fail_conditions = set()
            self.name = name;
            self.testnames = []

        @property
        def is_import(self):
            return self.import_dir or self.combo and self.combo.import_dir

        @property
        def is_fail(self):
            return self._is_fail or len(self._fail_conditions) >= 3 or self.combo and self.combo.is_fail

        @property
        def comment(self):
            if len(self._fail_conditions) == 0 or self.is_fail:
                return self._comment
            return ', '.join(self._fail_conditions) + ': ' + (self._comment if self._comment else 'Fail')

        def set_result(self, conditions, is_pass, comment):
            if not is_pass:
                if not conditions:
                    self._is_fail = True
                else:
                    for condition in conditions:
                        self._fail_conditions.add(condition)
            else:
                if conditions:
                    comment = ', '.join(conditions) + ': ' + comment
            self._comment = comment

    def add_test(self, name):
        if name in self.tests:
            raise Error("File name conflicts: " + name)
        test = W3CImplementationReportGenerator.Test(name)
        self.tests[name] = test
        return test

    def load_test_files(self, directory):
        for root, filename in self.find_test_files(directory):
            name, ext = os.path.splitext(filename)
            test = self.add_test(name)
            test.import_dir = root
            test.import_ext = ext

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

    def load_test_results(self, expectations):
        for path, conditions, is_pass, comment in self.read_test_expectations(expectations):
            filename = os.path.basename(path)
            name, ext = os.path.splitext(filename)
            test = self.tests.get(name, None)
            if not test:
                log.warn("Test for a failure not found: %s", filename)
                continue
            test.set_result(conditions, is_pass, comment)

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
                    conditions = conditions.strip('[]').split() if conditions else None
                    if 'Pass' in results:
                        log.info("Flaky as Pass: %s", line)
                        yield (path, conditions, True, 'Flaky')
                        continue
                    if is_actually_pass:
                        log.info("Fail as pass: %s # %s", line, comment)
                        yield (path, conditions, True, comment)
                        continue
                    log.debug("Fail Expectation found: %s %s %s", conditions, path, results)
                    yield (path, conditions, False, None)
                    continue
                log.warn("Line unknown: %s", line)

    def write_report(self, input, output):
        input = urllib2.urlopen(input).read()
        for line in input.splitlines():
            line = self.get_report_line(line)
            if line is not None:
                output.write(line + '\n')
        total, coverage, fail = self.get_stats()
        output.write('# Total = {0}, Coverage = {1} ({2}%), Pass = {3} ({4}% of total, {5}% of coverage), Fail = {6} ({7}% of total, {8}% of coverage)\n'.format(
            total,
            coverage, coverage * 100 / total,
            coverage - fail, (coverage - fail) * 100 / total, (coverage - fail) * 100 / coverage,
            fail, fail * 100 / total, fail * 100 / coverage))

    def get_report_line(self, line):
        if not line or line[0] == '#':
            return line
        values = line.split('\t')
        if len(values) == 3 and values[1] == '?' and values[2] == '':
            test = self.get_test_from_testname(values[0])
            if not test:
                return None
            if test.is_fail:
                values[1] = 'fail'
            else:
                values[1] = 'pass'
            if not values[2] and test.comment:
                values[2] = test.comment
            return '\t'.join(values)
        if line != 'testname    result  comment':
            log.warn("Unrecognized line in template: %s", values)
        return line

    def get_test_from_testname(self, testname):
        filename = os.path.basename(testname)
        name, ext = os.path.splitext(filename)
        test = self.tests.get(name, None)
        if not test:
            test = self.add_test(name)
        test.testnames.append(testname)
        if not test.combo and re.search(r'-\d{3}[a-z]$', name): # if affix, find the combo test
            test.combo = self.tests.get(name[0:-1], None)
        if test.import_ext and test.import_ext.startswith(ext) or test.combo and test.combo.import_ext and test.combo.import_ext.startswith(ext):
            return test
        return None

    def get_stats(self):
        total = 0
        coverage = 0
        fail = 0
        for filename, test in self.tests.iteritems():
            if not test.testnames:
                log.warn('Not found in template: %s', filename)
                continue
            total += 1
            if test.is_import:
                coverage += 1
                if test.is_fail:
                    fail += 1
        log.info("Total = %d, Coverage = %d, Fail= %d", total, coverage, fail)
        return (total, coverage, fail)

main()
