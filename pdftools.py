import PyPDF2
import warnings
import sys
from io import BytesIO
from os import path
from PIL import Image, JpegImagePlugin


class ImageExtractor:
    def __init__(self, filename):
        self.filename = filename
        self.images = []

    def __enter__(self):
        self.catch_warnings = warnings.catch_warnings()
        self.catch_warnings.__enter__()
        warnings.simplefilter('ignore')
        self.file = PyPDF2.PdfFileReader(open(self.filename, 'rb'))
        return self

    def __exit__(self, exType, exValue, backtrace):        
        self.file = None
        self.catch_warnings.__exit__(exType, exValue, backtrace)

    def _extract(self, pageNum: int, page):
        xObject = page['/Resources']['/XObject'].getObject()
        
        for obj in xObject:            
            obj = xObject[obj]
            if obj['/Subtype'] != '/Image':
                continue            
            filter = obj['/Filter']
            assert filter in [ '/FlateDecode', '/DCTDecode', '/JPXDecode'], filter
            img = Image.open(BytesIO(obj._data))
            self.images.append(img)

    def run(self):
        numPages = self.file.getNumPages()
        for i in range(0, numPages):
            self._extract(i, self.file.getPage(i))


def save_image(img, fname):
    print (fname)
    quantization = getattr(img, 'quantization', None)
    subsampling = JpegImagePlugin.get_sampling(img) if quantization else None
    if subsampling:
        img.save(fname, subsampling=subsampling, qtables=quantization)
    else:
        img.save(fname)


if __name__ == '__main__': 
    if (len(sys.argv) < 2):
        print("\nUsage: python {} input_file\n".format(sys.argv[0]))
        quit()
    
    filename = sys.argv[1]
    with ImageExtractor(filename) as extractor:
        extractor.run()
        print ('Extracted {} images'.format(len(extractor.images)))
                        
        for i, img in enumerate(extractor.images):
            save_image(img, 'page-{:05d}.jpg'.format(i))
