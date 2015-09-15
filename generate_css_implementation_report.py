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
    parser.add_argument('tests', nargs='?', default='~/src/chromium/src/third_party/WebKit/LayoutTests/imported/csswg-test/css-writing-modes-3')
    parser.add_argument('results', nargs='?', default='css-writing-modes-3/results.csv')
    parser.add_argument('template', nargs='?', default='css-writing-modes-3/implementation-report-TEMPLATE.data')
    args = parser.parse_args()
    if args.verbose > 1:
        logging.basicConfig(level=logging.DEBUG)
    elif args.verbose:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)
    args.tests = os.path.expanduser(args.tests)
    generator = W3CImplementationReportGenerator()
    with open(args.template) as template:
        generator.load_template(template)
    with open(args.results) as results:
        generator.load_test_results(results)
    generator.load_imported_files(args.tests)
    with open(os.path.join(args.tests, '../../../TestExpectations')) as expectations:
        generator.load_test_expectations(expectations)
    with open(os.path.join(args.tests, '../../../W3CImportExpectations')) as expectations:
        generator.load_import_expectations(expectations)
    generator.merge_results()
    if not args.output or args.output == '-':
        generator.write_report(sys.stdout)
    else:
        with open(args.output, 'w') as output:
            generator.write_report(output)
    with open(args.json, 'w') as output:
        generator.write_json(output)

class TestResult(object):
    def __init__(self, engine, result, source):
        self.engine = engine
        self._result = result
        self.source = source

    @property
    def result(self):
        return self._result

    def compare_precedence(self, other):
        if not other:
            return 1
        if self.is_imported != other.is_imported:
            return 1 if self.is_imported else -1
        if self.is_imported:
            return 0
        if self.reliability != other.reliability:
            return self.reliability - other.reliability
        return 0

    def precedes(self, other):
        return self.compare_precedence(other) > 0

class ImportTestResult(TestResult):
    def __init__(self, result):
        super(ImportTestResult, self).__init__("Blink", result, "blink")
        self.reliability = 2
        self._comment = None
        self.conditions = set()

    @property
    def result(self):
        if len(self.conditions) >= 3:
            return 'fail'
        if len(self.conditions) > 0:
            return 'pass'
        return super(ImportTestResult, self).result

    @result.setter
    def result(self, value):
        self._result = value

    @property
    def is_imported(self):
        return self._result != "skip"

    @property
    def comment(self):
        if 3 > len(self.conditions) > 0:
            return ', '.join(self.conditions) + ': ' + (self._comment if self._comment else "fail")
        return self._comment

class SubmitTestResult(TestResult):
    def __init__(self, result, source, date, engine, useragent):
        if engine == 'WebKit' and 'Chrome/' in useragent:
            engine = "Blink"
        super(SubmitTestResult, self).__init__(engine, result, source)
        self.reliability = SubmitTestResult.reliability_from_source(source)
        self.is_imported = False
        self.date = date
        self.comment = None

    def compare_precedence(self, other):
        precedence = super(SubmitTestResult, self).compare_precedence(other)
        if precedence:
            return precedence
        assert other.date
        if self.date > other.date:
            return 1
        elif self.date < other.date:
            return -1
        return 0

    known_sources = set(('fantasai', 'gtalbot', 'hshiozawa', 'kojiishi', 'lemoned', 'upsuper'))
    @staticmethod
    def reliability_from_source(source):
        if source in SubmitTestResult.known_sources:
            return 1;
        return 0;

