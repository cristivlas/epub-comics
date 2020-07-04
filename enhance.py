
#! /usr/bin/python3
import cv2
import itertools
import os
import sys
import numpy as np
from PIL import Image, ImageDraw, UnidentifiedImageError
from collections import defaultdict


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


def merge(rects):
    while (1):
        keep_going = False
        for ra, rb in itertools.combinations(rects, 2):
            if intersection(ra, rb):
                if ra in rects:
                    rects.remove(ra)
                if rb in rects:
                    rects.remove(rb)
                rects.append((union(ra, rb)))
                keep_going = True
                break
        if not keep_going:
            break
    return rects


def split_rects(rects, min_w=20, min_h=20):
    return [(x,y,w,h) for (x,y,w,h) in rects if w > min_w and h > min_h], [(x,y,w,h) for (x,y,w,h) in rects if w <= min_w or h <= min_h]


def split_across(t, r, im, xy):
    a = im.T    
    #f = np.all(np.mean(a,axis=0)>=t, axis=1)
    f = np.all(a>=t, axis=1)
    x = min(np.nonzero(f))
    if len(x):        
        x = min(x)
        h,w = im.shape[:2]
        assert h and w
        return [split(t, r, im[0:h, 0:x], xy), split(t, r, im[0:h, x:x+w], [xy[0]+x, xy[1]])]


def split_down(t, r, im, xy):
    a = im.T
    #f = np.all(np.mean(a,axis=0)>=t, axis=0)    
    f = np.all(a>=t, axis=0)
    y = min(np.nonzero(f))
    if len(y):
        y = min(y)
        h,w = im.shape[:2]
        assert h and w
        return [split(t, r, im[0:y,0:w], xy), split(t, r, im[y:y+h,0:w], [xy[0], xy[1]+y])]


def split(threshold, rects, im, xy=[0,0]):
    a = im.T
    #f = np.nonzero(np.mean(a,axis=0)<threshold)
    f = np.nonzero(a<threshold)
    assert len(f[0]) and len(f[1])
    x1,y1,x2,y2 = [min(f[0]), min(f[1]), max(f[0])+1, max(f[1])+1]
    im = im[y1:y2, x1:x2]
    xy = [xy[0]+x1, xy[1]+y1]        
    if not split_down(threshold, rects, im, xy) and not split_across(threshold, rects, im, xy):
        h,w = im.shape[:2]
        rects.append((xy[0], xy[1], w, h))
    return rects


def panelize(img, threshold, kern_size=3, iterations=2):
    h,w = img.shape
    cv2.rectangle(img, (0,0),(w,h), (255,255,255),5)
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
        rects.append(cv2.boundingRect(cnt))    
    return merge(rects)


def image_to_array(img):
    img = np.array(img)
    if len(img.shape) > 2:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)    
    return img


def auto_threshold(img, t=None): 
    if t is None:
        for t in range(0, 255):
            t1, img2 = cv2.threshold(img, t, 255, cv2.THRESH_BINARY)
            t2 = np.mean(img2)
            if t2 <= 127:
                return t, img2
    return cv2.threshold(img, t, 255, cv2.THRESH_BINARY)


def enhance(img, contrast=None):
    if contrast:
        img = cv2.convertScaleAbs(img, alpha=contrast)
    kernel = np.ones((2,2), np.uint8)
    img = cv2.erode(img, kernel)
    return cv2.GaussianBlur(img, (3,3), 0)


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
    print(f, angle)
    (h, w) = img.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_CONSTANT, borderValue=255)


if __name__ == '__main__':
    out_dir = '__temp__'
    dir_name = sys.argv[1] if len(sys.argv) > 1 else '.'
    os.makedirs(out_dir, exist_ok=True)

    threshold = None

    for n, f in enumerate(sorted(os.listdir(dir_name))):
        f = os.path.join(dir_name, f)
        if not os.path.isfile(f):
            continue
        
        try:
            img = Image.open(f)
        except UnidentifiedImageError:
            continue

        im = image_to_array(img)

        #im  = enhance(im, 2.5)
        #img = Image.fromarray(cv2.cvtColor(im, cv2.COLOR_GRAY2RGB))

        threshold, im = auto_threshold(im, threshold)
        #print (threshold)
        #threshold, im = auto_threshold(im)
        
        large,small = split_rects(panelize(im, threshold, kern_size=2, iterations=1))
        
        rects = []
        for (x,y,w,h) in large:
            #panel = correct_skew(f, im[y:y+h, x:x+w])
            panel = im[y:y+h, x:x+w]
            splits = []
            splits,_ = split_rects(split(np.mean(im), splits, panel, [x,y]))
            #splits,_ = split_rects(split(threshold, splits, panel, [x,y]))
            if len(splits)>1:
                #print (len(splits))
                rects += splits
            else:
                rects.append((x,y,w,h))
            

        draw = ImageDraw.Draw(img)
        print ('{}: {} area(s)'.format(f, len(rects)))

        for (x,y,w,h) in rects:
            draw.rectangle((x,y,x+w,y+h), outline='green', width=5)
        for (x,y,w,h) in small:
            #print (x,y,w,h)
            draw.rectangle((x,y,x+w,y+h), fill='white')

        img = img.resize([ i//2 for i in img.size ])
        #img.show()
        fout = os.path.join(out_dir, os.path.basename(f))
        img.save(fout)


