import socket
import sys
import json
from pylsl import StreamInfo, StreamOutlet, local_clock, vectord

DEFAULT_HOST = ""
DEFAULT_PORT = 5555

SAMPLING_RATE = 1000
STREAM_NAME = 'MindLogger'
CONTENT_TYPE = 'live_event'
DEVICE_ID =  'ml-' + socket.gethostname()
DEFAULT_LOG_FILE_NAME = 'x.txt'

class MLServer:
    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self.server_socket = None
        self.client_connection = None
        self.logfile = None
        self.stream_info = None
        self.outlet = None
        self.previous_channel_count = 0

    def setup_socket(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.server_socket.bind((self.host, self.port))
        except socket.error as msg:
            print('Bind failed. Error code: ' + str(msg[0]) + ' Message ' + msg[1])
            sys.exit()
        except OSError as msg:
            print('Bind failed. Error code: ' + str(msg[0]) + ' Message ' + msg[1])
            sys.exit()

        print('Socket bind complete')

    def listen(self):
        self.server_socket.listen(10)
        print('Listening for connections... On port: ' + str( DEFAULT_PORT ) )
        self.client_connection, addr = self.server_socket.accept()
        self.client_connection.settimeout(.01)
        print('Connected with ' + addr[0] + ':' + str(addr[1]))

    def open_log_file(self, filename=DEFAULT_LOG_FILE_NAME):
        self.logfile = open(filename, 'w')

    def log_event(self, values):
        self.logfile.write( str(values) + '\n' )

    def push_empty_event_to_outlet(self , event_time):
        if (self.previous_channel_count > 0):
            if self.outlet is not None:
                values = ["0"] * self.previous_channel_count
                self.outlet.push_sample(vectord(values), event_time, True)



    def create_stream(self,fields):
        channel_count = len( fields )

        stream_info = StreamInfo(STREAM_NAME , CONTENT_TYPE, channel_count , SAMPLING_RATE, 'string', DEVICE_ID)

        ml_channels = stream_info.desc().append_child('channels')

        for index in fields.keys():
            ch = ml_channels.append_child('channel')
            ch.append_child_value('label', index)
            ch.append_child_value('unit', 'string')
            ch.append_child_value('type', 'live_event')

        outlet = StreamOutlet(stream_info)

        self.destroy_previous_stream()

        self.stream_info = stream_info
        self.outlet = outlet
        self.previous_channel_count = channel_count

        print('LSL Stream setup complete channelCount: ' + str(channel_count))


    def handle_streams( self, data ):
        channel_count = len( data )

        if ( channel_count < 1 ):
            return

        self.create_stream( data )

    def destroy_previous_stream(self):
        try:
            if self.outlet is not None:
                del self.stream_info
                del self.outlet
            self.previous_channel_count = 0
        except Exception as e:
            print("An error occurred while destroying a stream:", str(e))

    def push_event(self,data,event_time):
        string_values = []

        for index in data.keys():
            value = data[index]
            if ( isinstance( value , str)):
                string_values.append( value )
            elif ( hasattr( value , "__len__" ) ):
                string_values.append( str( value[ 0 ] ) )
            else:
                string_values.append( str( value ) )

        print( string_values , self.previous_channel_count , 'pushing event' )
        if( len( string_values ) > 0 ):
            try:
                self.outlet.push_sample( vectord( string_values ), event_time, True)
            except Exception as e:
                print( str(e))

    def process_event(self, event,event_time):
        try:
            item = json.loads(event)
            data = item.get('data')

            if not data:
                return

            current_channel_count = len( data )
            if ( self.previous_channel_count != current_channel_count ):
                self.handle_streams( data )

            log_values = [data[k] for k in data.keys()]
            self.log_event(log_values)

            self.push_event( data , event_time )

        except json.decoder.JSONDecodeError:
            print('Decoding error')


    def receive_data(self):
        while True:
            event_time = local_clock()

            try:
                received_data = self.client_connection.recv(4096).decode('utf-8')


                if 'live_event' not in received_data or '$$$' not in received_data:
                    continue

                events = received_data.split('$$$')

                print(received_data)

                for event in events:
                    if not event.endswith('}'):
                        continue

                    self.process_event(event,event_time)
            except KeyboardInterrupt:
                self.close()
                break
            except socket.timeout:
                self.push_empty_event_to_outlet(event_time)

    def start(self):
        self.setup_socket()
        self.open_log_file()
        self.listen()
        self.receive_data()

    def close(self):
        if self.server_socket:
            self.server_socket.close()
        if self.client_connection:
            self.client_connection.close()
        if self.logfile:
            self.logfile.close()

if __name__ == "__main__":
    ml_server = MLServer()
    try:
        ml_server.start()
    except Exception as e:
        print("An error occurred:", str(e))
    finally:
        ml_server.close()
