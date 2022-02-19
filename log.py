#!/usr/bin/python3
# -*- coding: UTF-8 -*-# enable debugging

from csv import excel_tab
import sys
if sys.version_info[0] < 3:
    raise ImportError('Python < 3 is unsupported.')

if sys.version_info[0] == 3 and sys.version_info[1] < 5:
    raise ImportError('Python < 3.5 is unsupported.')

import cgitb
import time
import requests
import json
import os
import datetime
import pathlib
import mysql.connector
import mysql.connector.errorcode
import re
import traceback

path = os.path.dirname(os.path.realpath(__file__))
logdir = path + "/dxrando_logs/"

def main():
	#cgitb.enable(display=1, logdir=logdir)

	print("Status: 200" )
	print("")
	print( os.environ.get('REMOTE_ADDR') )

	content, content_length = get_content()

	if content_length == 0:
		run_tests()
		return

	response = ""
	if len(content) != content_length:
		response = "ERROR: only received "+str(len(content))+"/"+str(content_length)+" bytes"
	else:
		response = "ok received "+str(len(content))+"/"+str(content_length)+" bytes"

	version = get_version()

	if version != 'v1.7.2.9' and 'v1.7.3' not in version:
		response += " notification: New v1.7.2 available!\nMany updates!|nWould you like to visit https://github.com/Die4Ever/deus-ex-randomizer/releases now?"

	write_log(version, os.environ.get('REMOTE_ADDR'), content, response)
	try:
		write_db(version, os.environ.get('REMOTE_ADDR'), content)
	except Exception as e:
		print("failed to write to db")
		err("failed to write to db")
		logex(e)

	print(response)


def get_db_config():
	with open(path+'/config.json', 'r') as f:
		return json.load(f)
	err("failed to load db config")
	return {}


def db_connect():
	config = get_db_config()
	db = None
	try:
		db = mysql.connector.connect(**config)
	except Exception as e:
		print("failed to connect to db")
		err("failed to connect to db")
		logex(e)
	return db


def write_db(version, ip, content):
	db = db_connect()
	cursor = None
	try:
		create_tables(db)
		cursor = db.cursor()
		d = parse_content(content)
		cursor.execute("INSERT INTO logs SET "
						+ "created=NOW(), version=%s, ip=%s, message=%s, map=%s, seed=%s, flagshash=%s",
												(version, ip, content, d.get('map'), d.get('seed'), d.get('flagshash')))
		log_id = cursor.lastrowid
		info("inserted logs id "+str(log_id))
		for d in get_deaths(content):
			log_death(cursor, log_id, d)
		db.commit()
	except Exception as e:
		print("failed to write to db")
		err("failed to write to db")
		logex(e)
	
	db.commit()
	cursor.close()
	db.close()


def parse_content(content):
	d = {}
	r = re.compile(r'^(?P<level>\w+): (?P<map>[^\.]*)\.(?P<module>[^:]+)\d+: ((?P<firstword>\w+) (?P<remaining>.*)$)?', flags=re.MULTILINE)
	r2 = re.compile(r' (?P<key>\w+): (?P<value>[\w\d]+)')
	for i in r.finditer(content):
		try:
			d.update(i.groupdict())
			if d.get('remaining') is not None:
				for j in r2.finditer(d['remaining']):
					d[j.group('key')] = j.group('value')
			d.pop('remaining', None)
		except Exception as e:
			logex(e)
	return d

def get_deaths(content):
	deaths = []
	r = re.compile(
		r'^DEATH: [^:]+: (?P<player>.*) was killed( by (?P<killerclass>.*?) (?P<killer>.*?) with (?P<dmgtype>.*?) damage)? in (?P<map>.*?) \((?P<x>.*?),(?P<y>.*?),(?P<z>.*?)\)'
		, flags=re.MULTILINE)
	for i in r.finditer(content):
		d = i.groupdict()
		deaths.append(d)
	return deaths

def log_death(cursor, log_id, death):
	info(repr(death))
	cursor.execute("INSERT INTO deaths SET log_id=%s, name=%s, killer=%s, killerclass=%s, damagetype=%s, x=%s, y=%s, z=%s",
		(log_id, death['player'], death['killer'], death['killerclass'], death['dmgtype'], death['x'], death['y'], death['z']))

def try_exec(cursor, query):
	try:
		cursor.execute(query)
	except mysql.connector.Error as e:
		if e.errno == mysql.connector.errorcode.ER_TABLE_EXISTS_ERROR:
			print("table already exists.")
		else:
			logex(e)
		return ()
	except Exception as e:
		logex(e)
		return ()
	return cursor


def create_table(db, name, desc):
	cursor = db.cursor()
	desc = "CREATE TABLE " + name + " (" + desc + ")"
	curr_desc = ""

	results = try_exec(cursor, "SHOW CREATE TABLE "+name)
	for (table, tdesc) in results:
		curr_desc = tdesc
	
	if curr_desc.count(',') != desc.count(','):
		info("old table: "+curr_desc)
		try_exec(cursor, "DROP TABLE old_"+name)
		try_exec(cursor, "RENAME TABLE "+name+" TO old_"+name)
		info("create_table: "+desc)
		try_exec(cursor, desc)
	cursor.close()


