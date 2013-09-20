#!/usr/bin/env python3
# -*- indent-tabs-mode: t -*-

import sys, os, re
import http.server, socketserver, urllib.parse, json
from subprocess import Popen, PIPE #call

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
			#print(output)
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

				#print(command)

				#if re.search('automorf', command) or re.search('cg-proc', command) or re.search('autobil', command) or re.search('lrx-proc', command):
				#if not (re.search('lrx-proc', command) or re.search('transfer', command) or re.search('hfst-proc', command) or re.search('autopgen', command)):
				#if re.search('automorf', command) or re.search('cg-proc', command) or re.search('autobil', command):
				#if not re.search('apertium-pretransfer', command):
				#if not (re.search('lrx-proc', command)):
				if 1==1:
					if re.search('apertium-pretransfer', command):
						outCommand = command+" -z"
					else:
						outCommand = re.sub('^(.*?)\s(.*)$', '\g<1> -z \g<2>', command)
					outCommand = re.sub('\s{2,}', ' ', outCommand)
					outCommands.append(outCommand)
					#print(outCommand)
			toReturn = ' | '.join(outCommands)
			toReturn = re.sub('\s*\$2', '', re.sub('\$1', '-g', toReturn))
			#print(toReturn)
			return toReturn
		else:
			return False

	def translateMode(self, toTranslate, pair):
		strPair = '%s-%s' % pair
		#print(self.pairs, self.pipelines)
		if strPair in self.pairs:
			#print("DEBUG 0.6")
			if strPair not in self.pipelines:
				#print("DEBUG 0.7")
				modeFile = "%s/modes/%s.mode" % (self.pairs[strPair], strPair)
				modeFileLine = self.getModeFileLine(modeFile)
				commandList = []
				if modeFileLine:
					commandList = [ c.strip().split() for c in
							modeFileLine.split('|') ]
					commandsDone = []
					for command in commandList:
						if len(commandsDone)>0:
							newP = Popen(command, stdin=commandsDone[-1].stdout, stdout=PIPE)
						else:
							newP = Popen(command, stdin=PIPE, stdout=PIPE)
						commandsDone.append(newP)

					self.pipelines[strPair] = (commandsDone[0], commandsDone[-1])

			#print("DEBUG 0.8")
			if strPair in self.pipelines:
				(procIn, procOut) = self.pipelines[strPair]
				deformat = Popen("apertium-deshtml", stdin=PIPE, stdout=PIPE)
				deformat.stdin.write(bytes(toTranslate, 'utf-8'))
				procIn.stdin.write(deformat.communicate()[0])
				procIn.stdin.write(bytes('\0', "utf-8"))
				procIn.stdin.flush()
				#print("DEBUG 1 %s\\0" % toTranslate)
				d = procOut.stdout.read(1)
				#print("DEBUG 2 %s" % d)
				output = []
				while d and d != b'\0':
					output.append(d)
					d = procOut.stdout.read(1)
				#print("DEBUG 3 %s" % output)
				reformat = Popen("apertium-rehtml", stdin=PIPE, stdout=PIPE)
				reformat.stdin.write(b"".join(output))
				return reformat.communicate()[0].decode('utf-8')
			else:
				print("no pair in pipelines")
				return False
		else:
			print("strpair not in pairs")
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


	def translateSplitting(self, toTranslate, pair):
		"""Splitting it up a bit ensures we don't fill up FIFO buffers (leads
		to processes hanging on read/write)."""
		# This should be as high as possible while low enough
		# that buffers don't fill up:
		hardbreak=100000
		# We would prefer to split on a period seen before the
		# hardbreak, if we can:
		softbreak=int(hardbreak*0.9)
		allSplit = []	# [].append and join faster than str +=
		last=0
		while last<len(toTranslate):
			dot=toTranslate.find(".", last+softbreak, last+hardbreak)
			if dot>-1:
				next=dot
			else:
				next=last+hardbreak
			print("toTranslate[%d:%d]" %(last,next))
			allSplit.append(self.translateMode(toTranslate[last:next],
							   pair))
			last=next

		return "".join(allSplit)

	def translate(self, toTranslate, pair):
		return self.translateSplitting(toTranslate, pair)

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
		if "q" in data:
			toTranslate = data["q"][0]
			#print(toTranslate, l1, l2)

			translated = self.translate(toTranslate, (l1, l2))
			if translated:
				status = 200
			else:
				status = 404
				print("nothing returned")
		else:
			status = 404
			print("no query")
			#print(data)
			translated = False

		toReturn = {"responseData":
			{"translatedText": translated},
			"responseDetails": None,
			"responseStatus": status}

		self.sendResponse(status, toReturn, callback)


	def routeAction(self, path, data):
		print(path)
		if path=="/listPairs":
			self.handleListPairs(data)
		if path=="/translate":
			self.handleTranslate(data)

	def do_GET(self):
		params_parsed = urllib.parse.urlparse(self.path)
		query_parsed = urllib.parse.parse_qs(params_parsed.query)
		self.routeAction(params_parsed.path, query_parsed)


	def do_POST(self):
		length = int(self.headers['Content-Length'])
		indata = self.rfile.read(length)
		query_parsed = urllib.parse.parse_qs(indata.decode('utf-8'))
		params_parsed = urllib.parse.urlparse(self.path)
		self.routeAction(params_parsed.path, query_parsed)


def setup_server():
	global Handler, httpd
	Handler = MyHandler

	if len(sys.argv) != 3:
		raise Exception("Expects exactly two arguments, directory to apertium/trunk and port. Got: %s." % sys.argv)
	pairsPath, PORT = sys.argv[1], int(sys.argv[2])

	rawPairs = getPairsInPath(pairsPath)
	for pair in rawPairs:
		(f, l1, l2) = pair
		Handler.pairs["%s-%s" % (l1, l2)] = f

	socketserver.TCPServer.allow_reuse_address = True
	# is useful when debugging, possibly risky: http://thread.gmane.org/gmane.comp.python.general/509706

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
