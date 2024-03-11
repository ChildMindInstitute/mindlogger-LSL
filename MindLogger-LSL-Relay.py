import socket
import sys
import json
from pylsl import StreamInfo, StreamOutlet, local_clock, vectord
import numbers

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
        self.string_stream_info = None
        self.string_outlet = None
        self.previous_string_channel_count = 0

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
                values = [0] * self.previous_channel_count
                self.outlet.push_sample(vectord(values), event_time, True)



    def create_stream(self,fields,type):
        channel_count = len( fields )

        if( type == 'numeric' ):
            stream_info = StreamInfo(STREAM_NAME, CONTENT_TYPE, channel_count , SAMPLING_RATE, 'float32', DEVICE_ID)
        else:
            stream_info = StreamInfo("String stream: "+STREAM_NAME , CONTENT_TYPE, channel_count , SAMPLING_RATE, 'string', DEVICE_ID + "string")

        ml_channels = stream_info.desc().append_child('channels')

        for index in fields.keys():
            ch = ml_channels.append_child('channel')
            ch.append_child_value('label', index)
            if( type == 'numeric' ):
                ch.append_child_value('unit', 'pixels')
            else:
                ch.append_child_value('unit', 'string')
            ch.append_child_value('type', 'live_event')

        outlet = StreamOutlet(stream_info)

        if(type == 'numeric'):
            self.destroy_numeric_stream()

            self.stream_info = stream_info
            self.outlet = outlet
            self.previous_channel_count = channel_count
        else:
            self.destroy_string_stream()

            self.string_stream_info = stream_info
            self.string_outlet = outlet
            self.previous_string_channel_count = channel_count

        print('LSL Stream setup complete channelCount: ' + str(channel_count) + ", type: " + type )


    def handle_streams( self, data ):
        numeric_fields = {key: value for key, value in data.items() if isinstance(data[key] , numbers.Number ) or isinstance(data[key][0] , numbers.Number )}
        channel_count = len( data )

        if ( channel_count < 1 ):
            return

        self.create_stream(numeric_fields,'numeric')

        string_fields = None
        if ( len( numeric_fields ) != channel_count ):
            string_fields = {key: value for key, value in data.items() if not isinstance(data[key] , numbers.Number )}

        if string_fields is not None:
            self.create_stream(string_fields,'string')
        else:
            self.destroy_string_stream()

    def destroy_string_stream(self):
        try:
            if self.string_outlet is not None:
                del self.string_stream_info
                del self.string_outlet
            self.previous_string_channel_count = 0
        except Exception as e:
            print("An error occurred while destroying string_stream:", str(e))

    def destroy_numeric_stream(self):
        try:
            if self.outlet is not None:
                del self.stream_info
                del self.outlet
            self.previous_channel_count = 0
        except Exception as e:
            print("An error occurred while destroying numeric_stream:", str(e))

    def push_event_to_numeric_outlet(self,data , event_time):
        numeric_fields = {key: value for key, value in data.items() if isinstance(data[key] , numbers.Number ) or isinstance(data[key][0] , numbers.Number )}
        numeric_values = []

        for index in numeric_fields.keys():
            if ( isinstance(numeric_fields[index], numbers.Number)):
                numeric_values.append(numeric_fields[index])
            else:
                numeric_values.append(numeric_fields[index][0])

        print(numeric_values,self.previous_channel_count,'pushing number event')
        try:
            if ( len(numeric_fields) > 0 and len(numeric_values) == self.previous_channel_count):
                self.outlet.push_sample(vectord(numeric_values), event_time, True)
            else:
                self.handle_streams( data )
                self.push_event_to_numeric_outlet( data , event_time )
        except Exception as e:
            print(str(e))

    def push_event_to_string_outlet(self,data , event_time):
        string_fields = {key: value for key, value in data.items() if not isinstance(data[key] , numbers.Number )}
        string_values = []

        for index in string_fields.keys():
            if ( isinstance(string_fields[index], str)):
                string_values.append(string_fields[index])
            else:
                string_values.append(str(string_fields[index]))

        print(string_values,self.previous_string_channel_count,'pushing string event')
        if( len(string_fields) > 0 ):
            try:
                self.string_outlet.push_sample(vectord(string_values), event_time, True)
            except Exception as e:
                print(str(e))

    def process_event(self, event,event_time):
        try:
            item = json.loads(event)
            data = item.get('data')

            if not data:
                return

            current_channel_count = len( data )
            if ( self.previous_channel_count + self.previous_string_channel_count != current_channel_count ):
                self.handle_streams( data )

            log_values = [data[k] for k in data.keys()]
            self.log_event(log_values)

            self.push_event_to_numeric_outlet( data , event_time )
            self.push_event_to_string_outlet( data , event_time )

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
