import zeep
import socket
import datetime
import threading
import requests
import schedule
import time
import codecs
import re
import struct

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

def obtener_epoch_medianoche_actual():
    fecha_actual = datetime.datetime.now().date()
    medianoche = datetime.datetime.combine(fecha_actual, datetime.time.min)
    epoch_medianoche = int(time.mktime(medianoche.timetuple()))
    return epoch_medianoche + 18000

def get_coordinates(id_unit, sid):
    url_unload_msg = 'https://hst-api.wialon.com/wialon/ajax.html?svc=messages/unload&params={}&sid=' + sid
    res_unload_msg = requests.get(url_unload_msg)
    epoch_time_left = obtener_epoch_medianoche_actual()
    epoch_time_right = epoch_time_left + 86399
    url_coordinates = 'https://hst-api.wialon.com/wialon/ajax.html?svc=messages/load_interval&params={"itemId":'+ str(id_unit) +',"timeFrom":' + str(epoch_time_left) + ',"timeTo":' + str(epoch_time_right) + ',"flags":1,"flagsMask":65281,"loadCount":1}&sid=' + sid
    res_coordinates = requests.get(url_coordinates)
    logins_coordinates = res_coordinates.json()
    latitud = logins_coordinates["messages"][0]["pos"]["y"]
    longitud = logins_coordinates["messages"][0]["pos"]["x"]
    altitud = logins_coordinates["messages"][0]["pos"]["z"]
    heading = logins_coordinates["messages"][0]["pos"]["c"]    
    speed = logins_coordinates["messages"][0]["pos"]["s"]
    utc_datetime = datetime.datetime.utcfromtimestamp(logins_coordinates["messages"][0]["t"]).strftime('%m/%d/%Y %H:%M:%S')
    time_utc = datetime.datetime.strptime(utc_datetime, '%m/%d/%Y %H:%M:%S')
    res = {
    "latitud": latitud,
    "longitud": longitud,
    "altitud": altitud,
    "heading": float(heading),
    "time_utc": time_utc,
    "speed": speed
    }
    return res

# def get_event(data_motion):
#     placa = data_motion["placa"]
#     event_url = 'http://monitoringinnovation.com/api/geopark/get_last_event/placa=' + placa
#     res_event = requests.get(event_url)
#     logins_event = res_event.json()
#     eventType = logins_event["result"]
#     return eventType

# def create_event_motion(data_motion):
    data_to_send = {"params": data_motion}
    event_url = 'http://monitoringinnovation.com/api/geopark/create_event'
    res_event = requests.post(event_url, data=data_to_send)
    logins_event = res_event.json()
    return logins_event

def transform_wialon_to_soap(wialon_data):
    global global_token_geo
    # Extract relevant information from Wialon data
    controller_identifier = wialon_data[8:40]

    #Get wialon data
    sid = getSid()
    imei_unit = re.findall(r'\b\d{8,}\b', str(codecs.decode(controller_identifier, 'hex')))[0]
    url_imei = 'https://hst-api.wialon.com/wialon/ajax.html?svc=core/search_items&params={"spec":{"itemsType":"avl_unit","propName":"sys_unique_id","propValueMask":"' + imei_unit + '","sortType":"sys_unique_id"},"force":1,"flags":1,"from":0,"to":0}&sid='+sid
    res_imei = requests.get(url_imei)
    logins_imei = res_imei.json()
    id_unit = str(logins_imei["items"][0]["id"])
    url_data = 'https://hst-api.wialon.com/wialon/ajax.html?svc=core/search_item&params={%22id%22:' + id_unit + ',%22flags%22:1060865}&sid=' + sid
    res_data = requests.get(url_data)
    logins = res_data.json()
    sens_keys = logins["item"]["sens"]
    for key in sens_keys.values():
        if key.get("t") == "engine operation":
            ignition_key = key.get("p")
    prms_vals = logins["item"]["prms"]
    ignition_value = prms_vals.get(ignition_key)
    odometer = logins["item"]["cnm"]
    placa = logins["item"]["nm"]
    data_coordinates = get_coordinates(id_unit, sid)
    time_utc = data_coordinates["time_utc"]
    latitude = data_coordinates["latitud"]
    longitude = data_coordinates["longitud"]
    altitude = data_coordinates["altitud"]
    course = data_coordinates["heading"]
    speed = data_coordinates["speed"]

    # eventCode = get_event(placa)
    # event_type_f = eventCode if eventCode != "00" else "01"
    event_type_f = "01"

    # Create SOAP request payload
    payload = {
        'modemIMEI': placa,
        'eventTypeCode': event_type_f,
        'dateTimeUTC': time_utc,
        'GPSStatus': True,
        'latitude': latitude,
        'longitude': longitude,
        'altitude': altitude,
        'speed': speed,
        'odometer': int(odometer) * 1000,
        'heading': course,
        'engineStatus': True if ignition_value == 1 else False,
        'userToken': global_token_geo,
    }
    print("payload")
    print("payload")
    print(payload)
    print("payload")
    print("payload")
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
