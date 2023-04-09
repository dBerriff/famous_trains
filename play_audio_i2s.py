# SPDX-FileCopyrightText: 2020 Jeff Epler for Adafruit Industries
#
# SPDX-License-Identifier: MIT

# play_audio.py

"""
    CircuitPython Essentials Audio Out: plays MP3 and WAV files
    See: https://learn.adafruit.com/circuitpython-essentials/
                 circuitpython-audio-out
    Adapted by David Jones for Famous Trains, Derby. 2023
    
    I2SOut pins: bit_clock and word_select pins must be consecutive
    and in pin order
    
      Example of I2SOut pins  -->  MAX98357A

          16 bit_clock   ___  __>  LRC
                            \/       
          17 word_select ___/\__>  BCLK

          18 data        _______>  DIN

"""

import board
from audiobusio import I2SOut
from audio_lib import Button, PinOut, SdReader, AudioPlayer
     

def main():
    """ test: play audio files under button control
        - pins for Cytron Maker Pi Pico board """

    audio_source = {'SD': '/sd/audio/', 'board': '/'}

    # === USER parameters ===
    
    audio_folder = audio_source['SD']  # 'SD' or 'board'

    # button pins
    play_pins = board.GP20, board.GP21
    skip_pin = board.GP22  # useful while testing
    
    # I2S audio-out pins
    bit_clock = board.GP16
    word_select = board.GP17  # bit_clock pin + 1
    data = board.GP18

    # LED: indicates waiting for Play button push
    led_pin = board.LED

    button_control = True  # set to: True or False

    # === end USER parameters ===
    
    # assign the board pins
    # play_buttons: list or tuple
    if type(play_pins) != tuple:  # checking type(Pin) throws error
        play_buttons = Button(play_pins),
    else:
        play_buttons = tuple(Button(pin) for pin in play_pins)
    skip_btn = Button(skip_pin)
    led_out = PinOut(led_pin)
    
    # mound SD-card if required
    print(f'audio folder requested: {audio_folder}')
    if '/sd/' in audio_folder:
        # pins for Cytron Maker Pi Pico
        sd_card = SdReader(board.GP10,  # clock
                           board.GP11,  # mosi
                           board.GP12,  # miso
                           board.GP15)  # cs
        print(f'SD card mounted as: {sd_card.file_dir}')
    
    audio_channel = I2SOut(bit_clock, word_select, data)
    audio_player = AudioPlayer(audio_folder, audio_channel,
                               play_buttons, skip_btn, led_out,
                               button_mode=button_control)

    # optional: shuffle the file order
    audio_player.shuffle_files()
    print(f'audio files: {audio_player.files}')
    print()
    # play a file at startup to check system
    audio_player.play_audio_file(audio_player.files[0], print_name=True)
    audio_player.wait_audio_finish()
    audio_player.play_all_files()


if __name__ == '__main__':
    main()
