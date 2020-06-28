#
# Generate .epub from folder of comics, one image file per page
#
import argparse
import contextlib
import numpy as np
import shutil
import uuid
import warnings
import zipfile

from bs4 import BeautifulSoup
from os import chdir, getcwd, listdir, makedirs, path, rename, walk
from panels import Extractor
from xml.dom import minidom
from lxml import etree as ET
from PIL import Image
from pathvalidate import sanitize_filepath

TRIM_MARGINS = True

@contextlib.contextmanager
def pushd(new_dir):
    previous_dir = getcwd()
    if new_dir:
        chdir(new_dir)
    try:
        yield
    finally:
        chdir(previous_dir)

def scale_perc(x, scale, size):
    return '{}%'.format(round(100*x*scale/size, 2))


def detect_background_color(img):
    # TODO: check all four corners? or is left-top enough for now?
    a = np.array(img)
    color = tuple(a[0][0])
    return color


class Panel:
    def __init__(self, filename, img, xy, size):
        assert len(xy)==2, xy
        assert len(size)==2, size

        self.xywh = list(xy) + list(size)
        self.img_size = img.size

        if True:
            # corners as percentages
            (self.left, self.top) = ['{}%'.format(round(i*100./j,2)) for i,j in zip(xy, img.size)]
            (self.width, self.height) = ['{}%'.format(round(i*100./j,2)) for i,j in zip(size, img.size)]        
        else:
            # ... as pixels
            (self.left, self.top) = ['{}px'.format(i) for i in xy]
            (self.width, self.height) = ['{}px'.format(i) for i in size]

    def __str__(self):
        return '{} left={}%, top={}%, width={}%, height={}%'.format(self.xywh, self.left, self.top, self.width, self.height)
    
    def max_scale(self, client_size):
        scale = min([i / j for i, j in zip(client_size, self.xywh[2:])])
        return scale

    # box (magTarget)
    def zoom_target_box(self, scale, client_size):
        _,_,w,h = self.xywh
        return {
            'left':'{}%'.format(round(50*(client_size[0]-w*scale)/client_size[0],2)),
            'top': '{}%'.format(round(50*(client_size[1]-h*scale)/client_size[1],2)),
            'width':  scale_perc(w, scale, client_size[0]),
            'height': scale_perc(h, scale, client_size[1]),
        }

    # content (magTarget img)
    def zoom_target_img_box(self, scale, client_size):
        x,y,w,h = self.xywh
        new_size = [i*scale for i in self.img_size]                
        style = {
            'top': '{}%'.format(round(-y*100/h, 2)),
            'left': '{}%'.format(round(-x*100/w, 2)),

            'width':'{}px'.format(int(new_size[0])),
            'height':'{}px'.format(int(new_size[1])),

            'min-width':'{}px'.format(int(new_size[0])),
            'min-height':'{}px'.format(int(new_size[1])),
        }
        return style


def panel_id(page, ordinal):
    return '{}-{}'.format(page, ordinal)

def add_comic_book_meta(args, metadata):
    metadata.append(ET.Element('meta', {'name': 'orientation-lock', 'content': 'portrait'}))
    metadata.append(ET.Element('meta', {'name': 'fixed-layout', 'content': 'true'}))
    metadata.append(ET.Element('meta', {'name': 'book-type', 'content': 'comic'}))
    metadata.append(ET.Element('meta', {'name': 'zero-gutter', 'content': 'true'}))
    metadata.append(ET.Element('meta', {'name': 'zero-margin', 'content': 'true'}))
    metadata.append(ET.Element('meta', {'name': 'region-mag', 'content': 'true'}))
    metadata.append(ET.Element('meta', {'name': 'ke-border-color', 'content': '#000000'}))
    metadata.append(ET.Element('meta', {'name': 'ke-border-width', 'content': '3'}))
    metadata.append(ET.Element('meta', {'name': 'original-resolution', 'content':'{}x{}'.format(*args.client_size)}))
    metadata.append(ET.Element('meta', {'name': 'primary-writing-mode', 'content': 'horizontal-lr' }))


