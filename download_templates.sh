#!/bin/bash
cd css-writing-modes-3
curl -O http://test.csswg.org/suites/css-writing-modes-3_dev/nightly-unstable/implementation-report-TEMPLATE.data
curl -O http://test.csswg.org/suites/css-writing-modes-3_dev/nightly-unstable/testinfo.data
git diff *.data
cd ..
