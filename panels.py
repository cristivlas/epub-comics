import numpy as np
import sys
from PIL import Image, ImageDraw
from os import path

class Extractor:
    def __init__(self, name='image', threshold=200, min_size=50):
        self.name = name
        self.threshold = threshold
        self.min_size = min_size
        self.panels = {}

    @staticmethod
    def cropbox(im, threshold):
        a = np.array(im)
        a = a.T
        f = np.nonzero(np.mean(a,axis=0)<threshold)
        return [min(f[0]), min(f[1]), max(f[0])+1, max(f[1])+1]

    @staticmethod
    def autocrop(im, threshold, xy):
        box = Extractor.cropbox(im, threshold)
        return im.crop(box), [xy[0]+box[0], xy[1]+box[1]]

    def down(self, im, xy):
        a = np.array(im)
        a = a.T        
        f = np.all(np.mean(a,axis=0)>=self.threshold, axis=0)
        y = min(np.nonzero(f))
        if len(y):
            y = min(y)
            return [self.panels_from_image(im.crop((0, 0, im.size[0], y)), xy),
                    self.panels_from_image(im.crop((0, y, im.size[0], im.size[1])), [xy[0], xy[1]+y])]

    def across(self, im, xy):
        a = np.array(im)
        a = a.T
        f = np.all(np.mean(a,axis=0)>=self.threshold, axis=1)
        x = min(np.nonzero(f))
        if len(x):
            x = min(x)
            return [self.panels_from_image(im.crop((0, 0, x, im.size[1])), xy),
                    self.panels_from_image(im.crop((x, 0, im.size[0], im.size[1])), [xy[0]+x, xy[1]])]

    @staticmethod
    def open(filename):
        im = Image.open(filename)
        if im.mode[:3] != 'RGB':
            im = im.convert('RGB')
        elif im.mode == 'RGBA':
            im2 = Image.new('RGB', im.size, (255, 255, 255))
            im2.paste(im, (0,0), im)
            im = im2
        return im

    def panels_from_image(self, im, xy=[0,0]):
        assert im
        assert len(xy)==2, xy
        p = Extractor.autocrop(im, self.threshold, xy)
        if not self.down(*p) and not self.across(*p):
            count = len(self.panels)
            name = path.splitext(self.name)[0] + str(count).zfill(3)
            if im.size[0] > self.min_size and im.size[1] > self.min_size:
                assert len(p[1])==2, p
                self.panels[name]=p
        return self.panels

    def panels_from_file(self, filename):
        return self.panels_from_image(Extractor.open(filename), [0,0])


if __name__ == '__main__':
    if (len(sys.argv) != 2):
        print("\nUsage: python {} input_file\n".format(sys.argv[0]))
        sys.exit(1)
    filename = sys.argv[1]

    for n, (im, xy) in Extractor().panels_from_file(filename).items():
        print (n, im, xy)            