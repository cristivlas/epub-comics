from PIL import Image, JpegImagePlugin
import cv2
import numpy as np


# https://www.pyimagesearch.com/2017/02/20/text-skew-correction-opencv-python/
def correct_skew(img):

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

    (h, w) = img.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_CONSTANT, borderValue=255)


def enhance_bw(image):
    # PIL image to CV2 image
    img = np.array(image.convert('L'))
    img = cv2.fastNlMeansDenoising(img)
    img = cv2.threshold(img, 50, 255, cv2.THRESH_TOZERO)[1]
    # CV2 to PIL    
    return Image.fromarray(img)


class ImageFrame:
    def __init__(self, filename):
        self.filename = filename
        print(filename)
        img = Image.open(filename)
        self.mode = img.mode
        self.quantization = getattr(img, 'quantization', None)
        self.subsampling = JpegImagePlugin.get_sampling(img) if self.quantization else None
        self.img = Image.fromarray(correct_skew(np.array(img.convert('L')))).convert(img.mode)

    def save(self, filename, img=None):
        if img is None:
            img = self.img
        if self.mode=='L':
            img = enhance_bw(img)
        if self.subsampling:
            img.save(filename, subsampling=self.subsampling, qtables=self.quantization)
        else:
            img.save(filename)



    
