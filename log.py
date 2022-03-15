#!/usr/bin/python3
# -*- coding: UTF-8 -*-# enable debugging

from csv import excel_tab
from ctypes import sizeof
import sys
if sys.version_info[0] < 3:
	raise ImportError('Python < 3 is unsupported.')

if sys.version_info[0] == 3 and sys.version_info[1] < 5:
	raise ImportError('Python < 3.5 is unsupported.')
import cgitb
import time
import datetime
import requests
import json
import os
import datetime
import pathlib
import mysql.connector
import mysql.connector.errorcode
import re
import traceback
import math
import tweepy
import time
from better_profanity import profanity

path = os.path.dirname(os.path.realpath(__file__))
logdir = path + "/dxrando_logs/"
location_split = re.compile('\s*,\s*')

def main():
	#cgitb.enable(display=1, logdir=logdir)
	print("Status: 200" )
	print("")
	ip = os.environ.get('REMOTE_ADDR')
	#info( ip )

	content, content_length = get_content()

	if ip is None:
		run_tests()
		return

	response = {}
	if len(content) != content_length:
		response['status'] = "ERROR: only received "+str(len(content))+"/"+str(content_length)+" bytes"
	else:
		response['status'] = "ok received "+str(len(content))+"/"+str(content_length)+" bytes"

	qps = query_params()
	version = qps.get('version', "v1.0.0")
	mod = qps.get('mod')

	response.update(update_notification(mod, version))
	
	config = get_config()

	#write_log(mod, version, ip, content, response)
	
	try:
		db_data = write_db(mod, version, ip, content,config)
		response.update(db_data)
	except Exception as e:
		print("failed to write to db")
		err("failed to write to db")
		logex(e)
	
	print_response(mod, version, response)

def load_profanity_filter():
	profanity.load_censor_words(whitelist_words=['thug'])

def prepare_tweet(config, playthrough_data, events, mod, version):
	if len(events) == 0:
		return
	if config["twit_bearer_token"]=="" or config["twit_consumer_key"]=="" or config["twit_consumer_secret"]=="" or config["twit_access_token"]=="" or config["twit_access_token_secret"]=="":
		return
	
	twitApi = tweepy.Client( bearer_token=config["twit_bearer_token"], 
								consumer_key=config["twit_consumer_key"], 
								consumer_secret=config["twit_consumer_secret"], 
								access_token=config["twit_access_token"], 
								access_token_secret=config["twit_access_token_secret"], 
								return_type = requests.Response,
								wait_on_rate_limit=True)
	load_profanity_filter()	
	for event in events:
		msg = gen_event_msg(event, playthrough_data, mod, version)
		if msg!=None:
			send_tweet(twitApi,msg)

def damage_string(dmgtype):
	if dmgtype=="shot":
		return "was murdered"
	elif dmgtype=="teargas":
		return "was tear gassed to death"
	elif dmgtype=="poisongas":
		return "was poison gassed to death"
	elif dmgtype=="radiation":
		return "was radiated to death"
	elif dmgtype=="halongas":
		return "was gassed to death"
	elif dmgtype=="poisoneffect" or dmgtype=="poison":
		return "was poisoned to death"
	elif dmgtype=="sabot" or dmgtype=="autoshot":
		return "was filled with holes"
	elif dmgtype=="burned" or dmgtype=="flamed":
		return "was burned to death"
	elif dmgtype=="drowned":
		return "drowned"
	elif dmgtype=="emp" or dmgtype=="shocked":
		return "was shocked to death"
	elif dmgtype=="exploded":
		return "was blown to bits"
	elif dmgtype=="fell":
		return "was splattered all over the floor"
	else:
		if dmgtype:
			err('unknown dmgtype: '+dmgtype)
		return 'was killed'


def location_to_string(location):
	location = location_split.split(location)
	x = round(float(location[0]), 3)
	y = round(float(location[1]), 3)
	z = round(float(location[2]), 3)
	return str(x)+', '+str(y)+', '+str(z)