class Page:
    def _set_panels(self, args, img:Image, panels:dict):
        r = args.split_ratio
        for panel_name in sorted(panels.keys()):
            panel_img, xy = panels[panel_name]
            assert len(xy)==2, xy            
            w,h = panel_img.size
            # split wide panels
            if r > 0 and w > 2 * h:
                self.panels.append(Panel(self.filename, img, xy, (r*w, h)))
                self.panels.append(Panel(self.filename, img, [xy[0] + r * w, xy[1]], [(1.0 - r) * w, h]))
            else:
                self.panels.append(Panel(self.filename, img, xy, panel_img.size))

    def _trim(self, args, min_size, img, panels, bg):
        if len(panels) <= 1:
            self._set_panels(args, img, panels)
            return img
        
        # heuristic
        few_panels = len(panels) <= 3
        if not TRIM_MARGINS or few_panels:
            page = Image.new('RGB', img.size, bg) 
            if few_panels:
                page.paste(img, (0,0))
            for _,(panel_img,xy) in panels.items():
                assert len(xy)==2, xy
                page.paste(panel_img, xy[:2])
                assert len(xy)==2, xy

            self._set_panels(args, page, panels)

        else:
            points = []
            for _,(img,xy) in panels:
                assert len(xy)==2, xy
                points.append(xy)
                points.append([i+j for i, j in zip(xy, img.size)])
            
            margin = 50
            top_left = points[0]
            bottom_right = points[-1]
            size = [i-j+2*margin for i, j in zip(bottom_right, top_left)]
            
            page = Image.new('RGB', size, bg)
            for _,(img,xy) in panels:
                page.paste(img, [i-j+margin for i, j in zip(xy, top_left)])

            panels = Extractor('', threshold=args.threshold, min_size=min_size).panels_from_image(page)
            self._set_panels(args, page, panels)        

        return page

    def _make_page(self, args, filename):        
        img = Extractor.open(filename)        
        if args.scale != 1.0:
            print ('Scaling image: {}'.format(args.scale))
            img = img.resize([int(i*args.scale) for i in img.size])

        if args.bg:
            bg = args.bg
            if bg.lower()=='none':
                bg=None
        else:
            bg = detect_background_color(img)            

        #rotate
        if img.size[0] > img.size[1]:
            img = img.rotate(90, expand=True)

        min_size = min(img.size)/args.max_panels_per_edge
        panels = Extractor('', threshold=args.threshold, min_size=min_size).panels_from_image(img)
        return self._trim(args, min_size, img, panels, bg), bg

    def __init__(self, args, filename, output_dir, client_size):
        self.output_dir = output_dir
        self.client_size = client_size        
        self.panels = []
        images_dir = 'images'
        img_filename = sanitize_filepath(filename, platform='auto')
        self.filename = path.join(images_dir, path.splitext(path.basename(img_filename))[0] + '.jpg')        
        print (self.filename)
        images_dir = path.join(output_dir, images_dir)
        makedirs(images_dir, exist_ok=True)

        page, bg = self._make_page(args, filename)
        page.save(path.join(output_dir, self.filename))

        self.size = page.size
        self.create_bg_image_file(images_dir, bg)

    def enumerate_panels(self):
        return enumerate(self.panels, 1)
        
    def get_script(self, args):
        return 'zoom.js' if args.js else None

    def create_bg_image_file(self, dir, bg_color):
        if not bg_color:
           print ('defaulting to white background') 
           bg_color = 'white'

        fpath = path.join(dir, 'bg.png')
        if not path.exists(fpath):
            bg = Image.new('RGB', self.client_size, bg_color)
            bg.save(fpath)

    def gen_html(self, root_name, args):
        html = ET.Element('html', {'xmlns': 'http://www.w3.org/1999/xhtml'})
        head = ET.Element('head')
        html.append(head)
        head.append(ET.Element('meta', {'http-equiv': 'content-type', 'content': 'text/html; charset=utf-8'}))

        body = ET.Element('body')
        html.append(body)

        css_link = {
            'data-app-amzn-ke-created-style': 'data-app-amzn-ke-created-style',             
            'href': 'css/amzn-ke-style-template.css',
            'rel': 'stylesheet',
            'type': 'text/css'
        }
        script = self.get_script(args)
        if script:
            head.append(ET.Element('script', {'src': script}))        
            body.attrib['onkeyup'] = 'key_press(event)'

        # CSS
        head.append(ET.Element('link', css_link))
        css = self.gen_css(root_name)
        css_link['href'] = css
        head.append(ET.Element('link', css_link))

        top = ET.Element('div', {'class':'fs'})
        if script:
            top.attrib['ondblclick'] = 'zoom(event)'

        body.append(top)
        img_div = ET.Element('div')
        top.append(img_div)
        img = ET.Element('img', {'src':self.filename, 'class':'singlePage'})
        img_div.append(img)

        # pass one: div (regions for panels)
        for ordinal,_ in self.enumerate_panels():
            id = panel_id(root_name, ordinal)
            div = ET.Element('div', {'id': 'reg-' + id})
            top.append(div)
            data = '"sourceId":"reg-{}", "targetId":"reg-{}-magTargetParent", "ordinal":{}'.format(id, id, ordinal)
            div.append(ET.Element('a', {'class': 'app-amzn-magnify', 'data-app-amzn-magnify': '{' + data + '}'}))

        # pass two: magnification target divs
        for ordinal,_ in self.enumerate_panels():
            id = 'reg-' + panel_id(root_name, ordinal) + '-magTargetParent'
            div = ET.Element('div', {
                'id': id,
                'class': 'target-mag-parent',
            })
            top.append(div)
            
            target_id = 'reg-' + panel_id(root_name, ordinal) + '-magTarget'
            
            #lightbox: cover the single page
            div_lb=ET.Element('div', {'class': 'target-map-lb'})
            div.append(div_lb)
            style = 'opacity: .85; min-width: {}px; min-height:{}px;'.format(*self.client_size)
            div_lb.append(ET.Element('img', {'src':'images/bg.png', 'style':style}))

            div_target = ET.Element('div', {'id': target_id, 'class': 'target-mag'})
            div.append(div_target)

            img_src = self.filename
            div_target.append(ET.Element('img', {'src': img_src, 'class': 'target-mag'}))

        # write it out
        fname = path.join(self.output_dir, root_name) + '.html'
        print (fname)
        with open(fname, 'w') as f:
            doctype='<!DOCTYPE html SYSTEM "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">'
            html = ET.tostring(html, method='html', doctype=doctype, encoding='utf-8')
            f.write(BeautifulSoup(html, features='lxml', from_encoding='utf-8').prettify(formatter='html'))
        return (root_name, path.basename(fname), css)


    def gen_css(self, root_name):
        prefix = 'amzn-ke-style-'        

        dir = path.join(self.output_dir, 'css')
        fname = path.join(dir, path.join(path.dirname(root_name), prefix + path.basename(root_name) + '.css'))      
        print (fname)
        with open(fname, 'w') as f:
            f.write('div.fs {\n')
            for i in ['top', 'bottom', 'left', 'right']:
                f.write ('margin-{}: 0px;\n'.format(i))
            w,h = self.client_size
            f.write('width: {}px;\nheight: {}px;\n'.format(w, h))
            f.write('}\nimg.singlePage {\n')
            f.write('width: {}px;\nheight: {}px;\n'.format(w, h))
            f.write('min-width: {}px;\nmin-height: {}px;\n'.format(w, h))
            f.write('}\n')

            for (ordinal, panel) in self.enumerate_panels():
                id = panel_id(root_name, ordinal)
                scale = panel.max_scale(self.client_size)

                #region
                f.write('#reg-{} '.format(id))
                f.write('{\n')            
                for i in [ 'top', 'left', 'height', 'width']:
                    f.write('{}: {};\n'.format(i, getattr(panel, i)))
                f.write('}\n')

                # panel magnification box
                f.write('#reg-{}-magTarget '.format(id))
                f.write('{\n')
                target = panel.zoom_target_box(scale, self.client_size)
                for i in [ 'top', 'left', 'height', 'width']:
                    f.write('{}: {};\n'.format(i, target[i]))
                f.write('}\n')

                # panel magnification img
                f.write('#reg-{}-magTarget img '.format(id))
                f.write('{\n')

                target = panel.zoom_target_img_box(scale, self.client_size)                
                for i,v in target.items():
                    f.write('{}: {};\n'.format(i,v))

                f.write('}\n')

        return path.join('css', path.basename(fname))


