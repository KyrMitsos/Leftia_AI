import requests
import os.path
import csv
import pandas as pd
from requests.structures import CaseInsensitiveDict
import src.betfairAPI.betfairAPI as betfairAPI
import src.ufuncs as lib
import src.collection as collection
from functools import reduce
from tabulate import tabulate
import io
import time
import copy  # for copy.deepcopy
import traceback
from zoneinfo import ZoneInfo

# To append a dict to a csv (i.e. how I will keep stats of trades)
# https://www.geeksforgeeks.org/how-to-append-a-new-row-to-an-existing-csv-file/

# To debug and develop with the Betfair API you need the following links open:
# https://betfair-datascientists.github.io/api/apiPythontutorial/
# https://docs.developer.betfair.com/visualisers/api-ng-sports-operations/
# plus the Betfair website Football events while logged in and pressing F12 to view the XHR calls under 'Network'

# Simple Periodic calling of a function
# https://stackoverflow.com/questions/8600161/executing-periodic-actions-in-python

# Excellent article for multple ways of Periodic calling of a function
# https://medium.com/greedygame-engineering/an-elegant-way-to-run-periodic-tasks-in-python-61b7c477b679
# https://stackoverflow.com/questions/41643538/python-capture-user-input-while-in-loop-executing-other-code  # same as above but differently

# Articles for Text Colouring
# https://ozzmaker.com/add-colour-to-text-in-python/
# https://stackoverflow.com/questions/287871/how-to-print-colored-text-to-the-terminal

# EXAMPLES
# * Convert date to datetime *
# datetime_obj = datetime.datetime(date_obj.year, date_obj.month, date_obj.day)

# * Convert datetime to date *
# date_obj = datetime_obj.today()

# * UTC Time and Time Differences *
# tm = betfairAPI.datetime.datetime.now(betfairAPI.datetime.timezone.utc)
# tm2 = tm + datetime.timedelta(minutes=55)
# tm3 = tm2 + datetime.timedelta(minutes=55)

# * Extract time from string into datetime object*
# datetime_obj = datetime.datetime.strptime(marketCatalogueResult[0]['description']['marketTime'], '%Y-%m-%dT%H:%M:%S.%fZ')


def requestEventTimelines(eventIDs):
    event_time_lines = []
    eventIDs = ','.join(eventIDs)

    url = f"https://ips.betfair.com/inplayservice/v1/eventTimelines?_ak=nzIFcwyWhrlwYMrh&alt=json&eventIds={eventIDs}&locale=en_GB"

    headers = CaseInsensitiveDict()
    headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:84.0) Gecko/20100101 Firefox/84.0"
    headers["Accept"] = "application/json, text/plain, */*"
    headers["Accept-Language"] = "en-GB,en;q=0.5"
    headers["Origin"] = "https://www.betfair.com"
    headers["Connection"] = "keep-alive"
    headers["Referer"] = "https://www.betfair.com/exchange/plus/en/football-betting-1"
    headers["Cookie"] = f"vid=44566593-fb36-431a-819d-25464e6c1233; language=en_GB; betexPtk=betexCurrency%3DGBP%7EbetexTimeZone%3DEurope%2FLondon%7EbetexRegion%3DGBR%7EbetexLocale%3Den; bfsd=ts=1604472729765|st=reg; storageSSC=lsSSC%3D1; uge=y; ccawa=1921334624333875753535718971694858156372; __cfduid=d5d04c86c290e3a865036bb2eece707f61610542779; rfr=3013; PI=3013; pi=partner3013; StickyTags=rfr=3013; TrackingTags=; wsid=07e97951-64ae-11ea-b03a-fa163ed531ae; nlid=25f6169|75bd0f0; loggedIn=true; BVersion=V20.0.25.2; sess=active; geoIpCountryCode=GB; lka=1610710575604; mmapi.store.s.0=%7B%22mmparams.d%22%3A%7B%7D%2C%22mmparams.p%22%3A%7B%7D%7D; betexPtkSess=betexCurrencySessionCookie%3DGBP%7EbetexRegionSessionCookie%3DGBR%7EbetexTimeZoneSessionCookie%3DEurope%2FLondon%7EbetexLocaleSessionCookie%3Den%7EbetexSkin%3Dstandard%7EbetexBrand%3Dbetfair; BETEX_ESD=accountservices; exp=ex; ssoid={betfairAPI.sessionToken}"
    headers["dnt"] = "1"
    headers["TE"] = "Trailers"

    event_time_lines_response = None
    for attempt in range(2):
        try:
            event_time_lines_response = requests.get(url, headers=headers, timeout=10)
            event_time_lines_response.raise_for_status()
            print(f'Success!\nGET Status: {event_time_lines_response.status_code}')
            event_time_lines = lib.json.loads(event_time_lines_response.text)
            break
        except betfairAPI.HTTPError as http_err:
            status = http_err.response.status_code if http_err.response is not None else None
            print(f'HTTP error occurred: {http_err}')
            if status in [401, 403] and attempt == 0:
                newSessionToken = betfairAPI.getNewSessionToken()
                if newSessionToken:
                    betfairAPI._setSessionToken(newSessionToken)
                    headers["Cookie"] = headers["Cookie"].rsplit("ssoid=", 1)[0] + f"ssoid={betfairAPI.sessionToken}"
                    continue
            break
        except Exception as err:
            print(f'Other error occurred: {err}')
            break
    return event_time_lines


