import logging
import os
import time
from tb_device_mqtt import TBDeviceMqttClient, TBPublishInfo
import grovepi
from statistics import mean
from datetime import date
import datetime
import csv
import random
from math import isnan

# Configuration of logger, in this case it will send messages to console
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(module)s - %(lineno)d - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')

#On ouvre le fichier CSV et on remplace les anciennes données si certaines ont déjà été prise dans la même journée
f=open('/home/pi/Desktop/DataTemperatures/'+datetime.datetime.now().strftime('%d:%m:%y')+'-dataTemp.csv','w+')
writer=csv.writer(f)
writer.writerow(('temps','Meteo1','Meteo2','Meteo3','Meteo4','MeteoMoy','Piece','Exte'))
f.close()

log = logging.getLogger(__name__)

thingsboard_server = 'localhost'
access_token = 'J0664MddfReUz9dcoe8u'

def main():

    #declaration des ports temperature
    temp_meteo_1=2
    temp_meteo_2=3
    temp_meteo_3=4
    temp_meteo_4=5
    temp_piece=6
    temp_exte=16
    #declaration des ports relais
    chauffe_meteo=8
    chauffe_piece=15
    ventilateur=14
    grovepi.pinMode(chauffe_meteo,"OUTPUT")
    grovepi.pinMode(chauffe_piece,"OUTPUT")
    grovepi.pinMode(ventilateur,"OUTPUT")

    #declaration led
    led=7
    count=4
    grovepi.pinMode(led,"OUTPUT")
    grovepi.analogWrite(led,255)

    #déclaration des différents états à gérer
    #état des chauffages
    ChauffePieceState=False
    ChauffeMeteoState=False
    #etat des ventilateurs
    VentilateurState=False
    #etat des modes de chauffages
    MeteoAutoState=False
    PieceAutoState=False

    # Définition de la fonction servant à gérer les RPC (remote prcedure calls) entre l'interface et le rapsberry
    def on_server_side_rpc_request(request_id, request_body):
        #on affiche en log le rpc reçu
        log.info('received rpc: {}, {}'.format(request_id, request_body))
        #get et set du chauffage de la piéce
        if request_body['method'] == 'getChauffePieceState':
            client.send_rpc_reply(request_id, ChauffePieceState)
        elif request_body['method'] == 'setChauffePieceState':
            ChauffePieceState = request_body['params']
            grovepi.digitalWrite(chauffe_piece,ChauffePieceState)
        #get et set du chauffage de la météo
        elif request_body['method'] == 'setChauffeMeteoState':
            ChauffeMeteoState = request_body['params']
            grovepi.digitalWrite(chauffe_meteo,ChauffeMeteoState)
        elif request_body['method'] == 'getChauffeMeteoState':
            client.send_rpc_reply(request_id, ChauffeMeteoState)
        #get et set de l'activation des ventilateurs
        elif request_body['method'] == 'setVentilateurState':
            VentilateurState = request_body['params']
            grovepi.digitalWrite(ventilateur,VentilateurState)
        elif request_body['method'] == 'getVentilateurState':
            client.send_rpc_reply(request_id, VentilateurState)
        #get et set des modes de chauffages piéce et météo
        elif request_body['method'] == 'getMeteoAutoState':
            client.send_rpc_reply(request_id, MeteoAutoState)
        elif request_body['method'] == 'setMeteoAutoState':
            MeteoAutoState = request_body['params']
        elif request_body['method'] == 'getPieceAutoState':
            client.send_rpc_reply(request_id, PieceAutoState)
        elif request_body['method'] == 'setPieceAutoState':
            PieceAutoState = request_body['params']

    # Connection à Thingsboard
    client = TBDeviceMqttClient(thingsboard_server, access_token)
    client.set_server_side_rpc_request_handler(on_server_side_rpc_request)
    client.connect()

    #fonction retournant un dictionnaire avec toutes les temperatures
    def getTemperatures():
        Temperatures={}
        Temperatures['TemperatureMeteo1'] = grovepi.dht(temp_meteo_1,1)[0]
        if isnan(Temperatures['TemperatureMeteo1']):
        	Temperatures['TemperatureMeteo1']=0
        Temperatures['TemperatureMeteo2'] = grovepi.dht(temp_meteo_2,1)[0]
        if isnan(Temperatures['TemperatureMeteo2']):
        	Temperatures['TemperatureMeteo2']=0
        Temperatures['TemperatureMeteo3'] = grovepi.dht(temp_meteo_3,1)[0]
        if isnan(Temperatures['TemperatureMeteo3']):
        	Temperatures['TemperatureMeteo3']=0
        Temperatures['TemperatureMeteo4'] = grovepi.dht(temp_meteo_4,1)[0]
        if isnan(Temperatures['TemperatureMeteo4']):
        	Temperatures['TemperatureMeteo4']=0
        #moyenne des Températures extérieures
        TemperatureMoyenneMeteo=mean([Temperatures.get('TemperatureMeteo1'),Temperatures.get('TemperatureMeteo2'),Temperatures.get('TemperatureMeteo3'),Temperatures.get('TemperatureMeteo4')])
        Temperatures['TemperatureMoyenneMeteo']=TemperatureMoyenneMeteo
        if isnan(Temperatures['TemperatureMoyenneMeteo']):
        	Temperatures['TemperatureMoyenneMeteo']=0
        Temperatures['TemperaturePiece'] = grovepi.dht(temp_piece,1)[0]
        if isnan(Temperatures['TemperaturePiece']):
        	Temperatures['TemperaturePiece']=0
        Temperatures['TemperatureExte'] = grovepi.dht(temp_exte,1)[0]
        if isnan(Temperatures['TemperatureExte']):
        	Temperatures['TemperatureExte']=0
        return Temperatures

    #fonbction qui permet de déterminer l'état de chauffage nécessaire dans la piéce
    def HotOrColdPiece(TemperaturePiece):
        etat=False
        #ouverture du CSV
        CsvPiece=open("/home/pi/GrovePi/YES/automatisation/piece.csv","r+")
        reader=csv.reader(CsvPiece)
        i=0
        for row in reader:
            #si On est à la premiére itération on regarde le mode de chauffage
            if i==1:
                mode=row[0]
                log.info(mode)
            if i>=1:
                #Si on est en monde conventionnel on récupére les créneux en les transformant
                #en format datetime.datetime.time(), on regarde si l'heure actuelle appartient à ce créneau
                #si c'est le cas on regarde la température nécessaire dans ce créneau et on en déduit l'état du
                #chauffage
                if mode =='conv':
                    debut=datetime.datetime.strptime(row[1],'%H:%M:%S').time()
                    fin=datetime.datetime.strptime(row[2],'%H:%M:%S').time()
                    if debut <= datetime.datetime.now().time() <= fin :
                        log.info('bon créneau')
                        if TemperaturePiece>int(row[3]):
                            etat=False
                        else:
                            etat=True
                        break
                #En mode smart on récupérer seulement l'état rentré du côté Matlab dans la derniére colonne du CSV
                if mode=="smart":
                    if int(row[4])==1:
                        etat=True
                    else:
                        etat=False
                    break
            i=i+1

        CsvPiece.close()
        return etat

    #fonction qui génére l'état de la météo de maniére aléatoire
    def HotOrColdMeteo(TemperatureMoyenneMeteo):
        etat=random.choice((True,False))
        return etat


    try :
        while True:
            #Obtention de toutes les données nécessaires
            Telemetry=getTemperatures()
            #si le chuffage de la piéce est en mode auto on génére l'état de la résistance grace à la fonction prédéfinie
            if PieceAutoState:
                print('mode auto')
                grovepi.digitalWrite(chauffe_piece,HotOrColdPiece(Telemetry['TemperaturePiece']))
            #Si le chauffage de la météo est en mode auto on génére l'état des résistances et des ventilateurs en fonction de lma fonction prédéfinie
            if MeteoAutoState:
                if HotOrColdMeteo(Telemetry['TemperatureMoyenneMeteo']):
                    grovepi.digitalWrite(chauffe_meteo,True)
                    grovepi.digitalWrite(ventilateur,False)
                else :
                    grovepi.digitalWrite(chauffe_meteo,False)
                    grovepi.digitalWrite(ventilateur,True)

            log.info(Telemetry)
            #On envoie les données de telpératures à Thingsboard
            client.send_telemetry(Telemetry).get()
            #On crée la nouvelle ligne qui sera insérée dans le CSV
            ligne=[0,0,0,0,0,0,0,0]
            ligne[0]=str(datetime.datetime.now())
            ligne[1]=str(Telemetry['TemperatureMeteo1'])
            ligne[2]=str(Telemetry['TemperatureMeteo2'])
            ligne[3]=str(Telemetry['TemperatureMeteo3'])
            ligne[4]=str(Telemetry['TemperatureMeteo4'])
            ligne[5]=str(Telemetry['TemperatureMoyenneMeteo'])
            ligne[6]=str(Telemetry['TemperaturePiece'])
            ligne[7]=str(Telemetry['TemperatureExte'])
            f=open('/home/pi/Desktop/DataTemperatures/'+datetime.datetime.now().strftime('%d:%m:%y')+'-dataTemp.csv','a')
            writer=csv.writer(f)
            writer.writerow(ligne)
            log.info('written in csv')
            f.close()

            #condition sécuritaire si la température dépasse les 60 on quitte la boucle et va directeent au finally ou les actionneurs sont arretes
            if Telemetry["TemperatureMoyenneMeteo"]>=60 or Telemetry["TemperaturePiece"]>=60:
            	break
            #Ici on décide tous les combien de temps la prise de température doit être faite ainsi que l'actvation ou non des chauffages
            time.sleep(2)

    except Exception as e:
        raise e
        log.warning(e)
    finally:
        log.info("client disconnect")
        client.disconnect()
        grovepi.digitalWrite(chauffe_piece,False)
        grovepi.digitalWrite(chauffe_meteo,False)
        grovepi.digitalWrite(ventilateur,True)

if __name__ == '__main__':
    main()