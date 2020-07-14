
#! /usr/bin/python3
import cv2
import itertools
import os
import sys
import numpy as np
#import time
from PIL import Image, ImageDraw, JpegImagePlugin, UnidentifiedImageError

def split_across(t, r, im, xy):
    a = im.T
    f = np.all(a>=t, axis=1)
    x = min(np.nonzero(f))
    if len(x):        
        x = min(x)
        h,w = im.shape[:2]
        assert h and w
        return [split(t, r, im[0:h, 0:x], xy), split(t, r, im[0:h, x:x+w], [xy[0]+x, xy[1]])]


def split_down(t, r, im, xy):
    a = im.T
    f = np.all(a>=t, axis=0)
    y = min(np.nonzero(f))
    if len(y):
        y = min(y)
        h,w = im.shape[:2]
        assert h and w
        return [split(t, r, im[0:y,0:w], xy), split(t, r, im[y:y+h,0:w], [xy[0], xy[1]+y])]


def split(threshold, rects, im, xy=[0,0]):
    a = im.T
    f = np.nonzero(a<threshold)
    assert len(f[0]) and len(f[1])
    x1,y1,x2,y2 = [min(f[0]), min(f[1]), max(f[0])+1, max(f[1])+1]
    im = im[y1:y2, x1:x2]
    xy = [xy[0]+x1, xy[1]+y1]        
    if not split_down(threshold, rects, im, xy) and not split_across(threshold, rects, im, xy):
        h,w = im.shape[:2]
        rects.append((xy[0], xy[1], w, h))
    return rects


def auto_threshold(img, threshold=None):
    last = 0 if threshold is None else threshold

    for t in range(last+1, 256):
        _, img2 = cv2.threshold(img, t, 255, cv2.THRESH_BINARY)
        t2 = np.mean(img2)
        #print (t,t2)
        if 125 <= t2 <= 127:
            return t, img2

    for t in range(last, -1, -1):
        _, img2 = cv2.threshold(img, t, 255, cv2.THRESH_BINARY)
        t2 = np.mean(img2)      
        #print (t,t2)
        if 125 <= t2 <= 127:
            return t, img2
    return last, img2


def panelize_crop(im, threshold):
    kernel = np.ones((3, 3), np.uint8)
    im = cv2.erode(im, kernel, iterations=2)
    im = cv2.threshold(im, threshold, 255, cv2.ADAPTIVE_THRESH_MEAN_C)[1]    
    # recursive crop
    rects = []
    split(threshold, rects, im)
    return rects


def union(a,b):
    x = min(a[0], b[0])
    y = min(a[1], b[1])
    w = max(a[0]+a[2], b[0]+b[2]) - x
    h = max(a[1]+a[3], b[1]+b[3]) - y
    return (x, y, w, h)


def intersection(a,b):
    x = max(a[0], b[0])
    y = max(a[1], b[1])
    w = min(a[0]+a[2], b[0]+b[2]) - x
    h = min(a[1]+a[3], b[1]+b[3]) - y
    if w<0 or h<0: return ()
    return (x, y, w, h)


# def merge(rects):
#     #start = time.time()
#     num_rects = len(rects)
#     while (1):
#         keep_going = False
#         for ra, rb in itertools.combinations(rects, 2):
#             if intersection(ra, rb):
#                 if ra in rects:
#                     rects.remove(ra)
#                 if rb in rects:
#                     rects.remove(rb)
#                 rects.append((union(ra, rb)))
#                 keep_going = True
#                 break
#         if not keep_going:
#             break
#     #print ('merge({}): {}, {:.5f}'.format(num_rects, len(rects), time.time() - start))
#     return rects

class Rect:
    def __init__(self,r):
        self.r = r
        self.connected = set()
        self.group = None

def visit_rect(rects, i, group, depth=1):
    r = rects[i]
    if r.group is None:
        #print ('{:{}}{} [{}]'.format('', 2*depth, i, group))
        r.group = group
        for j in r.connected:
            visit_rect(rects, j, group, depth+1)
    else:
        assert r.group==group or depth==1, (r.group, group, i)

