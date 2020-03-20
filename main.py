import sys
# insert at 1, 0 is the script path (or '' in REPL)
sys.path.insert(1, '../ALttPEntranceRandomizer')
import asyncio
import glob, os, time

import EntranceRandomizer as ALTTPEntranceRandomizer
import Main as ALTTPMain
import Utils as ALTTPUtils
import MultiServer
from pathlib import Path

import discord

from collections import defaultdict
from dataclasses import dataclass, field


OUTPUT_ROOT = Path('./output/' + str(int(time.time())))
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


TOKEN_REMOVE_ME = open("SECRET.txt", "r").read()

client = discord.Client()

@dataclass
class ServerGames:
	by_user: dict = field(default_factory=dict)
	by_id: dict = field(default_factory=dict)

games_by_server = defaultdict(ServerGames)
global_game_id = 0

class Game:
	game_id: int
	args: list
	players: set
	def __init__(self, game_id, args):
		self.game_id = game_id
		self.args = args
		self.players = set()

@client.event
async def on_ready():
	print('We have logged in as {0.user}'.format(client))

async def print_chan(channel, message):
	await channel.send(message)

async def start_server():
	print('server start')
	sleep(10.0)
	print('server stop')

@client.event
async def on_message(message):
	if message.author == client.user:
		return

	if message.content.startswith('^'):
		content = message.content[1:].split()
		chan = message.channel

		if not content:
			return

		server = message.channel.guild

		server_games = games_by_server[server]
		

		print(content)

		if content[0] == 'open':
			game = server_games.by_user.get(message.author)

			if game:
				return await print_chan(chan, 'Error: You\'re already hosting a game here!')

			global global_game_id
			game = Game(global_game_id, content[1:])
			global_game_id += 1

			server_games.by_user[message.author] = game
			server_games.by_id[game.game_id] = game
			
			game.players.add(message.author.name)

			return await print_chan(chan, 'creating game')
		elif content[0] == 'start':
			game = server_games.by_user[message.author]

			if not game:
				return await print_chan(chan, 'Error: You don\'t have a game here!')
			
			parser = ALTTPEntranceRandomizer.make_parser()
			args = parser.parse_args(game.args)
			
			args.create_spoiler = True
			args.rom = './Zelda no Densetsu - Kamigami no Triforce (J) (V1.0).smc'

			args.names = ', '.join(game.players)
			
			path = OUTPUT_ROOT / str(game.game_id)

			args.outputpath = path

			ALTTPUtils.output_path.cached_path = path

			path.mkdir(parents=True, exist_ok=True)

			ALTTPMain.main(args)

			await print_chan(chan, 'starting...')

			multidata = None

			for root, dirs, files in os.walk(str(path)):
				for name in files:
					if name.endswith('.sfc'):
						await chan.send(file=discord.File(os.path.join(root, name)))
					elif name.endswith('_multidata'):
						multidata = os.path.join(root, name)



			loop = asyncio.get_event_loop()

			multi_args = MultiServer.get_parser().parse_args([])
			multi_args.multidata = multidata
			asyncio.ensure_future(MultiServer.main_inner(multi_args))
			return

		elif content[0] == 'end':
			game = server_games.by_user[message.author]

			if not game:
				return await print_chan(chan, 'Error: You don\'t have a game here!')

			server_games.by_user[message.author] = None
			server_games.by_id[game.game_id] = None

			path = OUTPUT_ROOT / str(game.game_id)


			for root, dirs, files in os.walk(str(path)):
				for name in files:
					if name.endswith('_Spoiler.txt'):
						await chan.send(file=discord.File(os.path.join(root, name)))


			return await print_chan(chan, 'end game')
		elif content[0] == 'join':
			if len(server_games.by_user) == 1:
				server_games.by_user[list(server_games.by_user)[0]].players.add(message.author.name)
				return await print_chan(chan, message.author.name + ' Joined!')
			else:
				return await print_chan(chan, 'Error: One game per server right now, sorry.')



client.run(TOKEN_REMOVE_ME)