# SPDX-FileCopyrightText: 2020 Jeff Epler for Adafruit Industries
#
# SPDX-License-Identifier: MIT

# audio_lib.py

"""
    CircuitPython Essentials Audio Out: plays MP3 and WAV files
    See: https://learn.adafruit.com/circuitpython-essentials/
                 circuitpython-audio-out
    Adapted by David Jones for Famous Trains, Derby. 2023

    - play .mp3 and .wav files from a micro SD card

    As module: classes and functions for:
    - play_audio.py
    - play_audio_i2s.py

    Note: class inheritance is not used (CP V 7.3.3 bug)
"""

# hardware
from digitalio import DigitalInOut, Direction, Pull

# audio
from audiomp3 import MP3Decoder
from audiocore import WaveFile
    
# SD storage
import busio
import sdcardio
import storage

# other
import os
import sys
from random import randint
import gc  # garbage collection for RAM


def file_ext(name_: str) -> str:
    """ return lower-case file extension """
    if name_.rfind('.', 1) > 0:
        ext_ = name_.rsplit('.', 1)[1].lower()
    else:
        ext_ = ''
    return ext_


def shuffle(tuple_: tuple) -> tuple:
    """ return a shuffled tuple of a tuple or list
        - Durstenfeld / Fisher-Yates shuffle algorithm """
    n = len(tuple_)
    if n < 2:
        return tuple_
    s_list = list(tuple_)
    limit = n - 1
    for i in range(limit):  # exclusive range
        j = randint(i, limit)  # inclusive range
        s_list[i], s_list[j] = s_list[j], s_list[i]
    return tuple(s_list)


class SdReader:
    """ sd card reader, SPI protocol """

    def __init__(self, clock, mosi, miso, cs, sd_dir='/sd'):
        if sd_dir[-1] != '/':
            self.dir = sd_dir + '/'
        spi = busio.SPI(clock, MOSI=mosi, MISO=miso)
        try:
            sd_card = sdcardio.SDCard(spi, cs)
        except OSError:
            print('No SD card found.')
            sys.exit()
        vfs = storage.VfsFat(sd_card)
        storage.mount(vfs, sd_dir)


class Button:
    """ input button, pull-up logic """

    def __init__(self, pin):
        self._pin_in = DigitalInOut(pin)
        self._pin_in.direction = Direction.INPUT
        self._pin_in.pull = Pull.UP

    @property
    def is_on(self) -> bool:
        """ pull-up logic for button pressed """
        return not self._pin_in.value

    @property
    def is_off(self) -> bool:
        """ pull-up logic for button not pressed """
        return self._pin_in.value


class PinOut:
    """ output pin """
    
    def __init__(self, pin):
        self._pin_out = DigitalInOut(pin)
        self._pin_out.direction = Direction.OUTPUT
        
    @property
    def state(self) -> bool:
        """ pin state """
        return self._pin_out.value
    
    @state.setter
    def state(self, value):
        self._pin_out.value = value


class AudioPlayer:
    """ play audio files under button control
        - only one instance is supported by CP running on a Pico
            -- CP reports insufficient number of timers
        - audio is an MP3 or WAV file
        - plays all audio files in: m_dir
        - audio_channel can be line or I2S output
        - CircuitPython supports mono and stereo audio,
            at 22 KHz sample rate (or less) and
            16-bit WAV format
        See: https://learn.adafruit.com/circuitpython-essentials/
             circuitpython-audio-out  
    """

    # for LED pin
    off = False
    on = True

    ext_list = ('mp3', 'wav')

    def __init__(self, m_dir: str, audio_channel: AudioOut,
                 play_buttons: tuple, skip_button: Button, wait_led: PinOut):
        self.m_dir = m_dir
        self.audio_channel = audio_channel
        self.play_buttons = play_buttons
        self.skip_button = skip_button
        self.wait_led = wait_led
        self.files = self.get_audio_filenames()
        self.decoder = self._set_decoder()

    def get_audio_filenames(self) -> tuple:
        """ from folder, return a list of type in ext_list
            - CircuitPython libraries replay .mp3 or .wav files
            - skip system files with first char == '.' """
        try:
            file_list = os.listdir(self.m_dir)
        except OSError:
            print(f'Error in reading directory: {self.m_dir}') 
            sys.exit()
        return tuple([f for f in file_list
                      if f[0] != '.' and file_ext(f) in self.ext_list])

    def wait_audio_finish(self):
        """ wait for audio to complete or skip_button pressed """
        while self.audio_channel.playing:
            if self.skip_button.is_on:
                self.audio_channel.stop()

    def wait_button_press(self):
        """ wait for a button to be pressed """
        print('Waiting for button press ...')
        wait = True
        while wait:
            for button in self.play_buttons:
                if button.is_on:
                    wait = False

    def _set_decoder(self) -> MP3Decoder:
        """ return decoder if .mp3 file found
            else set to None """
        decoder = None
        for filename in self.files:
            if file_ext(filename) == 'mp3':
                # decoder instantiation requires a file
                decoder = MP3Decoder(open(self.m_dir + filename, 'rb'))
                break  # instantiate once only
        return decoder

    def play_audio_file(self, filename: str, print_name: bool = False):
        """ play single audio file """
        try:
            audio_file = open(self.m_dir + filename, 'rb')
        except OSError:
            print(f'File not found: {filename}')
            return
        ext = file_ext(filename)
        if ext == 'mp3':
            self.decoder.file = audio_file
            stream = self.decoder
        elif ext == 'wav':
            stream = WaveFile(audio_file)
        else:
            print(f'Cannot play: {filename}')
            return
        if print_name:
            print(f'playing: {filename}')
        self.audio_channel.play(stream)

    def play_audio_files(self):
        """ play mp3 and wav files under button control """
        list_index = 0
        while True:
            list_index = (list_index + 1) % len(self.files)
            filename = self.files[list_index]
            gc.collect()  # free up memory between plays
            self.wait_led.state = self.on
            self.wait_button_press()
            self.wait_led.state = self.off
            self.play_audio_file(filename, print_name=True)
            self.wait_audio_finish()


def main():
    print('This file should be loaded to CircuitPython storage as a module.')


if __name__ == '__main__':
    main()
