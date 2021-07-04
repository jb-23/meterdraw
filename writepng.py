# ############################################################################ #
#  Copyright (c) 2021, Jason Bamford  www.bamfordresearch.com                  #
#  All rights reserved.                                                        #
#                                                                              #
#  This source code is licensed under the Modified BSD License found           #
#  in the LICENSE.md file in the root directory of this source tree.           #
# ############################################################################ #

import zlib


def encode_png(filename, planes, width, card=None, dpi=72):
    height = int(len(planes[0]) / width)
    if card is None: card = "www.bamfordresearch.com"

    signature = bytes((137, 80, 78, 71, 13, 10, 26, 10))

    chunk_ihdr = make_chunk("IHDR", make_header_data(width, height))

    chunk_phys = make_chunk("pHYs", make_physical_data(dpi))

    chunk_text = make_chunk("tEXt", make_text_data("Software", card))

    blob = pass_image(width, planes)
    data = zlib.compress(bytes(blob))
    chunk_idat = make_chunk("IDAT", data)

    chunk_iend = make_chunk("IEND")

    with open(filename, 'wb') as file:
        file.write(signature)
        file.write(chunk_ihdr)
        file.write(chunk_phys)
        file.write(chunk_text)
        file.write(chunk_idat)
        file.write(chunk_iend)


def make_chunk(type, data=b""):
    b = len(data).to_bytes(4, byteorder="big")  # Length of Data
    b += bytes(type, "ascii")                   # Chunk Type
    b += data                                   # Data Field
    crc = zlib.crc32(bytes(type, "ascii"))
    crc = zlib.crc32(data, crc)
    b += crc.to_bytes(4, byteorder="big")       # CRC
    return b

def make_header_data(width, height):
    b = width.to_bytes(4, byteorder="big")    # Width
    b += height.to_bytes(4, byteorder="big")  # Height
    b += (8).to_bytes(1, byteorder="big")     # Bit Depth
    b += (2).to_bytes(1, byteorder="big")     # Color Type = Truecolor
    b += (0).to_bytes(1, byteorder="big")     # Compression Method
    b += (0).to_bytes(1, byteorder="big")     # Filter Method
    b += (0).to_bytes(1, byteorder="big")     # Interlace Method = None
    return b

def make_physical_data(dpi): # Chunk pHYs
    x = int(dpi * 1000 / 25.4 + 0.5)
    b = x.to_bytes(4, byteorder="big")
    b += x.to_bytes(4, byteorder="big")
    b += (1).to_bytes(1, byteorder="big")
    return b

def make_text_data(keyword, text):
    b = bytes(keyword, "ascii")
    b += (0).to_bytes(1, byteorder="big")
    b += bytes(text, "ascii")
    return b

def pass_image(width, planes):
    lines = int(len(planes[0]) / width)
    blob = []
    for i in range(0, lines):
        scanline = get_scanline(i, width, planes)
        filtered = filter_0(scanline)
        blob += filtered
    return blob

def get_scanline(line_number, width, planes):
    start = line_number * width
    scanline = []
    for i in range(start, start+width):
        for p in planes:
            scanline.append(p[i])
    return scanline

def filter_0(scanline):
    return [0] + scanline

