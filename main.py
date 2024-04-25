import asyncio
import datetime
import socket
import requests
import xml.sax.saxutils
import re
import codecs
import zeep
import schedule
import time

global_token_geo = None
data_received_count = 0


async def getSid():
    url_token = "https://monitoringinnovation.com/api/enlistcontrolandroid/gettoken"
    resp = requests.get(url_token)
    resp_token = resp.json()
    token = resp_token["result"]
    url_sid = (
        'https://hst-api.wialon.com/wialon/ajax.html?svc=token/login&params={"token":"'
        + token
        + '"}'
    )
    res_sid = requests.get(url_sid)
    logins = res_sid.json()
    sid = logins.get("eid")
    return sid


async def getTokenGeo():
    # uses zeep to get a connection with the destination server
    # then uses the Authenticate service (receives userName, password) and 
    # get a token to save that on global_token_geo
    global global_token_geo
    wsdl_url = "http://naviwebsvc.azurewebsites.net/NaviMonitoringService.svc?wsdl"
    client = zeep.Client(wsdl_url)
    token_geo = client.service.Authenticate(
        userName="gp.gpscontrol", password="GsZsECVHZoJd@k9u"
    )
    global_token_geo = token_geo
    return token_geo


def obtener_epoch_medianoche_actual():
    fecha_actual = datetime.datetime.now().date()
    medianoche = datetime.datetime.combine(fecha_actual, datetime.time.min)
    epoch_medianoche = int(medianoche.timestamp())
    return epoch_medianoche + 18000 + 86399


async def get_last_event(placa):
    # uses the plate to get and return the last event registered on monitoring to
    # to make calcs with the new event to take place
    event_url = f"http://monitoringinnovation.com/api/geopark/get_last_event/placa={placa}"
    res_event = requests.get(event_url)
    logins_event = res_event.json()
    last_event = logins_event["result"]
    return last_event


async def get_event(payload):
    last_event = await get_last_event(payload["modemIMEI"])
    print(last_event)
    response = {}
    # verify if last event and re push the info transformed
    # if info is not in last event, push the info on the payload
    # then set the last event refactor info on the response 
    if last_event:
        last_event["latitude"] = float(last_event["latitude"])
        last_event["longitude"] = float(last_event["longitude"])
        last_event["speed"] = int(last_event["speed"])
        last_event["altitude"] = int(float(last_event["altitude"]))
        last_event["odometer"] = int(last_event["odometer"])
        last_event["heading"] = int(last_event["heading"])
        last_event["userToken"] = payload["userToken"]
        last_event["modemIMEI"] = last_event.pop("placa")
        last_event["eventTypeCode"] = last_event.pop("eventType")
        last_event["dateTimeUTC"] = datetime.datetime.utcfromtimestamp(
            last_event.pop("date")
        )

        response["last_event"] = last_event
        # 
        if last_event["dateTimeUTC"] == payload["dateTimeUTC"]:
            response["eventCode"] = last_event["eventTypeCode"]

        delta_speed = (last_event["speed"] - payload["speed"]) * 0.277778
        delta_time = int(last_event["dateTimeUTC"].timestamp()) - int(
            payload["dateTimeUTC"].timestamp()
        )
        speed_hard = 0
        if delta_time != 0:
            factor_event = delta_speed / delta_time
            speed_hard = factor_event / 9.807
        print(last_event)

        if (
            payload["engineStatus"] == 1
            and last_event["eventTypeCode"] == "04"
        ):
            response["eventCode"] = "01"
        elif (
            payload["engineStatus"] == 1
            and payload["speed"] == 0
            and payload["latitude"] == last_event["latitude"]
            and payload["longitude"] == last_event["longitude"]
        ):
            response["eventCode"] = "03"
        elif payload["engineStatus"] == 0:
            response["eventCode"] = "04"
        elif payload["speed"] >= 80:
            response["eventCode"] = "05"
        elif (
            last_event["speed"] > payload["speed"]
            and speed_hard > 0.35
        ):
            response["eventCode"] = "06"
        elif (
            last_event["speed"] < payload["speed"]
            and abs(speed_hard) > 0.35
        ):
            response["eventCode"] = "07"
        else:
            response["eventCode"] = "02"
        return response
    else:
        response["eventCode"] = "02"
        return response