def requestPricesFromWebsite(marketIDs):
    exchange_prices = []
    url = f"https://ero.betfair.com/www/sports/exchange/readonly/v1/bymarket?_ak=nzIFcwyWhrlwYMrh&alt=json&currencyCode=GBP&locale=en_GB&marketIds={marketIDs}&rollupLimit=2&rollupModel=STAKE&types=MARKET_STATE,RUNNER_STATE,RUNNER_EXCHANGE_PRICES_BEST"

    headers = CaseInsensitiveDict()
    headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:84.0) Gecko/20100101 Firefox/84.0"
    headers["Accept"] = "application/json, text/plain, */*"
    headers["Accept-Language"] = "en-GB,en;q=0.5"
    headers["Origin"] = "https://www.betfair.com"
    headers["Connection"] = "keep-alive"
    headers["Referer"] = "https://www.betfair.com/exchange/plus/en/football-betting-1"
    headers["Cookie"] = f"vid=44566593-fb36-431a-819d-25464e6c1233; language=en_GB; betexPtk=betexCurrency%3DGBP%7EbetexTimeZone%3DEurope%2FLondon%7EbetexRegion%3DGBR%7EbetexLocale%3Den; bfsd=ts=1604472729765|st=reg; storageSSC=lsSSC%3D1; uge=y; ccawa=1921334624333875753535718971694858156372; __cfduid=d5d04c86c290e3a865036bb2eece707f61610542779; rfr=3013; PI=3013; pi=partner3013; StickyTags=rfr=3013; TrackingTags=; wsid=07e97951-64ae-11ea-b03a-fa163ed531ae; nlid=25f6169|75bd0f0; loggedIn=true; BVersion=V20.0.25.2; sess=active; geoIpCountryCode=GB; lka=1610966756320; mmapi.store.s.0=%7B%22mmparams.d%22%3A%7B%7D%2C%22mmparams.p%22%3A%7B%7D%7D; betexPtkSess=betexCurrencySessionCookie%3DGBP%7EbetexRegionSessionCookie%3DGBR%7EbetexTimeZoneSessionCookie%3DEurope%2FLondon%7EbetexLocaleSessionCookie%3Den%7EbetexSkin%3Dstandard%7EbetexBrand%3Dbetfair; BETEX_ESD=accountservices; exp=ex; ssoid={betfairAPI.sessionToken}"
    headers["dnt"] = "1"
    headers["TE"] = "Trailers"

    exchange_prices_response = None
    try:
        exchange_prices_response = requests.get(url, headers=headers, timeout=10)
        exchange_prices_response.raise_for_status()
        print(f'Success!\nGET Status: {exchange_prices_response.status_code}')
        exchange_prices = lib.json.loads(exchange_prices_response.text)
    except betfairAPI.HTTPError as http_err:
        status = http_err.response.status_code if http_err.response is not None else None
        print(f'HTTP error occurred: {http_err}')
        if status in [401, 403]:
            newSessionToken = betfairAPI.getNewSessionToken()
            if newSessionToken:
                betfairAPI._setSessionToken(newSessionToken)
                try:
                    headers["Cookie"] = headers["Cookie"].rsplit("ssoid=", 1)[0] + f"ssoid={betfairAPI.sessionToken}"
                    exchange_prices_response = requests.get(url, headers=headers, timeout=10)
                    exchange_prices_response.raise_for_status()
                    exchange_prices = lib.json.loads(exchange_prices_response.text)
                except Exception as err:
                    print(f'Other error occurred: {err}')
    except Exception as err:
        print(f'Other error occurred: {err}')
    return exchange_prices


def saveDictArrayToCSV(filename, dictArray, mode='w'):
    result = False
    try:
        file_exists = os.path.isfile(filename)

        if (dictArray is not None):
            keys = list(dictArray[0].keys())

            # Open your CSV file in append mode
            # Create a file object for this file
            with io.open(filename, mode, encoding="utf-8") as f_object:
                # Pass the file object and a list
                # of column names to DictWriter()
                # You will get a object of DictWriter
                dictwriter_object = csv.DictWriter(f_object, fieldnames=keys, lineterminator='\r')

                # Write the Header first
                if not file_exists:
                    dictwriter_object.writeheader()

                for dict in dictArray:
                    # Pass the dictionary as an argument to the Writerow()
                    dictwriter_object.writerow(dict)

                result = True
    except Exception as err:
        print("error " + str(err))

    return result




def getCleanExchangePricesfromWebsite(marketIDs):
    batches = [marketIDs[i:i + 40] for i in range(0, len(marketIDs), 40)]
    marketBookFromWebsite = []

    # Website prices are kept as returned. Missing sides are repaired only when a snapshot is selected.
    for batch_index, batch in enumerate(batches):
        if batch_index > 0:
            time.sleep(0.2)
        marketIDs_string = ','.join(batch)
        raw_marketBookFromWebsite = requestPricesFromWebsite(marketIDs_string)
        try:
            marketBookFromWebsite.extend(raw_marketBookFromWebsite['eventTypes'][0]['eventNodes'])
        except Exception as err:
            print(err)

    return marketBookFromWebsite


def applyModel__DT1(data):
    choice = ""
    output = data['output']
    details = data['updateDetails']  # for extracting RED CARDS (fav and unfav)
    redCards = list(filter(lambda x: x['type'] == 'RedCard', details))
    homeReds = list(filter(lambda x: x['team'] == 'home', redCards))
    awayReds = list(filter(lambda x: x['team'] == 'away', redCards))

    if (output['HT_Home'] > output['HT_Away']):
        choice = "1" if not homeReds else "NO"
    elif (output['HT_Home'] < output['HT_Away']):
        choice = "2" if not awayReds else "NO"
    else:
        if (output['KO_1'] >= 2.1) and (output['KO_2'] < 1.9):
            choice = "2/X" if not awayReds else "NO"
        else:
            choice = "1/X" if not homeReds else "NO"
    return choice


def applyModel__ZZCX(data):
    choice = ""
    output = data['output']
    validScores = ['0', '1']  # scores for ties, i.e. 0-0 and 1-1

    if ((output['HT_Home'] in validScores) and output['HT_Home'] == output['HT_Away']):
        choice = "X"
    else:
        choice = "NO"
    return choice




def getFINAL(data):
    if (data['FT_Home'] > data['FT_Away']):
        choice = "1"
    elif (data['FT_Home'] < data['FT_Away']):
        choice = "2"
    else:
        choice = "X"
    return choice


