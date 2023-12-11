if __name__ == '__main__':
    try:
        import json

        import sounddevice

        print(json.dumps(sounddevice.query_devices(), indent=4))
    except BaseException:
        print('[]')