def gen_death_msg(event, player,location, seed, flagshash):
	safePlayerName = profanity.censor(player)
	if safePlayerName.count('*') >= len(safePlayerName)*0.7:
		safePlayerName = 'Inappropriate Player'
	killer = event.get('killer')
	dmgtype = event.get('dmgtype')
	msg = safePlayerName+" "+damage_string(dmgtype.lower())
	
	if (killer==player):
		msg+=" by themselves"
	elif (killer==None):
		msg+=""
	else:
		msg+=' by '+killer
	
	if 'mapname' in event:
		msg += ' in '+event['mapname'] + ' (' + event['map'] + ')'
	else:
		msg+=" in "+event['map']

	if seed:
		msg += ' on seed '+str(seed)
	if flagshash:
		msg += ' (flagshash: '+str(flagshash)+')'
	
	msg+="\n\nPosition: " + location_to_string(location)
	return msg


def twitter_sanitize(val):
	if not val:
		return ''
	return str(val).replace('#', '').replace('@', '')


def gen_event_msg(event,d,mod,version):
	msg = None
	
	info("Generating message for event: "+str(event))
	
	if "type" not in event:
		err("Event has no type field")
		return None

	for k in event:
		event[k] = twitter_sanitize(event[k])
	seed = twitter_sanitize(d.get('seed'))
	flagshash = twitter_sanitize(d.get('flagshash'))
	mod = twitter_sanitize(mod)
	version = twitter_sanitize(version)
	
	if event['type']=='DEATH':
		msg = gen_death_msg(event, event['player'],event['location'], seed, flagshash)
	
	elif event["type"]=="BeatGame":
		if   event["ending"]==1:
			msg = event["PlayerName"]+" destroyed Area 51, beginning a new dark age\n"
		elif event["ending"]==2:
			msg = event["PlayerName"]+" merged with Helios to create a benevolent cybernetic dictatorship\n"
		elif event["ending"]==3:
			msg = event["PlayerName"]+" killed Bob Page and joined the Illuminati to rule the world unopposed\n"
		elif event["ending"]==4:
			msg = event["PlayerName"]+" decided this whole conspiracy thing was boring and decided to have a dance party instead\n"
		else:
			#unknown ending
			err("Unknown ending value "+str(event["ending"]))
			return None
		
		msg+= "\n"
		msg+= "Seed: "+seed+"\n"
		msg+= "Time: "+str(datetime.timedelta(seconds=event["time"]))+"\n"
		
	else:
		err("Unrecognized event type: "+str(event["type"]))
		return None
		
	msg+= "\n#DeusEx #Randomizer"
	if mod and mod != 'DeusEx':
		msg += ' #' + mod
	if version:
		msg += ' ' + version
	msg = profanity.censor(msg)
		
	return msg

def send_tweet(api,msg):
	info("Tweeting '"+msg+"'")
	tweet = msg

	if len(tweet)>280:
		diff = len(tweet)-280
		tweet = msg[:-diff-3]+"..."
	try:
		response = api.create_tweet(text=tweet) 
	except Exception as e:
		err("Encountered an issue when attempting to tweet: "+str(e)+" "+str(e.args))

def update_notification(mod, version):
	response = {}
	desc = "Death Markers and Enemy Shuffling!"
	detail = ""
	assert len(desc) < 35
	assert len(detail) < 35
	if VersionStringToInt(version) < VersionToInt(1, 7, 3, 11):
		response['notification'] = "New v1.7.3 available!"
		response['message'] = desc
		response['message'] += "|n" + detail
		response['message'] += "|nWould you like to visit https://github.com/Die4Ever/deus-ex-randomizer/releases now?"
	return response

