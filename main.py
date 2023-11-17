import zeep
import socket
from datetime import datetime
import threading
import requests
import schedule
import time

global_token_geo = None

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

def getTokenGeo():
    global global_token_geo
    wsdl_url = 'http://naviwebsvc.azurewebsites.net/NaviMonitoringService.svc?wsdl'
    client = zeep.Client(wsdl_url)
    token_geo = client.service.Authenticate(userName='gp.gpscontrol', password='GsZsECVHZoJd@k9u')
    global_token_geo = token_geo
    return token_geo

def transform_wialon_to_soap(wialon_data):
    global global_token_geo
    # Extract relevant information from Wialon data
    packet_size = int(wialon_data[0:8], 16)
    controller_identifier = wialon_data[8:30]
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
    
    utc_datetime = datetime.utcfromtimestamp(utc_time).strftime('%m/%d/%Y %H:%M:%S')
    time_utc = datetime.strptime(utc_datetime, '%m/%d/%Y %H:%M:%S')


    #Get wialon data
    sid = getSid()
    url_data = 'https://hst-api.wialon.com/wialon/ajax.html?svc=core/search_item&params={%22id%22:26512780,%22flags%22:1060865}&sid=' + sid
    res_data = requests.get(url_data)
    logins = res_data.json()
    sens_keys = logins["item"]["sens"]
    for key in sens_keys.values():
        if key.get("t") == "engine operation":
            ignition_key = key.get("p")
    prms_vals = logins["item"]["prms"]
    ignition_value = prms_vals.get(ignition_key)
    odometer = logins["item"]["cnm"]

    # Create SOAP request payload
    payload = {
        'modemIMEI': controller_identifier,
        'eventTypeCode': bitmask,
        'dateTimeUTC': time_utc,
        'GPSStatus': True,
        'latitude': latitude,
        'longitude': longitude,
        'speed': speed,
        'odometer': odometer,
        'heading': course,
        'engineStatus': True if ignition_value == 1 else False,
        'userToken': global_token_geo,
    }

    print(payload)

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

    print("wiadata $$$$")
    print("wiadata $$$$")
    print(wialon_data)
    print("wiadata $$$$")
    print("wiadata $$$$")
    
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
        # Esperar un tiempo antes de volver a verificar las tareas programadas
        client, addr = server.accept()
        print(f"[*] Accepted connection from {addr[0]}:{addr[1]}")

        client_handler = threading.Thread(target=handle_client, args=(client,))
        client_handler.start()

if __name__ == "__main__":
    listen_port = 12395
    getTokenGeo()
    schedule.every(24).hours.do(getTokenGeo)

    # Iniciar el servidor en un hilo separado
    server_thread = threading.Thread(target=start_server, args=(listen_port,))
    server_thread.start()

    while True:
        # Ejecutar tareas programadas
        schedule.run_pending()

        # Esperar un tiempo antes de volver a verificar las tareas programadas
        time.sleep(1)
