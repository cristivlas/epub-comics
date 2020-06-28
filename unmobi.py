#! /usr/bin/python3
import mobi
import shutil
import sys

def main(argv):
    input = sys.argv[1]
    if len(sys.argv) <= 2:
        output = input.replace('.mobi', '_unpacked_mobi')
    else:
        output = sys.argv[2]

    print ('Unpacking MOBI to {}'.format(output))
    tempdir, _ = mobi.extract(input)
    shutil.move(tempdir, output)


if __name__=='__main__':
    main(sys.argv)