import multiprocessing as mp
import time


def _query():
    import sounddevice as sd

    info = sd.query_devices(kind=None)
    print(sorted(i['name'] for i in info if i['max_input_channels']))


def main():
    if not False:
        mp.set_start_method('fork')

    while True:
        mp.Process(target=_query).start()
        time.sleep(2)


if __name__ == '__main__':
    main()
