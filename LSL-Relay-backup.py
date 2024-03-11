import socket
import sys
import json
from pylsl import StreamInfo, StreamOutlet, local_clock
import pylsl

HOST = ''
PORT = 5555

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

try:
    s.bind((HOST, PORT))

except socket.error as msg:
    print('Bind failed. Error code: ' + str(msg[0]) + ' Message ' + msg[1])
    sys.exit()

print('Socket bind complete')

s.listen(10)

conn, addr = s.accept()

out = open('x.txt', 'w')
l = []

print('Connected with ' + addr[0] + ':' + str(addr[1]))

srate = 1000
name = 'MindLogger'
type = 'live_event'
n_channels = 3

info = StreamInfo(name, type, n_channels, srate, 'float32', 'ml-' + socket.gethostname())
ml_channels = info.desc().append_child('channels')

for label in ['x', 'y', 'time']:
    ch = ml_channels.append_child('channel')
    ch.append_child_value('label', label)
    ch.append_child_value('unit', 'pixels')
    ch.append_child_value('type', 'live_event')

outlet = StreamOutlet(info)

print('Now sending ML data...')

cont = True
conn.settimeout(.01)

while cont:
    now = local_clock()
    try:
        r = conn.recv(4096).decode('utf-8')
        print(r)
        if 'live_event' in r:
            if '$$$' in r:
                r = r.split('$$$')
            else:
                r = [r]
            for x in r:
                if len(x) > 0 and x[-1] == '}':
                    item = json.loads(x)
                    values = [item['data']['x'], item['data']['y'], item['data']['time']]
                    # values = [item['data'][k] for k in item['data'].keys()]
                    out.write(str(values) + '\n')
                    outlet.push_sample(pylsl.vectord(values), now, True)
    except KeyboardInterrupt:
        cont = False
    except socket.timeout:
        values = [0, 0, 0]
        outlet.push_sample(pylsl.vectord(values), now, True)
    except json.decoder.JSONDecodeError:
        print('Decoding error')

out.close()








