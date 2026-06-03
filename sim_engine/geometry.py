import numpy as np       
import matplotlib.pyplot as plt               
import json              
import time

C = 299792458
FREQUENCY_HZ = 433e6       # Watson-Watt için
WAVELENGTH   = C / FREQUENCY_HZ  # λ hesabı için
ANTENNA_SPACING_M = 0.5    # d/λ oranı için /// change later, this is random
sigma2 = "????" #look into hackrf noise

def readJson(config):
    try:
        with open("config.json","r") as file:
            data = json.load(file)
        print("file data: ",data)
    except Exception as err:
        print("Error: ",err)
    return data

def fsplLineer(distanceA): #Free Space Path Loss
    FSPL = np.power((4*(np.pi)*(distanceA)*(433e6) / C),2)
    return FSPL

def receivedPower(FSPL,dbPower): #How much power is left for the antenna
    return dbPower / FSPL #linear, dont forget

def antennaLocation(systemPos, d): #d is antenna spacing
    cx, cy = systemPos
    pos = {
        "N":[cx,cy+d],
        "S":[cx,cy-d],
        "E":[cx-d,cy],
        "W":[cx+d,cy]
    }
    return pos

def simulatePower(targetPos, systemPos, d,originalPower ):

    antennas = antennaLocation(systemPos,d)
    originalPowerLin=10**(originalPower/10)

    powers={}
    for name, pos in antennas.items():

        distance=np.linalg.norm(np.array(targetPos)-np.array(pos))
        fspl=fsplLineer(distance)
        receivedPowerA=receivedPower(fspl,originalPowerLin)

        noise = np.sqrt(sigma2 / 2) * np.random.randn() #sigma2 hackrfone noise
        #write np.random.randn(IQvalues) if you can gain IQ values
        powers[name]=max(receivedPowerA+noise,1e-9)
    
    return powers

def calculateSNR(originalPower,targetPos,systemPos):
    originalPowerLin=10**(originalPower/10)

    cx,cy=systemPos
    distance=np.linalg.norm(np.array(targetPos)-np.array([cx,cy]))
    receivedPowerA=receivedPower(fsplLineer(distance),originalPowerLin)

    snrLin=receivedPowerA/sigma2 #dont forget about sigma2
    return snrLin

def watsonWatt(powers):

    y = (powers["N"]-powers["S"])#/powers["Omni"]+++need to add virtualOmni immediately
    x = (powers["W"]-powers["E"])

    bearing=np.degrees(np.arctan2(y,x)) %360 #not sure if its for every part of the y,x plane???
    return bearing


def crlb(SNR):
    #write the proper formula
    return


def weightedLob(crlb,bearing1,bearing2):

    return [x,y]


def virtualAntenna():
    #this is like the hardest part omg, gonna cry
    return

def monteCarlos(target,system1,system2, n): #DONT FORGET TO CHECK HERE
    rmseBearing=0
    rmseMeters=0
    count=0
    targetY=(target.y-system1.y)
    targetX=(target.x-system1.x)
    targetBearing=np.degrees(np.arctan2(targetY,targetX))%360

    while(count<n):
        intendedBearing=watsonWatt(powers)#add variables and connect everythin
        rmseBearing+=(intendedBearing-targetBearing)**2 #check if the formula is correct
        
        intendedMeters=weightedLob(...) #change later DONT FORGET
        rmseMeters+=(np.linalg.norm(np.array([target.x,target.y])-np.array(intendedMeters)))**2

    rmseBearing=(1/n)*(rmseBearing)
    rmseMeters=(1/n)*(rmseMeters)
    
    rmseBearing=np.sqrt(rmseBearing)
    rmseMeters=np.sqrt(rmseMeters)

    return rmseBearing, rmseMeters

#ALSO ADD DYANMIC TARGETS TOO