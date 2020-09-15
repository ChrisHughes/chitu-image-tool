#!/usr/bin/python3

import argparse
import glob
from PIL import Image, ImageOps
import os
import sys

def rgb888_to_rgb565(color):
    r = (color[0] & 0b11111000) << 8
    g = (color[1] & 0b11111100) << 3
    b = color[2] >> 3
    return r | g | b

def rgb565_to_rgb888(word):
    r = (word & 0b1111100000000000) >> 8
    g = (word & 0b0000011111100000) >> 3
    b = (word & 0b0000000000011111) << 3
    return (r, g, b)

def process_image(file, width = 0, height = 0):
    # Loads and processes image file
    img_f = Image.open(file)
    img = img_f.copy()
    img_f.close()
    if width and height:
        img = ImageOps.fit(img, (width, height), Image.ANTIALIAS)
    return img

def encode(img, tag = bytearray(b'\x0B\x00\xFD\x12')):
    width = img.size[0]
    height = img.size[1]
    # Initialize new buffer with lead-in data
    data = tag + bytearray(b'\x00\x00\x00\x00')
    pixels = img.load() # create the pixel map
    # Flag set when last byte in data is control word
    global last_byte_control
    last_byte_control = False

    def commit(color, counter):
        global last_byte_control
        if not counter:
            return
        # Write color
        high_byte = (color & 0xFF00) >> 8
        low_byte = color & 0xFF
        # If color high byte falls in range of control bytes,
        # ensure we signal this with preceding color
        if last_byte_control == False:
            data[-1] &= 0b11011111
        data.append(high_byte)
        data.append(low_byte)
        last_byte_control = False
        # Decrement counter as color entry counts for 1
        counter -= 1
        # Note: Some revisions of Chitu firmware do not use this optimization
        # Prevent committing zero-pixel RLE entries
        if counter == 1:
            data[-1] &= 0b11011111
            data.append(high_byte)
            data.append(low_byte)
            counter -= 1
        if not counter:
            return
        # Set last pixel to signify control byte
        data[-1] |= 0b00100000
        # Write control code
        carry_over = max(0, counter - 0xFFE)
        counter = min(0xFFE, counter)
        high_byte = 0b00110000 | ((counter & 0b111100000000) >> 8)
        low_byte = counter & 0xFF
        data.append(high_byte)
        data.append(low_byte)
        last_byte_control = True
        if carry_over:
            commit(color, carry_over)
    
    # Last color
    last_color = None
    # RLE counter
    counter = 0
    for y in range(img.size[1]):    # for every col:
        for x in range(img.size[0]):    # For every row
            color = rgb888_to_rgb565(pixels[x,y])
            counter += 1
            if last_color is None: last_color = color
            if color != last_color:
                commit(last_color, counter - 1)
                counter = 1
                last_color = color
    commit(last_color, counter)
        
    # Write data length to header
    data_length = len(data) - 8
    data[4] = data_length & 0xFF
    data[5] = (data_length & 0xFF00) >> 8
    data[6] = (data_length & 0xFF0000) >> 16
    data[7] = (data_length & 0xFF000000) >> 24
    
    return data

def decode(data, width, height):
    # Decodes image file to PIL image
    tag = data[0] | (data[1] << 8) | (data[2] << 16) | (data[3] << 24)
    size = data[4] | (data[5] << 8) | (data[6] << 16) | (data[7] << 24)

    # Create PIL image
    img = Image.new('RGB', (width, height))
    pixels = img.load() # create the pixel map

    # Current draw color
    color = (0,0,0)
    # Start byte
    index = 0x8
    # Byte counter
    counter = -1
    # Current color pixel
    pixel = 0
    data_size = len(data)
    for y in range(img.size[1]):    # for every col:
        for x in range(img.size[0]):    # For every row
            if counter <= 0:
                high_byte = data[index]
                low_byte = data[index + 1]
                index += 2
                # If valid control signal
                if counter < 0 and high_byte >= 0x30 and high_byte < 0x40 and pixel & 0b100000:
                    counter = ((high_byte & 0b1111) << 8) | low_byte
                    if counter > 100 and pixel == 0xC638:
                        print(hex(high_byte), hex(low_byte))
                else:
                    pixel = (high_byte << 8) | low_byte
                    color = rgb565_to_rgb888(pixel)
            pixels[x,y] = color
            counter -= 1
    if index - 0x8 > size:
        raise IndexError("Buffer overrun")
    return tag, img

