#!/usr/bin/env python

import codecs
import os
import re
import sys
from datetime import datetime, timedelta, tzinfo
from glob import glob
from urllib.request import urlretrieve
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as etree
import yaml
from yaml import FullLoader
from bs4 import BeautifulSoup
from html2text import html2text_file

'''
exitwp - Wordpress xml exports to Jekykll blog format conversion

Tested with Wordpress 3.3.1 and jekyll 0.11.2

'''
######################################################
# Configration
######################################################

# define namespaces
ns = {
    "excerpt": "http://wordpress.org/export/1.2/excerpt/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "wfw": "http://wellformedweb.org/CommentAPI/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "wp": "http://wordpress.org/export/1.2/"
}

# Load the configuration file.
with open('config.yaml', 'r') as yaml_file:
    config = yaml.load(yaml_file, Loader=FullLoader)

# Get the configurations.
wp_exports_dir = config['wp_exports_dir']
build_dir = config['build_dir']
download_images = config['download_images']
use_hierarchical_folders = config['use_hierarchical_folders']
replace_existing = config['replace_existing']
target_format = config['target_format']
taxonomy_filter = set(config['taxonomies']['filter'])
taxonomy_entry_filter = config['taxonomies']['entry_filter']
taxonomy_name_mapping = config['taxonomies']['name_mapping']
item_type_filter = set(config['item_type_filter'])
item_field_filter = config['item_field_filter']
date_fmt = config['date_format']
body_replace = config['body_replace']

# Time definitions
ZERO = timedelta(0)
HOUR = timedelta(hours=1)


# UTC support
class UTC(tzinfo):
    """UTC."""

    def utcoffset(self, dt):
        return ZERO

    def tzname(self, dt):
        return 'UTC'

    def dst(self, dt):
        return ZERO


def all_item_children(item: etree.Element):
    if isinstance(item, etree.Element):
        # for child in item.iter():
        #     print(child.tag)
        #     if child.text:
        #         print(child.text)
        post_id1 = item.find("{http://wordpress.org/export/1.2/}post_id")
        post_id = item.find("wp:post_id", ns)
        if post_id1 is None:
            print('It keeps to not work!')
        else:
            print(post_id1.text, ns)
        if post_id is None:
            print('It keeps to not work!')
        else:
            print(post_id.text, ns)


# WordPress categories are specialized applications of taxonomies.
def parse_categories_for_item(item: etree.Element):
    categories = item.findall('category')
    result = {}

    for category in categories:
        # Skip if category does not have a `domain` XML attribute.
        if 'domain' not in category.attrib:
            continue

        domain = str(category.attrib['domain'])
        text = str(category.text)

        if (not (domain in taxonomy_filter) and
            not (domain
                 in taxonomy_entry_filter and
                 taxonomy_entry_filter[domain] == text)):
            if domain not in result:
                result[domain] = []
            result[domain].append(text)

    # print(f'Categories for item {item.find("guid").text}:', result)

    # all_item_children(item)

    return result


def html2fmt(html, target_format):
    #   html = html.replace("\n\n", '<br/><br/>')
    #   html = html.replace('<pre lang="xml">', '<pre lang="xml"><![CDATA[')
    #   html = html.replace('</pre>', ']]></pre>')
    if target_format == 'html':
        return html
    else:
        return html2text_file(html, None)


def parse_header(channel: etree.Element):
    try:
        desc = str(channel.find('description').text)
    except:
        desc = ''

    return {
        'title': str(channel.find('title').text),
        'link': str(channel.find('link').text),
        'description': desc,
    }


# <channel> nodes contains <item> nodes (that in RSS feeds are usually
# articles, stories, ecc). WordPress use <item> for many different kinds
# of posts: blog-posts, attachments, ecc.
def parse_items(channel: etree.Element):
    result = []
    items = channel.findall('item')

    for item in items:
        taxonomies = parse_categories_for_item(item)

        # Get item body.
        body = item.find('content:encoded', ns).text

        # Replace the keys found in body, if any, with replacement text.
        for key in body_replace:
            body = re.sub(key, body_replace[key], body)

        # Parse HTML body and eventually keep a storage of found images.
        img_srcs = []
        if body is not None:
            try:
                soup = BeautifulSoup(body, 'html.parser')

                # Store images if any.
                imgs = soup.find_all('img')
                for img in imgs:
                    img_srcs.append(img['src'])
            except:
                print('could not parse html: ' + body)

        result.append({
            'title': item.find('title').text,
            'link': item.find('link').text,
            'author': item.find('dc:creator', ns).text,
            'date': item.find('wp:post_date_gmt', ns).text,
            'description': item.find('description').text,
            'slug': item.find('wp:post_name', ns).text,
            'status': item.find('wp:status', ns).text,
            'type': item.find('wp:post_type', ns).text,
            'wp_id': item.find('wp:post_id', ns).text,
            'parent': item.find('wp:post_parent', ns).text,
            'comments': item.find('wp:comment_status', ns).text == 'open',
            'taxonomies': taxonomies,
            'body': body,
            'excerpt': item.find('excerpt:encoded', ns).text,
            'img_srcs': img_srcs
        })

    return result