def getMULTI(data, model):
    if (data[model] == "NO"):
        return 1.0
    else:
        if data['FINAL'] in data[model]:
            key = f"HT_{data[model]}"
            return data[key]
        else:
            return 0.0


# def getSTATUS(data, model):
#     if data['FINAL'] in data[model]:
#         return "WIN"
#     elif data[model] == "NO":
#         return "NO"
#     else:
#         return "LOSS"


def getPL(data, multi):
    return data['STAKE'] * (data[multi] - 1)




def reportTimeLines(eventTimeLines, all=False):
    if (eventTimeLines):
        eventTimeLines_Teams = '\n'.join([str(entry['eventId'])
                                         + ' [' + str(entry['elapsedRegularTime']) + ('\' +' + str(entry['elapsedAddedTime']) if 'elapsedAddedTime' in entry else '') + '\']'
                                         + ' ' + str(entry['score']['home']['name']) + ' - ' + str(entry['score']['away']['name'])
                                         + ' (' + str(entry['score']['home']['score']) + '-' + str(entry['score']['away']['score']) + ') '
                                         + '<' + str(entry['inPlayMatchStatus']) + '>'
                                         for entry in eventTimeLines])
        matchTypes_string = "All In-Play <ScoresAndEvents>" if all else str(eventTimeLines[0]['inPlayMatchStatus'])
        print(f"\n{matchTypes_string} Matches ({len(eventTimeLines)} - unordered):\n{eventTimeLines_Teams}\n")


def reportMarketCatalogue(marketCatalogue, returnedScoreAndEvents=[], all=False):
    if (marketCatalogue):
        marketCatalogue_Teams = '\n'.join([(lib.bcolors.FAIL if int(entry['event']['id']) not in returnedScoreAndEvents else '')
                                          + str(entry['event']['id'] + ' ')
                                          + str(entry['marketId'] + ' ')
                                          + str(entry['event']['name'])
                                          + (lib.bcolors.ENDC if int(entry['event']['id']) not in returnedScoreAndEvents else '')
                                          for entry in marketCatalogue if ('id' in entry['event'] and 'name' in entry['event'] and 'marketId' in entry)])
        matchTypes_string = "All In-Play <MarketCatalogue>"
        print(f"\n{matchTypes_string} Matches ({len(marketCatalogue)} - ordered):\n{marketCatalogue_Teams}\n")




def getPL_API(today):
    settledOrders = betfairAPI.getClearedOrders(1, today)
    pl = 0
    if (settledOrders):
        pl = reduce(lambda a, b: a + b['profit'], settledOrders['clearedOrders'], 0) if settledOrders['clearedOrders'] else 0
    return pl






config = lib.readFromJSON("config.json")
if config is None:
    print(f'Could not load configuration file config.json')
    exit()

# Session token is maintained by src.betfairAPI.betfairAPI

filename = ""
timeDeltaHours = 4
todays_threshold = betfairAPI.datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + betfairAPI.datetime.timedelta(hours=(24 + timeDeltaHours))
DA_TEAMS = []
saved_TEAMS = []
DA_TEAMS_Changed = []  # keep track of when DA_TEAMS actually changed to warranty writing its dump to disk (avoid constant WRITE to disks)
outputTemplate = lib.render(["", "", "", "",    # "Date", "Competition", "Home", "Away"
                             "", "", "", "",    # "HT_Home", "HT_Away", "FT_Home", "FT_Away"
                             0.0, 0.0, 0.0,     # "KO_1", "KO_2", "KO_X"
                             0.0, 0.0, 0.0,     # "HT_1", "HT_2", "HT_X"
                             0.0, 0.0, 0.0,     # "HT_1/X", "HT_2/X", "HT_1/2"
                             0.0, "",           # "STAKE", "FINAL"
                             "", 0.0, 0.0,    # "MODEL_DT1", "MULTI_DT1", "P/L_DT1"
                             "", 0.0, 0.0,    # "MODEL_ZZCX", "MULTI_ZZCX", "P/L_ZZCX"
                             ])
firstExecution = True


# Manual setting of Soccer ID
# ------------------------------
soccerEventTypeID = '1'  # '1' Corresponds to Soccer


# *** EXAMPLES ***
# 1)
# now = betfairAPI.datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')

# 2)
# # Store Exchange Prices from Website
# for index, entry in enumerate(marketBookFromWebsite['eventTypes'], start=0):
#     teams_found = list(filter(lambda d: d['marketId'] in entry['eventNodes'][0]['marketNodes'][0]['marketId'], DA_TEAMS))  # find matching match according to marketId
#     if (len(teams_found) > 0):
#         team = teams_found[0]  # if something was found, it should be the first entry so store it in team
#         for index2, multipliers in enumerate(entry['eventNodes'][0]['marketNodes'][0]['runners'], start=0):
#             team['runners'][index2]['exchange'] = multipliers['exchange']


# 1. Get today's date
# today = betfairAPI.datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)  # get today's date but at 00:00:00
# today_string = today.strftime('%Y%m%d')

# 2. If a .csv of the same day exists, then it means we are restarting from an abrupt stop of the script, in which case:

# a) construct the filename
# filename = f"{today_string}_results.csv"
# # b) if the filename exists in the same folder then, read it in the DA_TEAMS dict
# if os.path.isfile(filename):
#     with open(filename, mode='r') as infile:
#         dict_reader = csv.DictReader(infile)
#         ordered_dict_from_csv = list(dict_reader)[0]
#         DA_TEAMS = dict(ordered_dict_from_csv)

# # HERE ONWARDS THE MAIN LOOP
# if ((end + betfairAPI.datetime.timedelta(minutes=95) < today)):  # if we are passed 45 minutes into the next day, refresh all data
#     end = (today + betfairAPI.datetime.timedelta(1))  # .strftime('%Y-%m-%dT%H:%M:%SZ')
#     filename = f"{today.strftime('%Y%m%d')}_results.csv"
#    df = pd.json_normalize(DA_TEAMS)
#    df.to_csv(filename)