def print_response(mod, version, response):
	if VersionStringToInt(version) >= VersionToInt(1, 7, 3, 3):
		print(json.dumps(response))
	else:
		print(response['status'])
		if 'notification' in response:
			print("notification: " + response['notification'])
			print(response['message'])


def get_config():
	with open(path+'/config.json', 'r') as f:
		return json.load(f)
	err("failed to load config")
	return {}


def db_connect(config):
	db = None
	
	dbconfig = {}
	dbconfig["user"]=config["user"]
	dbconfig["password"]=config["password"]
	dbconfig["host"]=config["host"]
	dbconfig["database"]=config["database"]
	dbconfig["raise_on_warnings"]=config["raise_on_warnings"]
	
	try:
		db = mysql.connector.connect(**dbconfig)
	except Exception as e:
		print("failed to connect to db")
		err("failed to connect to db")
		logex(e)
	return db


def write_db(mod, version, ip, content, config):
	ret = {}
	db = db_connect(config)
	cursor = None
	
	if db == None:
		return ret
	
	try:
		#create_tables(db)
		cursor = db.cursor(dictionary=True)
		d = parse_content(content)
		d = get_playthrough(cursor, mod, ip, d)
		cursor.execute(
			"INSERT INTO logs SET created=NOW(), "
			+ "firstword=%s, modname=%s, version=%s, ip=%s, message=%s, map=%s, seed=%s, flagshash=%s, playthrough_id=%s",
			(d.get('firstword'), mod, version, ip, content, d.get('map'), d.get('seed'), d.get('flagshash'), d.get('playthrough_id') ))
		log_id = cursor.lastrowid
		info("inserted logs id "+str(log_id))
		deaths = get_deaths(content)
		events = get_events(content)
		events.extend(deaths)
		info("got events: "+repr(events))
		for event in events:
			if event['type'] == 'DEATH':
				log_death(cursor, log_id, event)
		prepare_tweet(config, d, events, mod, version)
		db.commit()
		ret = {}
		if d.get('firstword'):
			ret = select_deaths(cursor, mod, d.get('map'))
	except Exception as e:
		print("failed to write to db")
		err("failed to write to db")
		logex(e)
	
	db.commit()
	cursor.close()
	db.close()
	return ret


def get_playthrough(cursor, mod, ip, d):
	if 'playthrough_id' in d and 'seed' in d and 'flagshash' in d:
		return d
	if 'playthrough_id' not in d:
		cursor.execute("SELECT playthrough_id, seed, flagshash FROM logs WHERE ip=%s ORDER BY id DESC LIMIT 1", (ip,))
	else:
		cursor.execute("SELECT playthrough_id, seed, flagshash FROM logs WHERE ip=%s AND playthrough_id=%s ORDER BY id DESC LIMIT 1", (ip,d['playthrough_id']))
	for (r) in cursor:
		if 'playthrough_id' in r:
			d['playthrough_id'] = r['playthrough_id']
		if 'seed' in r and 'seed' not in d:
			d['seed'] = r['seed']
		if 'flagshash' in r and 'flagshash' not in d:
			d['flagshash'] = r['flagshash']
	return d

def unrealscript_sanitize(s):
	allow = "-_[]\{\}()`~!@#$%^&*\+=|;:<>,."
	s = re.sub('[^\w\d %s]' % allow, '', str(s))
	s = re.sub('\s+', ' ', s)
	return s


# for k in ['num', 'name', 'killer', 'damagetype', 'age', 'x', 'y', 'z', 'killerclass']:
def compare_deaths(a, b):
	# name
	if a[1] != b[1]:
		return False

	# age, difference of 1 hour
	if abs(a[4] - b[4]) > 3600:
		return False
	
	# x, y, z, checking for > 100 feet
	dist = math.sqrt((a[5] - b[5]) ** 2 + (a[6] - b[6]) ** 2 + (a[7] - b[7]) ** 2)
	if dist > 16*100:
		return False
	
	return True

