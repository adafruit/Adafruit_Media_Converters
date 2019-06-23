#!/usr/bin/python

# Image and sound converter -- generates PROGMEM arrays for Arduino sketches
# from WAV files and common image formats.  Requires PIL or Pillow library.

import sys
import math
from PIL import Image   # install with `pip install pillow`
from os import path


# FORMATTED HEX OUTPUT -----------------------------------------------------

class HexTable:

  # Initialize counters, etc. for write() function below
  def __init__(self, count, columns=12, digits=2):
    self.hexLimit   = count   # Total number of elements in array
    self.hexCounter = 0       # Current array element number 0 to hexLimit-1
    self.hexDigits  = digits  # Digits per array element (after 0x)
    self.hexColumns = columns # Max number of elements before line wrap
    self.hexColumn  = columns # Current column number, 0 to hexColumns-1
    # hexColumn is initialized to columns to force first-line indent

  # Write hex value (with some formatting for C array) to stdout
  def write(self, n):
    if self.hexCounter > 0:
      sys.stdout.write(",")                      # Comma-delimit prior item
      if self.hexColumn < (self.hexColumns - 1): # If not last item on line,
        sys.stdout.write(" ")                    # append space after comma
    self.hexColumn += 1                          # Increment column number
    if self.hexColumn >= self.hexColumns:        # Max column exceeded?
      sys.stdout.write("\n  ")                   # Line wrap, indent
      self.hexColumn = 0                         # Reset column number
    sys.stdout.write("{0:#0{1}x}".format(n, self.hexDigits + 2))
    self.hexCounter += 1                         # Increment item counter
    if self.hexCounter >= self.hexLimit: print(" };\n"); # Cap off table


# IMAGE CONVERSION ---------------------------------------------------------

# Currently handles two modes of image conversion for specific projects:
# 1. Convert bitmap (2-color) image to PROGMEM array for Adafruit_GFX
#    drawBitmap() function.
# 2. Convert color or grayscale image to 5/6/5 color PROGMEM array for
#    NeoPixel animation (e.g. CircuitPlaygroundMakeBelieve project).

