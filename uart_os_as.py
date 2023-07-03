# uart_os_as.py

# Test of uasyncio stream_tr I/O using UART
# Author: Peter Hinch
# Copyright Peter Hinch 2017-2022 Released under the MIT license
# Link X1 and X2 to test.

"""
    developed by David B Jones for Famous Trains model railway, Derby.
    - http://www.famoustrains.org.uk
    initial development of uasyncio.Stream UART connection:
    - uses Queue for receive stream_tr although not actually required at 9600 BAUD
    - ! deque is not implemented in MP so develop queue using a circular list !
    - uses 'one-shot' send for commands
    - coro is short for coroutine
"""

import uasyncio as asyncio
from machine import UART, Pin
from collections import deque
from machine import Pin


class Queue:
    """ simple FIFO queue
        - requires a re-write """

    def __init__(self, max_len=1):
        self.max_len = max_len
        # use deque for efficiency
        self._q = deque((), max_len)
        self._len = 0
        self.is_data = asyncio.Event()
        self.is_space = asyncio.Event()
        self.is_space.set()

    def add_item(self, item):
        """ add item to the queue """
        if self._len < self.max_len:
            self._q.append(item)
            self.is_data.set()
            self._len += 1
        if self._len == self.max_len:
            self.is_space.clear()

    def rmv_item(self):
        """ remove item from the queue if not empty """
        # assumes Event is_data prevents attempted removal from empty queue
        self._len -= 1
        item = self._q.popleft()
        self.is_space.set()
        if self._len == 0:
            self.is_data.clear()
        return item

    @property
    def q_len(self):
        """ number of items in the queue """
        return self._len


class StreamTR:
    """ implement UART Tx and Rx as stream_tr """

    def __init__(self, stream, buf_len, q_len=32):
        self.stream = stream
        self.buf_len = buf_len
        self.rx_queue = Queue(q_len)
        self.s_writer = asyncio.StreamWriter(self.stream, {})
        self.s_reader = asyncio.StreamReader(self.stream)
        self.in_buf = bytearray(buf_len)

    async def sender(self, data):
        """ coro: send out data item """
        self.s_writer.write(data)
        await self.s_writer.drain()

    async def receiver(self):
        """ coro: read data stream_tr into buffer """
        while True:
            res = await self.s_reader.readinto(self.in_buf)
            if res == self.buf_len:
                # add received bytearray when queue has space
                await self.rx_queue.is_space.wait()
                self.rx_queue.add_item(bytearray(self.in_buf))


async def main():
    """ coro: test module classes """
    
    async def data_send():
        """ send out bytearrays of data """
        data = bytearray(b'\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09')
        for i in range(10):
            data[0] = i
            print(f'Tx {data}')
            await stream_tr.sender(data)

    async def q_consume(q_):
        """ destructive! : print queue contents:  """
        while True:
            await q_.is_data.wait()
            item = q_.rmv_item()
            print(f'Rx {item} q-length: {q_.q_len}')

    print('Requires Pico loopback; connect Tx pin to Rx pin')
    print()

    uart = UART(0, 9600)
    uart.init(tx=Pin(0), rx=Pin(1))
    stream_tr = StreamTR(uart, buf_len=10)
    asyncio.create_task(stream_tr.receiver())
    asyncio.create_task(data_send())
    await asyncio.sleep_ms(200)
    asyncio.create_task(q_consume(stream_tr.rx_queue))

    await asyncio.sleep_ms(5_000)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Interrupted')
    finally:
        print('Close current event loop')
        asyncio.new_event_loop()