def parse_wp_xml(file):
    #print(f'Parsing {file}')

    tree = etree.parse(file)
    root = tree.getroot()

    # Parse namespace prefixes from file
    ns_prefixes = dict([
        node for _, node in etree.iterparse(
            file, events=['start-ns'])
    ])

    # Specify empty namespace
    ns_prefixes[''] = ''

    # Append parentheses around prefixes for namespaces
    ns = {}
    for k, v in ns_prefixes.items():
        ns[k] = '{' + v + '}'

    # <channel> is basically the root node of WordPress export XML files.
    channel = root.find('channel')

    return {
        'header': parse_header(channel),
        'items': parse_items(channel),
    }


def get_blog_path(data, path_infix='jekyll'):
    name = data['header']['link']
    name = re.sub('^https?', '', name)
    name = re.sub('[^A-Za-z0-9_.-]', '', name)
    return os.path.normpath(build_dir + '/' + path_infix + '/' + name)


def compute_output_dir(dirname, basename):
    result = os.path.normpath(dirname + '/' + basename)
    if (not os.path.exists(result)):
        os.makedirs(result)
    return result


def open_file(file):
    f = codecs.open(file, 'w', encoding='utf-8')
    return f


def get_item_dest_path(item, dirname, basename=''):
    output_dir = compute_output_dir(dirname, basename)

    filename_parts = [output_dir, '/']
    if 'uid' in item:
        filename_parts.append(item['uid'])

    if item['type'] == 'page':
        if (not os.path.exists(''.join(filename_parts))):
            os.makedirs(''.join(filename_parts))
        filename_parts.append('/index')
    filename_parts.append('.')
    filename_parts.append(target_format)

    return ''.join(filename_parts)


def get_item_uid(item, uids={}, date_prefix=False, namespace=''):
    result = None

    if namespace not in uids:
        uids[namespace] = {}

    if item['wp_id'] in uids[namespace]:
        result = uids[namespace][item['wp_id']]
    else:
        uid = []
        if (date_prefix):
            try:
                dt = datetime.strptime(item['date'], date_fmt)
            except:
                dt = datetime.today()
                #print('Wrong date in', item['title'])
            uid.append(dt.strftime('%Y-%m-%d'))
            uid.append('-')
        s_title = item['slug']
        if s_title is None or s_title == '':
            s_title = item['title']
        if s_title is None or s_title == '':
            s_title = 'untitled'
        s_title = s_title.replace(' ', '_')
        s_title = re.sub('[^a-zA-Z0-9_-]', '', s_title)
        uid.append(s_title)
        fn = ''.join(uid)
        n = 1
        while fn in uids[namespace]:
            n = n + 1
            fn = ''.join(uid) + '_' + str(n)
            uids[namespace][item['wp_id']] = fn
        result = fn
    return result


def get_attachment_path(src, dir, attachments, blogpath, dir_prefix='assets'):
    try:
        files = attachments[dir]
    except KeyError:
        attachments[dir] = files = {}

    try:
        filename = files[src]
    except KeyError:
        file_root, file_ext = os.path.splitext(os.path.basename(
            urlparse(src)[2]))
        file_infix = 1
        if file_root == '':
            file_root = '1'
        current_files = list(files.values())
        maybe_filename = file_root + file_ext
        while maybe_filename in current_files:
            maybe_filename = file_root + '-' + str(file_infix) + file_ext
            file_infix = file_infix + 1
        files[src] = filename = maybe_filename

    if use_hierarchical_folders:
        target_dir = os.path.normpath(
            blogpath + '/' + dir_prefix + '/' + dir)
        target_file = os.path.normpath(target_dir + '/' + filename)
    else:
        # Instead of hierarchical structure, use flat structure to save
        target_dir = os.path.normpath(blogpath + '/' + dir_prefix)
        target_file = os.path.normpath(
            target_dir + '/' + dir + '_' + filename)

    if (not os.path.exists(target_dir)):
        os.makedirs(target_dir)

    # if src not in attachments[dir]:
    #     print(target_name)
    return target_file


def set_item_type_post(item, item_uids, blogpath, yaml_header):
    item['uid'] = get_item_uid(item, item_uids, date_prefix=True)
    filepath = get_item_dest_path(item, dirname=blogpath, basename='_posts')
    dest_file = open_file(filepath)
    yaml_header['template'] = 'blog-post'
    return dest_file


def set_item_type_page(item, item_uids, blogpath, yaml_header):
    item['uid'] = get_item_uid(item, item_uids)
    # Chase down parent path, if any
    parentpath = ''
    item = item
    while item['parent'] != '0':
        item = next((parent for parent in data['items']
                     if parent['wp_id'] == item['parent']), None)
        if item:
            parentpath = get_item_uid(
                item, item_uids) + '/' + parentpath
        else:
            break
    fn = get_item_dest_path(item, dirname=blogpath, basename=parentpath)
    out = open_file(fn)
    yaml_header['template'] = 'page'
    return out


