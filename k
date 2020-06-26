#! /usr/bin/env bash

out=${1/.epub/.mobi}
kindle/kindlegen $1 -o temp.mobi -verbose
ebook-convert temp.mobi $out --mobi-file-type both
rm -f temp.mobi