class ImageItem:
    def __init__(self, unk1, tag, offset, group_tag, width, height):
        self.unk1 = unk1
        self.tag = tag
        self.offset = offset
        self.group_tag = group_tag
        self.width = width
        self.height = height
        
    def __repr__(self):
        return 'unk1=0x%04x, tag=0x%04x, offset=0x%04x, group_tag=0x%04x, width=%d, height=%d' % (self.unk1, self.tag, self.offset, self.group_tag, self.width, self.height)
        
def decode_ui_package(data):
    # For each directory entry (starting at 0x18)
    # 4 bytes ????
    # 4 bytes 'tag'
    # 4 bytes 'location'
    # 4 bytes 'group_tag'
    # 2 bytes W
    # 2 bytes H
    tag = data[0] | (data[1] << 8) | (data[2] << 16) | (data[3] << 24)
    size = data[4] | (data[5] << 8) | (data[6] << 16) | (data[7] << 24)
    # Check file size
    assert(size == len(data) - 8)
    index = 0x18
    output = []
    first_tag = None
    
    # Directory contains 'zero' entries as tags need to be sequential
    while True:
        item_unk1 = data[index + 0] | (data[index + 1] << 8) | (data[index + 2] << 16) | (data[index + 3] << 24)
        item_tag = data[index + 4] | (data[index + 5] << 8) | (data[index + 6] << 16) | (data[index + 7] << 24)
        item_offset = data[index + 8] | (data[index + 9] << 8) | (data[index + 10] << 16) | (data[index + 11] << 24)
        item_group_tag = data[index + 12] | (data[index + 13] << 8) | (data[index + 14] << 16) | (data[index + 15] << 24)
        item_width = data[index + 16] | (data[index + 17] << 8)
        item_height = data[index + 18] | (data[index + 19] << 8)
        if first_tag is not None and first_tag == item_tag:
            break
        if first_tag is None:
            first_tag = item_tag
        index += 20
        image_item = ImageItem(item_unk1, item_tag, item_offset, item_group_tag, item_width, item_height)
        output.append(image_item)
    
    # Check we have a complete directory with matching tags to offsets
    for item in output:
        if item.tag == 0:
            continue
        index = item.offset
        item_tag = data[index + 0] | (data[index + 1] << 8) | (data[index + 2] << 16) | (data[index + 3] << 24)
        item_size = data[index + 4] | (data[index + 5] << 8) | (data[index + 6] << 16) | (data[index + 7] << 24)
        assert(item.tag == item_tag)

    return tag, output

