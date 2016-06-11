import aiohttp
import json
from datetime import timedelta


class Riot:
    """
    This class handles the Riot API and stores variables and calls related to that API.
    """
    def __init__(self, redis):
        """
        Initialize the API and store API variables and the global connection pool for redis.

        :RedisPool redis: The global aioredis connection pool used by AngelBot
        """
        # API Endpoints: Global is used for static data. NA is North America NA1. Status is for Shard Status endpoints.
        self.apiurls = {'global': 'https://global.api.pvp.net/api/lol', 'na': 'https://na.api.pvp.net/api/lol',
                        'status': 'http://status.leagueoflegends.com/', 'observer': 'https://na.api.pvp.net/observer-mode'}
        self.pools = redis
        self.commands = [['islolup', self.status], ['lolfree', self.free_rotation], ['lolstatus', self.region_status],
                         ['lolfeatures', self.featured_games], ['lolrecent', self.match_list], ['lolstats', self.summoner_stats]]
        self.regions = ['jp1', 'oc1', 'la2', 'la1', 'eun1', 'eu', 'na1']
        self.header = {'User-Agent': 'AngelBot ( aiohttp 0.26.1 python 3.5.1 )'}
        self.events = [[self.update_freerotation, 0]]
        self.maps = {1: "Summoner's Rift (Original Summer)", 2: "Summoner's Rift (Original Autumn)", 4: 'Twisted Treeline (Original)',
                     8: 'The Crystal Scar', 10: 'Twisted Treeline', 11: "Summoner's Rift", 12: 'Howling Abyss', 14: "Butcher's Bridge"}

    def update_freerotation(self, loop):
        """
        A helper function that handles calling the asynchronous function to update the free champion rotation updater.
        Free champion rotations are checked every 48 hours due to inconsistent rotation schedules.

        :event_loop loop:
        """
        pass
        loop.create_task(self._update_freerotation())
        loop.call_later(172800, self.update_freerotation, loop)

    async def _update_freerotation(self):
        """
        This function will handle asking for the free champion rotation and then updating our data.

        """
        async with self.pools.get() as dbp:
            key = await dbp.get("RiotGames")
            test = await dbp.exists("LOLFreeRotation")
            current = []
            if test:
                current = await dbp.get("LOLFreeRotation")
                current = json.loads(current)  # Storage format is a list of dictionaries with an id and name attribute.
            with aiohttp.ClientSession() as session:
                async with session.get(self.apiurls['na'] + '/na/v1.2/champion', params={'freeToPlay': 'True', 'api_key': key}, headers=self.header) as response:
                    jsd = await response.json()
                    templist = []
                    new = []
                    for x in jsd['champions']:
                        templist.append(x['id'])
                    if current:
                        different = False
                        for x in current:
                            if x['id'] not in templist:
                                different = True
                        if different:
                            for x in templist:
                                async with session.get(self.apiurls['global'] + '/static-data/na/v1.2/champion/{}'.format(x), params={'api_key': key}, headers=self.header) as csd:
                                    champsd = await csd.json()
                                    new.append({'id': x, 'name': champsd['name']})
                            await dbp.set("LOLFreeRotation", json.dumps(new))
                    else:
                        for x in templist:
                            async with session.get(
                                            self.apiurls['global'] + '/static-data/na/v1.2/champion/{}'.format(x),
                                            params={'api_key': key}, headers=self.header) as csd:
                                champsd = await csd.json()
                                new.append({'id': x, 'name': champsd['name']})
                        await dbp.set("LOLFreeRotation", json.dumps(new))

    async def status(self, message):
        """
        This will query the status of the League of Legends shards. This is cached for an hour at a time.

        :class message: A discord.py message class
        :return: a message containing the status of the shards for League of Legends
        """
        async with self.pools.get() as dbp:
            msg = "```xl\n"
            for region in self.regions:
                test = await dbp.exists("LOL"+region)
                if test:
                    jsd = await dbp.get("LOL"+region)
                    jsd = json.loads(jsd)
                    msg += jsd['name'] + '\n'
                    for service in jsd['services']:
                        msg += ' '*4 + service['name'] + ' "' + service['status'] + '"\n'
                        if len(service['incidents']):
                            msg += '    '*2 + 'Currently there {} {} {}\n'.format('is' if len(service['incidents']) == 1 else 'are', len(service['incidents']), 'Incident' if len(service['incidents']) == 1 else 'Incidents')
                else:
                    with aiohttp.ClientSession() as session:
                        async with session.get(self.apiurls['status'] + "/shards/{}".format(region), headers=self.header) as response:
                            jsd = await response.json()
                            await dbp.set("LOL"+region, json.dumps(jsd))
                            await dbp.expire("LOL"+region, 3600)  # Cache clears every hour
                            msg += jsd['name'] + '\n'
                            for service in jsd['services']:
                                msg += ' '*4 + service['name'] + ' "' + service['status'] + '"\n'
                                if len(service['incidents']):
                                    msg += '    '*2 + 'Currently there {} {} {}\n'.format('is' if len(service['incidents']) == 1 else 'are', len(service['incidents']), 'Incident' if len(service['incidents']) == 1 else 'Incidents')
            return msg + "```"

    async def free_rotation(self, message):
        """
        Returns the current free rotation heroes for League of Legends.

        :class message:
        :return:
        """
        async with self.pools.get() as dbp:
            jsd = await dbp.get("LOLFreeRotation")
            jsd = json.loads(jsd)
            msg = "The current free rotation is ->\n"
            for x in jsd:
                msg += '    {} ({})\n'.format(x['name'], x['id'])
            return msg

    async def region_status(self, message):
        """
        Returns status for a specific lol server shard.

        :class message:
        :return:
        """
        if len(message.content.split(" ")) == 1:
            return "Need to provide a region. Most likely na1 (North America), eu (Europe) or eun1 (Nordic and Eastern Europe)."
        else:
            region = message.content.split(" ")[1]
            if region in self.regions:
                async with self.pools.get() as dbp:
                    test = await dbp.exists("LOL" + region)
                    if test:
                        jsd = await dbp.get("LOL"+region)
                        jsd = json.loads(jsd)
                        msg = "```xl\nStatus for {}\n".format(jsd['name'])
                        for service in jsd['services']:
                            msg += ' ' * 4 + service['name'] + ' "' + service['status'] + '"\n'
                            if len(service['incidents']):
                                msg += '    ' * 2 + 'Currently there {} {} {}\n'.format('is' if len(service['incidents']) == 1 else 'are', len(service['incidents']), 'Incident' if len(service['incidents']) == 1 else 'Incidents')
                        return msg + "```"
                    else:
                        with aiohttp.ClientSession() as session:
                            async with session.get(self.apiurls['status'] + "/shards/{}".format(region), headers=self.header) as response:
                                jsd = await response.json()
                                await dbp.set("LOL" + region, json.dumps(jsd))
                                await dbp.expire("LOL" + region, 3600)  # Cache clears every hour
                                msg = "```xl\nStatus for {}\n".format(jsd['name'])
                                for service in jsd['services']:
                                    msg += ' ' * 4 + service['name'] + ' "' + service['status'] + '"\n'
                                    if len(service['incidents']):
                                        msg += '    ' * 2 + 'Currently there {} {} {}\n'.format('is' if len(service['incidents']) == 1 else 'are', len(service['incidents']), 'Incident' if len(service['incidents']) == 1 else 'Incidents')
                                return msg + "```"
            else:
                return "Region must be one of {}".format(",".join(self.regions))

    async def featured_games(self, message):
        """
        Return featured games from the riot api. This easily surpasses the 2k character limit, so returns a list of messages.
        AngelBot loves lists.


        :class message:
        """
        async with self.pools.get() as dbp:
            key = await dbp.get("RiotGames")
            test = await dbp.exists("LOLFeatured")
            data = 0
            if test:
                data = await dbp.get("LOLFeatured")
                data = json.loads(data)
            else:
                with aiohttp.ClientSession() as session:
                    async with session.get(self.apiurls['observer'] + "/rest/featured", params={'api_key': key}, headers=self.header) as response:
                        data = await response.json()
                        await dbp.set("LOLFeatured", json.dumps(data))
                        await dbp.expire("LOLFeatured", 1800)
            msg = []
            for game in data['gameList']:
                tempmsg = ""
                if game['gameMode'] == "TUTORIAL" or game['gameType'] == "TUTORIAL_GAME":
                    continue
                tempmsg += "{} on {} ({}) [{}]\n```xl\n".format(game['gameMode'], self.maps[game['mapId']], game['gameId'], str(timedelta(seconds=game['gameLength'])))
                teams = {}
                for player in game['participants']:
                    if player['bot']:
                        continue
                    if player['teamId'] in teams:
                        teams[player['teamId']].append({'name': player['summonerName'], 'champion': player['championId']})
                    else:
                        teams[player['teamId']] = [{'name': player['summonerName'], 'champion': player['championId']}]
                champs = await dbp.get("LOLCHAMPS")
                champs = json.loads(champs)
                champs = champs['keys']
                for x in ['A', 'B']:
                    tempmsg += "  Team {}\n".format(x)
                    if x == 'A':
                        for y in teams[100]:
                            tempmsg += "    '{}' playing '{}'\n".format(y['name'], champs[str(y['champion'])])
                    else:
                        for y in teams[200]:
                            tempmsg += "    '{}' playing '{}'\n".format(y['name'], champs[str(y['champion'])])
                msg.append(tempmsg + "```")
            return msg

    async def get_summoner_id(self, name):
        async with self.pools.get() as dbp:
            key = await dbp.get("RiotGames")
            test = await dbp.exists(name.lower().replace('%20', ''))
            if test:
                return await dbp.get(name.lower())
            with aiohttp.ClientSession() as session:
                async with session.get(self.apiurls['na'] + "/na/v1.4/summoner/by-name/{}".format(name), params={'api_key': key}, headers=self.header) as response:
                    if response.status == 404:
                        return 0
                    else:
                        jsd = await response.json()
                        await dbp.set(name.lower().replace('%20', ''), jsd[name.lower().replace('%20', '')]['id'])
                        await dbp.set("LOLSUM{}".format(jsd[name.lower().replace('%20', '')]['id']), json.dumps(jsd))
                        return jsd[name.lower().replace('%20', '')]['id']

    @staticmethod
    async def parse_summoner_stat_data(jsondata):
        data = {'Unranked': {'totalNeutralMinionsKilled': 0, 'totalMinionKills': 0, 'totalChampionKills': 0,
                             'totalAssists': 0, 'totalTurretsKilled': 0, 'wins': 0},
                'Ranked': {'totalNeutralMinionsKilled': 0, 'totalMinionKills': 0, 'totalChampionKills': 0,
                           'totalAssists': 0, 'totalTurretsKilled': 0, 'wins': 0}}
        if 'playerStatSummaries' not in jsondata:
            return data
        for x in jsondata['playerStatSummaries']:
            if 'aggregatedStats' in x:
                if x['playerStatSummaryType'] in ["Unranked3x3", "Unranked"]:
                    data['Unranked']['totalNeutralMinionsKilled'] += x['aggregatedStats'].get('totalNeutralMinionsKilled', 0)
                    data['Unranked']['totalMinionKills'] += x['aggregatedStats'].get('totalMinionKills', 0)
                    data['Unranked']['totalChampionKills'] += x['aggregatedStats'].get('totalChampionKills', 0)
                    data['Unranked']['totalAssists'] += x['aggregatedStats'].get('totalAssists', 0)
                    data['Unranked']['totalTurretsKilled'] += x['aggregatedStats'].get('totalTurretsKilled', 0)
                    data['Unranked']['wins'] += x['wins']
                elif x['playerStatSummaryType'] == "RankedSolo5x5":
                    data['Ranked']['totalNeutralMinionsKilled'] += x['aggregatedStats'].get('totalNeutralMinionsKilled', 0)
                    data['Ranked']['totalMinionKills'] += x['aggregatedStats'].get('totalMinionKills', 0)
                    data['Ranked']['totalChampionKills'] += x['aggregatedStats'].get('totalChampionKills', 0)
                    data['Ranked']['totalAssists'] += x['aggregatedStats'].get('totalAssists', 0)
                    data['Ranked']['totalTurretsKilled'] += x['aggregatedStats'].get('totalTurretsKilled', 0)
                    data['Ranked']['wins'] += x['wins']
        return data

    async def summoner_stats(self, message):
        if len(message.content.split(" ")) == 1:
            return "Need a summoner name or ID."
        sid = "%20".join(message.content.split(" ")[1:])
        if not sid.isdigit():
            sid = await self.get_summoner_id(sid)
        if sid == 0 or sid is None:
            return "Couldn't find that summoner."
        async with self.pools.get() as dbp:
            key = await dbp.get("RiotGames")
            test = await dbp.exists("LOLStats{}".format(sid))
            stats = 0
            if test:
                stats = await dbp.get("LOLStats{}".format(sid))
                stats = await self.parse_summoner_stat_data(json.loads(stats))
            else:
                with aiohttp.ClientSession() as session:
                    async with session.get(self.apiurls['na'] + "/na/v1.3/stats/by-summoner/{}/summary".format(sid), params={'api_key': key}, headers=self.header) as response:
                        stats = await response.json()
                        await dbp.set("LOLStats{}".format(sid), json.dumps(stats))
                        await dbp.expire("LOLStats{}".format(sid), 86400)
                        stats = await self.parse_summoner_stat_data(stats)
            msg = "Stat Summary for {}\n".format(" ".join(message.content.split(" ")[1:]))
            msg += "Unranked\n```xl\n  Jungle Minion Kills: {}\n  Minion Kills: {}\n  Champion Kills: {}\n  Assists: {}\n  Towers Destroyed: {}\n  Wins: {}\n```".format(stats['Unranked']['totalNeutralMinionsKilled'],
                                                                                                                                                                     stats['Unranked']['totalMinionKills'],
                                                                                                                                                                     stats['Unranked']['totalChampionKills'],
                                                                                                                                                                     stats['Unranked']['totalAssists'],
                                                                                                                                                                     stats['Unranked']['totalTurretsKilled'],
                                                                                                                                                                     stats['Unranked']['wins'])
            msg += "Ranked\n```xl\n  Jungle Minion Kills: {}\n  Minion Kills: {}\n  Champion Kills: {}\n  Assists: {}\n  Towers Destroyed: {}\n  Wins: {}\n```".format(stats['Ranked']['totalNeutralMinionsKilled'],
                                                                                                                                                                   stats['Ranked']['totalMinionKills'],
                                                                                                                                                                   stats['Ranked']['totalChampionKills'],
                                                                                                                                                                   stats['Ranked']['totalAssists'],
                                                                                                                                                                   stats['Ranked']['totalTurretsKilled'],
                                                                                                                                                                   stats['Ranked']['wins'])
            return msg

    async def match_list(self, message):
        if len(message.content.split(" ")) == 1:
            return "Need a summoner name or ID."
        sid = "%20".join(message.content.split(" ")[1:])
        if not sid.isdigit():
            sid = await self.get_summoner_id(sid)
        if sid == 0:
            return "Couldn't find that summoner."
        async with self.pools.get() as dbp:
            key = await dbp.get("RiotGames")
            test = await dbp.exists("LOLMatches{}".format(sid))
            data = 0
            if test:
                data = await dbp.get("LOLMatches{}".format(sid))
                data = json.loads(data)
            else:
                with aiohttp.ClientSession() as session:
                    async with session.get(self.apiurls['na'] + "/na/v1.3/game/by-summoner/{}/recent".format(sid), params={'api_key': key}, headers=self.header) as response:
                        data = await response.json()
                        await dbp.set("LOLMatches{}".format(sid), json.dumps(data))
                        await dbp.expire("LOLMatches{}".format(sid), 86400)
            msg = "Recent Games\n"
            for x in data['games'][:10]:
                msg += "```xl\n   {} on {} (ID:{}) - {}\n```".format(x['gameMode'], self.maps[x['mapId']], x['gameId'], "Won" if x['stats']['win'] else "Lost")
            return msg