def gen_content_opf(args, pages, output_dir):
    package = ET.Element('package',
        {
            'unique-identifier': 'PrimaryID',
            'version': '3.0',
            #'unique-identifier': '{' + str(uuid.uuid4()) + '}',
            #'version': '2.0',
            '{http://www.w3.org/XML/1998/namespace}lang': 'en',
            'xmlns': 'http://www.idpf.org/2007/opf'
        },
        nsmap={ 'xml': 'http://www.w3.org/XML/1998/namespace' })

    metadata = ET.Element('metadata', nsmap={
        'dc': 'http://purl.org/dc/elements/1.1/',
        'opf': 'http://www.idpf.org/2007/opf'
    })
    manifest = ET.Element('manifest')
    package.append(metadata)
    package.append(manifest)
    
    add_comic_book_meta(args, metadata)

    # unique id
    e = ET.Element('{http://purl.org/dc/elements/1.1/}identifier', {'id': 'PrimaryID' })
    e.text = str(uuid.uuid4())
    metadata.append(e)

    e = ET.Element('{http://purl.org/dc/elements/1.1/}publisher')
    e.text = 'Fake News Media'
    metadata.append(e)

    # metadata language
    e = ET.Element('{http://purl.org/dc/elements/1.1/}language')
    e.text = 'en'
    metadata.append(e)

    # metadata author
    if args.author:
        for author in args.author.split(','):
            e = ET.Element('{http://purl.org/dc/elements/1.1/}creator')
            e.text = author.strip()
            metadata.append(e)

    # metadata title
    if args.title:
        e = ET.Element('{http://purl.org/dc/elements/1.1/}title')
        e.text = args.title
        metadata.append(e) 

    # metadata cover
    if args.cover:
        metadata.append(ET.Element('meta', {'content':'cover-image', 'name': 'cover'}))        
        manifest.append(ET.Element('item', {'href': 'images/cover.jpg', 'id': 'cover-image', 'media-type':'image/jpeg'}))

    spine = ET.Element('spine', {'toc':'ncx'})
    package.append(spine)

    for _,_,files in walk(path.join(output_dir, 'images')):
        for i,f in enumerate(files):
            if f.endswith('.jpg'):
                mime = 'image/jpeg'
            elif f.endswith('.png'):
                mime = 'image/png'

            manifest.append(ET.Element('item', {'href': 'images/' + f, 'id': 'img-{}'.format(i), 'media-type': mime }))

    for (id, page, css) in pages:
        manifest.append(ET.Element('item', {'href': page, 'id': id, 'media-type': 'application/xhtml+xml' }))
        manifest.append(ET.Element('item', {'href': css, 'id': id + '-css', 'media-type': 'text/css' }))
        spine.append(ET.Element('itemref', {'idref': id, 'linear': 'yes' }))
    
    manifest.append(ET.Element('item', { 'href': 'css/amzn-ke-style-template.css', 'id':'css-template', 'media-type': 'text/css' }))
    manifest.append(ET.Element('item', { 'href': 'toc.ncx', 'id':'ncx', 'media-type': 'application/x-dtbncx+xml' }))
    
    # <item href="toc.xml" id="toc" media-type="application/xhtml+xml"/>
    manifest.append(ET.Element('item', { 'href': 'toc.xml', 'id':'toc', 'media-type': 'application/xhtml+xml' }))
    
    # <item href="toc.xhtml" id="tocn" media-type="application/xhtml+xml" properties="nav"/>
    manifest.append(ET.Element('item', { 'href': 'toc.xhtml', 'id':'tocn', 'media-type': 'application/xhtml+xml', 'properties': 'nav' }))

    # write content.opf
    content = ET.tostring(package, encoding='utf-8', pretty_print=True)
    with open(path.join(output_dir, 'content.opf'), 'w') as f:
        f.write(content.decode('utf-8'))