def filter_deaths(deaths):
	if not deaths:
		return deaths
	
	for d in deaths.values():
		d[0] = int(d[0])
		d[4] = int(d[4])
		d[5] = float(d[5])
		d[6] = float(d[6])
		d[7] = float(d[7])
	
	keys = sorted(deaths.keys(), key=lambda d: deaths[d][4])
	end = len(keys)
	
	i = 0
	while i < end:
		j = i + 1
		bads = 0
		while j < end:
			if compare_deaths(deaths[keys[i]], deaths[keys[j]]):
				bads += 1
				if bads > 3:
					deaths[keys[i]][0] += 1
					del keys[j]
					end -= 1
					j -= 1
			j += 1
		i += 1
	
	newdeaths = {}
	for k in keys[:50]:
		newdeaths[k] = deaths[k]
	return newdeaths


def select_deaths(cursor, mod, map):
	if not map:
		map = "01_nyc_unatcoisland"
	ret = {}
	# we select more than we return because we might combine some, or choose some more spread out ones instead of just going by age?
	modcondition = ""
	if mod == "RevRandomizer":
		modcondition = " AND modname == \"RevRandomizer\" "
	else:
		modcondition = " AND NOT modname <=> \"RevRandomizer\" "

	# select more than we want, because filter_deaths will remove the excess
	cursor.execute("SELECT "
		+ "deaths.id as deathid, modname, ip, name, killer, killerclass, damagetype, x, y, z, TIME_TO_SEC(TIMEDIFF(now(), created)) as age "
		+ "FROM deaths JOIN logs on(deaths.log_id=logs.id) "
		+ "WHERE map=%s "
		+ modcondition
		+ " ORDER BY created DESC LIMIT 100", (map,))
	
	for (d) in cursor:
		# need to sanitize these because unrealscript's json parsing isn't perfect
		key = 'deaths.' + str(d['deathid']) #d['x']+','+d['y']+','+d['z']
		d.pop('ip', None)
		d['num'] = 1
		ret[key] = []
		for k in ['num', 'name', 'killer', 'damagetype', 'age', 'x', 'y', 'z', 'killerclass']:
			s = unrealscript_sanitize(d[k])
			if not s:
				s = ''
			ret[key].append(s)
	
	return filter_deaths(ret)

def parse_content(content):
	d = {}
	r = re.compile(r'^(?P<level>\w+): (?P<map>[^\.]+)\.(?P<module>[^:]+)\d+: ((?P<firstword>\w+) )?(?P<remaining>.*)$', flags=re.MULTILINE)
	r2 = re.compile(r' (?P<key>\w+): (?P<value>[\w\d]+)')
	for i in r.finditer(content):
		try:
			t = i.groupdict()
			firstword = t.pop('firstword', None)
			if firstword and 'firstword' not in d and t.get('module')=='DXRFlags':
				d['firstword'] = firstword
			# order is semi-important because we want to keep the first value found for each key
			d = {**d, **t}
			if d.get('remaining') is not None:
				for j in r2.finditer(d['remaining']):
					d[j.group('key')] = j.group('value')
			d.pop('remaining', None)
		except Exception as e:
			logex(e)
	if 'map' not in d:
		warn("parse_content didn't find map in: "+content)
	return d

def get_deaths(content):
	# deprecated
	deaths = []
	r = re.compile(
		r'^DEATH: [^:]+: (?P<player>.*) was killed( by (?P<killerclass>.*?) (?P<killer>.*?))?( with (?P<dmgtype>.*?) damage)? in (?P<map>.*?) \((?P<x>.*?),(?P<y>.*?),(?P<z>.*?)\)'
		, flags=re.MULTILINE)
	for i in r.finditer(content):
		d = i.groupdict()
		d['type'] = 'DEATH'
		d['location'] = d['x'] + ', ' + d['y'] + ', ' + d['z']
		deaths.append(d)
	return deaths