async def get_coordinates(id_unit, sid):
    url_unload_msg = (
        "https://hst-api.wialon.com/wialon/ajax.html?svc=messages/unload&params={}&sid="
        + sid
    )
    res_unload_msg = requests.get(url_unload_msg)
    epoch_time_right = obtener_epoch_medianoche_actual()
    url_coordinates = (
        "https://hst-api.wialon.com/wialon/ajax.html?svc=messages/load_last&params={"
        + '"itemId":'
        + str(id_unit)
        + ',"lastTime":'
        + str(epoch_time_right)
        + ',"lastCount":1,"flags":7,"flagsMask":0,"loadCount":1}'
        + "&sid="
        + sid
    )
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
    utc_datetime = datetime.datetime.fromtimestamp(
        logins_coordinates["messages"][0]["t"] - 36000
    ).strftime("%m/%d/%Y %H:%M:%S")
    time_utc = datetime.datetime.strptime(utc_datetime, "%m/%d/%Y %H:%M:%S")
    res = {
        "latitud": latitud,
        "longitud": longitud,
        "altitud": altitud,
        "heading": heading,
        "time_utc": time_utc,
        "speed": speed,
    }
    return res


async def create_event_motion(data_motion):
    data_motion["dateTimeUTC"] = data_motion["dateTimeUTC"].strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    data_to_send = {"params": data_motion}
    event_url = (
        "https://monitoringinnovation.com/api/geopark/create_event"
    )
    res_event = requests.post(event_url, json=data_to_send)
    logins_event = res_event
    return logins_event


async def transform_wialon_to_soap(wialon_data):
    #Receives as input the data request on hex
    global global_token_geo
    # get the part of the data that contains the "imei"
    controller_identifier = wialon_data[8:40]
    sid = await getSid()
    # uses a regular expression to get the fst data that coincides with the imei info
    # and create a url with the imei and sid to auth 
    imei_unit = re.findall(r"\b\d{8,}\b", str(codecs.decode(controller_identifier, "hex")))[0]
    url_imei = (
        "https://hst-api.wialon.com/wialon/ajax.html?svc=core/search_items&params={%22spec%22:{%22itemsType%22:%22avl_unit%22,%22propName%22:%22sys_unique_id%22,%22propValueMask%22:%22"
        + imei_unit
        + '%22,%22sortType%22:%22sys_unique_id%22},%22force%22:1,%22flags%22:1060865,%22from%22:0,%22to%22:0}'
        + "&sid="
        + sid
    )
    print("url_imei")
    print(url_imei)
    # set a get request with the url and transform the response to a json
    res_imei = requests.get(url_imei)
    logins_imei = res_imei.json()
    print("logins_imei")
    print(logins_imei)
    
    if len(logins_imei["items"]) > 0:
        # since here just iterate to get the ignition value
        id_unit = str(logins_imei["items"][0]["id"])
        sens_keys = logins_imei["items"][0]["sens"]
        for key in sens_keys.values():
            if key.get("t") == "engine operation":
                ignition_key = key.get("p")
            else:
                continue
        prms_vals = logins_imei["items"][0]["prms"]
        ignition_value_obj = prms_vals.get(ignition_key)
        print("prms_vals")
        print(prms_vals)
        print(ignition_value_obj)
        print("ignition_value_obj")
        # if can not get ignition value, set as default 1
        if ignition_value_obj is None:
            ignition_value = 1
        # if get the value, set that on ignition value
        else:
            ignition_value = ignition_value_obj.get("v")
        # call the data from the response and save that on vars
        odometer = logins_imei["items"][0]["cnm"]
        placa = logins_imei["items"][0]["nm"]
        data_coordinates = await get_coordinates(id_unit, sid)
        time_utc = data_coordinates["time_utc"]
        latitude = data_coordinates["latitud"]
        longitude = data_coordinates["longitud"]
        altitude = data_coordinates["altitud"]
        course = data_coordinates["heading"]
        speed = data_coordinates["speed"]
        # initialize event code as "02" , "00" means error
        event_code = "02"
        # arm the payload in accordance with the api documentation
        payload = {
            "modemIMEI": placa,
            "eventTypeCode": event_code,
            "dateTimeUTC": time_utc,
            "GPSStatus": True,
            "latitude": latitude,
            "longitude": longitude,
            "altitude": altitude,
            "speed": speed,
            "odometer": int(odometer) * 1000,
            "heading": course,
            "engineStatus": True if ignition_value == 1 else False,
            "userToken": global_token_geo,
        }
        strat_time = time.time()
        last_event = await get_event(payload)
        edn_time = time.time()
        fin_time = strat_time - edn_time
        print(f"Tiempo de obtención del evento: {fin_time} segundos")
        payload["eventTypeCode"] = last_event["eventCode"]
        if not payload["latitude"]:
            payload["latitude"] = float(last_event["last_event"]["latitude"])
            payload["longitude"] = float(last_event["last_event"]["longitude"])
            payload["altitude"] = int(last_event["last_event"]["altitude"])
            payload["speed"] = int(last_event["last_event"]["speed"])
            payload["odometer"] = int(last_event["last_event"]["odometer"])
            payload["heading"] = int(last_event["last_event"]["heading"])
        print("payload")
        print(payload)
    else:
        print("error en imei")
        print(imei_unit)
        payload = {"eventTypeCode": "00"}
    return payload