# IDEAL -----------------------------------------------------
# L1 is this:
# filteredMarketCatalogueByETId = betfairAPI.getMarketCatalogueByEventTypeId(soccerEventTypeID)   # gets marketbook of matches according to eventId sorted by time
# L2 is this:
# <extract all eventIDs from above>
# L3 - Get MarketID
# eventTimeLines = requestEventTimelines(_eventIDs)
# eventTimeLines_Teams = '\n'.join([str(entry['eventId']) + ' ' + str(entry['score']['home']['name']) + ' - ' + str(entry['score']['away']['name']) for entry in eventTimeLines])
# print(f"\nIn-Play Matches ({len(eventTimeLines)}):\n{eventTimeLines_Teams}\n")
# # Possible selections:
# # inPlayMatchStatus: ["KickOff", "FirstHalfEnd", "SecondHalfKickOff", "Finished"]
# eventSelected = ["SecondHalfKickOff"]
# HTEvents = list(filter(lambda d: d['inPlayMatchStatus'] in eventSelected, eventTimeLines))  # in ["FirstHalfEnd"]
# L4 - Get RunnerID
# filteredMarketIDs = '","'.join([str(entry['eventId']) for entry in HTEvents])

# # marketBookFromWebsite = requestPricesFromExchange(str(filteredMarketCatalogueIDs_List[0]))
# marketBookFromWebsite = requestPricesFromWebsite(filteredMarketCatalogue[0]['marketId'])
# L5 - Place Order
# -----------------------------------------------------


NORMAL_DELAY = 30
FOCUSED_DELAY = 15
KO_FOCUS_BEFORE_MINUTES = 5
KO_KEEP_AFTER_SCHEDULE_MINUTES = 20
HT_FOCUS_AFTER_FIRST_HALF_MINUTES = 10
HT_CAPTURE_GRACE_MINUTES = 5
RECOVERY_RETRIES = 5
RECOVERY_WAIT = 0.5
FOCUSED_MINUTE_WINDOWS = []  # e.g. [(50, 2, 2), (55, 2, 2)]

PRICE_HISTORY = {}
FIRST_HALF_END_TIMES = {}
SECOND_HALF_START_TIMES = {}
NEAR_START_CATALOGUE = {}
CURRENT_INPLAY_CATALOGUE = {}
LATEST_TIMELINES = {}
RESTORED_FROM_DUMP = False
LOG_CODES = {}
KO_MISSING = set()


def loadLogCodes():
    codes = {}
    try:
        with open('log_codes.csv', mode='r', encoding='utf-8') as infile:
            for row in csv.DictReader(infile):
                codes[row['key']] = row['code']
    except Exception as err:
        print(f"Could not load log_codes.csv: {err}")
    return codes


def parseBetfairTimestamp(value):
    if not value:
        return None
    for fmt in ['%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ']:
        try:
            result = betfairAPI.datetime.datetime.strptime(value, fmt)
            return result.replace(tzinfo=betfairAPI.datetime.timezone.utc).timestamp()
        except Exception:
            pass
    return None


def currentUKDay():
    return betfairAPI.datetime.datetime.now(ZoneInfo('Europe/London')).strftime('%Y%m%d')


def orderedCatalogueRunners(entry):
    runners = entry.get('runners', [])
    event_name = entry.get('event', {}).get('name', '')
    if ' v ' in event_name:
        home_name, away_name = event_name.split(' v ', 1)
        home = next((runner for runner in runners if runner.get('runnerName') == home_name), None)
        away = next((runner for runner in runners if runner.get('runnerName') == away_name), None)
        draw = next((runner for runner in runners if 'draw' in runner.get('runnerName', '').lower()), None)
        if home and away and draw:
            return [home, away, draw]
    return sorted(runners, key=lambda runner: runner.get('sortPriority', 999))[:3]


def selectionIDs(entry):
    return [runner.get('selectionId') for runner in orderedCatalogueRunners(entry)]


def getHomeAway(entry):
    runners = orderedCatalogueRunners(entry)
    home = runners[0].get('runnerName', '') if len(runners) > 0 else ''
    away = runners[1].get('runnerName', '') if len(runners) > 1 else ''
    return home, away


def getEventID(entry):
    return collection.normalise_id(entry.get('event', {}).get('id', entry.get('eventId', '')))


def getMarketID(entry):
    return collection.normalise_id(entry.get('marketId', ''))


def findTeamByEvent(event_id):
    return next((team for team in DA_TEAMS if collection.same_id(team.get('event', {}).get('id'), event_id)), None)




def findCatalogueByEvent(event_id):
    event_id = collection.normalise_id(event_id)
    return CURRENT_INPLAY_CATALOGUE.get(event_id) or NEAR_START_CATALOGUE.get(event_id)


def initialiseTeam(entry, event_details=None):
    team = copy.deepcopy(entry)
    home, away = getHomeAway(team)
    team['score'] = event_details.get('score', '') if event_details else ''
    team['updateDetails'] = event_details.get('updateDetails', '') if event_details else ''
    team['output'] = outputTemplate.copy()
    team['output']['Date'] = team.get('event', {}).get('openDate', '')
    team['output']['Competition'] = team.get('competition', {}).get('name', 'N/A')
    team['output']['Home'] = home
    team['output']['Away'] = away
    DA_TEAMS.append(team)
    return team


def logIssue(entry, key, point='', detail=''):
    global LOG_CODES
    if not LOG_CODES:
        LOG_CODES = loadLogCodes()

    if 'output' in entry:
        timestamp = entry['output'].get('Date', '')
        home = entry['output'].get('Home', '')
        away = entry['output'].get('Away', '')
    else:
        timestamp = entry.get('event', {}).get('openDate', '')
        home, away = getHomeAway(entry)

    date_epoch = parseBetfairTimestamp(timestamp)
    if date_epoch is not None:
        date = betfairAPI.datetime.datetime.fromtimestamp(date_epoch, betfairAPI.datetime.timezone.utc).strftime('%Y%m%d')
    else:
        date = betfairAPI.datetime.datetime.now().strftime('%Y%m%d')

    filename = f"{date}_log.txt"
    file_exists = os.path.isfile(filename)
    code = LOG_CODES.get(key, key)
    with open(filename, mode='a', encoding='utf-8', newline='') as outfile:
        writer = csv.writer(outfile, lineterminator='\n')
        if not file_exists:
            writer.writerow(['Timestamp', 'Home', 'Away', 'Code', 'Point', 'Details'])
        writer.writerow([timestamp, home, away, code, point, detail])
    print(f"{timestamp},{home},{away},{code},{point},{detail}")


