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
import xml.sax.saxutils

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
    return epoch_medianoche + 18000 + 86399
def get_last_event(placa):
    event_url = 'http://monitoringinnovation.com/api/geopark/get_last_event/placa=' + placa
    res_event = requests.get(event_url)
    logins_event = res_event.json()
    last_event = logins_event["result"]
    return last_event

def get_event(payload):
    last_event = get_last_event(payload["modemIMEI"])
    print(last_event)
    if last_event:
        last_event["latitude"] = float(last_event["latitude"])
        last_event["longitude"] = float(last_event["longitude"])
        last_event["speed"] = int(last_event["speed"])
        last_event["altitude"] = int(last_event["altitude"])
        last_event["odometer"] = int(last_event["odometer"])
        last_event["heading"] = int(last_event["heading"])
        last_event["userToken"] = payload['userToken']
        last_event['modemIMEI'] = last_event.pop('placa')
        last_event['eventTypeCode'] = last_event.pop('eventType')
        last_event['dateTimeUTC'] = datetime.datetime.utcfromtimestamp(last_event.pop('date'))

        response = {}
        response["last_event"] = last_event

        if last_event['dateTimeUTC'] == payload["dateTimeUTC"]:
            response["eventCode"] = last_event["eventTypeCode"]
        delta_speed = (last_event["speed"] - payload["speed"]) * 0.277778
        delta_time = int(last_event["dateTimeUTC"].timestamp()) - int(payload["dateTimeUTC"].timestamp())
        speed_hard = 0
        if delta_time != 0:
            factor_event = delta_speed/delta_time
            speed_hard = factor_event/9.807
        print(last_event)

        if payload["engineStatus"] == 1 and last_event["eventTypeCode"] == "04":
            response["eventCode"] = "01"
        elif payload["engineStatus"] == 1 and payload["speed"] == 0 and payload["latitude"] == last_event["latitude"] and payload["longitude"] == last_event["longitude"]:
            response["eventCode"] = "03"
        elif payload["engineStatus"] == 0:
            response["eventCode"] = "04"
        elif payload["speed"] >= 80:
            response["eventCode"] = "05"
        elif last_event["speed"] > payload["speed"] and speed_hard > 0.35:
            response["eventCode"] = "06"
        elif last_event["speed"] < payload["speed"] and abs(speed_hard) > 0.35:
            response["eventCode"] = "07"
        else:
            response["eventCode"] = "02"
        return response
    else:
        response["eventCode"] = "02"
        return response

def get_coordinates(id_unit, sid):
    url_unload_msg = 'https://hst-api.wialon.com/wialon/ajax.html?svc=messages/unload&params={}&sid=' + sid
    res_unload_msg = requests.get(url_unload_msg)
    epoch_time_right = obtener_epoch_medianoche_actual()
    url_coordinates = 'https://hst-api.wialon.com/wialon/ajax.html?svc=messages/load_last&params={"itemId":'+ str(id_unit) +',"lastTime":' + str(epoch_time_right) + ',"lastCount":1,"flags":7,"flagsMask":0,"loadCount":1}&sid=' + sid
    print(url_coordinates)
    res_coordinates = requests.get(url_coordinates)
    logins_coordinates = res_coordinates.json()
    if logins_coordinates["messages"][0].get("pos") is None:
        latitud = False
        longitud = False
        altitud = False
        heading = False
        speed = False
    else:
        latitud = logins_coordinates["messages"][0]["pos"]["y"]
        longitud = logins_coordinates["messages"][0]["pos"]["x"]
        altitud = logins_coordinates["messages"][0]["pos"]["z"]
        heading = logins_coordinates["messages"][0]["pos"]["c"]    
        speed = logins_coordinates["messages"][0]["pos"]["s"]
    utc_datetime = datetime.datetime.utcfromtimestamp(logins_coordinates["messages"][0]["t"]-18000).strftime('%m/%d/%Y %H:%M:%S')
    time_utc = datetime.datetime.strptime(utc_datetime, '%m/%d/%Y %H:%M:%S')
    res = {
        "latitud": latitud,
        "longitud": longitud,
        "altitud": altitud,
        "heading": heading,
        "time_utc": time_utc,
        "speed": speed
    }
    return res

def create_event_motion(data_motion):
    data_motion["dateTimeUTC"] = data_motion["dateTimeUTC"].strftime('%Y-%m-%d %H:%M:%S')
    data_to_send = {"params": data_motion}
    event_url = 'https://monitoringinnovation.com/api/geopark/create_event'
    res_event = requests.post(event_url, json=data_to_send)
    logins_event = res_event
    return logins_event

