#!/usr/bin/python
import argparse
import base64
import json
import os
import signal
import sys
import time
import zlib
import requests
import http.client
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

# The Soft-AP IP address
deviceIPAddr = "192.168.4.1"

userCancel   = False

def zSleep(zTime):
	global userCancel
	try:
		time.sleep(zTime)
	except IOError:
		userCancel = True
	return not userCancel

def provBuildRegJson(pubKey, ssid, passwd, conf):
	d = {
		"ssid"     : ssid,
		"password" : provEncode(passwd, pubKey),
		"iot_url"  : conf["iotURL"],
		"api_url"  : conf["apiURL"],
		"api_key"  : provEncode(conf["apiKey"], pubKey)
	}
	return json.dumps(d)

def provEncode(inData, pubKey):
	#Encrypt using public key
	rsaKey = RSA.importKey(pubKey)
	rsaKey = PKCS1_v1_5.new(rsaKey)
	eData  = rsaKey.encrypt(inData.encode('utf-8'))
	return base64.b64encode(eData).decode('utf-8')

def provGetNetworks(hconn):
	try:
		hconn.request("GET", "/v1/prov/networks")
		resp = hconn.getresponse()
	except:
		return None
	return resp.read()

def provGetStatus(hconn):
	try:
		hconn.request("GET", "/v1/prov/status")
		resp = hconn.getresponse()
	except:
		return None, None, 0

	respData = resp.read()
	x = json.loads(respData)
	if "status" in x and "progress" in x and "t_ms" in x:
		return x["status"], x["progress"], x["t_ms"]
	else:
		return None, None, 0

def provGetSession(hconn):
	hconn.request("GET", "/v1/prov/session")
	resp = hconn.getresponse()
	print(resp.status, resp.reason)
	respData = resp.read()

	# public-key is base64 encoded PEM
	return json.loads(respData)

def provPostRegistration(hconn, provData):
	hconn.request("POST", "/v2/prov/registration", provData)
	resp = hconn.getresponse()
	respData = resp.read()
	return True if (200 == resp.status) else False

def provPostAck(hconn):
	try:
		hconn.request("POST", "/v1/prov/acknowledge", "")
		resp = hconn.getresponse()
	except:
		return None

	# Read and discard any data
	respData = resp.read()

def getNetworks(hconn):
	print("Request networks")
	respJson = provGetNetworks(hconn)
	if None == respJson:
		print("  No response")
		return
	resp = json.loads(respJson)
	apList = resp["access_points"]
	print("")
	print(" #  SSID                              Chan  RSSI")
	print("--  --------------------------------  ----  ----")
	line = 1
	for ap in apList:
		print("{0:2d}  {1:32s}  {2:4d}  {3:4d}".format(line, ap["ssid"], ap["chan"], ap["rssi"]))
		line += 1
	print("")

def doProvision(hconn, ssid, passwd, conf):
	print("Get device information and encryption key")
	info = provGetSession(hconn)
	if not info:
		return -1

	print("")
	print("Device type         : {0}".format(info["device_type"]))
	print("Device serial number: {0}".format(info["serial_number"]))
	print("ATCA serial number  : {0}".format(info["atca_sn"]))
	print("certificate id      : {0}".format(info["cert_id"]))
	if "iot_sn" in info:
		print("IoT serial number   : {0}".format(info["iot_sn"]))
	if "thing" in info:
		print("Thing Name          : {0}".format(info["thing"]))

	print("")

	pubKey = base64.b64decode(info["session_key"])

	provData = provBuildRegJson(pubKey, ssid, passwd, conf)

	print("Send registration")
	if not provPostRegistration(hconn, provData):
		return -1

	print('Waiting for completion')
	preStat = ""
	preProg = ""

	# Set up 30-second time limit for completion
	tEnd = 30.0 + time.monotonic()

	while True:
		curStat, curProg, tMs = provGetStatus(hconn)

		if preStat == curStat and preProg == curProg:
			# Poll 2x per second for until change of status
			if not zSleep(0.5):
				# Canceled
				return -1
			if time.monotonic() >= tEnd:
				print("Timed out")
				return -1
			continue

		preStat = curStat
		preProg = curProg

		print("status: {0:>6.3f} {1}/{2}".format(tMs/1000.0, curStat, curProg))

		if None == curStat:
			print("Soft-AP disconnected")
			retCode = -1
			break
		elif "iot_connected" == curStat:
			print("Completed - send ACK")
			provPostAck(hconn)
			retCode = 0
			break
		elif "iot_register_failed" == curStat:
			print("Failed to register certificate")
			retCode = -1
			break
		elif "failed" == curStat:
			print("Wi-Fi connection failed - maybe wrong ssid or passwd")
			retCode = -1
			break
		elif "iot_failed" == curStat:
			print("IoT connection failed - maybe wrong iot_url")
			retCode = -1
			break

	return retCode