def transitionTime(event_details, event_type):
    for detail in event_details.get('updateDetails', []):
        if detail.get('updateType') == event_type or detail.get('type') == event_type:
            epoch = parseBetfairTimestamp(detail.get('updateTime'))
            if epoch is not None and epoch > 86400:
                return epoch
    return None


def hasTransition(event_details, event_type):
    if event_details.get('inPlayMatchStatus') == event_type:
        return True
    return any(detail.get('updateType') == event_type or detail.get('type') == event_type
               for detail in event_details.get('updateDetails', []))


def rememberTimelineStates(timelines):
    global RESTORED_FROM_DUMP
    now_epoch = time.time()
    for event in timelines:
        event_id = collection.normalise_id(event.get('eventId'))
        LATEST_TIMELINES[event_id] = event
        status = event.get('inPlayMatchStatus', '')

        if hasTransition(event, 'FirstHalfEnd') and event_id not in FIRST_HALF_END_TIMES:
            event_time = transitionTime(event, 'FirstHalfEnd')
            if event_time is None and RESTORED_FROM_DUMP:
                event_time = now_epoch - (HT_FOCUS_AFTER_FIRST_HALF_MINUTES * 60)
            FIRST_HALF_END_TIMES[event_id] = event_time if event_time is not None else now_epoch

        team = findTeamByEvent(event_id)
        if team is not None:
            team['score'] = event.get('score', team.get('score', ''))
            team['updateDetails'] = event.get('updateDetails', team.get('updateDetails', ''))

    RESTORED_FROM_DUMP = False


def addPriceHistory(entry, snapshot):
    if snapshot is None:
        return
    market_id = getMarketID(entry)
    record = copy.deepcopy(snapshot)
    record['time'] = time.time()
    PRICE_HISTORY.setdefault(market_id, []).append(record)
    PRICE_HISTORY[market_id] = PRICE_HISTORY[market_id][-30:]


def extractSnapshot(entry, marketbook):
    event_id = getEventID(entry)
    event_node = next((item for item in marketbook if collection.same_id(item.get('eventId'), event_id)), None)
    if event_node is None:
        return None
    return collection.market_snapshot(event_node, entry.get('marketId'), selectionIDs(entry))


def updateTeamExchange(team, snapshot):
    if snapshot is None:
        return
    ids = selectionIDs(team)
    exchanges = snapshot.get('exchanges', [])
    for selection_id, exchange in zip(ids, exchanges):
        runner = next((item for item in team.get('runners', []) if collection.same_id(item.get('selectionId'), selection_id)), None)
        if runner is not None and exchange:
            runner['exchange'] = copy.deepcopy(exchange)


def pollEntries(entries, aggressive=False, point='', allow_history_fallback=True):
    entries_by_market = {}
    for entry in entries:
        market_id = getMarketID(entry)
        if market_id:
            entries_by_market[market_id] = entry

    if not entries_by_market:
        return {}

    history_before = {market_id: list(PRICE_HISTORY.get(market_id, [])) for market_id in entries_by_market}
    candidates = {market_id: [] for market_id in entries_by_market}
    marketbook = getCleanExchangePricesfromWebsite(list(entries_by_market.keys()))

    for market_id, entry in entries_by_market.items():
        snapshot = extractSnapshot(entry, marketbook)
        if snapshot is not None:
            candidates[market_id].append(snapshot)
            addPriceHistory(entry, snapshot)

    bad = [market_id for market_id, values in candidates.items() if not values or not collection.snapshot_is_strong(values[-1], history_before[market_id])]
    initial_bad = set(bad)

    source_problem = len(entries_by_market) >= 10 and len(bad) / len(entries_by_market) >= 0.50
    if source_problem:
        print(f"Website source problem: {len(bad)}/{len(entries_by_market)} focused markets returned bad data")
    if aggressive and bad and not source_problem:
        for _ in range(RECOVERY_RETRIES):
            if not bad:
                break
            time.sleep(RECOVERY_WAIT)
            retry_entries = [entries_by_market[market_id] for market_id in bad]
            retry_book = getCleanExchangePricesfromWebsite(bad)
            still_bad = []
            for entry in retry_entries:
                market_id = getMarketID(entry)
                snapshot = extractSnapshot(entry, retry_book)
                if snapshot is not None:
                    candidates[market_id].append(snapshot)
                    addPriceHistory(entry, snapshot)
                if snapshot is None or not collection.snapshot_is_strong(snapshot, history_before[market_id]):
                    still_bad.append(market_id)
            bad = still_bad

    results = {}
    for market_id, entry in entries_by_market.items():
        values = candidates[market_id]
        chosen = collection.choose_complete_snapshot(values, history_before[market_id])
        method = 'OBS'

        if chosen is None:
            mixed = collection.mix_candidates(values, history_before[market_id])
            if mixed is not None:
                last_good = collection.latest_consistent(history_before[market_id])
                target = collection.expected_book(history_before[market_id])
                near_edge = mixed['book'] < 0.90 or mixed['book'] > 1.35 or abs(mixed['book'] - target) > 0.25
                if near_edge:
                    repaired = collection.repair_suspect_back(mixed['back'], values, history_before[market_id])
                    if repaired is not None:
                        chosen = repaired
                        method = 'INF'
                    elif allow_history_fallback and last_good is not None:
                        chosen = last_good
                        method = 'LAST'
                    else:
                        chosen = mixed
                        method = 'MIX'
                else:
                    chosen = mixed
                    method = 'MIX'

        if chosen is None:
            repaired = []
            for snapshot in reversed(values):
                fixed = collection.repair_missing_back(snapshot, history_before[market_id])
                if fixed is not None:
                    fixed['raw_snapshot'] = snapshot
                    repaired.append(fixed)
            if repaired:
                target = collection.expected_book(history_before[market_id])
                chosen = min(repaired, key=lambda item: abs(item['book'] - target))
                method = 'INF'

        if chosen is None and allow_history_fallback:
            last_good = collection.latest_consistent(history_before[market_id])
            if last_good is not None:
                chosen = last_good
                method = 'LAST'

        if chosen is None:
            results[market_id] = {'back': [0.0, 0.0, 0.0], 'book': None, 'method': 'MISS', 'raw': values[-1] if values else None}
            if not source_problem and (aggressive or market_id in initial_bad):
                logIssue(entry, 'missing_price', point, '')
            continue

        raw = chosen.get('raw_snapshot') if isinstance(chosen, dict) else None
        if raw is None and values:
            raw = min(values, key=lambda item: abs((item.get('book') or 99) - (chosen.get('book') or collection.BOOK_TARGET)))

        results[market_id] = {'back': list(chosen['back']), 'book': chosen.get('book'), 'method': method, 'raw': raw}
        if not source_problem and market_id in initial_bad:
            if method == 'OBS':
                logIssue(entry, 'retry_recovered', point, f"{chosen.get('book', 0):.3f}")
            elif method == 'MIX':
                logIssue(entry, 'mixed_recovery', point, f"{chosen.get('book', 0):.3f}")
            elif method == 'INF':
                logIssue(entry, 'inferred_price', point, f"{chosen.get('book', 0):.3f}")
            elif method == 'LAST':
                logIssue(entry, 'last_good', point, f"{chosen.get('book', 0):.3f}")

    return results


