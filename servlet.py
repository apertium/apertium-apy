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

	def translate(self, toTranslate, pair):
		strPair = '%s-%s' % pair
		if strPair in self.pairs:
			p1 = Popen(["echo", toTranslate], stdout=PIPE)
			p2 = Popen(["apertium", "-d %s" % self.pairs[strPair], strPair], stdin=p1.stdout, stdout=PIPE)
			p1.stdout.close()  # Allow p1 to receive a SIGPIPE if p2 exits.
			output = p2.communicate()[0].decode('utf-8')
			print(output)
		else:
			return False
		return output

	def sendResponse(self, status, data):
		outData = json.dumps(data)

		self.send_response(status)
		self.send_header("Content-type", "application/json")
		self.end_headers()
		self.wfile.write(outData.encode('utf-8'))
		#self.send_response(403)


	def handleListPairs(self):
		responseData = []
		for pair in self.pairs:
			(l1, l2) = pair.split('-')
			responseData.append({"sourceLanguage": l1, "targetLanguage": l2})
		status = 200

		toReturn = {"responseData": responseData,
			"responseDetails": None,
			"responseStatus": status}

		self.sendResponse(status, toReturn)

		
	def handleTranslate(self, data):
		pair = data["langpair"][0]
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

		self.sendResponse(status, toReturn)


	def routeAction(self, path, data):
		if path=="/listPairs":
			self.handleListPairs()
		if path=="/translate":
			self.handleTranslate(data)

	def do_GET(self):
		parsed_params = urllib.parse.urlparse(self.path)
		query_parsed = urllib.parse.parse_qs(parsed_params.query)
		self.routeAction(parsed_params.path, query_parsed)


	def do_POST(self):
		length = int(self.headers['Content-Length'])
		indata = self.rfile.read(length)
		post_data = urllib.parse.parse_qs(indata.decode('utf-8'))
		if len(post_data) == 0:
			post_data = indata.decode('utf-8')

		data = json.loads(post_data)
		print(data, self.path)

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
