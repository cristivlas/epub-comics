import cv2
import exhibit
import numpy as np
import sys
from PIL import Image, ImageDraw
from os import path


class Extractor:
    def __init__(self, name='image', threshold=240, min_size=100):
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

    def name_panel(self, num):
        return '{}{:03d}'.format(path.splitext(self.name)[0], num)

    @staticmethod
    def open(filename):
        f = exhibit.ImageFrame(filename)
        im = f.img
        if im.mode[:3] != 'RGB':
            im = im.convert('RGB')
        elif im.mode == 'RGBA':
            im2 = Image.new('RGB', im.size, (255, 255, 255))
            im2.paste(im, (0,0), im)
            im = im2
        f.img = im
        return f

    def panels_from_image(self, im:Image, xy=[0,0]):
        assert im.mode[:3]=='RGB'
        assert len(xy)==2, xy
        
        p = Extractor.autocrop(im, self.threshold, xy)
        if not self.down(*p) and not self.across(*p):
            count = len(self.panels)
            name = self.name_panel(count)
            if im.size[0] > self.min_size and im.size[1] > self.min_size:
                assert len(p[1])==2, p
                self.panels[name]=p
        return self.panels


def detect_panels_by_contour(img, div=16):
    img = np.array(img.convert('L'))
    img = cv2.fastNlMeansDenoising(img)
    img = cv2.threshold(img, 127, 255, cv2.THRESH_TOZERO)[1]    
    box = cv2.boundingRect(img)
    max_area = box[2] * box[3]
    min_area = (max_area)/div
    areas = []
    contours = cv2.findContours(img, cv2.RETR_TREE, cv2.CHAIN_APPROX_TC89_KCOS)[0]
    ap = None
    for cnt in contours:
        x,y,w,h = cv2.boundingRect(cnt)
        a = w*h
        if min_area < a < max_area:
            if ap and abs(ap-a)/max(a,ap) < 0.15:
                continue
            ap = a
            perc = abs(cv2.contourArea(cnt)-a)/a
            if perc <= 0.1:
                areas.append((x,y,x+w,y+h))
    return areas


class PanelExtractor(Extractor):
    def from_frame(self, f:exhibit.ImageFrame):
        #draw = ImageDraw.Draw(f.img)
        extra = {}
        panels = super().panels_from_image(f.img)
        for nm, (panel, xy) in panels.items():
            x,y = xy
            w,h = panel.size
            #draw.rectangle([x,y,x+w,y+h], outline='red', width=3)
            areas = detect_panels_by_contour(panel)
            for i, a in enumerate(areas):
                #draw.rectangle((a[0]+x, a[1]+y, a[2]+x, a[3]+y), outline='green', width=3)
                #n = self.name_panel(len(panels)+len(extra))
                n = nm + '-' + self.name_panel(i)
                #print (nm, len(panels), n)
                a = a[0]+x,a[1]+y,a[2]+x,a[3]+y
                extra[n] = f.img.crop(a), a[:2]
        for k,p in extra.items():
            panels[k]=p
        print (panels.keys())
        return panels


if __name__ == '__main__':
    if (len(sys.argv) != 2):
        print("\nUsage: python {} input_file\n".format(sys.argv[0]))
        sys.exit(1)
    filename = sys.argv[1]

    for n, (im, xy) in Extractor().panels_from_file(filename).items():
        print (n, im, xy)