#
# EPUB Toc, content, etc.
# 
def toc_item(type, id, href, text):
    a = ET.Element('a', {'href': href})
    if text:
        a.text = text
    li = ET.Element(type, { 'id': id })
    li.append(a)
    return li


def toc_list_item(id, href, text=None):
    return toc_item('li', id, href, text)


def toc_list_para(cls, href, text=None):
    p = ET.Element('p', { 'class': cls })
    if href:
        a = ET.Element('a', {'href': href})
        if text:
            a.text = text    
        p.append(a)

    elif text:
        p.text = text

    return p


def gen_toc_xhtml(pages, output_dir):
    html = ET.Element('html', {'xmlns': 'http://www.w3.org/1999/xhtml'}, nsmap={'epub': 'http://www.idpf.org/2007/ops'})

    head = ET.Element('head') 
    html.append(head)
    
    title = ET.Element('title')
    title.text = 'Contents'
    head.append(title)
    
    style = ET.Element('style', {'type': 'text/css'})
    style.text = 'nav#toc ol { list-style-type: none; }'
    head.append(style)

    body = ET.Element('body')
    html.append(body)

    nav = ET.Element('nav', { '{http://www.idpf.org/2007/ops}type': 'toc', 'id': 'toc'})
    body.append(nav)

    h1 = ET.Element('h1')
    h1.text = 'Contents'
    nav.append(h1)
    
    toc_list = ET.Element('ol')
    nav.append(toc_list)
        
    toc_list.append(toc_list_item('level1-toc', 'toc.xml', 'Contents'))    
    for id, page, _ in pages:
        toc_list.append(toc_list_item(id, page, id.replace('-', ' ')))

    toc = ET.tostring(html, encoding='utf-8', pretty_print=True, xml_declaration=True)
    with open(path.join(output_dir, 'toc.xhtml'), 'w') as f:
        f.write(toc.decode('utf-8'))