async def send_soap_request(payload):
    global global_token_geo
    for key, value in payload.items():
        if isinstance(value, str):
            payload[key] = xml.sax.saxutils.escape(value)
    wsdl_url = "http://naviwebsvc.azurewebsites.net/NaviMonitoringService.svc?wsdl"
    client = zeep.Client(wsdl=wsdl_url)
    try:
        try:
            print("payload 2")
            print(payload)
            wsdl_url = (
                "http://naviwebsvc.azurewebsites.net/NaviMonitoringService.svc?wsdl"
            )
            client = zeep.Client(wsdl=wsdl_url)
            result = client.service.SaveTracking(**payload)
            print(result)
        except Exception as error:
            wsdl_url = (
                "http://naviwebsvc.azurewebsites.net/NaviMonitoringService.svc?wsdl"
            )
            client = zeep.Client(wsdl=wsdl_url)
            global_token_geo = await getTokenGeo()
            payload["userToken"] = global_token_geo
            result = client.service.SaveTracking(**payload)
            print(result)
    except Exception as error:
        print("ocurrio un error:", error)


async def handle_client(client_socket):
    # receives the client socket (connection) as args
    global data_received_count
    start_time = time.time()
    # assign to request data the info sended by the client with the buffer size as 1024 
    request_data = client_socket.recv(1024)
    if request_data:
        start_time = time.time()
        data_received_count += 1
    print("*"*10)
    print("request data on handle client")
    print(request_data)
    # saves the data in hex
    wialon_data = request_data.hex()
    print("*"*10)
    print("request data on handle client on hex")
    print(wialon_data)
    # uses transform_wialon_to_soap with the data as args 
    # 
    soap_payload = await transform_wialon_to_soap(wialon_data)
    # verify if the response contains eventType... != 00, due that 
    # significs error on imei 
    if soap_payload["eventTypeCode"] != "00":
        # if has not error on imei, continues with the info sending
        await send_soap_request(soap_payload)
        await create_event_motion(soap_payload)
        print(data_received_count)
    else:
        print("eventTypeCode: 00")
    # saves the exec time 
    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"Tiempo de procesamiento del mensaje: {elapsed_time} segundos")
    # and closes the connection
    client_socket.close()


async def start_server(port):
    # create a server based on IPV4 and socked used to TCP
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # listen all on the server and the specified port
    server.bind(("0.0.0.0", port))
    # set a max of 5 clients connections 
    server.listen(5)
    print(f"[*] Listening on 0.0.0.0:{port}")
    while True:
        # accept the requests and get the client object (the connection) and client ip and port in a tuple
        client, addr = server.accept()
        print(f"[*] Accepted connection from {addr[0]}:{addr[1]}")
        #defines client_handler as async task calling handle_client with the client as arg 
        client_handler = asyncio.create_task(handle_client(client))
        await client_handler


if __name__ == "__main__":
    # defines a port to listen
    listen_port = 12395 
    # uses asyncio to run getTokenGeo to save in global get_token_geo the token
    asyncio.run(getTokenGeo()) 
    # ensure to get a valid token on global get_token_geo, due that expires on 24 hrs
    schedule.every(24).hours.do(asyncio.run, getTokenGeo()) 
    # starts a server listening on a indicated port
    asyncio.run(start_server(listen_port))
    while True:
        schedule.run_pending()
        time.sleep(1)
