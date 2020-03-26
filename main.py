import sys
# insert at 1, 0 is the script path (or '' in REPL)
sys.path.insert(1, '../ALttPEntranceRandomizer')
import asyncio
import glob, os, shlex, time

import EntranceRandomizer as ALTTPEntranceRandomizer
import Utils as ALTTPUtils
ALTTPUtils.local_path.cached_path = '../ALttPEntranceRandomizer'
import Main as ALTTPMain
import Utils as ALTTPUtils
import MultiServer
from pathlib import Path

import discord
import discord.ext
import discord.ext.commands
import discord.ext.tasks

import aiohttp
from collections import defaultdict
from dataclasses import dataclass, field
import pickledb

from aiohttp import web
import multiprocessing.connection
import alttphttp
import queue
OUTPUT_ROOT = Path('./output/' + str(int(time.time())))
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


TOKEN_REMOVE_ME = open("SECRET.txt", "r").read()

client = discord.Client()
nachobot_guild = None
nachobot_emojis = {}

userdb = pickledb.load('user.db', True)

@dataclass
class ServerGames:
	by_user: dict = field(default_factory=dict)
	by_id: dict = field(default_factory=dict)

games_by_server = defaultdict(ServerGames)

games_by_token = {}

global_game_id = 0


@dataclass
class PlayerInfo:
	sword_level: int = 0
	mail_level: int = 0
	shield_level: int = 0

class Game:
	game_id: int
	args: list
	players: set
	token: None
	address: str
	info_box: None
	goal: str
	log: list
	def __init__(self, game_id, args):
		self.game_id = game_id
		self.args = args
		self.players = set()
		self.token = None
		self.address = ''
		self.info_box = None
		self.goal = ''
		self.log = ['']*10
		self.goal_count = defaultdict(int)
		self.found_items = {}
		self.heart_count = defaultdict(lambda: 3 * 4)
		self.player_info = defaultdict(PlayerInfo) 
	def log_message(self, msg):
		self.log = self.log[1:] + [msg] 

async def setup_web():

	app = web.Application()

	app.add_routes([web.static('/output', './output')])

	runner = web.AppRunner(app)
	await runner.setup()
	site = web.TCPSite(runner, 'localhost', 5001)
	await site.start()


async def start_game(message, filename, game):
	chan = message.channel

	url = 'http://localhost:5001/' + filename

	data = {
		'multidata_url': url,
		'admin': message.author.id,
		'meta': {
			'channel': None if isinstance(message.channel, discord.DMChannel) else message.channel.name,
			'guild': message.guild.name if message.guild else None,
			'multidata_url': url,
			'name': f'{message.author.name}#{message.author.discriminator}'
		}
	}

	print(data)

	try:
		multiworld = await alttphttp.request_json_post(url='http://localhost:5000/game', data=data, returntype='json')
	except aiohttp.ClientResponseError as err:
		#raise SahasrahBotException('Unable to generate host using the provided multidata.	Ensure you\'re using the latest version of the mutiworld (<https://github.com/Bonta0/ALttPEntranceRandomizer/tree/multiworld_31>)!') from err
		await print_chan(chan, 'Unable to generate host using the provided multidata.  Ensure you\'re using the latest version of the mutiworld.')
		return

	if not multiworld.get('success', True):
		await print_chan(chan, 'Unable to generate host using the provided multidata')
		#raise SahasrahBotException(f"Unable to generate host using the provided multidata.  {multiworld.get('description', '')}")
		return 

	game.token = multiworld['token'] 
	game.address = 'hylianmulti.world:'+str(multiworld['port'])

	games_by_token[game.token] = game

	game.info_box = await chan.send(embed=make_embed(message.channel.guild, game))


async def end_game(message, game):
	await send_game_command(message, game.token, '/exit')

async def send_game_command(message, token, command):
	result = await alttphttp.request_generic(url=f'http://localhost:5000/game/{token}', method='get', returntype='json')

	if not result['admin'] == message.author.id:
		#raise SahasrahBotException('You must be the creater of the game to send messages to it.')
		await print_chan(message.channel, 'Error: You must be the creater of the game to send messages to it.')
		return

	data = {'msg': command}	
	
	response = await alttphttp.request_json_put(url=f'http://localhost:5000/game/{token}/msg', data=data, returntype='json')

	if 'resp' in response and response['resp'] is not None:
		await message.channel.send(response['resp'])



@client.event
async def on_ready():
	print('We have logged in as {0.user}'.format(client))
	global nachobot_guild
	global nachobot_emojis
	nachobot_guild = await client.fetch_guild(675536369686413312)
	nachobot_emojis = {e.name:e for e in await nachobot_guild.fetch_emojis()}
	print(nachobot_emojis.keys())
	await setup_web()

async def print_chan(channel, message):
	await channel.send(message)



LAST_CHANNEL = None