def gen_toc_xml(pages, output_dir):
    html = ET.Element('html', {'xmlns': 'http://www.w3.org/1999/xhtml'}, nsmap={'epub': 'http://www.idpf.org/2007/ops'})
    head = ET.Element('head')
    html.append(head)
    head.append(ET.Element('meta', { 'content': 'urn:uuid:3903d0b4-0aaa-4ad1-8a4e-4a6fb2bb0251', 'name': 'Adept.expected.resource'}))

    body = ET.Element('body')
    html.append(body)
    
    div = ET.Element('div', { 'id': 'toc' })
    body.append(div)

    h1 = ET.Element('h1', { 'class': 'chaptertitle paired'})
    h1.text = 'Contents'
    div.append(h1)
    div.append(ET.Element('hr'))
    #div.append(toc_list_para('toc sub', 'toc.xml', 'Contents'))
    for (id, page, _) in pages:
        div.append(toc_list_para('toc', page, id.replace('-', ' ')))

    toc = ET.tostring(html, encoding='utf-8', pretty_print=True)
    with open(path.join(output_dir, 'toc.xml'), 'w') as f:
        f.write(toc.decode('utf-8'))


def gen_toc(pages, output_dir):
    gen_toc_xhtml(pages, output_dir)
    gen_toc_xml(pages, output_dir)


def gen_ncx(pages, output_dir):
    ncx = ET.Element('ncx',
        {'version': '2005-1',
        '{http://www.w3.org/XML/1998/namespace}lang': 'en',
        'xmlns': 'http://www.daisy.org/z3986/2005/ncx' },
        nsmap={ 'xml': 'http://www.w3.org/XML/1998/namespace' })

    head = ET.Element('head')
    ncx.append(head)

    head.append(ET.Element('meta', {'content': 'true', 'name': 'generated'}))
    start_play_order = 1    

    map = ET.Element('navMap')
    ncx.append(map)

    point = ET.Element('navPoint', {
            'class': 'toc',
            'id': 'level1-toc',
            'playOrder': '1'
        })
    point.append(ET.Element('content', {'src':'toc.xml'}))    
    map.append(point)

    for i, (id, page, _) in enumerate(pages):
        point = ET.Element('navPoint', {
            'class': 'level-' + id,
            'id': id,
            'playOrder': str(i+1+start_play_order)
        })
        map.append(point)
        point.append(ET.Element('content', {'src': page}))

    doctype = "<!DOCTYPE ncx PUBLIC '-//NISO//DTD ncx 2005-1//EN' 'http://www.daisy.org/z3986/2005/ncx-2005-1.dtd'>"
    navigation = ET.tostring(ncx, encoding='utf-8', pretty_print=True, xml_declaration=True, doctype=doctype)
    with open(path.join(output_dir, 'toc.ncx'), 'w') as f:
        f.write(navigation.decode('utf-8'))


