#!/usr/bin/env python
# https://wiki.csswg.org/test/implementation-report

import argparse
import csv
import json
import logging
import os
import re
import sys

log = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description='Generate CSS WG implementation reports from Blink repository.')
    parser.add_argument('--json', '-j', action='store', default='css-writing-modes-3/implementation-report.json')
    parser.add_argument('--output', '-o', action='store', default='css-writing-modes-3/implementation-report.txt')
    parser.add_argument('--verbose', '-v', action='count')
    parser.add_argument('dir', nargs='?', default='~/src/chromium/src/third_party/WebKit/LayoutTests/imported/csswg-test/css-writing-modes-3')
    parser.add_argument('results', nargs='?', default='css-writing-modes-3/results.csv')
    parser.add_argument('template', nargs='?', default='css-writing-modes-3/implementation-report-TEMPLATE.data')
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
    with open(os.path.join(args.dir, '../../../TestExpectations')) as expectations:
        generator.load_test_expectations(expectations)
    with open(args.results) as results:
        generator.load_test_results(results)
    with open(args.template) as template:
        generator.load_template(template)
    if not args.output or args.output == '-':
        generator.write_report(sys.stdout)
    else:
        with open(args.output, 'w') as output:
            generator.write_report(output)
    with open(args.json, 'w') as output:
        generator.write_json(output)