async def log_item(token, a, a_id, b, b_id, i, l, l_id):
	if not token in games_by_token:
		print('no token')
		return
	game = games_by_token[token]
	print('found game')
	msg = ''
	if a == b:
		msg = a + ' found their own ' + i
	else:
		msg = a + ' found ' + b + '\'s ' + i
	msg += ' in ' + l
	
	game.found_items.setdefault(a_id, set())


	if l_id not in game.found_items[a_id]:
		game.found_items[a_id].add(l_id)

		game.log_message(msg)

		player_info = game.player_info[b_id[1]]

		if i == "Triforce Piece":
			game.goal_count[b_id[1]] = game.goal_count[b_id[1]] + 1
		elif "Heart Container" in i:
			game.heart_count[b_id[1]] += 4
		elif i == "Piece of Heart":
			game.heart_count[b_id[1]] += 1
		# TODO: this doesn't deal with being given a specific level yet
		elif i == "Progressive Sword":
			player_info.sword_level += 1
		elif i == "Progressive Shield":
			player_info.shield_level += 1
		elif i == "Progressive Armor": 
			player_info.mail_level += 1

		await game.info_box.edit(embed=make_embed(game.info_box.channel.guild, game))

import traceback

async def handle_ms_msg(o):
	try:
		print(o)
		if o['cmd'] == 'found_item':
			print('found item')
			d = o['data']
			await log_item(d['token'], d['player_found'], d['player_found_id'], d['player_owned'], d['player_owned_id'], d['item'], d['location'], d['location_id'])
		else:
			print('unknown message ' + o['cmd'])
	except:
		traceback.print_exc()
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
		
			if game.token:
				await print_chan(chan, 'your game is already running!')
				return

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
								# getattr(args, k)[index] = validkeys[k](t[k])
								getattr(args, k)[index] = t[k]
							except:
								await print_chan(chan, 'Invalid user setting ' + k + "=" + t[k] + ' for ' + name)

				index += 1

			args.names = ",".join(names)


			# generate roms
			ALTTPMain.main(args)

			game.goal = args.goal
			game.log_message('Game started!')
			await print_chan(chan, 'starting game with ' + str(args.multi) + ' players')

			multidata = None
			# upload roms and find multidata
			for root, dirs, files in os.walk(str(path)):
				for name in files:
					if name.endswith('.sfc'):
						await chan.send(file=discord.File(os.path.join(root, name)))
					elif name.endswith('_multidata'):
						multidata = os.path.join(root, name)

			await print_chan(chan, multidata)
			await start_game(message, multidata, game)

			#start server
			if False:
				loop = asyncio.get_event_loop()
				multi_args = MultiServer.parse_args()
				multi_args.multidata = multidata
				multi_args.loglevel = 'info'
				game.server = asyncio.ensure_future(MultiServer.main(multi_args))
				# MultiServer.global_item_found_cb = log_item
			return

		elif content[0] == 'end':
			game = server_games.by_user.get(message.author.id)

			if not game:
				return await print_chan(chan, 'Error: You don\'t have a game here!')

			await print_chan(chan, 'Game Over!')
			server_games.by_user[message.author.id] = None
			server_games.by_id[game.game_id] = None

			path = OUTPUT_ROOT / str(game.game_id)

			for root, dirs, files in os.walk(str(path)):
				for name in files:
					if name.endswith('_Spoiler.txt'):
						await chan.send(file=discord.File(os.path.join(root, name)))


			# game.server.cancel()
			await end_game(message, game)
			return 
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

				if ' ' in k:
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



def make_embed(server, game):
	embed = discord.Embed(
				title='MultiWorld Game',
				description=f'{game.goal[1]}',
				color=discord.Color.green()
			)
	embed.add_field(name="Host", value=f"{game.address}", inline=False)
	nacho = discord.utils.get(server.emojis, name='NachoHD')
	bullet = u'\u2022'
	hearts = [discord.utils.get(server.emojis, name=f'heart_container{i}') for i in range(0,5)]

	for idx, player in enumerate(game.players, start=1):
		name = get_user_kv(player, 'name')

		player_info = game.player_info[idx]
		
		levels = (player_info.sword_level, player_info.shield_level, player_info.mail_level)


		if game.goal[idx] == 'triforcehunt':
			nachoCount = game.goal_count[idx] 
			desc = f'{nachoCount}/20 {nacho}'
		else:
			desc = game.goal[idx]

		total_hearts = game.heart_count[idx] // 4


		def calc_heart(i):
			if total_hearts == 1 + i * 2:
				return 1
			if total_hearts == 11 + i * 2:
				return 3
			if total_hearts >= 12 + i * 2:
				return 4
			if total_hearts >= 2 + i * 2:
				return 2
			return 0


		desc = str(nachobot_emojis[f'link{levels[2]}{levels[0]}{levels[1]}']) + ''.join([str(hearts[calc_heart(i)]) for i in range(0,5)]) + ' ' + desc

		embed.add_field(name=f'{name}', value=f'{desc}')

	log = '\n'.join([bullet + ' ' + game.log[i] for i in range(1,10)])
	embed.add_field(name='Log:', value=f'{log}',inline=False)

	return embed



class BotConnection(discord.ext.commands.Cog):
	def __init__(self):
		self.listener = multiprocessing.connection.Listener('/tmp/nachobot', 'AF_UNIX')
		self.listener._listener._socket.settimeout(1.0)
		self.msc = None
#	@discord.ext.tasks.loop(seconds=0.25)
	async def poll_connection(self):
		try:
			if not self.msc:
				self.msc = self.listener.accept() 
			while self.msc.poll():
				o = self.msc.recv()

				await handle_ms_msg(o)
		except:
			self.msc = None

	
async def update_bot():
	bot = BotConnection()
	while True:
		await bot.poll_connection()
		await asyncio.sleep(0.1)
asyncio.get_event_loop().create_task(update_bot())

	
client.run(TOKEN_REMOVE_ME)