def convertImage(filename):
  try:
    prefix = path.splitext(path.split(filename)[1])[0]
    im     = Image.open(filename)

    if im.mode == '1':

      # BITMAP IMAGE
      pixels = im.load()
      hex    = HexTable(((im.size[0] + 7) // 8) * im.size[1], 12, 2)

      sys.stderr.write("Image OK\n")
      sys.stdout.write(
        "#define %sWidth  %d\n"
        "#define %sHeight %d\n"
        "const uint8_t PROGMEM %sBitmap[] = {" %
        (prefix, im.size[0], prefix, im.size[1], prefix))

      for y in range(im.size[1]):
        bits = 0
        sum  = 0
        for x in range(im.size[0]):
          p     = 1 if pixels[x, y] > 0 else 0
          sum   = (sum << 1) + p
          bits += 1
          if bits >= 8:
            hex.write(sum)
            bits = 0
            sum  = 0
        if bits > 0: # Scanline pad if not a multiple of 8
          hex.write(sum)

      return 0 # Bitmap image; no gamma tables needed

    else:

      # COLOR OR GRAYSCALE IMAGE
      # Image height should match NeoPixel strip length,
      # no conversion or runtime checks are performed.

      im     = im.convert("RGB")
      pixels = im.load()
      hex    = HexTable(im.size[0] * im.size[1], 9, 4)

      sys.stderr.write("Image OK\n")
      sys.stdout.write(
        "#define %sFPS 30\n"
        "const uint16_t PROGMEM %sPixelData[] = {" %
        (prefix, prefix))

      # Quantize 24-bit image to 16 bits:
      # RRRRRRRR GGGGGGGG BBBBBBBB -> RRRRRGGGGGGBBBBB
      for x in range(im.size[0]): # Column major
        for y in range(im.size[1]):
          p = pixels[x, y]
          hex.write(((p[0] & 0b11111000) << 8) |
                    ((p[1] & 0b11111100) << 3) |
                    ( p[2] >> 3))

      return 1 # Color/gray image; generate gamma tables

  except:
    sys.stderr.write("Not an image file (?)\n")
  return -1 # Fail


# AUDIO CONVERSION ---------------------------------------------------------

# Output is always mono (stereo sources will be 50/50 mixed), 8- or 10-bit.

reduce16 = 8 # 16-bit audio reduction, MUST be 8 or 10

# Decode unsigned value from a series of bytes in WAV file (LSB first)
def uvalue(bytes):
  result = 0
  for i, b in enumerate(bytes):
    result += b << (i * 8)
  return result

def convertWav(filename):
  try:
    bytes = open(filename, "rb").read()

    assert bytes[0:4] == b'RIFF' and bytes[8:16] == b'WAVEfmt '
    
    prefix     = path.splitext(path.split(filename)[1])[0]
    chunksize  = uvalue(bytes[16:20])
    channels   = uvalue(bytes[22:24])
    rate       = uvalue(bytes[24:28])
    bytesPer   = uvalue(bytes[32:34])
    bitsPer    = uvalue(bytes[34:36])
    bytesTotal = uvalue(bytes[chunksize + 24:chunksize + 28])
    samples    = bytesTotal // bytesPer
    index_in   = chunksize + 28
    buf        = [0] * 5
    bufIdx     = 1

    if (bitsPer == 16) and (reduce16 == 10): bits = 10
    else:                                    bits =  8
    sys.stderr.write("WAV OK\n")
    sys.stdout.write(
      "#define %sSampleRate %d\n"
      "#define %sSamples    %d\n"
      "#define %sBits       %d\n\n"
      "const uint8_t PROGMEM %sAudioData[] = {" %
      (prefix, rate, prefix, samples, prefix, bits, prefix))

    # Merge channels, convert to 8- or 10-bit
    if bitsPer == 16:
      if reduce16 == 10:
        div = channels *  64
        # 5 bytes per 4 samples (pad to multiple of 4)
        hex = HexTable(5 * ((samples + 3) // 4), 12, 2)
      else:
        div = channels * 256
        hex = HexTable(samples, 12, 2)
    else:
      div = channels
      hex = HexTable(samples, 12, 2)

    for i in range(samples):
      sum = 0
      for c in range(channels):
        if bitsPer == 8:
          # 8-bit data is UNSIGNED
          sum      += bytes[index_in]
          index_in += 1
        elif bitsPer == 16:
          # 16-bit data is SIGNED, requires
          # conversion from unsigned 8-bit src
          x = (bytes[index_in] +
              (bytes[index_in + 1] << 8))
          if x & 0x8000: x -= 32768
          else:          x += 32768
          sum      += x
          index_in += 2

      if (bitsPer == 16) and (reduce16 == 10):
        sum //= div
        buf[0]      = (buf[0] << 2) | (sum >> 8)
        buf[bufIdx] = sum & 0xFF
        bufIdx += 1
        if bufIdx >= 5:
          for b in buf: hex.write(b)
          buf = [0] * 5
          bufIdx = 1
      else:
        hex.write(sum // div)

    if (bitsPer == 16) and (reduce16 == 10) and (bufIdx > 1):
      for b in buf: hex.write(b)

    return 1 # Success
  except AssertionError:
    sys.stderr.write("Not a WAV file\n")

  return -1 # Fail


# MAIN ---------------------------------------------------------------------

gammaFlag = 0

for i, filename in enumerate(sys.argv): # Each argument...
  if i == 0: continue # Skip first argument; is program name
  if filename == '10':
    reduce16 = 10
    continue
  if filename == '8':
    reduce16 = 8
    continue

  # Attempt image conversion.  If fails, try WAV conversion on same.
  foo = convertImage(filename)
  if foo == 1:       gammaFlag = 1 # Color/gray image was converted
  elif foo == -1: convertWav(filename) # Error; maybe WAV file?

# If any color/gray images loaded OK, output 5- and 6-bit gamma tables
if gammaFlag == 1:
  hex = HexTable(32, 12, 2)
  sys.stdout.write("const uint8_t PROGMEM gamma5[] = {")
  for i in range(32):
    hex.write(int(math.pow(float(i)/31.0,2.7)*255.0+0.5))
  hex = HexTable(64, 12, 2)
  sys.stdout.write("const uint8_t PROGMEM gamma6[] = {")
  for i in range(64):
    hex.write(int(math.pow(float(i)/63.0,2.7)*255.0+0.5))