def transform_wialon_to_soap(wialon_data):
    global global_token_geo
    controller_identifier = wialon_data[8:40]
    sid = getSid()
    imei_unit = re.findall(r'\b\d{8,}\b', str(codecs.decode(controller_identifier, 'hex')))[0]
    url_imei = 'https://hst-api.wialon.com/wialon/ajax.html?svc=core/search_items&params={"spec":{"itemsType":"avl_unit","propName":"sys_unique_id","propValueMask":"' + imei_unit + '","sortType":"sys_unique_id"},"force":1,"flags":1,"from":0,"to":0}&sid='+sid
    print("url_imei")
    print(url_imei)
    res_imei = requests.get(url_imei)
    logins_imei = res_imei.json()
    print("logins_imei")
    print(logins_imei)
    id_unit = str(logins_imei["items"][0]["id"])
    url_data = 'https://hst-api.wialon.com/wialon/ajax.html?svc=core/search_item&params={%22id%22:' + id_unit + ',%22flags%22:1060865}&sid=' + sid
    print("url_data")
    print(url_data)
    res_data = requests.get(url_data)
    logins = res_data.json()
    print("sensores data")
    print(logins)
    sens_keys = logins["item"]["sens"]
    for key in sens_keys.values():
        if key.get("t") == "engine operation":
            ignition_key = key.get("p")
        else:
            continue
    prms_vals = logins["item"]["prms"]
    ignition_value_obj = prms_vals.get(ignition_key)
    print("prms_vals")
    print(prms_vals)
    print(ignition_value_obj)
    print("ignition_value_obj")
    if ignition_value_obj is None:
        ignition_value = 1
    else:
        ignition_value = ignition_value_obj.get("v")
    odometer = logins["item"]["cnm"]
    placa = logins["item"]["nm"]
    data_coordinates = get_coordinates(id_unit, sid)
    time_utc = data_coordinates["time_utc"]
    latitude = data_coordinates["latitud"]
    longitude = data_coordinates["longitud"]
    altitude = data_coordinates["altitud"]
    course = data_coordinates["heading"]
    speed = data_coordinates["speed"]
    event_code = "02"
    payload = {
        'modemIMEI': placa,
        'eventTypeCode': event_code,
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
    last_event = get_event(payload)
    payload["eventTypeCode"] = last_event["eventCode"]
    if not payload["latitude"]:
        payload["latitude"] = float(last_event["last_event"]["latitude"])
        payload["longitude"] = float(last_event["last_event"]["longitude"])
        payload["altitude"] = int(last_event["last_event"]["altitude"])
        payload["speed"] = int(last_event["last_event"]["speed"])
        payload["odometer"] = int(last_event["last_event"]["odometer"])
        payload["heading"] = int(last_event["last_event"]["heading"])
    time.sleep(1)
    print("payload")
    print(payload)
    return payload

def send_soap_request(payload):
    global global_token_geo
    for key, value in payload.items():
        if isinstance(value, str):
            payload[key] = xml.sax.saxutils.escape(value)
    wsdl_url = 'http://naviwebsvc.azurewebsites.net/NaviMonitoringService.svc?wsdl'
    client = zeep.Client(wsdl=wsdl_url)
    try:
        try:
            wsdl_url = 'http://naviwebsvc.azurewebsites.net/NaviMonitoringService.svc?wsdl'
            client = zeep.Client(wsdl=wsdl_url)
            result = client.service.SaveTracking(**payload)
            print(result)
        except Exception as error:
            wsdl_url = 'http://naviwebsvc.azurewebsites.net/NaviMonitoringService.svc?wsdl'
            client = zeep.Client(wsdl=wsdl_url)
            global_token_geo = getTokenGeo()
            payload["userToken"] = global_token_geo
            result = client.service.SaveTracking(**payload)
            print(result)
    except Exception as error:
        print("ocurrio un error:", error)

def handle_client(client_socket):
    request_data = client_socket.recv(1024)
    wialon_data = request_data.hex()    
    soap_payload = transform_wialon_to_soap(wialon_data)
    create_event_motion(soap_payload)
    if soap_payload['eventTypeCode'] != "00":
        send_soap_request(soap_payload)
    else:
        print("eventTypeCode: 00")
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
    getTokenGeo()
    schedule.every(24).hours.do(getTokenGeo)
    server_thread = threading.Thread(target=start_server, args=(listen_port,))
    server_thread.start()
    while True:
        schedule.run_pending()
        time.sleep(1)
