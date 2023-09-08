# dfp_player.py
""" Control DFPlayer Mini over UART """

import uasyncio as asyncio
from data_link import DataLink
from dfp_mini import CommandHandler
from extended_player import ExtPlayer
from queue import Buffer


async def main():
    """ test DFPlayer controller """

    def get_command_lines(filename):
        """ read in command-lines from a text file """
        with open(filename) as fp:
            commands_ = [line for line in fp]
        return commands_
    
    async def run_commands(commands_):
        """ control DFP from simple text commands
            - format is: "cmd parameter" or "cmd, parameter"
            - work-in-progress! """

        for line in commands_:
            line = line.strip()  # trim
            if line == '':  # skip empty line
                continue
            if line[0] == '#':  # print comment line then skip
                print(line)
                continue
            # remove commas; remove extra spaces
            line = line.replace(',', ' ')
            while '  ' in line:
                line = line.replace('  ', ' ')

            tokens = line.split(' ')
            cmd_ = tokens[0]
            params = [int(p) for p in tokens[1:]]
            print(f'{cmd_} {params}')
            if cmd_ == 'zzz':
                await player.track_end_ev.wait()
                await asyncio.sleep(params[0])
            elif cmd_ == 'trk':
                await player.play_track(params[0])
            elif cmd_ == 'trl':
                await player.play_trk_list(params)
            elif cmd_ == 'nxt':
                await player.next_track()
            elif cmd_ == 'prv':
                await player.prev_track()
            elif cmd_ == 'rst':
                await player.reset()
            elif cmd_ == 'vol':
                await player.set_vol(params[0])
            elif cmd_ == 'stp':
                await player.pause()

    # pin_tx, pin_rx, baud_rate, ba_size)
    uart_params = (0, 1, 9600, 10)
    rx_queue = Buffer()
    # instantiate rx queue and app layers
    data_link = DataLink(*uart_params, rx_queue)
    cmd_handler = CommandHandler(data_link)
    player = ExtPlayer(cmd_handler)
    await asyncio.sleep_ms(1000)  # allow power-up
    await player.startup()

    print(f"{player.config['name']}: configuration file loaded")
    print(f'Number of SD tracks: {player.track_count}')

    print('Run commands')
    commands = get_command_lines('test.txt')
    player.repeat_flag = True  # allow repeat 
    await run_commands(commands)
    await asyncio.sleep_ms(1000)
    player.print_player_settings()
    # additional commands can now be run
    await player.play_track(77)
    await player.track_end_ev.wait()
    await asyncio.sleep_ms(1000)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    finally:
        asyncio.new_event_loop()  # clear retained state
        print('execution complete')