def create_tables(db):
	base = ", id int unsigned NOT NULL AUTO_INCREMENT, PRIMARY KEY(id)"
	create_table(db, "deaths", "log_id int unsigned, name varchar(255), killer varchar(255), killerclass varchar(255), damagetype varchar(255), x float, y float, z float" + base)
	create_table(db, "logs", "map varchar(255), created datetime, version varchar(255), ip varchar(100), message varchar(30000), seed int unsigned, flagshash int unsigned, INDEX(map, created)" + base)

def get_version():
	version = ""
	if os.environ.get('QUERY_STRING'):
		version = os.environ.get('QUERY_STRING')
		version = version.replace("version=", "").replace("%20", " ")
	return version


def write_log(version, ip, content, response):
	try:
		now = datetime.datetime.now()
		foldername = logdir + now.strftime("%Y-%m") +"/"
		filename = foldername + ip + "_" + version + ".txt"
		pathlib.Path(foldername).mkdir(parents=True, exist_ok=True)
		with open( filename, "a") as file:
			file.write( "\n" + now.strftime("%Y-%m-%d %H:%M:%S") + ": " + version + ": " + response +"\n" + content + "\n")
	except Exception as e:
		logex(e)


def get_content():
	s_content_length = os.environ.get('CONTENT_LENGTH')
	if s_content_length is None:
		s_content_length = "0"
	else:
		s_content_length = str(s_content_length)

	content_length = int(s_content_length)
	content = ""

	try:
		#while len(args) < content_length AND (datetime.datetime.now() - now).total_seconds() < 10:
		if content_length > 0:
			content = content + sys.stdin.read()
			content = content.replace('\x00','').replace('\r','')
	except Exception as e:
		logex(e)
	
	return content, content_length


class MockFailCursor:
	def execute(self, q):
		raise Exception("MockFailCursor: "+q)

def run_tests():
	info("running tests...")

	# ensure proper error handling
	results = try_exec(MockFailCursor(), "expected failure")
	for t in results:
		err("we shouldn't hit this")
	
	for d in get_deaths("\nDEATH: 01_NYC_UNATCOIsland.JCDentonMale2: JC Denton was killed by SecurityBot3 UJ-31 with shot damage in 01_NYC_UNATCOISLAND (-502.167694,40.753559,-119.199997)\nDEATH: 01_NYC_UNATCOIsland.JCDentonMale2: Die4Ever was killed in 01_NYC_UNATCOISLAND (-502.167694,40.753559,-119.199997)"):
		info(repr(d))
	
	info("testing parse_content")
	d = parse_content("INFO: 01_NYC_UNATCOIsland.DXRMachines0: _SpawnNewActor 01_NYC_UNATCOIsland.DataCube12 at (6404.268066,4184.700195,-123.422623)\nINFO: 01_NYC_UNATCOIsland.DXRando12: done randomizing 01_NYC_UNATCOISLAND using seed 191616\nINFO: 01_NYC_UNATCOIsland.DXRFlags12: AnyEntry 01_NYC_UNATCOISLAND DeusEx.DXRFlags - v1.7.3.2 Alpha, seed: 191616, flagshash: 1192551168, playthrough_id: 1686588103, flagsversion: 1070302, gamemode: 0, difficulty: 1.500000, loadout: 0, brightness: 15, newgameplus_loops: 0, autosave: 0, crowdcontrol: 0, codes_mode: 2\nINFO: 01_NYC_UNATCOIsland.DXRFlags12: AnyEntry 01_NYC_UNATCOISLAND - ammo: 70, merchants: 30, minskill: 50, maxskill: 300, skills_disable_downgrades: 0, skills_reroll_missions: 5, skills_independent_levels: 0, multitools: 70, lockpicks: 70, biocells: 70, medkits: 70, speedlevel: 1, keysrando: 4, doorsmode: 259, doorspickable: 50, doorsdestructible: 50, deviceshackable: 100, passwordsrandomized: 100, enemiesrandomized: 30, enemyrespawn: 0, infodevices: 100, startinglocations: 100, goals: 100, equipment: 2, dancingpercent: 25, medbots: 25, repairbots: 25, medbotuses: 0, repairbotuses: 0, medbotcooldowns: 1, repairbotcooldowns: 1, medbotamount: 1, repairbotamount: 1, turrets_move: 50, turrets_add: 70, banned_skills: 5, banned_skill_levels: 5, enemies_nonhumans: 60, swapitems: 100, swapcontainers: 100, augcans: 100, aug_value_rando: 100, skill_value_rando: 100, min_weapon_dmg: 50, max_weapon_dmg: 150, min_weapon_shottime: 50, max_weapon_shottime: 150\nINFO: 01_NYC_UNATCOIsland.DXRTelemetry8: health: 100, HealthLegLeft: 100, HealthLegRight: 100, HealthTorso: 100, HealthHead: 100, HealthArmLeft: 100, HealthArmRight: 100")
	info(repr(d))

	info("path: "+os.path.dirname(os.path.realpath(__file__)))
	info("cwd: "+os.getcwd())
	info("logdir: "+logdir)
	info("db config: " + repr(get_db_config()))
	#write_db("0", "test")
	info("test success")

error_log = logdir + "error_log"
def write_error_log(msg):
	print(msg, file=sys.stderr)
	with open(error_log, "a") as file:
			file.write(msg+"\n")


def info(msg):
	write_error_log("INFO: "+msg)

def warn(msg):
	write_error_log("WARNING: "+msg)

def err(msg):
	write_error_log("ERROR: "+msg)

def logex(e):
	write_error_log("ERROR: "+traceback.format_exc())

main()
