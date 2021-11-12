#This file opens a websocket running on port 8037 and, whenever Dwarf Fortress sends something to the console,
#it formats and forwards it for Neos. Neos should then look at the first character of every message it receives.
#If it's a B, the rest of the message should get printed to the background layer, if F, it should go to the foreground
#layer. (What's currently there is overwritten)

import subprocess
import websockets
import asyncio
from threading import Lock
import pyte
import os

#These are the default colors that Dwarf Fortress uses for the 16 console colors.
colors = {
	"black" : "#000000",
	"blue" : "#000080",
	"cyan" : "#008080",
	"green" : "#008000",
	"purple" : "#800080",
	"red" : "#800000",
	"white" : "#C0C0C0",
	"yellow" : "#808000",
	"brightBlack" : "#808080",
	"brightBlue" : "#0000FF",
	"brightCyan" : "#00FFFF",
	"brightGreen" : "#00FF00",
	"brightPurple" : "#FF00FF",
	"brightRed" : "#FF0000",
	"brightWhite" : "#FFFFFF",
	"brightYellow" : "#FFFF00"
}

#the websocket that'll accept a connection from Neos
websocket = None

#gets the current terminal size from the OS. This value is used to keep the screen size in the terminal emulator (pyte) in sync with with that of the terminal this runs in.
terminalSize = os.get_terminal_size()
#sets up the pyte screen, with the given size from above.
pyteScreen = pyte.Screen(terminalSize.columns, terminalSize.lines)
#the stream that will be receiving all output from Dwarf Fortress
pyteStream = pyte.Stream(pyteScreen)

#This lock gets locked once the client connects so that we never accept another client. (since the DF game is started after that)
mainLock = Lock()

async def outputHandler():
	#read DF output and send it to Neos
	for line in iter(dorf.stdout.readline, ""):
		#reset the screen size (in case the terminal has been resized)
		terminalSize = os.get_terminal_size()
		pyteScreen.resize(terminalSize.lines, terminalSize.columns)
		
		#feed the output from DF into pyte
		pyteStream.feed(line.decode("utf-8"))
		
		#start generating a Neos compatible representation of the pyte screen
		neosBackground = "" #the background layer
		neosForeground = "" #the foreground layer
		lastChar = pyteScreen.buffer[0][0] #running last character we've looked at while iterating over the screen.
		
		#Set the opening formatting codes for the first character.
		if lastChar.bg != "default":
			neosBackground += "<color=" + lastChar.bg + ">"
		if lastChar.fg != "default":
			neosForeground += "<color=" + lastChar.fg + ">"
		if lastChar.bold:
			neosForeground += "<b>"
		if lastChar.italics:
			neosForeground += "<i>"
		if lastChar.underscore:
			neosForeground += "<u>"
		if lastChar.strikethrough:
			neosForeground += "<s>"
		
		#iterate over the pyte terminal screen
		for y in range(0, terminalSize.lines):
			for x in range(0, terminalSize.columns):
				thisChar = pyteScreen.buffer[y][x]
				
				#check background color, set if it's different
				if lastChar.bg != thisChar.bg:
					if lastChar.bg != "default": #if we're back to default color, one </color> will close all color tags.
						neosBackground += "</color>"
					if thisChar.bg != "default": #Else, we just open a new color tag. This'll override the previous one, so </color> is not needed.
						neosBackground += "<color=" + colors[thisChar.bg] + ">"
				
				#foreground color, handled the same way as the background color.
				if lastChar.fg != thisChar.fg:
					if lastChar.fg != "default":
						neosForeground += "</color>"
					if thisChar.fg != "default":
						neosForeground += "<color=" + colors[thisChar.fg] + ">"
				
				#other style attributes, these just get opened/closed when we cross a border of different-styled characters.
				if lastChar.bold != thisChar.bold:
					neosForeground += "<b>" if thisChar.bold else "</b>"
				if lastChar.italics != thisChar.italics:
					neosForeground += "<i>" if thisChar.italics else "</i>"
				if lastChar.underscore != thisChar.underscore:
					neosForeground += "<u>" if thisChar.underscore else "</u>"
				if lastChar.strikethrough != thisChar.strikethrough:
					neosForeground += "<s>" if thisChar.strikethrough else "</s>"
				
				#add the actual characters to the Neos strings. (using █ to fill the background layer in Neos.)
				neosBackground += "█"
				neosForeground += thisChar.data
				
				#the current character becomes the previous one.
				lastChar = thisChar
			
			#at the end of a line, insert a newline into the Neos strings
			neosBackground += "\n"
			neosForeground += "\n"
		
		#send the two strings to Neos, prepend with B or F for back-/foreground
		await websocket.send("B" + neosBackground)
		await websocket.send("F" + neosForeground)
		
		#Uncomment these lines to spam enter to DF whenever you get ouput
		#since keyboard input doesn't work right now:
		#
		#dorf.stdin.write(bytes("\n", "utf-8"))
		#dorf.stdin.flush()

#websocket function (Called when a connection from Neos is accepted and sets up the game.)
async def neosConnection(socket, path):
	#define globals
	global websocket #the socket reference, for sending data to Neos from other functions
	global dorf #the Dwarf Fortress subprocess
	
	#try aquiring the main lock. This will fail if there is already a client connected.
	if mainLock.acquire(False):
		websocket = socket
		print("Client connected.")
		#run dwarf fortress subprocess
		dorf = subprocess.Popen("./df_linux/df", stdout=subprocess.PIPE, stdin=subprocess.PIPE, shell=True)
		
		#create a task for reading its output and handing that to pyte
		dfOutputTask = asyncio.create_task(outputHandler())
		
		#iterate through the messages from Neos and send them to DF's stdin
		#Note: This currently doesn't work. I assume that's because the above task doesn't take any breaks.
		async for message in socket:
			print("Sending '" + message + "' to subprocess.")
			dorf.stdin.write(bytes(message, "utf-8"))
			dorf.stdin.flush()
		
		#currently never gets reached.
		mainLock.release()
	else:
		print("Client declined.")

#start websocket and listen on port 8037
print("Starting websocket...")
start_server = websockets.serve(neosConnection, "localhost", 8037)

asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()