def saveRunDump(entry_hint=None):
    global DA_TEAMS_Changed
    if entry_hint is None and not DA_TEAMS:
        return
    lib.saveToJSON(DA_TEAMS, f"{currentUKDay()}_run_dump.json")
    DA_TEAMS_Changed = [copy.deepcopy(d) for d in DA_TEAMS]


def freezeKO(team, result):
    prices = result['back']
    team['output']['KO_1'] = prices[0]
    team['output']['KO_2'] = prices[1]
    team['output']['KO_X'] = prices[2]
    updateTeamExchange(team, result.get('raw'))
    print(f"KO: {team['output']['Home']} - {team['output']['Away']} {prices}")
    saveRunDump(team)


def freezeHT(team, result, event_details):
    prices = result['back']
    team['output']['HT_1'] = prices[0]
    team['output']['HT_2'] = prices[1]
    team['output']['HT_X'] = prices[2]
    team['score'] = event_details.get('score', team.get('score', ''))

    home_score = team.get('score', {}).get('home', {})
    away_score = team.get('score', {}).get('away', {})
    team['output']['HT_Home'] = home_score.get('halfTimeScore') or home_score.get('score', '-1')
    team['output']['HT_Away'] = away_score.get('halfTimeScore') or away_score.get('score', '-1')
    team['output']['HT_1/X'] = lib.doubleChance(team['output']['HT_1'], team['output']['HT_X']) if team['output']['HT_1'] and team['output']['HT_X'] else 0.0
    team['output']['HT_2/X'] = lib.doubleChance(team['output']['HT_2'], team['output']['HT_X']) if team['output']['HT_2'] and team['output']['HT_X'] else 0.0
    team['output']['HT_1/2'] = lib.doubleChance(team['output']['HT_1'], team['output']['HT_2']) if team['output']['HT_1'] and team['output']['HT_2'] else 0.0
    team['output']['MODEL_DT1'] = applyModel__DT1(team)
    team['output']['MODEL_ZZCX'] = applyModel__ZZCX(team)
    team['output']['STAKE'] = config['Bet_Size']
    updateTeamExchange(team, result.get('raw'))
    print(f"HT: {team['output']['Home']} - {team['output']['Away']} {prices}")
    saveRunDump(team)


def koIsFilled(team):
    return getMarketID(team) in KO_MISSING or any(team['output'].get(key, 0) for key in ['KO_1', 'KO_2', 'KO_X'])


def htIsFilled(team):
    return team['output'].get('HT_Home', '') != ''


def processKOEvents(timelines):
    for event in timelines:
        if event.get('inPlayMatchStatus') != 'KickOff':
            continue

        event_id = collection.normalise_id(event.get('eventId'))
        team = findTeamByEvent(event_id)
        entry = findCatalogueByEvent(event_id)
        if team is None and entry is not None:
            team = initialiseTeam(entry, event)
        if team is None or koIsFilled(team):
            continue

        history = PRICE_HISTORY.get(getMarketID(team), [])
        chosen = collection.latest_consistent(history)
        if chosen is None:
            KO_MISSING.add(getMarketID(team))
            logIssue(team, 'late_start', 'KO', '')
            continue

        result = {'back': chosen['back'], 'book': chosen.get('book'), 'method': 'LAST', 'raw': chosen}
        freezeKO(team, result)


def processSecondHalfStarts(timelines):
    attempted = set()
    for event in timelines:
        if not hasTransition(event, 'SecondHalfKickOff'):
            continue

        event_id = collection.normalise_id(event.get('eventId'))
        team = findTeamByEvent(event_id)
        if team is None or htIsFilled(team):
            continue

        first_detection = event_id not in SECOND_HALF_START_TIMES
        if first_detection:
            SECOND_HALF_START_TIMES[event_id] = transitionTime(event, 'SecondHalfKickOff') or time.time()
            market_id = getMarketID(team)
            attempted.add(market_id)
            result = pollEntries([team], aggressive=True, point='HT', allow_history_fallback=False).get(market_id)
            if result is not None and any(result['back']):
                freezeHT(team, result, event)
    return attempted


