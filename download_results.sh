#!/bin/bash
cd css-writing-modes-3
curl -O http://test.csswg.org/suites/css-writing-modes-3_dev/nightly-unstable/results.zip
unzip -o results.zip
rm results.zip
(head -n 1 results.csv && tail -n +2 results.csv | sort -t , -k 4) > results_sorted.csv
mv -f results_sorted.csv results.csv
git diff results.csv
cd ..
