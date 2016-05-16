import requests
import time
import aiohttp
from datetime import timedelta
import json
import encryption
from secret import *


class AList:
    def __init__(self, redis):
        self.apiurl = "https://anilist.co/api"
        self.commands = [['awaifu', self.waifu], ['ahusbando', self.husbando], ['acharacter', self.searchcharacter],
                         ['acurrent', self.currentanime], ['aanime', self.searchanime], ['amanga', self.searchmanga],
                         ['auser', self.get_user], ['anotifications', self.get_notifications]]
        self.pools = redis
        self.events = [[self.get_readonly, 0]]
        self.enc = encryption.AESCipher(cryptokey)
        self.headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    def get_readonly(self, loop):
        loop.create_task(self._get_readonly())
        loop.call_later(3500, self.get_readonly, loop)

    async def _get_readonly(self):
        async with self.pools.get() as pool:
            cid = await pool.hget("AniList", "ClientID")
            csecret = await pool.hget("AniList", "ClientSecret")
            data = {'grant_type': 'client_credentials', 'client_id': cid,
                    'client_secret': csecret}
            url = self.apiurl + "/auth/access_token"
            with aiohttp.ClientSession() as session:
                async with session.post(url, params=data) as resp:
                    jsd = await resp.json()
                    await pool.hset("ALReadOnly", "Expiration", jsd['expires'])
                    await pool.hset("ALReadOnly", "AccessToken", jsd['access_token'])

    async def get_oauth(self, id):
        async with self.pools.get() as dbp:
            expiration = await dbp.hget(id, "Anilist_Expires")
            if int(expiration) < time.time():
                refresh = await dbp.hget(id, "Anilist_Refresh")
                cid = await dbp.hget("AniList", "ClientID")
                csec = await dbp.hget("AniList", "ClientSecret")
                params = {'grant_type': 'refresh_token', 'client_id': cid, 'client_secret': csec, 'refresh_token': refresh}
                with aiohttp.ClientSession() as session:
                    async with session.post("https://anilist.co/api/auth/access_token", params=params) as response:
                        text = await response.text()
                        if text == "\n" or response.status == 404:
                            return 0
                        else:
                            jsd = json.loads(text)
                            await dbp.hset(id, "Anilist_Expires", jsd['expires'])
                            await dbp.hset(id, "Anilist_Token", self.enc.encrypt(jsd['access_token']))
                            return jsd['access_token']
            else:
                atoken = await dbp.hget(id, "Anilist_Token")
                return self.enc.decrypt(atoken)

    async def waifu(self, message):
        name = message.content[8:]
        async with self.pools.get() as pool:
            token = await pool.hget("ALReadOnly", "AccessToken")
            data = {'access_token': token}
            if name.isdigit():
                url = self.apiurl + "/character/" + str(name)
            else:
                url = self.apiurl + "/character/search/" + name.replace(' ', '%20')
            with aiohttp.ClientSession() as session:
                async with session.get(url, params=data) as resp:
                    text = await resp.text()
                    if resp.status == 404 or text == "\n":
                        return "What character? You don't even know the name of your waifu? The shame."
                    jsd = json.loads(text)
                    if isinstance(jsd, list):
                        jsd = jsd[0]
                    whc = "{0} confesses their undying devotion to their waifu {1}{2}!\n{3}".format(message.author.name,
                                                                                                    jsd['name_first'],
                                                                                                    ' ' + jsd['name_last'] if jsd['name_last'] is not None else '',
                                                                                                    jsd['image_url_med'])
                    return whc

    async def husbando(self, message):
        name = message.content[10:]
        async with self.pools.get() as pool:
            token = await pool.hget("ALReadOnly", "AccessToken")
            data = {'access_token': token}
            if name.isdigit():
                url = self.apiurl + "/character/" + str(name)
            else:
                url = self.apiurl + "/character/search/" + name.replace(' ', '%20')
            with aiohttp.ClientSession() as session:
                async with session.get(url, params=data) as resp:
                    text = await resp.text()
                    if text == "\n" or resp.status == 404:
                        return "What character? You don't even know the name of your husbando? The shame."
                    jsd = json.loads(text)
                    if isinstance(jsd, list):
                        jsd = jsd[0]
                    whc = "{0} confesses their undying devotion to their husbando {1}{2}!\n{3}".format(message.author.name,
                                                                                               jsd['name_first'],
                                                                                               ' ' + jsd['name_last'] if jsd['name_last'] is not None else '',
                                                                                               jsd['image_url_med'])
                    return whc

    async def searchcharacter(self, message):
        name = message.content[12:]
        if name.isdigit():
            return await self.parsecharacter(name)
        async with self.pools.get() as pool:
            token = await pool.hget("ALReadOnly", "AccessToken")
            data = {'access_token': token}
            url = self.apiurl + "/character/search/" + name.replace(' ', '%20')
            with aiohttp.ClientSession() as session:
                async with session.get(url, params=data) as resp:
                    text = await resp.text()
                    if text == '\n' or resp.status == 404:
                        return "[ANILIST] No results for a character named {0} in Anilist.".format(name)
                    else:
                        jsd = json.loads(text)
                        if len(jsd) > 1:
                            msg = "Found these characters ->\n"
                            for i in jsd:
                                msg += " {0}{1} (ID: {2})\n".format(i['name_first'], '\b' + i['name_last'] if i['last_name'] != '' else '', i['id'])
                            return msg
                        elif len(jsd) == 1:
                            return await self.parsecharacter(jsd[0]['id'])

    async def parsecharacter(self, id):
        async with self.pools.get() as pool:
            token = await pool.hget("ALReadOnly", "AccessToken")
            data = {'access_token': token}
            url = self.apiurl + "/character/" + str(id)
            with aiohttp.ClientSession() as session:
                async with session.get(url, params=data) as resp:
                    jsd = await resp.json()
                    return " {0} {1}\nInfo: {2}\n{3}".format(jsd['name_first'], jsd['name_last'],
                                                            jsd['info'], jsd['image_url_med'])

    async def searchanime(self, message):
        name = message.content[8:]
        if name.isdigit():
            return await self.parseanime(name)
        async with self.pools.get() as pool:
            token = await pool.hget("ALReadOnly", "AccessToken")
            data = {'access_token': token}
            url = self.apiurl + "/anime/search/" + name.replace(' ', '%20')
            with aiohttp.ClientSession() as session:
                async with session.get(url, params=data) as resp:
                    text = await resp.text()
                    if text == '\n' or resp.status == 404:
                        return "[ANILIST] No results found on Anilist for Anime {0}".format(name)
                    else:
                        jsd = json.loads(text)
                        if len(jsd) > 1:
                            msg = "Found these Anime ->\n"
                            for i in jsd:
                                msg += " {0} (ID: {1})\n".format(i['title_english'], i['id'])
                            return msg
                        elif len(jsd) == 1:
                            return await self.parseanime(jsd[0]['id'])

    async def parseanime(self, id):
        async with self.pools.get() as pool:
            token = await pool.hget("ALReadOnly", "AccessToken")
            data = {'access_token': token}
            url = self.apiurl + "/anime/" + str(id)
            with aiohttp.ClientSession() as session:
                async with session.get(url, params=data) as resp:
                    jsd = await resp.json()
                    return "Titles\n English: {0}\n Romaji: {1}\n Japanese: {2}\nStatus: {3}\n{4}\nAverage Score: {5}\nGenres: {6}\nDescriptions: {7}\n{8}".format(
                        jsd['title_english'], jsd['title_romaji'], jsd['title_japanese'],
                        jsd['airing_status'], 'Episode {0} in {1}'.format(jsd['airing']['next_episode'], str(timedelta(seconds=jsd['airing']['countdown']))) if jsd['airing_status'].lower() == 'currently airing' else 'Episodes: {0}'.format(jsd['total_episodes']),
                        jsd['average_score'], ', '.join(jsd['genres']), jsd['description'].replace('<br>', '\n'),
                        jsd['image_url_med'])

    async def currentanime(self, message):
        async with self.pools.get() as pool:
            token = await pool.hget("ALReadOnly", "AccessToken")
            data = {'access_token': token, 'status': 'Currently Airing',
                    'sort': 'popularity-desc', 'year': '2016'}
            url = self.apiurl + "/browse/anime"
            with aiohttp.ClientSession() as session:
                async with session.get(url, params=data) as resp:
                    jsd = await resp.json()
                    msg = "Currently Airing Popular Anime ->\n"
                    for item in jsd[0:10]:
                        msg += " {0}: {1}\n".format(item['title_english'], item['id'])
                    return msg

    async def searchmanga(self, message):
        name = message.content[8:]
        if name.isdigit():
            return await self.parsemanga(name)
        async with self.pools.get() as pool:
            token = await pool.hget("ALReadOnly", "AccessToken")
            data = {'access_token': token}
            url = self.apiurl + "/manga/search/" + name.replace(' ', '%20')
            with aiohttp.ClientSession() as session:
                async with session.get(url, params=data) as resp:
                    text = await resp.text()
                    if resp.text() == "\n" or resp.status == 404:
                        return "[ANILIST] No results found for {0} in Manga.".format(name)
                    else:
                        jsd = json.loads(text)
                        if len(jsd) == 1:
                            return await self.parsemanga(jsd[0]['id'])
                        elif len(jsd) > 1:
                            msg = "Found these Manga ->\n"
                            for i in jsd:
                                msg += " {0} (ID: {1})\n".format(i['title_english'], i['id'])
                            return msg

    async def parsemanga(self, id):
        async with self.pools.get() as pool:
            token = await pool.hget("ALReadOnly", "AccessToken")
            data = {'access_token': token}
            url = self.apiurl + "/manga/" + str(id)
            with aiohttp.ClientSession() as session:
                async with session.get(url, params=data) as resp:
                    jsd = await resp.json()
                    return "Titles\n English: {0}\n Romaji: {1}\n Japanese: {2}\nStatus: {3}\nLength: {4} volumes and {5} chapters\nAverage Score: {6}\nGenres: {7}\nDescriptions: {8}\n{9}".format(
                        jsd['title_english'], jsd['title_romaji'], jsd['title_japanese'],
                        jsd['publishing_status'], jsd['total_volumes'], jsd['total_chapters'],
                        jsd['average_score'], ','.join(jsd['genres']), jsd['description'],
                        jsd['image_url_med'])

    async def get_user(self, message):
        url = self.apiurl + "/user"
        if len(message.content) <= 6:
            key = await self.get_oauth(message.author.id)
            if key == 0:
                return "I can't pull your details from AniList because you haven't verified your account. PM me about anilist to do that."
            else:
                header = self.headers
                header['Authorization'] = 'Bearer {0}'.format(key)
                with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=header) as response:
                        text = await response.text()
                        if response.status == 404 or text == "\n":
                            return "Anilist says you don't exist."
                        else:
                            jsd = json.loads(text)
                            return "{0} ({1})\n{2} Pending Notifications.\n{3}\n\nI've spent {4} on Anime and read {5} Manga Chapters.\n{6}".format(jsd['display_name'], jsd['id'], jsd['notifications'], jsd['about'], str(timedelta(seconds=jsd['anime_time'])), jsd['manga_chap'], jsd['image_url_lge'])
        else:
            name = message.content[7:]
            async with self.pools.get() as dbp:
                token = await dbp.hget("ALReadOnly", "AccessToken")
                data = {'access_token': token}
                url = url + "/" + name
                with aiohttp.ClientSession() as session:
                    async with session.get(url, params=data) as response:
                        if response.status in [403, 401]:
                            return "Your profile is private."
                        elif response.status == 404:
                            return "No user found by name {0}".format(name)
                        else:
                            text = await response.text()
                            if text == "\n":
                                return "No user found by name {0}".format(name)
                            else:
                                jsd = json.loads(text)
                                return "{0} ({1})\n{2} Pending Notifications.\n{3}\n\nI've spent {4} on Anime and read {5} Manga Chapters.\n{6}".format(jsd['display_name'], jsd['id'], jsd['notifications'], jsd['about'],str(timedelta(seconds=jsd['anime_time'])), jsd['manga_chap'], jsd['image_url_lge'])

    async def get_notifications(self, message):
        url = self.apiurl + "/user/notifications"
        key = await self.get_oauth(message.author.id)
        if key == 0:
            return "Notifications require you to verify your account with Oauth. PM me about anilist to do that."
        else:
            header = self.headers
            header['Authorization'] = 'Bearer {0}'.format(key)
            with aiohttp.ClientSession() as session:
                async with session.get(url, headers=header) as response:
                    text = await response.text()
                    if text == "\n" or response.status == 404:
                        return "Something went wrong. I wasn't able to get your notifications."
                    else:
                        jsd = json.loads(text)
                        print(json.dumps(jsd))
                        return json.dumps(jsd)