def get_json_from_event_msg(eventmsg):
	jsonstr = ""
	
	jsonstart = eventmsg.find("{")
	
	if jsonstart != -1:
		jsonstr = eventmsg[jsonstart:]
		
	return jsonstr

def get_events(content):
	events = []
	for line in content.splitlines():
		try:
			if 'EVENT: ' not in line:
				continue
			eventjsonstr = get_json_from_event_msg(line)
			event = json.loads(eventjsonstr)
			events.append(event)
		except Exception as e:
			err('failed to get_events in line: ' + line)
			logex(e)
	return events
			
		
		
def log_death(cursor, log_id, death):
	info(repr(death))
	location = location_split.split(death['location'])
	cursor.execute("INSERT INTO deaths SET log_id=%s, name=%s, killer=%s, killerclass=%s, damagetype=%s, x=%s, y=%s, z=%s",
		(log_id, death['player'], death.get('killer'), death.get('killerclass'), death.get('dmgtype'), location[0], location[1], location[2]))

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
	create_table(db, "logs", "map varchar(255), created datetime, version varchar(255), ip varchar(100), message varchar(30000), seed int unsigned, flagshash int unsigned, modname varchar(255), firstword varchar(255), playthrough_id int unsigned, INDEX(modname, seed, playthrough_id, created), INDEX(modname, created), INDEX(firstword, created), INDEX(map, created), INDEX(playthrough_id,map,created)" + base)


# copied from DXRando
def VersionToInt(major, minor, patch, build):
	return int(major)*1000000+int(minor)*10000+int(patch)*100+int(build)

def VersionStringToInt(version):
	try:
		m = re.search(r'v(\d+)\.(\d+)\.(\d+)(\.(\d+))?', version)
		group5 = m.group(5)
		if group5 is None:
			group5 = "0"
		return VersionToInt(m.group(1), m.group(2), m.group(3), group5)
	except Exception as e:
		print("VersionStringToInt error parsing "+version)
		logex(e)
	return 0

def parse_query_string(q):
	d = {}
	for m in re.finditer(r'(([^=]+)=([^\&]+)&?)', q):
		d[m.group(2)] = m.group(3).replace("%20", " ")
	return d

def query_params():
	if os.environ.get('QUERY_STRING'):
		return parse_query_string(os.environ.get('QUERY_STRING'))
	return {}