def preKOFocusEntries():
    now_epoch = time.time()
    entries = []
    for entry in NEAR_START_CATALOGUE.values():
        market_time = parseBetfairTimestamp(entry.get('description', {}).get('marketTime') or entry.get('event', {}).get('openDate'))
        if market_time is None:
            continue
        if market_time - (KO_FOCUS_BEFORE_MINUTES * 60) <= now_epoch <= market_time + (KO_KEEP_AFTER_SCHEDULE_MINUTES * 60):
            team = findTeamByEvent(getEventID(entry))
            if team is None or not koIsFilled(team):
                entries.append(entry)
    return entries


def htFocusEntries():
    now_epoch = time.time()
    entries = []
    for team in DA_TEAMS:
        if htIsFilled(team):
            continue
        event_id = getEventID(team)
        first_half_end = FIRST_HALF_END_TIMES.get(event_id)
        if first_half_end is None or now_epoch < first_half_end + (HT_FOCUS_AFTER_FIRST_HALF_MINUTES * 60):
            continue
        second_half_start = SECOND_HALF_START_TIMES.get(event_id)
        if second_half_start is not None and now_epoch > second_half_start + (HT_CAPTURE_GRACE_MINUTES * 60):
            continue
        entries.append(team)
    return entries


def minuteFocusEntries():
    entries = []
    for team in DA_TEAMS:
        event = LATEST_TIMELINES.get(getEventID(team), {})
        minute = event.get('elapsedRegularTime')
        if minute is None:
            continue
        for target, before, after in FOCUSED_MINUTE_WINDOWS:
            if target - before <= minute <= target + after:
                entries.append(team)
                break
    return entries


def focusEntries():
    entries = preKOFocusEntries() + htFocusEntries() + minuteFocusEntries()
    result = {}
    for entry in entries:
        result[getMarketID(entry)] = entry
    return list(result.values())


def pendingHTMarketIDs():
    return {getMarketID(team) for team in DA_TEAMS
            if not htIsFilled(team) and getEventID(team) in SECOND_HALF_START_TIMES}


def applyPendingHT(timelines, results):
    by_event = {collection.normalise_id(event.get('eventId')): event for event in timelines}
    now_epoch = time.time()
    for team in DA_TEAMS:
        if htIsFilled(team):
            continue
        event_id = getEventID(team)
        start = SECOND_HALF_START_TIMES.get(event_id)
        if start is None:
            continue

        event = by_event.get(event_id) or LATEST_TIMELINES.get(event_id, {})
        result = results.get(getMarketID(team))
        if result is not None and any(result['back']):
            freezeHT(team, result, event)
            continue

        if now_epoch > start + (HT_CAPTURE_GRACE_MINUTES * 60):
            post_start = [item for item in PRICE_HISTORY.get(getMarketID(team), []) if item.get('time', 0) >= start]
            last_good = collection.latest_consistent(post_start)
            if last_good is not None:
                fallback = {'back': last_good['back'], 'book': last_good.get('book'), 'method': 'LAST', 'raw': last_good}
                freezeHT(team, fallback, event)
                logIssue(team, 'last_good', 'HT', f"{last_good.get('book', 0):.3f}")
            else:
                freezeHT(team, {'back': [0.0, 0.0, 0.0], 'book': None, 'method': 'MISS', 'raw': None}, event)
                logIssue(team, 'missing_price', 'HT', '')


def finaliseTeam(team, event):
    team['score'] = event.get('score', team.get('score', ''))
    team['updateDetails'] = event.get('updateDetails', team.get('updateDetails', ''))
    score = team.get('score', {})
    team['output']['HT_Home'] = score.get('home', {}).get('halfTimeScore', team['output'].get('HT_Home', ''))
    team['output']['HT_Away'] = score.get('away', {}).get('halfTimeScore', team['output'].get('HT_Away', ''))
    team['output']['FT_Home'] = score.get('home', {}).get('fullTimeScore') or score.get('home', {}).get('score', '')
    team['output']['FT_Away'] = score.get('away', {}).get('fullTimeScore') or score.get('away', {}).get('score', '')
    team['output']['STAKE'] = config['Bet_Size']
    team['output']['FINAL'] = getFINAL(team['output'])
    team['output']['MULTI_DT1'] = getMULTI(team['output'], 'MODEL_DT1')
    team['output']['MULTI_ZZCX'] = getMULTI(team['output'], 'MODEL_ZZCX')
    team['output']['P/L_DT1'] = getPL(team['output'], 'MULTI_DT1')
    team['output']['P/L_ZZCX'] = getPL(team['output'], 'MULTI_ZZCX')

    date_epoch = parseBetfairTimestamp(team['output']['Date'])
    date = betfairAPI.datetime.datetime.fromtimestamp(date_epoch, betfairAPI.datetime.timezone.utc) if date_epoch is not None else betfairAPI.datetime.datetime.now()
    filename = f"{date.strftime('%Y%m%d')}_results.csv"
    if saveDictArrayToCSV(filename, [team['output']], 'a'):
        saved_TEAMS.append(copy.deepcopy(team))
        if team in DA_TEAMS:
            DA_TEAMS.remove(team)
        saveRunDump(team)


def processFinished(timelines):
    saved_market_ids = {getMarketID(team) for team in saved_TEAMS}
    for event in timelines:
        if event.get('inPlayMatchStatus') != 'Finished':
            continue

        event_id = collection.normalise_id(event.get('eventId'))
        team = findTeamByEvent(event_id)
        if team is None:
            entry = findCatalogueByEvent(event_id)
            if entry is None or getMarketID(entry) in saved_market_ids:
                continue
            team = initialiseTeam(entry, event)
        finaliseTeam(team, event)