def gen_navigation_files(pages, output_dir):
    gen_toc(pages, output_dir)
    gen_ncx(pages, output_dir)


def command_line_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('input_dir', help='input dir')
    parser.add_argument('-a', '--author')
    parser.add_argument('-c', '--cover')

    # for splitting wide panels
    parser.add_argument('-s', '--split-ratio', type=float, default=0)

    parser.add_argument('--scale', default=1.0, type=float)

    parser.add_argument('-t', '--title')
    parser.add_argument('--trim', action='store_true', help='trim margins')
    parser.add_argument('--js', action='store_true', help='embed Javascript')
    parser.add_argument('--threshold', type=int, default=200, help='panel detection threshold')

    # for determining the minimum required size of a panel
    parser.add_argument('--max-panels-per-edge', type=int, default=8)

    # don't panelize if less than min-panels detected
    parser.add_argument('--min-panels', default=3)
    parser.add_argument('--bg')

    #parser.add_argument('--client-size', nargs=2, default=[500, 850], type=int)
    parser.add_argument('--client-size', nargs=2, default=[960, 1280], type=int)

    args = parser.parse_args()

    global TRIM_MARGINS
    TRIM_MARGINS = args.trim

    return args


def main():
    args = command_line_args()
    client_size = args.client_size
    print ('Client size:', client_size)
    
    input_dir = path.realpath(args.input_dir)

    if not path.isdir(input_dir): 
        raise Exception(input_dir + ' is not a directory')

    output = path.basename(input_dir) + '.epub'
    output_dir = path.basename(input_dir) + '-epub'    

    # setup META-INF and mimetype
    shutil.copytree('META-INF', path.join(output_dir, 'META-INF'))    
    with open(path.join(output_dir, 'mimetype'), 'w') as f:
        f.write('application/epub+zip')
    
    # prepare content and CSS output locations
    output_dir = path.join(output_dir, 'OEBPS')
    css_dir = path.join(output_dir, 'css')
    makedirs(css_dir)

    if args.cover:
        img = Image.open(args.cover)
        cover = path.join(output_dir, 'images')
        makedirs(cover)
        cover = path.join(cover, 'cover.jpg')
        img.save(cover)
    
    pages = []
    for f in sorted(listdir(input_dir)):
        if path.splitext(f)[1] in [ '.jpg', '.png']:
            f = path.join(input_dir, f)
            if args.cover and path.realpath(f)==path.realpath(args.cover):
                continue
            page = Page(args, f, output_dir, client_size)
            i = len(pages)
            pages.append(page.gen_html('page-{}'.format(i), args))

    res_files = ['css/amzn-ke-style-template.css']
    if args.js:
        with open('script/zoom.js') as sf:
            script = sf.read()
            with open(path.join(output_dir, 'zoom.js'), 'w') as df:
                df.write('var page_count = {}\n'.format(len(pages)))
                df.write(script)
    
    for f in res_files:
        shutil.copy(f, path.join(output_dir, f))            

    gen_content_opf(args, pages, output_dir)
    gen_navigation_files(pages, output_dir)

    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root,_,files in walk(path.dirname(output_dir)):
            for file in files:
                fpath = path.join(root, file)
                arcname = '/'.join(str(fpath).split('/')[1:])
                zipf.write(fpath, arcname)
    

if __name__ == '__main__':    
    with pushd(path.dirname(__file__)):
        main()