class Test(object):
    def __init__(self, id):
        self.id = id
        self.combo = None
        self.combo_of = []
        self.results = {}
        self.import_result = None
        self.revision = None
        self.testnames = []
        self.issue = None

    def result_for_engine(self, engine, direction = 0):
        return self.results.get(engine)

    def add_result(self, result):
        if result.precedes(self.results.get(result.engine)):
            self.results[result.engine] = result

    def add_issue(self, url):
        assert not self.issue
        self.issue = url

    def set_imported(self, result = 'pass'):
        assert not self.import_result
        self.import_result = ImportTestResult(result)

    def clear_imported(self):
        assert self.import_result
        self.import_result = None

    def add_test_expectation(self, conditions, result, comment):
        assert self.import_result
        self.import_result.result = result
        if conditions:
            for condition in conditions:
                self.import_result.conditions.add(condition)
        self.import_result._comment = comment

    def add_import_expectation(self, result, comment):
        assert not self.import_result
        self.import_result = ImportTestResult(result)
        self.import_result._comment = comment

    def merge_results(self):
        if self.import_result:
            self.import_result.contributor_result = self.results.get("Blink")
            self.results["Blink"] = self.import_result

    def resolve_combo_results(self):
        combo = self.combo
        if combo:
            for engine, result in self.results.iteritems():
                combo_result = combo.results.get(engine)
                precedence = result.compare_precedence(combo_result)
                if precedence > 0:
                    combo.results[engine] = result
                elif precedence < 0:
                    self.results[engine] = combo_result
                elif result.result != "pass" and combo_result.result == "pass":
                    combo.results[engine] = result

