from machine import UART, Pin
import uasyncio as asyncio
import hex_fns as hex_f
from uart_os_as import Queue, StreamTR


class CommandHandler:
    """ formats, sends and receives command and query messages
        - see Flyron Technology Co documentation for references
        - www.flyrontech.com
    """

    BUF_SIZE = const(10)
    # data-byte indices
    CMD = const(3)
    P_H = const(5)  # parameter
    P_L = const(6)
    C_H = const(7)  # checksum
    C_L = const(8)

    R_FB = const(1)  # require ACK feedback
    WAIT_MS = const(200)

    data_template = {0: 0x7E, 1: 0xFF, 2: 0x06, 4: R_FB, 9: 0xEF}
    
    hex_str = {
        0x01: 'next',
        0x02: 'prev',
        0x03: 'track',  # 1-3000
        0x04: 'vol_inc',
        0x05: 'vol_dec',
        0x06: 'vol_set',  # 0-30
        0x07: 'eq_set',  # 0:normal/1:pop/2:rock/3:jazz/4:classic/5:bass
        0x08: 'repeat_trk',  # track # as parameter; 3.6.3
        0x0c: 'reset',
        0x0d: 'play',
        0x0e: 'stop',
        0x0f: 'folder_trk',  # play: MSB: folder; LSB: track
        0x11: 'repeat_all',  # root folder; 0: stop; 1: start
        0x3a: 'media_insert',
        0x3b: 'media_remove',
        0x3d: 'sd_fin',
        0x3f: 'q_init',  # 02: SD-card
        0x40: 'error',
        0x41: 'ack',
        0x42: 'q_status',  # 0: stopped; 1: playing; 2: paused
        0x43: 'q_vol',
        0x44: 'q_eq',
        0x48: 'q_sd_files',  # in root directory
        0x4c: 'q_sd_trk'
        }
    
    # inverse dictionary mapping
    str_hex = {value: key for key, value in hex_str.items()}

    # add Rx-only codes
    hex_str[0x3a] = 'media_insert'
    hex_str[0x3b] = 'media_remove'

    # build set of commands that play a track
    # required to clear the track_end_ev event
    play_set_str = {'play', 'next', 'prev', 'track', 'folder_trk',
                    'repeat_trk', 'repeat_all'}
    play_set = {0}
    # set comprehension raises an error
    for element in play_set_str:
        play_set.add(str_hex[element])
    play_set.remove(0)

    def __init__(self, stream):
        self.stream = stream
        self.tx_word = bytearray(self.BUF_SIZE)
        self.rx_word = bytearray(self.BUF_SIZE)
        # pre-load template fixed values
        for key in self.data_template:
            self.tx_word[key] = self.data_template[key]
        self.rx_cmd = 0x00
        self.rx_param = 0x0000
        self.track_count = 0  # not currently used
        self.current_track = 0  # not currently used
        self.ack_ev = asyncio.Event()
        self.track_end_ev = asyncio.Event()
        self.error_ev = asyncio.Event()  # not currently monitored
        self.verbose = True

    def get_checksum(self):
        """ return the 2's complement checksum of:
            - bytes 1 to 6 """
        return hex_f.slice_reg16(-sum(self.tx_word[1:7]))

    def check_checksum(self, buf_):
        """ returns 0 for consistent checksum """
        byte_sum = sum(buf_[1:self.C_H])
        checksum_ = buf_[self.C_H] << 8  # msb
        checksum_ += buf_[self.C_L]  # lsb
        return (byte_sum + checksum_) & 0xffff

    async def send_command(self, cmd_str, param=0):
        """ set tx bytearray values and send
            - commands set own timing """
        self.ack_ev.clear()  # require ACK
        cmd_hex = self.str_hex[cmd_str]
        self.tx_word[self.CMD] = cmd_hex
        self.tx_word[self.P_H], self.tx_word[self.P_L] = \
            hex_f.slice_reg16(param)
        self.tx_word[self.C_H], self.tx_word[self.C_L] = \
            self.get_checksum()
        if cmd_hex in self.play_set:
            self.track_end_ev.clear()
        await self.stream.sender(self.tx_word)
        print('Tx:', cmd_str, hex_f.byte_str(cmd_hex), hex_f.reg16_str(param))
        await self.ack_ev.wait()

    async def consume_rx_data(self):
        """ parses and prints queued data """

        def parse_rx_message(message_):
            """ parse incoming message parameters and
                set dependent attributes
                - partial implementation for known requirements """
            rx_str_cmd = self.hex_str[message_[self.CMD]]
            rx_cmd = self.str_hex[rx_str_cmd]
            rx_param = hex_f.set_reg16(
                message_[self.P_H], message_[self.P_L])

            if rx_cmd == 0x41:  # ack
                self.ack_ev.set()
            elif rx_cmd == 0x3d:  # sd_finish
                self.prev_track = self.rx_param
                self.track_end_ev.set()
            elif rx_cmd == 0x3f:  # q_init
                if rx_param != 0x0002:
                    raise Exception('DFPlayer error: no SD card?')
            elif rx_cmd == 0x40:  # error
                self.error_ev.set()
            elif rx_cmd == 0x43:  # q_vol
                self.volume = self.rx_param
            elif rx_cmd == 0x48:  # q_sd_files
                self.track_count = self.rx_param
            elif rx_cmd == 0x4c:  # q_sd_trk
                self.current_track = self.rx_param
            elif rx_cmd == 0x3a:  # media_insert
                pass
            elif rx_cmd == 0x3b:  # media_remove
                raise Exception('DFPlayer error: SD card removed!')
            
            self.rx_cmd = rx_cmd
            self.rx_param = rx_param
            if rx_cmd != 0x41:  # skip ack
                print('Rx:', rx_str_cmd, hex_f.byte_str(rx_cmd),
                      hex_f.reg16_str(rx_param))

        while True:
            await self.stream.rx_queue.is_data.wait()  # wait for data input
            self.rx_word = self.stream.rx_queue.rmv_item()
            parse_rx_message(self.rx_word)