def encode_ui_package(files, tag):
    data = bytearray()
    data.append(tag & 0xFF)
    data.append((tag >> 8) & 0xFF)
    data.append((tag >> 16) & 0xFF)
    data.append((tag >> 24) & 0xFF)
    # Placeholder for size
    data.extend(b'\x00\x00\x00\x00')
    data.extend([0] * 0x10)
    images = []
    index = 0x18
    assert(len(files) > 0)
    files.sort()
    last_tag = 0
    for file in files:
        img = process_image(file)
        item_tag = auto_int(file.split(os.path.sep)[-1].split('_')[1])
        # Generate sequential placeholders
        if last_tag == 0:
            last_tag = item_tag & 0xFFFF
        for i in range((item_tag & 0xFFFF) - last_tag - 1):
            print(0)
            data.extend([0] * 0x14)
            index += 0x14
        last_tag = item_tag & 0xFFFF
        item_group_tag = auto_int(file.split(os.path.sep)[-1].split('_')[2].split('.')[0])
        item = ImageItem(0, item_tag, 0, item_group_tag, img.size[0], img.size[1])
        images.append((img, item))
        data.append(item.unk1 & 0xFF)
        data.append((item.unk1 >> 8) & 0xFF)
        data.append((item.unk1 >> 16) & 0xFF)
        data.append((item.unk1 >> 24) & 0xFF)
        index += 0x4
        data.append(item.tag & 0xFF)
        data.append((item.tag >> 8) & 0xFF)
        data.append((item.tag >> 16) & 0xFF)
        data.append((item.tag >> 24) & 0xFF)
        index += 0x4
        # Placeholder for offset
        data.extend([0] * 4)
        index += 0x4
        data.append(item.group_tag & 0xFF)
        data.append((item.group_tag >> 8) & 0xFF)
        data.append((item.group_tag >> 16) & 0xFF)
        data.append((item.group_tag >> 24) & 0xFF)
        index += 0x4
        data.append(item.width & 0xFF)
        data.append((item.width >> 8) & 0xFF)
        index += 0x2
        data.append(item.height & 0xFF)
        data.append((item.height >> 8) & 0xFF)
        index += 0x2
    # Add directory termination
    data.append(images[0][1].tag & 0xFF)
    data.append((images[0][1].tag >> 8) & 0xFF)
    data.append((images[0][1].tag >> 16) & 0xFF)
    data.append((images[0][1].tag >> 24) & 0xFF)
    index += 0x4
    # Begin image data
    for image_item in images:
        item = image_item[1]
        item_tag = bytearray()
        item_tag.append(item.tag & 0xFF)
        item_tag.append((item.tag >> 8) & 0xFF)
        item_tag.append((item.tag >> 16) & 0xFF)
        item_tag.append((item.tag >> 24) & 0xFF)
        image_data = encode(image_item[0], item_tag)
        data.extend(image_data)
        item_size = len(image_data)
        # Backfill offset
        data[0x4 + (item.tag & 0xFFFF) * 0x14 + 0x8] = index & 0xFF
        data[0x4 + (item.tag & 0xFFFF) * 0x14 + 0x9] = (index >> 8) & 0xFF
        data[0x4 + (item.tag & 0xFFFF) * 0x14 + 0xA] = (index >> 16) & 0xFF
        data[0x4 + (item.tag & 0xFFFF) * 0x14 + 0xB] = (index >> 24) & 0xFF
        index += item_size
    # Write master package size
    size = len(data) - 8
    assert(index == size)
    data[0x4] = size & 0xFF
    data[0x5] = (size >> 8) & 0xFF
    data[0x6] = (size >> 16) & 0xFF
    data[0x7] = (size >> 24) & 0xFF
    return data
    
