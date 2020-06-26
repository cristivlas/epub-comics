#! /usr/bin/env bash
in=$1
out=${in/.epub/.mobi}
shift 1
temp_file=$(mktemp tmp-XXXXX.mobi)
echo $temp_file
kindle/kindlegen $in -o $temp_file $@
ebook-convert $temp_file $out --mobi-file-type new
rm -f $temp_file
