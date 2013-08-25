#!/usr/bin/env python3

import sys, os, re
import http.server, socketserver, urllib.parse, json
from subprocess import Popen, PIPE #call

pairsPath = "/home/jonathan/quick/apertium/svn/trunk/"
PORT = 2737

Handler = None
httpd = None


def getPairsInPath(pairsPath):
	REmodeFile = re.compile("([a-z]{2,3})-([a-z]{2,3})\.mode")

	pairs = []
	contents = os.listdir(pairsPath)
	for content in contents:
		curContent = os.path.join(pairsPath, content)
		if os.path.isdir(curContent):
			curMode = os.path.join(curContent, "modes")
			if os.path.isdir(curMode):
				modeFiles = os.listdir(curMode)
				for modeFile in modeFiles:
					if REmodeFile.match(modeFile):
						l1 = REmodeFile.sub("\g<1>", modeFile)
						l2 = REmodeFile.sub("\g<2>", modeFile)
						#pairTuple = (os.path.join(curMode, modeFile), l1, l2)
						pairTuple = (curContent, l1, l2)
						pairs.append(pairTuple)
	return pairs


class MyHandler(http.server.SimpleHTTPRequestHandler):

	pairs = {}
	pipelines = {}

	def translateApertium(self, toTranslate, pair):
		strPair = '%s-%s' % pair
		if strPair in self.pairs:
			p1 = Popen(["echo", toTranslate], stdout=PIPE)
			p2 = Popen(["apertium", "-d %s" % self.pairs[strPair], strPair], stdin=p1.stdout, stdout=PIPE)
			p1.stdout.close()  # Allow p1 to receive a SIGPIPE if p2 exits.
			output = p2.communicate()[0].decode('utf-8')
			print(output)
			return output
		else:
			return False

	def getModeFileLine(self, modeFile):
		modeFileContents = open(modeFile, 'r').readlines()
		modeFileLine = None
		for line in modeFileContents:
			if '|' in line:
				modeFileLine = line
		if modeFileLine != None:
			commands = modeFileLine.split('|')
			outCommands = []
			for command in commands:
				command = command.strip()
				#if re.search('lrx-proc', command):
				#	outCommand = command
				#else:
				#	outCommand = re.sub('^(.*?)\s(.*)$', '\g<1> -z \g<2>', command)
				outCommand = re.sub('^(.*?)\s(.*)$', '\g<1> -z \g<2>', command)
				outCommand = re.sub('\s{2,}', ' ', outCommand)
				outCommands.append(outCommand)
			toReturn = ' | '.join(outCommands)
			toReturn = re.sub('\$1', '-g', toReturn)
			#print(toReturn)
			return toReturn
		else:
			return False

	def translateMode(self, toTranslate, pair):
		strPair = '%s-%s' % pair
		if strPair in self.pairs:
			if strPair not in self.pipelines:
				modeFile = "%s/modes/%s.mode" % (self.pairs[strPair], strPair)
				modeFileLine = self.getModeFileLine(modeFile)
				commandList = []
				if modeFileLine:
					for command in modeFileLine.split('|'):
						thisCommand = command.strip().split(' ')
						commandList.append(thisCommand)
					commandsDone = []
					for command in commandList:
						if len(commandsDone)>0:
							newP = Popen(command, stdin=commandsDone[-1].stdout, stdout=PIPE)
						else:
							newP = Popen(command, stdin=PIPE, stdout=PIPE)
						commandsDone.append(newP)

					self.pipelines[strPair] = (commandsDone[0], commandsDone[-1])

				if strPair in self.pipelines:
					(procIn, procOut) = self.pipelines[strPair]
					procIn.stdin.write(bytes(toTranslate, 'utf-8'))
					procIn.stdin.write(bytes('\0', "utf-8"))
					print("DEBUG 1")
					procIn.stdin.write(bytes('\0', "utf-8"))
					print("DEBUG 1.1")
					d = procOut.stdout.read(1)
					print("DEBUG 2 %s" % d)
					subbuf = b''
					while d != '\0':
						subbuf = subbuf + d
						if d == b'\0':
							break
						d = procOut.stdout.read(1)
					return subbuf.decode('utf-8')
			else:
				return False
		else:
			return False


	def translateModeDirect(self, toTranslate, pair):
		strPair = '%s-%s' % pair
		if strPair in self.pairs:
			modeFile = "%s/modes/%s.mode" % (self.pairs[strPair], strPair)
			modeFileLine = self.getModeFileLine(modeFile)
			commandList = []
			if modeFileLine:
				for command in modeFileLine.split('|'):
					thisCommand = command.strip().split(' ')
					commandList.append(thisCommand)
				p1 = Popen(["echo", toTranslate], stdout=PIPE)
				commandsDone = [p1]
				for command in commandList:
					#print(command, commandsDone, commandsDone[-1])
					#print(command)
					newP = Popen(command, stdin=commandsDone[-1].stdout, stdout=PIPE)
					commandsDone.append(newP)

				p1.stdout.close()  # Allow p1 to receive a SIGPIPE if p2 exits.
				output = commandsDone[-1].communicate()[0].decode('utf-8')
				print(output)
				return output
			else:
				return False
		else:
			return False

	def translateModeSimple(self, toTranslate, pair):
		strPair = '%s-%s' % pair
		if strPair in self.pairs:
			modeFile = "%s/modes/%s.mode" % (self.pairs[strPair], strPair)
			p1 = Popen(["echo", toTranslate], stdout=PIPE)
			p2 = Popen(["sh", modeFile, "-g"], stdin=p1.stdout, stdout=PIPE)
			p1.stdout.close()  # Allow p1 to receive a SIGPIPE if p2 exits.
			output = p2.communicate()[0].decode('utf-8')
			print(output)
			return output
		else:
			return False


	def translate(self, toTranslate, pair):
		return self.translateMode(toTranslate, pair)

	def sendResponse(self, status, data, callback=None):
		outData = json.dumps(data)

		self.send_response(status)
		self.send_header("Content-type", "application/json")
		self.end_headers()
		if callback==None:
			self.wfile.write(outData.encode('utf-8'))
		else:
			returner = callback+"("+outData+")"
			self.wfile.write(returner.encode('utf-8'))
			
		#self.send_response(403)


	def handleListPairs(self, data):
		if "callback" in data:
			callback = data["callback"][0]
		else:
			callback = None
		responseData = []
		for pair in self.pairs:
			(l1, l2) = pair.split('-')
			responseData.append({"sourceLanguage": l1, "targetLanguage": l2})
		status = 200

		toReturn = {"responseData": responseData,
			"responseDetails": None,
			"responseStatus": status}

		self.sendResponse(status, toReturn, callback)

		
	def handleTranslate(self, data):
		pair = data["langpair"][0]
		if "callback" in data:
			callback = data["callback"][0]
		else:
			callback = None
		(l1, l2) = pair.split('|')
		toTranslate = data["q"][0]
		print(toTranslate, l1, l2)

		translated = self.translate(toTranslate, (l1, l2))
		if translated:
			status = 200
		else:
			status = 404

		toReturn = {"responseData":
			{"translatedText": translated},
			"responseDetails": None,
			"responseStatus": status}

		self.sendResponse(status, toReturn, callback)


	def routeAction(self, path, data):
		if path=="/listPairs":
			self.handleListPairs(data)
		if path=="/translate":
			self.handleTranslate(data)

	def do_GET(self):
		parsed_params = urllib.parse.urlparse(self.path)
		query_parsed = urllib.parse.parse_qs(parsed_params.query)
		self.routeAction(parsed_params.path, query_parsed)


	def do_POST(self):
		#length = int(self.headers['Content-Length'])
		#indata = self.rfile.read(length)
		#post_data = urllib.parse.parse_qs(indata.decode('utf-8'))
		#if len(post_data) == 0:
		#	post_data = indata.decode('utf-8')
		#
		#data = json.loads(post_data)
		#print(data, self.path)
		self.send_response(403)

def setup_server():
	global Handler, httpd
	Handler = MyHandler

	rawPairs = getPairsInPath(pairsPath)
	for pair in rawPairs:
		(f, l1, l2) = pair
		Handler.pairs["%s-%s" % (l1, l2)] = f

	httpd = socketserver.TCPServer(("", PORT), Handler)
	print("Server is up and running on port %s" % PORT)
	try:
		httpd.serve_forever()
	except TypeError:
		httpd.shutdown()
	except KeyboardInterrupt:
		httpd.shutdown()
	except NameError:
		httpd.shutdown()

setup_server()