def connect(rects, i, j):
    assert i != j
    rects[i].connected.add(j)
    rects[j].connected.add(i)

def merge(areas):
    #start = time.time()
    rects = []
    for r in areas:
        rects.append(Rect(r))
    num_rects = len(rects)
    for i in range(0, num_rects):
        for j in range(i+1, num_rects):
            a = rects[i]
            b = rects[j]
            if intersection(a.r, b.r):
                connect(rects, i, j)
    for i, r in enumerate(rects):
        #print ('--- {} ---'.format(i))
        visit_rect(rects, i, i)
    #return [i.r for i in rects]
    union = {}
    for r in rects:
        x,y,w,h = r.r
        x1,y1,x2,y2 = union.setdefault(r.group, (x,y,x+w,y+h))
        if x<x1:
            x1=x
        if y<y1:
            y1=y
        if x+w>x2:
            x2=x+w
        if y+h>y2:
            y2=y+h
        union[r.group]=(x1,y1,x2,y2)

    items = union.items()
    delete = set()
    for k,(x1,y1,x2,y2) in items:
        for j,(_x1,_y1,_x2,_y2) in items:
            if j==k:
                continue
            if x1 >= _x1 and y1 >= _y1 and x2 <= _x2 and y2 <= _y2:
                delete.add(k)

    for k in delete:
        del union[k]

    #print ('merge_rects({}): {}, {:.5f}'.format(num_rects, len(union), time.time() - start))    
    return [(x1,y1,x2-x1,y2-y1) for _,(x1,y1,x2,y2) in items]


