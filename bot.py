import asyncio
import binascii
import discord
from discord.ext import commands
import hashlib
import json
import os
import pathlib
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree

SCRIPT_PATH = pathlib.Path(os.path.dirname(os.path.realpath(__file__)))
token = ''
update_frequency = 60 * 10

class GameUpdate:
    def __init__(self, name, link):
        self.name = name
        self.link = link

class GameInfo:
    def __init__(self, name, force_retrieval=False):
        self.name = name
        self.games = {}
        self.hash = None
        self.save_path = pathlib.Path(SCRIPT_PATH, 'lists/{}.json'.format(self.name))

        # First, attempt to read existing game info from disk
        if not force_retrieval and self.save_path.is_file():
            with open(self.save_path, 'r') as f:
                data = json.load(f)
                self.hash = data['hash']
                self.games = data['games']
        else:
            self.__retrieve_rss_feed(self.name)
            self.__read_from_xml()
            self.__calculate_sha256()

    def __retrieve_rss_feed(self, search):
        params = urllib.parse.urlencode({'rss': 1, 'search': search})
        url = 'https://predb.me/?{}'.format(params)
        request = urllib.request.Request(url, data=None, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'
        })

        with urllib.request.urlopen(request) as f:
            self._xml_raw = f.read()
    
    def __read_from_xml(self):
        channel = next(xml.etree.ElementTree.fromstring(self._xml_raw.decode('utf-8')).iterfind('channel'))

        for item in channel:
            title = item.find('title')
            link = item.find('link')

            if title is not None and link is not None:
                self.games[title.text] = { 'link': link.text }

    def __calculate_sha256(self):
        h = hashlib.sha256()
        h.update(self._xml_raw)
        self.hash = binascii.hexlify(h.digest()).decode('utf-8')

    def save(self):
        pathlib.Path(self.save_path.parent).mkdir(parents=True, exist_ok=True)
        data = { 'hash': self.hash, 'games': self.games}

        with open(self.save_path, 'w') as out:
            json.dump(data, out, indent=4, sort_keys=True)

cached_existing_gameinfo = {}

def get_existing_gameinfo(name):
    info = cached_existing_gameinfo.get(name)

    if info is not None:
        return info

    info = GameInfo(name)
    cached_existing_gameinfo[name] = info
    return info

def get_updates(info_names):
    updates = []

    for name in info_names:
        existing_gameinfo = get_existing_gameinfo(name)
        new_gameinfo = GameInfo(name, force_retrieval=True)

        if new_gameinfo.hash == existing_gameinfo.hash:
            new_gameinfo.save()
            continue

        added_entries = { k : new_gameinfo.games[k] for k in set(new_gameinfo.games) - set(existing_gameinfo.games) }

        new_gameinfo.save()
        cached_existing_gameinfo[name] = new_gameinfo

        updates += [ GameUpdate(name, entry['link']) for name, entry in added_entries.items()]

    return updates

bot = commands.Bot('!')

async def update():
    print('Checking for updates...')

    channel = discord.utils.get(bot.get_all_channels(), name='information-submission')
    updates = get_updates(['NSW-BigBlueBox', 'NSW-HR'])

    if not updates:
        print('No updates found.')
        return

    for update in updates:
        await bot.send_message(channel, 'New game detected: {}.\nMore info: {}'.format(update.name, update.link))

    print('Up-to-date.')

async def auto_update_check():
    await bot.wait_until_ready()

    while not bot.is_closed:
        try:
            await update()
        except Exception as e:
            print('auto_update_check: An error ocurred: %s'.format(str(e)))
            
        await asyncio.sleep(update_frequency) # Update every 10 minutes

class InfoCheck:
    def __init__(self, bot):
        self.bot = bot

    @commands.has_any_role('Owner', 'Data admin')
    @commands.command(pass_context=True, name="update")
    async def update_command(self):
        try:
            await update()
        except Exception as e:
            print('update_command: An error ocurred: %s'.format(str(e)))

    @commands.has_any_role('Owner', 'Data admin')
    async def terminate(self):
        print('Terminating...')
        sys.exit()

bot.add_cog(InfoCheck(bot))
bot.loop.create_task(auto_update_check())

print('Running...')

# Read config
with open(pathlib.Path(SCRIPT_PATH, 'config.json'), 'r') as f:
    data = json.load(f)
    token = data['token']
    update_frequency = data['update_frequency']

bot.run(token)