def refreshCatalogueCaches(current_catalogue, near_start_catalogue):
    CURRENT_INPLAY_CATALOGUE.clear()
    for entry in current_catalogue:
        CURRENT_INPLAY_CATALOGUE[getEventID(entry)] = entry
    for entry in near_start_catalogue:
        NEAR_START_CATALOGUE[getEventID(entry)] = entry

    cutoff = time.time() - (KO_KEEP_AFTER_SCHEDULE_MINUTES * 60 * 2)
    expired = []
    for event_id, entry in NEAR_START_CATALOGUE.items():
        market_time = parseBetfairTimestamp(entry.get('description', {}).get('marketTime') or entry.get('event', {}).get('openDate'))
        if market_time is not None and market_time < cutoff:
            expired.append(event_id)
    for event_id in expired:
        NEAR_START_CATALOGUE.pop(event_id, None)


def focusedCycle():
    entries = focusEntries()
    if not entries:
        return

    print(f"Focused capture: {len(entries)} market(s)")
    event_ids = list({getEventID(entry) for entry in entries if getEventID(entry)})
    timelines = requestEventTimelines(event_ids) if event_ids else []
    rememberTimelineStates(timelines)
    processKOEvents(timelines)
    attempted = processSecondHalfStarts(timelines)

    entries = [entry for entry in focusEntries() if getMarketID(entry) not in attempted]
    pending_ht = pendingHTMarketIDs()
    ht_entries = [entry for entry in entries if getMarketID(entry) in pending_ht]
    other_entries = [entry for entry in entries if getMarketID(entry) not in pending_ht]

    results = pollEntries(other_entries, aggressive=True, point='WIN') if other_entries else {}
    if ht_entries:
        results.update(pollEntries(ht_entries, aggressive=True, point='HT', allow_history_fallback=False))
    applyPendingHT(timelines, results)
    if DA_TEAMS:
        saveRunDump()


def main():
    global todays_threshold, DA_TEAMS, saved_TEAMS, DA_TEAMS_Changed, filename, outputTemplate, firstExecution, timeDeltaHours, RESTORED_FROM_DUMP

    now = betfairAPI.datetime.datetime.today()

    if (firstExecution):
        firstExecution = False
        dumpFilename = f"{currentUKDay()}_run_dump.json"
        if (os.path.isfile(dumpFilename)):
            restored = lib.readFromJSON(dumpFilename)
            if restored is not None:
                DA_TEAMS = restored
                RESTORED_FROM_DUMP = True
    else:
        if(DA_TEAMS != DA_TEAMS_Changed):
            saveRunDump()

    teamsToDump = [team for team in DA_TEAMS if lib.expiredMatch(team, now, timeDeltaHours)]
    if teamsToDump:
        listOfOutputs = list(map(lambda item: item['output'], teamsToDump))
        df = pd.json_normalize(listOfOutputs)
        print(tabulate(df, headers='keys', tablefmt='psql'))

    if (todays_threshold < now):
        yesterday = now - betfairAPI.datetime.timedelta(days=1)
        filename = f"{yesterday.strftime('%Y%m%d')}_dump"
        df = pd.json_normalize(teamsToDump)
        df.to_csv(filename + ".csv")
        lib.saveToJSON(teamsToDump, filename + ".json")

        thePL = getPL_API(yesterday)
        print(f"{yesterday.strftime('%d/%m/%Y')} PL is {thePL}")

        todays_threshold = betfairAPI.datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + betfairAPI.datetime.timedelta(hours=(24 + timeDeltaHours))
        DA_TEAMS = [x for x in DA_TEAMS if x not in teamsToDump]
        saved_TEAMS = []

    current_catalogue = betfairAPI.getMarketCatalogueByEventTypeId(soccerEventTypeID) or []
    near_start_catalogue = betfairAPI.getMarketCatalogueNearStartByEventTypeId(soccerEventTypeID, minutes_before=KO_KEEP_AFTER_SCHEDULE_MINUTES, minutes_after=KO_FOCUS_BEFORE_MINUTES) or []
    refreshCatalogueCaches(current_catalogue, near_start_catalogue)

    inplay_event_ids = list({getEventID(entry) for entry in current_catalogue if getEventID(entry)})
    timelines = requestEventTimelines(inplay_event_ids) if inplay_event_ids else []

    returned_timeline_ids = [collection.normalise_id(item.get('eventId')) for item in timelines]
    missing_timeline = len([item for item in inplay_event_ids if item not in returned_timeline_ids])
    reportMarketCatalogue(current_catalogue, [int(item) for item in returned_timeline_ids if item.isdigit()])
    if timelines:
        reportTimeLines(timelines, all=True)
    print(f"MarketCatalogue: {len(current_catalogue)} | NearKO: {len(near_start_catalogue)} | Timelines: {len(timelines)} | Missing: {missing_timeline}")

    rememberTimelineStates(timelines)
    processKOEvents(timelines)
    attempted = processSecondHalfStarts(timelines)

    entries = [entry for entry in focusEntries() if getMarketID(entry) not in attempted]
    pending_ht = pendingHTMarketIDs()
    ht_entries = [entry for entry in entries if getMarketID(entry) in pending_ht]
    other_entries = [entry for entry in entries if getMarketID(entry) not in pending_ht]

    results = pollEntries(other_entries, aggressive=True, point='WIN') if other_entries else {}
    if ht_entries:
        results.update(pollEntries(ht_entries, aggressive=True, point='HT', allow_history_fallback=False))
    applyPendingHT(timelines, results)
    processFinished(timelines)
    if DA_TEAMS:
        saveRunDump()

    print(betfairAPI.datetime.datetime.now())


delay = NORMAL_DELAY
while True:
    try:
        main()
        if focusEntries():
            time.sleep(FOCUSED_DELAY)
            focusedCycle()
            time.sleep(max(NORMAL_DELAY - FOCUSED_DELAY, 0))
        else:
            time.sleep(NORMAL_DELAY)
    except KeyboardInterrupt:
        if DA_TEAMS:
            saveRunDump()
        break
    except Exception as e:
        print(f"An error occurred: {e}")
        traceback.print_exc()
        try:
            if DA_TEAMS:
                saveRunDump()
        except Exception as dump_err:
            print(f"Dump error: {dump_err}")
        time.sleep(NORMAL_DELAY)