if __name__ == "__main__":
    def auto_int(x):
        return int(x, 0)
    def auto_int_list(x):
        return list(map(lambda y: auto_int(y), x.split(',')))
    parser = argparse.ArgumentParser(description='Encoder and decoder for boot screen image stored in firmware of Tronxy 3D Printers.')
    # Main action of app
    subparsers = parser.add_subparsers(dest='action', required=True, help='Action to perform')
    # Encode (.logo)
    parser_encode = subparsers.add_parser('encode')
    parser_encode.add_argument('Input', metavar='input', type=str, help='Input file (image)')
    parser_encode.add_argument('Output', metavar='output', type=str, help='Output file (.logo)')
    parser_encode.add_argument('-t', '--tag', type=auto_int, default=0x12FD000B, help='Image tag (defaults to bootscreen)')
    parser_encode.add_argument('-W', '--width', type=auto_int, default=480, help='Width of image to encode (480)')
    parser_encode.add_argument('-H', '--height', type=auto_int, default=320, help='Height of image to encode (320)')
    # Decode (.logo)
    parser_decode = subparsers.add_parser('decode')
    parser_decode.add_argument('Input', metavar='input', type=str, help='Input file (.logo)')
    parser_decode.add_argument('-o', '--output', type=str, help='Output decoded image to file (.png)')
    parser_decode.add_argument('-s', '--show', action='store_true', help='Show the image after decode')
    parser_decode.add_argument('-W', '--width', type=auto_int, default=480, help='Width of image to decode (480)')
    parser_decode.add_argument('-H', '--height', type=auto_int, default=320, help='Height of image to decode (320)')
    # Decode package (.bin)
    parser_decode_package = subparsers.add_parser('decode_package')
    parser_decode_package.add_argument('Input', metavar='input', type=str, help='Input file (.bin)')
    parser_decode_package.add_argument('-t', '--tags', type=auto_int_list, help='Decode a specific image tag from the package (comma separated)')
    # Encode package (.bin)
    parser_encode_package = subparsers.add_parser('encode_package')
    parser_encode_package.add_argument('Input', metavar='input', type=str, help='Input folder')
    parser_encode_package.add_argument('Output', metavar='output', type=str, help='Output file (.bin)')
    parser_encode_package.add_argument('-t', '--tag', type=auto_int, help='Collection tag (uses folder name by default)')

    args = parser.parse_args()

    if args.action == 'encode':
        # Encode image file
        input_file = args.Input
        if not os.path.isfile(input_file):
            print('The path specified does not exist')
            sys.exit(1)
        img = process_image(input_file, args.width, args.height)
        tag = bytearray()
        tag.append(args.tag & 0xFF)
        tag.append((args.tag >> 8) & 0xFF)
        tag.append((args.tag >> 16) & 0xFF)
        tag.append((args.tag >> 24) & 0xFF)
        data = encode(img, tag)
        output_file = args.Output
        if output_file != None:
            if not os.path.isdir(os.path.dirname(os.path.abspath(output_file))):
                print('The output directory specified does not exist')
                sys.exit(2)
        file_ptr = open(output_file, 'wb')
        file_ptr.write(data)
        file_ptr.close()

    elif args.action == 'decode':
        # Read image to bytes
        input_file = args.Input
        if not os.path.isfile(input_file):
            print('The path specified does not exist')
            sys.exit(1)
        file_ptr = open(input_file, "rb")
        data = file_ptr.read()
        file_ptr.close()
        tag, img = decode(data, args.width, args.height)
        output_file = args.output
        if output_file != None:
            if not os.path.isdir(os.path.dirname(os.path.abspath(output_file))):
                print('The output directory specified does not exist')
                sys.exit()
            img.save(output_file)
        if args.show:
            img.show()

    elif args.action == 'decode_package':
        # Decode package such as UI catalog
        input_file = args.Input
        if not os.path.isfile(input_file):
            print('The path specified does not exist')
            sys.exit()
        file_ptr = open(input_file, "rb")
        data = file_ptr.read()
        file_ptr.close()
        tag, package = decode_ui_package(data)
        if not os.path.isdir(hex(tag)):
            os.makedirs(hex(tag))
        files = glob.glob(hex(tag) + '/img_*_*.png')
        for f in files:
            os.remove(f)
        for item in package:
            if item.offset == 0:
                continue
            if args.tags is not None and item.tag not in args.tags:
                continue
            item_tag, img = decode(data[item.offset:], item.width, item.height)
            img.save(os.path.join(hex(tag), 'img_' + hex(item_tag) + '_' + hex(item.group_tag) + '.png'))
    
    elif args.action == 'encode_package':
        # Encode package such as UI catalog
        input_folder = args.Input
        if not os.path.isdir(input_folder):
            print('The folder specified does not exist')
            sys.exit()
        tag = args.tag
        if tag is None:
            try:
                tag = auto_int(input_folder)
            except:
                print("Failed to get tag from folder name, please specify 4 byte tag with --tag 0x12345678")
                sys.exit(1)
        output_file = args.Output
        if output_file != None:
            if not os.path.isdir(os.path.dirname(os.path.abspath(output_file))):
                print('The output directory specified does not exist')
                sys.exit(2)
        files = glob.glob(input_folder + '/img_*_*.png')
        data = encode_ui_package(files, tag)
        file_ptr = open(output_file, "wb")
        file_ptr.write(data)
        file_ptr.close()