class W3CImplementationReportGenerator(object):
    def __init__(self):
        self.tests = {}

    class Test(object):
        def __init__(self, id):
            self.id = id
            self.combo = None
            self.combo_of = []
            self.import_dir = None
            self.import_ext = None
            self.import_result = None
            self.submit_result = None
            self.revision = None
            self.testnames = []

        @property
        def _result(self):
            if self.import_result:
                if len(self.import_result.conditions) >= 3:
                    return 'fail'
                return self.import_result.result
            if self.submit_result:
                return self.submit_result.result
            return None

        @property
        def result(self):
            result = self._result
            if result:
                return result
            if self.combo:
                return self.combo._result
            if self.combo_of:
                if all([c._result == 'pass' for c in self.combo_of]):
                    return 'pass'
                return 'fail'
            return '?'

        @property
        def source(self):
            if self.import_result:
                return 'blink'
            if self.submit_result:
                if not self.submit_result.reliability:
                    return 'anonymous'
                return self.submit_result.source
            if self.combo:
                return self.combo.source
            return None

        @property
        def reliability(self):
            if self.import_result:
                return 2
            if self.submit_result:
                return self.submit_result.reliability
            if self.combo:
                return self.combo.reliability
            return 0

        @property
        def comment(self):
            if self.import_result:
                return self.import_result.comment
            if self.submit_result and self.submit_result.reliability == 0:
                return 'Anonymous'
            return None

        def set_import(self, dir, ext):
            self.import_dir = dir
            self.import_ext = ext
            self.import_result = W3CImplementationReportGenerator.ImportTestResult('pass')

        def add_expectation(self, conditions, result, comment):
            assert self.import_result
            self.import_result.result = result
            if conditions:
                for condition in conditions:
                    self.import_result.conditions.add(condition)
            self.import_result._comment = comment

        def add_submit_result(self, result):
            if result.precedes(self.submit_result):
                self.submit_result = result

    class ImportTestResult(object):
        def __init__(self, result):
            self.result = result
            self.conditions = set()
            self._comment = None

        @property
        def comment(self):
            if 3 > len(self.conditions) > 0:
                return ', '.join(self.conditions) + ': ' + (self._comment if self._comment else self.result)
            return self._comment

    class SubmitTestResult(object):
        def __init__(self, result, source, date):
            self.result = result
            self.source = source
            self.reliability = W3CImplementationReportGenerator.SubmitTestResult.reliability_from_source(source)
            self.date = date

        def precedes(self, other):
            if not other:
                return True
            if self.reliability != other.reliability:
                return self.reliability > other.reliability
            return self.date > other.date

        known_sources = set(('gtalbot', 'hshiozawa', 'kojiishi', 'lemoned'))
        @staticmethod
        def reliability_from_source(source):
            if source in W3CImplementationReportGenerator.SubmitTestResult.known_sources:
                return 1;
            return 0;

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
            test.set_import(root, ext)

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

    def load_test_expectations(self, expectations):
        for path, conditions, result, comment in self.read_test_expectations(expectations):
            filename = os.path.basename(path)
            name, ext = os.path.splitext(filename)
            test = self.tests.get(name, None)
            if not test:
                log.warn("Test for TestExpectations not found: %s", filename)
                continue
            test.add_expectation(conditions, result, comment)

    def read_test_expectations(self, expectations):
        pattern = re.compile(r'([^\[]+)(\[[^\]]+])?\s+(\S+)\s+\[\s*([^\]]+)]$')
        comment = None
        is_actually_pass = False
        for line in expectations:
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
                    yield (path, conditions, 'pass', 'Flaky')
                    continue
                if is_actually_pass:
                    log.info("Fail as pass: %s # %s", line, comment)
                    yield (path, conditions, 'pass', comment)
                    continue
                log.debug("Fail Expectation found: %s %s %s", conditions, path, results)
                yield (path, conditions, 'fail', None)
                continue
            log.warn("Line unknown: %s", line)

    def load_test_results(self, results):
        reader = csv.reader(results)
        header = next(reader)
        for row in reader:
            useragent = row[6]
            if not 'Chrome/' in useragent:
                continue
            test = self.get_test_from_testcase(row[0])
            result = W3CImplementationReportGenerator.SubmitTestResult(row[1], row[4], row[3])
            test.add_submit_result(result)

    def load_template(self, template):
        for line in template:
            line = line.rstrip()
            if not line or line[0] == '#':
                continue
            values = line.split('\t')
            if len(values) >= 3:
                if values[2] == '?':
                    test = self.get_test_from_testname(values[0])
                    test.revision = values[1]
                    continue
                if values[0] == 'testname':
                    continue
            log.warn("Unrecognized line in template: %s", line)

    def get_test_from_testname(self, testname):
        filename = os.path.basename(testname)
        name, ext = os.path.splitext(filename)
        test = self.get_test_from_testcase(name)
        test.testnames.append(testname)
        return test

    def get_test_from_testcase(self, name):
        test = self.tests.get(name)
        if not test:
            test = self.add_test(name)
        if not test.combo and re.search(r'-\d{3}[a-z]$', name): # if affix, find the combo test
            combo = self.tests.get(name[0:-1])
            if combo:
                test.combo = combo
                combo.combo_of.append(test)
        return test

    def write_report(self, output):
        total = 0
        coverage = 0
        passed = 0
        imported = 0
        imported_passed = 0
        for test in sorted(self.tests.itervalues(), key=lambda t: t.id):
            if not test.testnames:
                log.warn('Not found in template: %s', test.id)
                continue
            total += 1
            result = test.result
            values = [test.testnames[0], test.revision, result]
            line = '\t'.join(values)
            is_passed = result == 'pass'
            if is_passed:
                coverage += 1
                passed += 1
            elif result == 'fail':
                coverage += 1
            if test.import_result or test.combo and test.combo.import_result:
                imported += 1
                if is_passed:
                    imported_passed += 1
            else:
                line = "# " + line
            if test.comment:
                line += " # " + test.comment
            output.write(line + "\n")
        output.write('# Total = {0}, Coverage = {1} ({2}%), Pass = {3} ({4}% of total, {5}% of coverage), Fail = {6} ({7}% of total, {8}% of coverage)\n'.format(
            total,
            coverage, coverage * 100 / total,
            passed, passed * 100 / total, passed * 100 / coverage,
            coverage - passed, (coverage - passed) * 100 / total, (coverage - passed) * 100 / coverage))
        output.write('# Imported = {0} ({1}%), Pass = {2} ({3}% of total, {4}% of imported), Fail = {5} ({6}% of total, {7}% of imported)\n'.format(
            imported, imported * 100 / total,
            imported_passed, imported_passed * 100 / total, imported_passed * 100 / imported,
            imported - imported_passed, (imported - imported_passed) * 100 / total, (imported - imported_passed) * 100 / imported))

    def write_json(self, output):
        tests = []
        for test in sorted(self.tests.itervalues(), key=lambda t: t.id):
            if not test.testnames:
                continue
            tests.append({
                'id': test.id,
                'result': test.result,
                'source': test.source,
            })
        json.dump(tests, output, indent=0)

main()
