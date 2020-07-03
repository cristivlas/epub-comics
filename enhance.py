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
        found = 0
        for ra, rb in itertools.combinations(rects, 2):
            if intersection(ra, rb):
                if ra in rects:
                    rects.remove(ra)
                if rb in rects:
                    rects.remove(rb)
                rects.append((union(ra, rb)))
                found = 1
                break
        if found == 0:
            break
    return rects

def xmerge(rects):
    while (1):
        found = 0
        for ra, rb in itertools.combinations(rects, 2):
            if abs(ra[1]-rb[1]) > 2:
                continue
            
            if (ra[0] < rb[0] < ra[0]+ra[2]) or (rb[0] < ra[0] < rb[0]+rb[2]):
                if ra in rects: rects.remove(ra)
                if rb in rects: rects.remove(rb)
                rects.append((union(ra, rb)))
                found = 1
                break
        if not found:
            break
    return rects




def detect_panels(img, threshold=None, contrast=None, clip_margin=(5,5), rect_area_ratio=0.015):
    img = np.array(img)
    if len(img.shape) > 2:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)    
    if contrast:
        img = cv2.convertScaleAbs(img, alpha=contrast)
    
    h,w = img.shape[:2]
    img_area = w*h    
    
    def is_large(a):
        return a/img_area > rect_area_ratio    
    # clip off images that extend to the page
    cv2.rectangle(img, (0,0),(w-clip_margin[0],h-clip_margin[1]),(255,255,255), max(clip_margin))

    kernel = np.ones((2,2), np.uint8)
    img = cv2.erode(img, kernel, iterations=1)

    if True: # aggressive
        img = cv2.GaussianBlur(img, (3,3), 0)    
        img = cv2.erode(img, kernel, iterations=2)    
    else:
        # smoothen    
        img = cv2.GaussianBlur(img, (1,1), 0)    
        img = cv2.erode(img, kernel, iterations=1)    
    
    if not threshold:
        threshold = np.mean(img)

    #method=cv2.THRESH_TOZERO
    method=cv2.ADAPTIVE_THRESH_MEAN_C
    img = cv2.threshold(img, threshold, 255, method)[1]

    large_ext = []
    small_ext = []

    d=1 # shrink large areas by this amount, and expand small areas by same    

    # hier: [Next, Previous, First_Child, Parent]
    contours,hier = cv2.findContours(img, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    for i, cnt in enumerate(contours):
        j = hier[0][i][3]         
        # grab level one only
        if j == -1 or hier[0][j][3] != -1:
            continue 
        x,y,w,h = cv2.boundingRect(cnt)
        a = w*h
        if is_large(a):
            large_ext.append((x+d,y+d,w-2*d,h-2*d))
        elif a > 100:
            small_ext.append((x-d,y-d,w+2*d,h+2*d))
    return large_ext + list(filter(lambda x: is_large(x[2]*x[3]), merge(small_ext)))


def enhance(img, contrast=None, bw=False):
    img = np.array(img)
    if bw:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        img = cv2.threshold(img, 127, 255, cv2.THRESH_TOZERO)[1]
    if contrast:
        img = cv2.convertScaleAbs(img, alpha=contrast)
    kernel = np.ones((2,2), np.uint8)
    img = cv2.erode(img, kernel, iterations=1)
    # smoothen
    img = cv2.GaussianBlur(img, (1,1), 0)
    return Image.fromarray(img)



if __name__ == '__main__':
    out_dir = '__enhanced__'
    dir_name = sys.argv[1] if len(sys.argv) > 1 else '.'
    os.makedirs(out_dir, exist_ok=True)

    for n, f in enumerate(sorted(os.listdir(dir_name))):
        f = os.path.join(dir_name, f)
        if not os.path.isfile(f):
            continue
        
        try:
            img = Image.open(f)
            img = img.resize([i//2 for i in img.size])
        except UnidentifiedImageError:
            continue

        #areas = detect_panels(img, threshold=127, contrast=1.25, rect_area_ratio=0.01)
        #areas = detect_panels(img, threshold=None, contrast=1.25, rect_area_ratio=0.01)
        areas = detect_panels(img)
        #xmerge(areas)
        #img  = enhance(img, 1.75, bw=True).convert('RGB')
        draw = ImageDraw.Draw(img)

        print ('{}: {} area(s)'.format(f, len(areas)))

        for a in areas:
            x,y,w,h = a
            draw.rectangle((x,y,x+w,y+h), outline='green', width=5)

        fout = os.path.join(out_dir, os.path.basename(f))
        img.save(fout)
