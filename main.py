import zeep
import socket
from datetime import datetime
import threading
import requests

def getSid():
    url_token = "https://monitoringinnovation.com/api/enlistcontrolandroid/gettoken"
    resp = requests.get(url_token)
    resp_token = resp.json()
    token = resp_token["result"]
    url_sid = 'https://hst-api.wialon.com/wialon/ajax.html?svc=token/login&params={%22token%22:%22' + token + '%22}'
    res_sid = requests.get(url_sid)
    logins = res_sid.json()
    sid = logins.get('eid')
    return sid

def transform_wialon_to_soap(wialon_data):
    # Extract relevant information from Wialon data
    packet_size = int(wialon_data[0:8], 16)
    controller_identifier = wialon_data[8:24]
    utc_time = int(wialon_data[24:32], 16)
    bitmask = int(wialon_data[32:40], 16)
    longitude = float.fromhex(wialon_data[80:96])
    latitude = float.fromhex(wialon_data[96:112])
    altitude = float.fromhex(wialon_data[112:128])
    speed = int(wialon_data[128:132], 16)
    course = int(wialon_data[132:136], 16)
    satellites = int(wialon_data[136:138], 16)
    power_ext_value = float.fromhex(wialon_data[142:158])
    avl_inputs_value = int(wialon_data[160:162], 16)

    # Convert UTC time to a readable format
    utc_datetime = datetime.utcfromtimestamp(utc_time).strftime('%Y-%m-%d %H:%M:%S')

    #Get wialon data
    sid = getSid()
    url_data = 'https://hst-api.wialon.com/wialon/ajax.html?svc=core/search_item&params={%22id%22:26512780,%22flags%22:1060865}&sid=' + sid
    res_data = requests.get(url_data)
    logins = res_data.json()
    sens_keys = logins["sens"]["item"]["sens"]
    for key in range(sens_keys.values()):
        if key.get("t") == "engine operation":
            ignition_key = key.get("p")
    prms_vals = logins["sens"]["item"]["prms"]
    ignition_value = prms_vals.get(ignition_key)
    odometer = logins["sens"]["item"]["cnm"]

    wsdl_url = 'http://naviwebsvc.azurewebsites.net/NaviMonitoringService.svc?wsdl'
    client = zeep.Client(wsdl_url)
    token_geo = client.service.Authenticate(userName='gp.gpscontrol', password='GsZsECVHZoJd@k9u')

    # Create SOAP request payload
    payload = {
        'modemIMEI': controller_identifier,
        'eventTypeCode': bitmask,
        'dateTimeUTC': utc_datetime,
        'GPSStatus': True,
        'latitude': latitude,
        'longitude': longitude,
        'altitude': altitude,
        'speed': speed,
        'odometer': odometer,
        'heading': course,
        'engineStatus': True if ignition_value == 1 else False,
        'userToken': token_geo,
    }

    return payload

def send_soap_request(payload):
    # Define the WSDL URL
    wsdl_url = 'http://naviwebsvc.azurewebsites.net/NaviMonitoringService.svc?wsdl'
    # Create a Zeep client
    client = zeep.Client(wsdl=wsdl_url)
    # Call the SaveTracking operation
    result = client.service.SaveTracking(**payload)
    # Print the result (optional)
    print(result)

def handle_client(client_socket):
    request_data = client_socket.recv(1024)  # Adjust buffer size as needed
    wialon_data = request_data.hex()
    
    # Transform Wialon data to SOAP request format
    soap_payload = transform_wialon_to_soap(wialon_data)

    # Send SOAP request
    send_soap_request(soap_payload)

    client_socket.close()

def start_server(port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('0.0.0.0', port))
    server.listen(5)

    print(f"[*] Listening on 0.0.0.0:{port}")

    while True:
        client, addr = server.accept()
        print(f"[*] Accepted connection from {addr[0]}:{addr[1]}")

        client_handler = threading.Thread(target=handle_client, args=(client,))
        client_handler.start()

if __name__ == "__main__":
    listen_port = 12395

    # Start the server
    start_server(listen_port)