def download_item_images(item, attachments, blogpath):
    counter = 0
    featured_image_path = ''

    # Each WordPress item can have a property 'img_srcs'.
    for img in item['img_srcs']:
        url = urljoin(data['header']['link'], str(img))
        outpath = get_attachment_path(
            img, item['uid'], attachments, blogpath)
        relpath = outpath.replace(blogpath, '').replace('\\', '/')

        if 'flickr.com' in url:
            # Convert Flickr "farm?.static..." url to downloadable url
            downurl = re.sub('(farm\d.static.)',
                             'live.static', url)
            # Specify large size (1064)
            downurl = re.sub('(.jpg)', '_b.jpg', downurl)
        else:
            downurl = url

        try_download = True
        if os.path.isfile(outpath):
            if replace_existing:
                sys.stdout.write(
                    f"Replacing image: {downurl} => {outpath}")
                sys.stdout.flush()
            else:
                sys.stdout.write(f"Skip existing: {outpath}\n")
                sys.stdout.flush()
                item['body'] = item['body'].replace(url, relpath)
                try_download = False
        if try_download:
            try:
                sys.stdout.write(f"Downloading image")
                urlretrieve(downurl, outpath)
                # urlretrieve(urljoin(data['header']['link'],
                #                     img.encode('utf-8')),
                #             get_attachment_path(img, i['uid']))
            except:
                print('\nUnable to download ' + downurl)
                print('Error: ', sys.exc_info()[0])
                # raise
            else:
                sys.stdout.write("...replace link...")
                sys.stdout.flush()
                try:
                    item['body'] = item['body'].replace(
                        url, relpath)
                except Exception as e:
                    print(e)
                else:
                    print("ok.")
        if counter == 0:
            featured_image_path = relpath
        counter += 1

    return featured_image_path


def toyaml(data):
    return yaml.safe_dump(data, allow_unicode=True, default_flow_style=False)


def write_jekyll(data, target_format):
    """
        Write data to jekyll in target_format (.md, .markdown, .html)

        Parameters
        ----------

        data : Dict
            The data obtained by parsing WordPress XML exports.

        target_format : str
            A string ('md') identifying the output format.
    """

    item_uids = {}
    attachments = {}

    # Get location of output files.
    blogpath = get_blog_path(data)

    sys.stdout.write('Writing')

    for item in data['items']:
        skip_item = False

        # Skip this item if any property of the WordPress item is equal to
        # any entry in the `item_field_filter` dictionary.
        for field, value in item_field_filter.items():
            if(item[field] == value):
                skip_item = True
                break

        if (skip_item):
            continue

        sys.stdout.write('.')
        sys.stdout.flush()
        out = None

        try:
            date = datetime.strptime(
                item['date'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=UTC())
        except:
            date = datetime.today()
            print('Cannot parse date in', item['title'])

        yaml_header = {
            'title': item['title'],
            # 'link': i['link'],
            # 'author': i['author'],
            'date': date,
            'description': item['description'],
            'slug': '/' + item['slug'],
            # 'wordpress_id': int(i['wp_id']),
            # 'comments': i['comments'],
        }

        if isinstance(item['excerpt'], str) and len(item['excerpt']) > 0:
            yaml_header['excerpt'] = item['excerpt']

        if item['status'] != 'publish':
            yaml_header['published'] = False

        if item['type'] in item_type_filter:
            pass
        elif item['type'] == 'post':
            out = set_item_type_post(item, item_uids, blogpath, yaml_header)
        elif item['type'] == 'page':
            out = set_item_type_page(item, item_uids, blogpath, yaml_header)
        else:
            print('Unknown item type :: ' + item['type'])

        # Set featured image if images exists
        if item['img_srcs']:
            featured_image_path = urljoin(
                data['header']['link'], str(item['img_srcs'][0]))
        else:
            featured_image_path = ''

        # Download images, if requested.
        if download_images:
            featured_image_path = download_item_images(
                item, attachments, blogpath)
        yaml_header['featuredImage'] = featured_image_path

        if out is not None:
            tax_out = {}
            for taxonomy in item['taxonomies']:
                for tvalue in item['taxonomies'][taxonomy]:
                    t_name = taxonomy_name_mapping.get(taxonomy, taxonomy)
                    if t_name not in tax_out:
                        tax_out[t_name] = []
                    if tvalue in tax_out[t_name]:
                        continue
                    tax_out[t_name].append(tvalue)

            out.write('---\n')
            if len(yaml_header) > 0:
                out.write(toyaml(yaml_header))
            if len(tax_out) > 0:
                out.write(toyaml(tax_out))

            out.write('---\n\n')
            try:
                out.write(html2fmt(item['body'], target_format))
            except:
                print('\n Parse error on: ' + item['title'])

            out.close()
    print('done\n')


# Get an array of paths of all the WordPress exports found in `wp_exports_dir`.
wp_exports_paths = glob(wp_exports_dir + '/*.xml')

for wp_export in wp_exports_paths:
    # Parse each export in to `data`.
    data = parse_wp_xml(wp_export)
    # print('data:', data)

    # Once done, write the jekyll output.
    write_jekyll(data, target_format)

print('done')
