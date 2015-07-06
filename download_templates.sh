#!/bin/bash
cd css-writing-modes-3
curl -O http://test.csswg.org/suites/css-writing-modes-3_dev/nightly-unstable/implementation-report-TEMPLATE.data
git diff implementation-report-TEMPLATE.data
cd ..