async def busy_pin_state(pin_):
    """ poll DFPlayer Pin 16
        - set Pico onboard LED to On if busy
        - included to show alternative control option
        - low when working, high when standby
        - 'working' means playing a track?
        - follows LED on DFPlayer?
    """
    pin_in = Pin(pin_, Pin.IN, Pin.PULL_UP)
    led = Pin('LED', Pin.OUT)
    while True:
        if pin_in.value():
            led.value(0)
        else:
            led.value(1)
        await asyncio.sleep_ms(20)


async def main():
    """ test CommandHandler and UartTxRx """
    
    async def reset():
        """ reset the DFPlayer
            - with SD card response should be:
                Rx word: q_init 0x3f 0x0002
                -- signifies online storage: SD card
                -- not currently checked by software
        """
        await c_h.send_command('reset', 0)
        await c_h.ack_ev.wait()
        await asyncio.sleep_ms(2000)
        if c_h.rx_cmd != 0x3f:
            raise Exception('DFPlayer could not be reset')
        else:
            print('DFPlayer reset')
            
    async def next_trk(n=1):
        """ play n next tracks """
        for _ in range(n):
            await c_h.send_command('next', 0)
            await c_h.ack_ev.wait()
            await c_h.track_end_ev.wait()

    async def prev_trk(n=1):
        """ play n previous tracks """
        for _ in range(n):
            await c_h.send_command('prev', 0)
            await c_h.ack_ev.wait()
            await c_h.track_end_ev.wait()

    async def track_index(index):
        """ play track 1 """
        await c_h.send_command('track', index)
        await c_h.ack_ev.wait()
        await c_h.track_end_ev.wait()

    async def play():
        """ play track 1 """
        await c_h.send_command('play', 0)
        await c_h.ack_ev.wait()
        await c_h.track_end_ev.wait()

    async def stop():
        """ stop playing """
        await c_h.send_command('stop', 0)
        await c_h.ack_ev.wait()
        c_h.track_end_ev.set()

    async def vol_set(level):
        """ set volume level 0-30 """
        level = min(30, level)
        await c_h.send_command('vol_set', level)
        await c_h.ack_ev.wait()

    async def q_vol():
        """ query volume level """
        await c_h.send_command('q_vol')
        await c_h.ack_ev.wait()

    async def q_sd_files():
        """ query number of SD files (in root?) """
        await c_h.send_command('q_sd_files')
        await c_h.ack_ev.wait()

    async def q_sd_trk():
        """ query current track number """
        await c_h.send_command('q_sd_trk')
        await c_h.ack_ev.wait()

    # streaming object
    uart = UART(0, 9600)
    uart.init(tx=Pin(0), rx=Pin(1))
    # stream transmit / receive object
    stream_tr = StreamTR(uart, 10, Queue(20))
    # command-handler object
    c_h = CommandHandler(stream_tr)
    # Rx tasks run as cooperative tasks
    task0 = asyncio.create_task(stream_tr.receiver())
    task1 = asyncio.create_task(c_h.consume_rx_data())
    # demonstrate busy-pin polling - not used for control
    task2 = asyncio.create_task(busy_pin_state(2))
    
    print('Send commands')
    await reset()
    await vol_set(15)
    await q_vol()  # confirm volume setting
    await q_sd_files()  # return number of files
    await play()  # cannot be stopped
    await stop()
    await next_trk(2)
    await track_index(23)
    await track_index(22)
    await track_index(21)
    await track_index(46)
    await track_index(13)
    await track_index(21)
    await asyncio.sleep_ms(5000)
    await stop()

    # demo complete
    print('cancel tasks')
    task2.cancel()  # DFP busy-pin polling
    task1.cancel()  # Rx stream
    task0.cancel()  # parse Rx data


if __name__ == '__main__':
    try:
        asyncio.run(main())
    finally:
        asyncio.new_event_loop()  # clear retained state
        print('test complete')
