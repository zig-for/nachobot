import sys
# insert at 1, 0 is the script path (or '' in REPL)
sys.path.insert(1, '../ALttPEntranceRandomizer')
import asyncio
import glob, os, shlex, time

import EntranceRandomizer as ALTTPEntranceRandomizer
import Main as ALTTPMain
import Utils as ALTTPUtils
import MultiServer
from pathlib import Path

import discord

from collections import defaultdict
from dataclasses import dataclass, field
import pickledb


OUTPUT_ROOT = Path('./output/' + str(int(time.time())))
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


TOKEN_REMOVE_ME = open("SECRET.txt", "r").read()

client = discord.Client()

userdb = pickledb.load('user.db', True)

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
	server: None
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


LAST_CHANNEL = None

def log_item(a, b, i):
	global LAST_CHANNEL
	asyncio.ensure_future(print_chan(LAST_CHANNEL, a + ' found ' + b + '\'s ' + i))

def set_user_kv(author, k, v):
	strid = str(author)

	if not userdb.exists(strid):
		userdb.dcreate(strid)
	
	userdb.dadd(strid, (k,v))
	
def get_user_kv(author, k):
	strid = str(author)
	if userdb.exists(strid):
		if userdb.dexists(strid, k):
			return userdb.dget(strid, k)
	return None

def get_user_kvs(author):
	strid = str(author)
	if userdb.exists(strid):
		return userdb.dgetall(strid)

def join_game(author, game):
	game.players.add(author.id)

	if not get_user_kv(author.id, 'name'):
		set_user_kv(author.id, 'name', author.name)


@client.event
async def on_message(message):
	if message.author == client.user:
		return

	if message.content.startswith('^'):

		content = shlex.split(message.content[1:])
		chan = message.channel
		global LAST_CHANNEL
		LAST_CHANNEL = chan

		if not content:
			return

		server = message.channel.guild

		server_games = games_by_server[server]
		

		print(content)

		if content[0] == 'create':
			game = server_games.by_user.get(message.author.id)

			if game:
				return await print_chan(chan, 'Error: You\'re already hosting a game here!')

			global global_game_id
			game = Game(global_game_id, content[1:])
			global_game_id += 1

			server_games.by_user[message.author.id] = game
			server_games.by_id[game.game_id] = game

			join_game(message.author, game)

			return await print_chan(chan, 'creating game')
		elif content[0] == 'start' or content[0] == 'begin':
			game = server_games.by_user.get(message.author.id)

			if not game:
				return await print_chan(chan, 'Error: You don\'t have a game here!')
			
			# output dir
			path = OUTPUT_ROOT / str(game.game_id)
			ALTTPUtils.output_path.cached_path = path
			path.mkdir(parents=True, exist_ok=True)

			# setup args
			args = ALTTPEntranceRandomizer.parse_arguments(game.args + ["--multi", str(len(game.players))])
			args.create_spoiler = True
			args.rom = './Zelda no Densetsu - Kamigami no Triforce (J) (V1.0).smc'
			
			args.outputpath = path

			index = 1

			names = []

			print(game.players)

			validkeys = ['logic', 'mode', 'swords', 'goal', 'difficulty', 'item_functionality',
						 'shuffle', 'crystals_ganon', 'crystals_gt', 'openpyramid',
						 'mapshuffle', 'compassshuffle', 'keyshuffle', 'bigkeyshuffle', 'startinventory',
						 'retro', 'accessibility', 'hints', 'beemizer',
						 'shufflebosses', 'shuffleenemies', 'enemy_health', 'enemy_damage', 'shufflepots',
						 'ow_palettes', 'uw_palettes', 'sprite', 'disablemusic', 'quickswap', 'fastmenu', 'heartcolor', 'heartbeep',
						 'remote_items']



			validkeys = { key : type(getattr(args, key)[1]) for key in validkeys }


			for player_id in game.players:
				user_args = []

				t = get_user_kvs(player_id)

				name = t.get('name', "WHERE_IS_YOUR_NAME")

				names.append(name)

				print(t)
				for k in t:
					if k in validkeys:
						
						if validkeys[k] == bool:
							s = t[k].lower()
							print(s)
							print(t[k])
							if s == "true":
								getattr(args, k)[index] = True
							elif s == "false":
								getattr(args, k)[index] = False
							else:
								await print_chan(chan, 'Invalid user setting ' + k + "=" + t[k] + ' for ' + name)
						else:
							try:
								getattr(args, k)[index] = validkeys[k](t[k])
							except:
								await print_chan(chan, 'Invalid user setting ' + k + "=" + t[k] + ' for ' + name)

				index += 1

			args.names = ",".join(names)

			print(args)
			

			# generate roms
			ALTTPMain.main(args)

			await print_chan(chan, 'starting game with ' + str(args.multi) + ' players')

			multidata = None
			# upload roms and find multidata
			for root, dirs, files in os.walk(str(path)):
				for name in files:
					if name.endswith('.sfc'):
						await chan.send(file=discord.File(os.path.join(root, name)))
					elif name.endswith('_multidata'):
						multidata = os.path.join(root, name)


			#start server
			loop = asyncio.get_event_loop()
			multi_args = MultiServer.parse_arguments([])
			multi_args.multidata = multidata
			multi_args.loglevel = 'info'
			game.server = asyncio.ensure_future(MultiServer.main(multi_args))
			MultiServer.global_item_found_cb = log_item
			return

		elif content[0] == 'end':
			game = server_games.by_user.get(message.author.id)

			if not game:
				return await print_chan(chan, 'Error: You don\'t have a game here!')

			server_games.by_user[message.author.id] = None
			server_games.by_id[game.game_id] = None

			path = OUTPUT_ROOT / str(game.game_id)

			for root, dirs, files in os.walk(str(path)):
				for name in files:
					if name.endswith('_Spoiler.txt'):
						await chan.send(file=discord.File(os.path.join(root, name)))


			game.server.cancel()

			return await print_chan(chan, 'end game')
		elif content[0] == 'join':
			if len(server_games.by_user) == 1:
				game = server_games.by_user[list(server_games.by_user)[0]]
				join_game(message.author, game)
				return await print_chan(chan, message.author.name + ' Joined!')
			else:
				return await print_chan(chan, 'Error: One game per server right now, sorry.')
		elif content[0] == 'set':
			if content[1] == 'user':
				k = content[2]
				v = content[3]

				if ' ' in k or ' ' in v:
					return await print_chan(chan, 'Error: Invalid kv pair.')

				set_user_kv(message.author.id, k, v)
				print(get_user_kvs(message.author.id))
				return await print_chan(chan, 'set ' + str(message.author.id) + " " + k + "=" + get_user_kv(message.author.id, k))
		elif content[0] == 'get':
			if content[1] == 'user':
				k = content[2]

				if ' ' in k:
					return await print_chan(chan, 'Error: Invalid kv pair.')

				v = get_user_kv(message.author.id, k)
				return await print_chan(chan, 'get ' + str(message.author.id) + " " + k + "=" + v)





client.run(TOKEN_REMOVE_ME)