def panelize_contours(img, threshold, kern_size=2, iterations=1):
    h,w = img.shape
    cv2.rectangle(img, (0,0),(w,h), (255,255,255),5)
    #img = cv2.fastNlMeansDenoising(img)

    #test = cv2.cvtColor(copy, cv2.COLOR_GRAY2RGB)
    kernel = np.ones((kern_size,kern_size), np.uint8)
    img = cv2.erode(img, kernel, iterations=iterations)
    img = cv2.GaussianBlur(img, (3,3), 0)
    img = cv2.threshold(img, threshold, 255, cv2.ADAPTIVE_THRESH_MEAN_C)[1]

    rects = []
    contours,hier = cv2.findContours(img, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    for i, cnt in enumerate(contours):
        # hierarchy looks like this: [Next, Previous, First_Child, Parent]
        j = hier[0][i][3]
        # grab level one only
        if j == -1 or hier[0][j][3] != -1:
            continue
        x,y,w,h = cv2.boundingRect(cnt)
        if w < 2 or h < 2:
            continue
        #cv2.rectangle(test, (x,y), (x+w, y+h), (0,255,0), 2)
        rects.append((x,y,w,h))
    rects = sort_panels(img, merge(rects))
    return rects, kern_size, iterations


def sort_panels(img, panels, grid=10):
    min_w = img.shape[1]//grid
    min_h = img.shape[0]//grid
    def roundup(x,y,w,h):
        return (y//min_h)*min_h, (x//min_w)*min_w
    return sorted(panels, key=lambda rect: roundup(*rect))


def image_to_array(img):
    img = np.array(img)
    if len(img.shape) > 2:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)    
    return img


def change_resolution(page, paper_format=None, dpi=300, format=False):
    if not paper_format:
        paper_format = [8.5, 11] # letter

    paper_size = [int(i*dpi) for i in paper_format]
    page_aspect = page.size[0] / page.size[1]
    size = (int(paper_size[1] * page_aspect), paper_size[1])
    if size[0] > paper_size[0]:
        paper_aspect = paper_size[0]/paper_size[1]
        size = (paper_size[0], int(paper_size[1] / page_aspect * paper_aspect))
        assert size[1] <= paper_size[1]

    page = page.resize(size, Image.LANCZOS)

    if format:
        xy = [int((i-j)/2) for i,j in zip(paper_size, size)]
        img = Image.new(img.mode, paper_size, 'white')
        img.paste(page, xy)
        page = img
    return page


def enhance(f, im, contrast=None):
    if contrast:
        im = cv2.convertScaleAbs(im, alpha=contrast)
    im = cv2.threshold(im, 127, 255, cv2.THRESH_TOZERO)[1]
    im = correct_skew(f, im)
    kernel = np.ones((2,2), np.uint8)
    im = cv2.erode(im, kernel, iterations=1)
    im = cv2.GaussianBlur(im, (3,3), 0)
    im = cv2.dilate(im, kernel, iterations=1)
    return im


# https://www.pyimagesearch.com/2017/02/20/text-skew-correction-opencv-python/
def correct_skew(f, img):
    # threshold the image, setting all foreground pixels to
    # 255 and all background pixels to 0
    thresh = 255-cv2.threshold(img, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    # grab the (x, y) coordinates of all pixel values that
    # are greater than zero, then use these coordinates to
    # compute a rotated bounding box that contains all
    # coordinates
    coords = np.column_stack(np.where(thresh > 0))
    angle = cv2.minAreaRect(coords)[-1]

    # the `cv2.minAreaRect` function returns values in the
    # range [-90, 0); as the rectangle rotates clockwise the
    # returned angle trends to 0 -- in this special case we
    # need to add 90 degrees to the angle
    if angle < -45:
        angle = -(90 + angle)
    # otherwise, just take the inverse of the angle to make
    # it positive
    else:
        angle = -angle
    print('{} skew: {:.4f}'.format(f, angle))
    (h, w) = img.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_CONSTANT, borderValue=255)


def redact_out(img, text):
    text = text.split(' ')
    d = pytesseract.image_to_data(img, output_type='dict')
    words = d['text']
    for i, w in enumerate(words):
        found = True
        for j,t in enumerate(text):
            if i+j >= len(words) or words[i+j] != t:
                found = False
                break
        if not found:
            continue
        print ('Redacting out text at index:', i)
        for j in range(i, i+len(text)):
            x,y,w,h = d['left'][j],d['top'][j],d['width'][j],d['height'][j]
            #print (x,y,w,h)
            ImageDraw.Draw(img).rectangle((x,y,x+w,y+h), fill='white')


def auto_crop(im, threshold=200):
    a = im.T
    f = np.nonzero(a<127)
    assert len(f[0]) and len(f[1])
    x1,y1,x2,y2 = [min(f[0]), min(f[1]), max(f[0])+1, max(f[1])+1]
    return im[y1:y2, x1:x2]
    

def test_panelize(files, out_dir):
    threshold = None

    for n, f in enumerate(files):
        f = os.path.join(dir_name, f)
        if not os.path.isfile(f):
            continue
        
        try:
            img = Image.open(f)

        except UnidentifiedImageError:
            continue

        im = image_to_array(img)

        threshold, _ = auto_threshold(im, threshold)
        print ('auto threshold:', threshold)

        use_countours_method = True
        if use_countours_method:
            rects,_,_  = panelize_contours(im, threshold, ksize, iters)
        else:            
            rects = panelize_crop(im, threshold)

        print ('{}: {} area(s))'.format(f, len(rects)))

        draw = ImageDraw.Draw(img)
        for (x,y,w,h) in rects:
            draw.rectangle((x,y,x+w,y+h), outline='green', width=5)

        fout = os.path.join(out_dir, os.path.splitext(os.path.basename(f))[0] + '.jpg')
        img.save(fout)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        quit()

    dir_name = sys.argv[1]
    out_dir = os.path.basename(dir_name)
    if len(out_dir)==0:
        out_dir = os.path.basename(dir_name.strip('/'))
    out_dir += '-enhanced'
    os.makedirs(out_dir, exist_ok=True)

    threshold,ksize, iters = None,2,1

    files = sorted(os.listdir(dir_name))
    test_panelize(files, out_dir)