def write_log(mod, version, ip, content, response):
	warn('obsolete write_log function')
	try:
		now = datetime.datetime.now()
		foldername = logdir + now.strftime("%Y-%m") +"/"
		filename = foldername + ip + "_" + version + ".txt"
		pathlib.Path(foldername).mkdir(parents=True, exist_ok=True)
		with open( filename, "a") as file:
			file.write( "\n" + now.strftime("%Y-%m-%d %H:%M:%S") + ": " + version + ": " + response['status'] +"\n" + content + "\n")
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

	info(repr(update_notification("vanilla", "v1.3.0")))

	# ensure proper error handling
	results = try_exec(MockFailCursor(), "expected failure")
	for t in (results):
		err("we shouldn't hit this")
	
	for d in get_deaths("\nDEATH: 01_NYC_UNATCOIsland.JCDentonMale2: JC Denton was killed by SecurityBot3 UJ-31 with shot damage in 01_NYC_UNATCOISLAND (-502.167694,40.753559,-119.199997)\nDEATH: 01_NYC_UNATCOIsland.JCDentonMale2: Die4Ever was killed in 01_NYC_UNATCOISLAND (-502.167694,40.753559,-119.199997)\nDEATH: 01_NYC_UNATCOIsland.JCDentonMale2: JC Denton was killed with shot damage in 01_NYC_UNATCOISLAND (-502.167694,40.753559,-119.199997)\nDEATH: 01_NYC_UNATCOIsland.JCDentonMale2: JC Denton was killed with  damage in 01_NYC_UNATCOISLAND (-502.167694,40.753559,-119.199997)"):
		info(repr(d))
	
	info("testing parse_content")
	d = parse_content("DX.DXRando0: RandoEnter() firstTime: True, IsTravel: False, seed: 601088 DX\nINFO: DX.DXRando0: randomizing DX using seed 601088\nINFO: DX.DXRFlags0: PreFirstEntry DX DeusEx.DXRFlags - v1.7.3.5 Beta, seed: 601088, flagshash: 90622488, playthrough_id: 1686707255, flagsversion: 1070305, gamemode: 0, difficulty: 1.000000, loadout: 0, brightness: 15, newgameplus_loops: 0, autosave: 2, crowdcontrol: 0, codes_mode: 2\nDEATH: 01_NYC_UNATCOIsland.JCDentonMale8: JC Denton was killed by JCDentonMale JC Denton with exploded damage in 01_NYC_UNATCOISLAND (748.419373,-433.573730,-123.300003)\nINFO: 01_NYC_UNATCOIsland.JCDentonMale8: Speed Enhancement deactivated")
	print(d['firstword'])
	assert d['firstword'] == "PreFirstEntry"

	d = parse_query_string("version=v1.2.3 Alpha&mod=DeusEx&another=param")
	assert d['version'] == "v1.2.3 Alpha"
	assert d['mod'] == "DeusEx"
	assert d['another'] == "param"

	assert VersionStringToInt(d['version']) == VersionToInt(1, 2, 3, 0)
	assert VersionStringToInt("v1.3.1") == VersionToInt(1, 3, 1, 0)
	assert VersionStringToInt("v1.7.2.5") == VersionToInt(1, 7, 2, 5)
	assert VersionStringToInt("v1.7.3.5 Alpha") == VersionToInt(1, 7, 3, 5)

	info(unrealscript_sanitize("this is a test, Die4Ever; ok: another test {      } \\  bye "))

	# for k in ['name', 'killer', 'damagetype', 'age', 'x', 'y', 'z', 'killerclass']:
	d = [1, 'Die4Ever', '', '', 3600, 0, 0, 0]
	d2 = d.copy()
	d2[1] = 'TheAstropath'
	d3 = d.copy()
	d3[4] = '3000'
	d3[5] = '10'
	d4 = d.copy()
	d4[5] = 16*150 # 150 feet
	deaths = filter_deaths({'a':d, 'b':d2, 'c':d3, 'd':d.copy(), 'e':d4, 'f':d.copy(), 'g':d3.copy(), 'h':d.copy()})
	info("filter_deaths down to "+repr(deaths))
	assert len(deaths) == 6

	load_profanity_filter()
	msg = gen_event_msg({'type': 'DEATH', 'player': 'fuck', 'killer': 'thug', 'killerclass': 'thug', 'dmgtype': 'shot', 'location': '1.7456324, 2, 3.0,', 'map': 'fuck'}, {}, 'DeusEx', 'v1.5.0')
	info(msg)
	assert 'fuck' not in msg
	assert 'thug' in msg
	msg = gen_event_msg({'type': 'DEATH', 'player': '# fuck @', 'killer': 'fucker', 'killerclass': 'fucker', 'dmgtype': 'fucked', 'location': '1.1, 2.34, 0.3,', 'map': 'fuck'}, {}, 'Fake#Mod@', 'v1.5.0')
	info(msg)
	assert 'fuck' not in msg
	assert '@' not in msg
	assert '# ****' not in msg
	assert 'Fake#Mod@' not in msg
	assert 'FakeMod' in msg

	info(repr(get_events('EVENT: {"location":"12.3, 4.56, 7.89"}')))
	
	info("path: "+os.path.dirname(os.path.realpath(__file__)))
	info("cwd: "+os.getcwd())
	info("logdir: "+logdir)
	info("db config: " + repr(get_config()))
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
