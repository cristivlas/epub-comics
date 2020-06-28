#! /usr/bin/calibre-debug
#
# calibre-debug
#
from calibre.ebooks.oeb.base import Manifest, Metadata
from calibre.ebooks.oeb.polish.container import get_container
from calibre.ebooks.mobi.writer2.resources import Resources
from calibre.ebooks.mobi.writer8.main import KF8Writer
from calibre.ebooks.mobi.writer8.mobi import KF8Book
from calibre.ebooks.mobi.writer8.exth import EXTH_CODES


import sys
from os import path

amzn_exth_codes = {
    u'fixed-layout': 122,
    u'book-type': 123,
    u'orientation-lock': 124,
    u'original-resolution': 126,
    u'zero-gutter': 127,
    u'zero-margin': 128,
    u'RegionMagnification': 132,
    u'KF8_Count_of_Resources_Fonts_Images': 125,
    u'KF8_Masthead/Cover_Image': 129,
    u'Language': 524,
    u'primary-writing-mode': 525,
    u'(542)':542,
    u'(547)': 547,
}

comic_book_exth_values = {
    'fixed-layout': 'true',
    'book-type': 'comic',
    'orientation-lock': 'portrait',
    'original-resolution': '960x1280',
    'zero-gutter': 'true',
    'zero-margin': 'true',
    'KF8_Count_of_Resources_Fonts_Images': 0,
    #'(542)':'C1te',
    #'(547)': 'InMemory'
}

def patch_exth_codes():
    for c in amzn_exth_codes:
        if EXTH_CODES.has_key(c):
            print ('EXTH code already defined: ', c)
        EXTH_CODES[c] = amzn_exth_codes[c]

def dump_metadata(metadata):
    for k in metadata:
        for item in metadata[k]:
            print ('{}: {}'.format(k, item))


def fixup_metadata(oeb):
    metadata = Metadata(oeb)
    for k in oeb.metadata:
        v = oeb.metadata[k]
        if k in ['contributor']:
            print ('stripping {}: {}'.format(k, v))
            continue
        for i in v:
            if k=='language' and i.value=='eng':
                metadata.add(k, 'en')
            else:
                metadata[k].append(i)

    for k,v in comic_book_exth_values.items():
        metadata.add(k,v)

    oeb.metadata = metadata


def create_kf8_book(oeb, opts, resources, for_joint=False):
    fixup_metadata(oeb)
    writer = KF8Writer(oeb, opts, resources)
    book = KF8Book(writer, for_joint=for_joint)
    dump_metadata(book.metadata)
    return book


def set_cover_image(oeb):
    if not oeb.metadata['cover']:            
        cover = None
        for _, item in oeb.manifest.hrefs.items():
            #if item.id in [ 'cover-image', 'img-0' ]:
            if item.id in [ 'cover-image' ]:
                if not cover or item.id == 'cover-image':
                    cover = item.id
        if cover:
            oeb.metadata.add('cover', cover)

                

def opf_to_book(opf, outpath, container):
    from calibre.ebooks.conversion.plumber import Plumber, create_oebbook

    class Item(Manifest.Item):

        def _parse_css(self, data):
            # The default CSS parser used by oeb.base inserts the h namespace
            # and resolves all @import rules. We dont want that.
            return container.parse_css(data)

    def specialize(oeb):
        oeb.manifest.Item = Item

    plumber = Plumber(opf, outpath, container.log)
    plumber.setup_options()

    oeb = create_oebbook(container.log, opf, plumber.opts, specialize=specialize)
    set_cover_image(oeb)

    # Generate KF8 Book
    plumber.opts.dont_compress = True
    plumber.opts.toc_title = None
    plumber.opts.mobi_toc_at_start = False
    plumber.opts.no_inline_toc = True
    plumber.opts.mobi_periodical = False
    
    res = Resources(oeb, plumber.opts, False, process_images=False)

    book = create_kf8_book(oeb, plumber.opts, res, False)
    
    #... and write it out
    book.opts.prefer_author_sort = False
    book.opts.share_not_sync = False

    book.write(outpath)


def epub_to_book(epub, outpath=None):
    container = get_container(epub, tweak_mode=True)
    outpath = outpath or (epub.rpartition('.')[0] + '.azw3')
    opf_to_book(container.name_to_abspath(container.opf_name), outpath, container)


def extract_mobi(mobi_path, extract_to):
     from calibre.ebooks.mobi.debug.main import inspect_mobi
     inspect_mobi(mobi_path, ddir=extract_to)


def main(argv=sys.argv):
    input_path = sys.argv[1]
    if input_path.endswith('.mobi'):
        extract_mobi(input_path, path.splitext(input_path)[0] + '_extracted_mobi')
    else:        
        output_path = path.splitext(input_path)[0] + '.azw3'
        patch_exth_codes()
        epub_to_book(input_path, output_path)

if __name__ == '__main__':
    main()