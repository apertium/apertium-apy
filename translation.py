import re, threading
from subprocess import Popen, PIPE

def getModeFileLine(modeFile):
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
        print(toReturn)
        return toReturn
    else:
        return False
        
def translateNULFlush(toTranslate, pair, translock, pipelines, pairs):
    with translock:
        strPair = '%s-%s' % pair
        #print(pairs, pipelines)
        #print("DEBUG 0.6")
        if strPair not in pipelines:
            #print("DEBUG 0.7")
            modeFile = "%s/modes/%s.mode" % (pairs[strPair], strPair)
            modeFileLine = getModeFileLine(modeFile)
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

                pipelines[strPair] = (commandsDone[0], commandsDone[-1])

        #print("DEBUG 0.8")
        if strPair in pipelines:
            (procIn, procOut) = pipelines[strPair]
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
            
def translateModeDirect(toTranslate, pair, pairs):
    strPair = '%s-%s' % pair
    if strPair in pairs:
        modeFile = "%s/modes/%s.mode" % (pairs[strPair], strPair)
        modeFileLine = getModeFileLine(modeFile)
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
        
def translateModeSimple(toTranslate, pair, pairs):
    strPair = '%s-%s' % pair
    if strPair in pairs:
        modeFile = "%s/modes/%s.mode" % (pairs[strPair], strPair)
        p1 = Popen(["echo", toTranslate], stdout=PIPE)
        p2 = Popen(["sh", modeFile, "-g"], stdin=p1.stdout, stdout=PIPE)
        p1.stdout.close()  # Allow p1 to receive a SIGPIPE if p2 exits.
        output = p2.communicate()[0].decode('utf-8')
        print(output)
        return output
    else:
        return False
        
def hardbreakFn():
    """If others are waiting on us, we send short requests, otherwise we
    try to minimise the number of requests, but without
    letting buffers fill up.

    Unfortunately, if we've already started a long
    request, the next one to come along will have to wait
    one long request until they start getting shorter.

    These numbers could probably be tweaked a lot.
    """
    if threading.active_count()>2:
        hardbreak=10000
        # (would prefer "translock.waiting_count", but doesn't seem exist)
    else:
        hardbreak=50000
    print((threading.active_count(), hardbreak))
    return hardbreak
    
def translateSplitting(toTranslate, pair, translock, pipelines, pairs):
    """Splitting it up a bit ensures we don't fill up FIFO buffers (leads
    to processes hanging on read/write)."""
    allSplit = []	# [].append and join faster than str +=
    last=0
    while last<len(toTranslate):
        hardbreak = hardbreakFn()
        # We would prefer to split on a period seen before the
        # hardbreak, if we can:
        softbreak = int(hardbreak*0.9)
        dot=toTranslate.find(".", last+softbreak, last+hardbreak)
        if dot>-1:
            next=dot
        else:
            next=last+hardbreak
        print("toTranslate[%d:%d]" %(last,next))
        allSplit.append(translateNULFlush(toTranslate[last:next], pair, translock, pipelines, pairs))
        last=next
    return "".join(allSplit)
    
def translate(toTranslate, pair, translock, pipelines, pairs):
    return translateSplitting(toTranslate, pair, translock, pipelines, pairs)