class W3CImplementationReportGenerator(object):
    def __init__(self):
        self.tests = {}

    def add_test(self, name):
        if name in self.tests:
            raise Error("File name conflicts: " + name)
        test = Test(name)
        self.tests[name] = test
        return test

    def test_from_id_or_add(self, name):
        test = self.tests.get(name)
        if not test:
            test = self.add_test(name)
        return test

    def test_from_testname_or_add(self, testname):
        filename = os.path.basename(testname)
        name, ext = os.path.splitext(filename)
        test = self.test_from_id_or_add(name)
        test.testnames.append(testname)
        return test

    def test_from_path(self, path):
        filename = os.path.basename(path)
        name, ext = os.path.splitext(filename)
        return self.tests.get(name)

    def merge_results(self):
        for test in self.tests.itervalues():
            if re.search(r'-\d{3}[a-z]$', test.id): # if affix, find the combo test
                test.combo = self.tests.get(test.id[0:-1])
            test.merge_results()
        for test in self.tests.itervalues():
            test.resolve_combo_results()

    def load_template(self, template):
        for line in template:
            line = line.rstrip()
            if not line or line[0] == '#':
                continue
            values = line.split('\t')
            if len(values) >= 3:
                if values[2] == '?':
                    test = self.test_from_testname_or_add(values[0])
                    test.revision = values[1]
                    continue
                if values[0] == 'testname':
                    continue
            log.warn("Unrecognized line in template: %s", line)

    def load_test_results(self, results):
        reader = csv.reader(results)
        header = next(reader)
        for row in reader:
            test = self.test_from_id_or_add(row[0])
            result = SubmitTestResult(row[1], row[4], row[3], row[5], row[6])
            test.add_result(result)

    def load_imported_files(self, directory):
        for root, filename in self.find_imported_files(directory):
            name, ext = os.path.splitext(filename)
            test = self.test_from_id_or_add(name)
            test.set_imported('fail' if os.path.exists(os.path.join(root, name + '-expected.txt')) else 'pass')

    def find_imported_files(self, directory):
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
        pattern = re.compile(r'([^\[]+)(\[[^\]]+])?\s+(\S+)\s+\[\s*([^\]]+)]$')
        comment = None
        result_override = None
        for line in expectations:
            line = line.strip()
            if not line:
                comment = None
                result_override = None
                continue
            if line[0] == '#':
                comment = line[1:].strip()
                if 'pass but' in comment:
                    result_override = 'pass'
                else:
                    result_override = None
                log.debug("Comment found, ovrrride=%s: %s", result_override, comment)
                continue
            match = pattern.match(line)
            if match:
                conditions, path, results = match.group(2, 3, 4)
                if not path.startswith('imported/csswg-test/css-writing-modes-3/'):
                    continue
                test = self.test_from_path(path)
                if not test:
                    log.warn("Test for TestExpectations not found: %s", path)
                    continue
                results = results.rstrip().split()
                conditions = conditions.strip('[]').split() if conditions else None
                if 'Pass' in results:
                    log.info("Flaky as Pass: %s", line)
                    test.add_test_expectation(conditions, 'pass', 'Flaky')
                    continue
                if result_override:
                    log.info("Override %s as %s: %s # %s", results, result_override, line, comment)
                    test.add_test_expectation(conditions, result_override, comment)
                    continue
                if results == ['Skip']:
                    test.clear_imported()
                    continue
                if 'Failure' in results or 'ImageOnlyFailure' in results:
                    log.debug("Fail Expectation found: %s %s %s", conditions, path, results)
                    test.add_test_expectation(conditions, 'fail', None)
                    continue
                log.warn("Unsupported results ignored: %s", line)
                continue
            log.warn("Line unknown: %s", line)

    def load_import_expectations(self, expectations):
        pattern = re.compile(r'^(\S+)\s+\[\s*([^\]]+)]$')
        issue_pattern = re.compile(r'https://github\.com/w3c/[-\w]+/issues/\d+')
        comment = None
        result = "skip"
        issue_url = None
        for line in expectations:
            line = line.strip()
            if not line:
                comment = None
                result = "skip"
                issue_url = None
                continue
            if line[0] == '#':
                comment = line[1:].lstrip()
                match = issue_pattern.search(comment)
                if match:
                    result = "invalid"
                    issue_url = match.group(0)
                    continue
                issue_url = None
                if 'have known issues' in comment:
                    result = "invalid"
                elif 'do not plan to support' in comment:
                    result = 'not_supported'
                elif '"combo"' in comment:
                    result = None
                else:
                    result = "skip"
                continue
            if not result:
                continue
            match = pattern.match(line)
            if match:
                path, results = match.group(1, 2)
                if not path.startswith('imported/csswg-test/css-writing-modes-3/'):
                    continue
                results = results.rstrip().split()
                log.debug("ImportExpectations found: %s %s", results, path)
                test = self.test_from_path(path)
                if not test:
                    log.warn("Test for W3CImportExpectations not found: %s", path)
                    continue
                test.add_import_expectation(result, comment)
                if issue_url:
                    test.add_issue(issue_url)
                continue
            log.warn("ImportExpectations: Line unknown: %s", line)

    def write_report(self, output):
        total = 0
        coverage = 0
        passed = 0
        imported = 0
        imported_passed = 0
        output.write("\t".join(["testname", "revision", "result", "comment"]) + "\n")
        for test in sorted(self.tests.itervalues(), key=lambda t: t.id):
            if not test.testnames:
                log.warn('Not found in template: %s', test.id)
                continue
            total += 1
            result = test.result_for_engine("Blink")
            if not result:
                output.write("# " + "\t".join((test.testnames[0], test.revision, "?")) + "\n")
                continue
            result_value = result.result
            if result_value == 'not_supported':
                result_value = 'fail'
            values = [test.testnames[0], test.revision, result_value]
            line = '\t'.join(values)
            is_passed = result_value == 'pass'
            if is_passed:
                coverage += 1
                passed += 1
            elif result_value == "fail":
                coverage += 1
            if result.is_imported:
                imported += 1
                if is_passed:
                    imported_passed += 1
            else:
                line = "# " + line
            if result.comment:
                line += " # " + result.comment
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
            test_json = {
                'id': test.id,
            }
            if test.issue:
                test_json["issue"] = test.issue
            for engine, result in test.results.iteritems():
                result_json = {
                    "result": result.result,
                }
                if result.reliability:
                    result_json["source"] = result.source
                test_json[engine] = result_json
            tests.append(test_json)
        json.dump(tests, output, indent=0, sort_keys=True)

main()