def loadConfig(cfgFile):
	if not os.path.exists(cfgFile):
		print("File {0} not found".format(cfgFile))
		return None

	# Read the file
	with open(cfgFile, "r") as fh:
		cfgJson = fh.read()

	# Expecting a JSON object
	try:
		cfgData = json.loads(cfgJson)
	except:
		print("File {0} does not contain valid JSON".format(cfgFile))
		return None

	# Check for expected contents and load them
	missing = []

	if "ssid" not in cfgData:
		missing.append("ssid")

	if "password" not in cfgData:
		missing.append("password")

	if "iotURL" not in cfgData:
		missing.append("iotURL")

	if "apiURL" not in cfgData:
		missing.append("apiURL")

	if "apiKey" not in cfgData:
		missing.append("apiKey")

	if len(missing) > 0:
		# List all missing elements
		print("Configuration is missing: {0}".format(", ".join(missing)))
		return None

	return cfgData

def sigint_handler(sigNum, frame):
	global userCancel
	userCancel = True
	print("User cancel")

signal.signal(signal.SIGINT, sigint_handler)

def listNets(args, hconn):
	getNetworks(hconn)

def listInfo(args, hconn):
	info = provGetSession(hconn)
	if info:
		print("")
		print("Device type         : {0}".format(info["device_type"]))
		print("Device serial number: {0}".format(info["serial_number"]))
		print("ATCA serial number  : {0}".format(info["atca_sn"]))
		print("certificate id      : {0}".format(info["cert_id"]))

def config(args, hconn):
	conf = loadConfig(args.cfgFile)
	if None == conf:
		return 1

	if args.ssid:
		wifiSSID = args.ssid
	else:
		wifiSSID = conf["ssid"]

	if args.passwd:
		wifiPass = args.passwd
	else:
		wifiPass = conf["password"]

	return doProvision(hconn, wifiSSID, wifiPass, conf)

def readManifest(args, hconn):
	try:
		hconn.request("GET", "/v1/prov/manifest")
		resp = hconn.getresponse()
	except:
		return None
	print(resp)
	data = resp.read()

	if 200 == resp.status:
		x = json.loads(data)

		mTxt = base64.b64decode(x["content"])
		mCrc = hex(zlib.crc32(mTxt))[2:]

		if mCrc == x["crc32"]:
			with open(args.outFile, "w") as fh:
				fh.write(mTxt.decode("utf-8"))
		else:
			print("CRC does not match")
			return -1
	else:
		print("Status {0} : {1}".format(resp.status, data.decode()))
		return -1

	return 0

def main(argc, argv):
	parser = argparse.ArgumentParser()

	subParse = parser.add_subparsers()

	parseNets = subParse.add_parser("nets", help="List Wi-Fi networks")
	parseNets.set_defaults(func=listNets)

	parseInfo = subParse.add_parser("info", help="List device information")
	parseInfo.set_defaults(func=listInfo)

	parseManifest = subParse.add_parser("manifest", help="Read the device security manifest")
	parseManifest.set_defaults(func=readManifest)
	parseManifest.add_argument(
		"outFile",
		metavar="output",
		help="Manifest file"
	)

	parseConf = subParse.add_parser("conf", help="Configure device")
	parseConf.set_defaults(func=config)

	parseConf.add_argument(
		"--ssid",
		nargs="?",
		default=None,
		help='Wi-Fi SSID'
	)
	parseConf.add_argument(
		"--passwd",
		nargs="?",
		default=None,
		help="Wi-Fi Password"
	)
	parseConf.add_argument(
		"cfgFile",
		metavar="config",
		help="Configuration file"
	)

	args = parser.parse_args()
	# Connect to the provisioning host
	try:
		hconn = http.client.HTTPConnection(deviceIPAddr, timeout=15)
		hconn.connect()
	except Exception as ex:
		print("Failed to connect to Soft-AP: {0}".format(ex))
		return -1

	ret = args.func(args, hconn)
	hconn.close()
	return ret

#Main entry point
if __name__ == "__main__":
	ret = main(len(sys.argv), sys.argv)
	sys.exit(0 if (ret == 0) else 1)
