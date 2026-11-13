# Based on Pimoroni Badger 2040 badge example code, Copyright (c) Pimoroni Ltd, MIT License.
# https://github.com/pimoroni/badger2040  (see THIRD_PARTY_NOTICES.md).
import badger2040
import jpegdec
import pngdec
import qrcode
import gc
import os
import time
import math
import badger_os


# Global Constants
WIDTH = badger2040.WIDTH
HEIGHT = badger2040.HEIGHT

IMAGE_WIDTH = 104

COMPANY_HEIGHT = 30
DETAILS_HEIGHT = 20
NAME_HEIGHT = HEIGHT - COMPANY_HEIGHT - (DETAILS_HEIGHT * 2) - 2
TEXT_WIDTH = WIDTH - IMAGE_WIDTH - 1

COMPANY_TEXT_SIZE = 2
NAME_TEXT_SIZE = 0.8
DETAILS_TEXT_SIZE = 0.6
QR_TEXT_SIZE = 0.6

LEFT_PADDING = 5
NAME_PADDING = 5
DETAIL_SPACING = 10


COMPANY = "AWS Community South Africa"
NAME = "Hennie Francis"
HANDLE = "Executive Director"
JOB = "awscommunity.co.za"

QRCODE_LINK = "https://henniefrancis.tech"
QRCODE_TITLE_1 = "Scan for my"
QRCODE_TITLE_2 = "Socials!"
QRCODE_TITLE_3 = "@henniefrancis"

# ------------------------------
#      Drawing functions
# ------------------------------

def measure_qr_code(size, code):
    w, h = code.get_size()
    module_size = int(size / w)
    return module_size * w, module_size


def draw_qr_code(ox, oy, size, code):
    size, module_size = measure_qr_code(size, code)
    display.set_pen(15)
    display.rectangle(ox, oy, size, size)
    display.set_pen(0)
    for x in range(size):
        for y in range(size):
            if code.get_module(x, y):
                display.rectangle(ox + x * module_size, oy + y * module_size, module_size, module_size)


def draw_qr_txt_code():
    display.led(128)
  
    # Clear the Display
    display.set_pen(15)  # Change this to 0 if a white background is used
    display.clear()
    
    display.set_pen(0)

    code.set_text(QRCODE_LINK)
    size, _ = measure_qr_code(128, code)
    left = top = int((badger2040.HEIGHT / 2) - (size / 2))
    draw_qr_code(left, top, 128, code)

    left = 128 + 5

    display.set_font("sans")
    display.text(QRCODE_TITLE_1, left, 40, badger2040.WIDTH, QR_TEXT_SIZE)
    display.text(QRCODE_TITLE_2, left, 60, badger2040.WIDTH, QR_TEXT_SIZE)
    display.text(QRCODE_TITLE_3, left, 100, badger2040.WIDTH, QR_TEXT_SIZE)

    
    display.update()
    

# Draw the badge, including user text
def draw_txt_badge():
    display.set_pen(0)
    display.clear()

    # Draw badge image
    png.open_file("/hennie.png")
    png.decode(WIDTH - IMAGE_WIDTH, 0)

    # Draw a border around the image
    display.set_pen(0)
    display.line(WIDTH - IMAGE_WIDTH, 0, WIDTH - 1, 0)
    display.line(WIDTH - IMAGE_WIDTH, 0, WIDTH - IMAGE_WIDTH, HEIGHT - 1)
    display.line(WIDTH - IMAGE_WIDTH, HEIGHT - 1, WIDTH - 1, HEIGHT - 1)
    display.line(WIDTH - 1, 0, WIDTH - 1, HEIGHT - 1)

    display.set_pen(15)  # Change this to 0 if a white background is used
    display.set_font("bitmap8")
    display.text(COMPANY, LEFT_PADDING, 5, WIDTH, COMPANY_TEXT_SIZE)

    # Draw a white background behind the name
    display.set_pen(15)
    display.rectangle(1, COMPANY_HEIGHT + 1, TEXT_WIDTH, NAME_HEIGHT)

    # Draw the name, scaling it based on the available width
    display.set_pen(0)
    display.set_font("sans")
    
    name_length = display.measure_text(NAME, NAME_TEXT_SIZE)

    display.text(NAME, (TEXT_WIDTH - name_length) // 2, (NAME_HEIGHT // 2) + COMPANY_HEIGHT + 1, WIDTH, NAME_TEXT_SIZE)
            
    # Draw a white backgrounds behind the details
    display.set_pen(15)
    display.rectangle(1, HEIGHT - DETAILS_HEIGHT * 2, TEXT_WIDTH, DETAILS_HEIGHT - 1)
    display.rectangle(1, HEIGHT - DETAILS_HEIGHT, TEXT_WIDTH, DETAILS_HEIGHT - 1)

    # Draw the first detail's title and text
    display.set_pen(0)
    display.set_font("sans")
    name_length = display.measure_text(HANDLE, DETAILS_TEXT_SIZE)
    display.text(HANDLE, LEFT_PADDING, HEIGHT - ((DETAILS_HEIGHT * 3) // 2), WIDTH, DETAILS_TEXT_SIZE)

    # Draw the second detail's title and text
    name_length = display.measure_text(JOB, DETAILS_TEXT_SIZE)
    display.text(JOB, LEFT_PADDING, HEIGHT - (DETAILS_HEIGHT // 2), WIDTH, DETAILS_TEXT_SIZE)

    display.update()
    
def button(pin):
    global changed
    changed = True

    if pin == badger2040.BUTTON_UP:
        draw_txt_badge()
    if pin == badger2040.BUTTON_DOWN:
        draw_qr_txt_code()


# ------------------------------
#        Program setup
# ------------------------------

# Create a new Badger and set it to update NORMAL
display = badger2040.Badger2040()
display.led(128)
display.set_update_speed(badger2040.UPDATE_NORMAL)
display.set_thickness(2)

png = pngdec.PNG(display.display)

code = qrcode.QRCode()

# ------------------------------
#       Main program
# ------------------------------

draw_txt_badge()

while True:
    # Sometimes a button press or hold will keep the system
    # powered *through* HALT, so latch the power back on.
    display.keepalive()
    
    if display.pressed(badger2040.BUTTON_UP):
        button(badger2040.BUTTON_UP)
    if display.pressed(badger2040.BUTTON_DOWN):
        button(badger2040.BUTTON_DOWN)

    # If on battery, halt the Badger to save power, it will wake up if any of the front buttons are pressed
    display.halt()
