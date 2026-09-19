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


def _requestEventTimelinesRaw(eventIDs):
    event_time_lines = None
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


def _requestPricesFromWebsiteRaw(marketIDs):
    exchange_prices = None
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


ENDPOINT_BACKOFF_SECONDS = 5
ENDPOINT_BACKOFF_UNTIL = {'timeline': 0.0, 'price': 0.0}
ENDPOINT_LAST_ERROR = {'timeline': None, 'price': None}


def endpointBackoffActive(endpoint):
    return time.time() < ENDPOINT_BACKOFF_UNTIL.get(endpoint, 0.0)


def _endpointFailed(endpoint, reason='request_failed'):
    ENDPOINT_LAST_ERROR[endpoint] = reason
    ENDPOINT_BACKOFF_UNTIL[endpoint] = time.time() + ENDPOINT_BACKOFF_SECONDS


def _endpointRecovered(endpoint):
    ENDPOINT_LAST_ERROR[endpoint] = None
    ENDPOINT_BACKOFF_UNTIL[endpoint] = 0.0


def requestEventTimelines(eventIDs, force=False):
    if endpointBackoffActive('timeline') and not force:
        ENDPOINT_LAST_ERROR['timeline'] = 'backoff'
        return []
    result = _requestEventTimelinesRaw(eventIDs)
    if result is None:
        _endpointFailed('timeline')
        return []
    _endpointRecovered('timeline')
    return result if isinstance(result, list) else []


def requestPricesFromWebsite(marketIDs, force=False):
    if endpointBackoffActive('price') and not force:
        ENDPOINT_LAST_ERROR['price'] = 'backoff'
        return {}
    result = _requestPricesFromWebsiteRaw(marketIDs)
    if result is None:
        _endpointFailed('price')
        return {}
    _endpointRecovered('price')
    return result if isinstance(result, dict) else {}


TWO_DECIMAL_OUTPUT_COLUMNS = {
    'HT_1/X', 'HT_2/X', 'HT_1/2',
    'MULTI_DT1', 'P/L_DT1', 'MULTI_ZZCX', 'P/L_ZZCX'
}


def roundOutputDecimals(output):
    for key in TWO_DECIMAL_OUTPUT_COLUMNS:
        value = output.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            output[key] = round(value, 2)
    return output


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
                    dictwriter_object.writerow(roundOutputDecimals(dict.copy()))

                result = True
    except Exception as err:
        print("error " + str(err))

    return result




def getCleanExchangePricesfromWebsite(marketIDs, force=False):
    batches = [marketIDs[i:i + 40] for i in range(0, len(marketIDs), 40)]
    marketBookFromWebsite = []

    # Website prices are kept as returned. Missing sides are repaired only when a snapshot is selected.
    for batch_index, batch in enumerate(batches):
        if batch_index > 0:
            time.sleep(0.2)
        marketIDs_string = ','.join(batch)
        raw_marketBookFromWebsite = requestPricesFromWebsite(marketIDs_string, force=force)
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
outputTemplate = lib.render(["", "", "", "",    # "Date", "Competition", "Home", "Away"
                             "", "", "", "",    # "HT_Home", "HT_Away", "FT_Home", "FT_Away"
                             0.0, 0.0, 0.0,     # "KO_1", "KO_2", "KO_X"
                             0.0, 0.0, 0.0,     # "HT_1", "HT_2", "HT_X"
                             0.0, 0.0, 0.0,     # "HT_1/X", "HT_2/X", "HT_1/2"
                             0.0, "",           # "STAKE", "FINAL"
                             "", 0.0, 0.0,    # "MODEL_DT1", "MULTI_DT1", "P/L_DT1"
                             "", 0.0, 0.0,    # "MODEL_ZZCX", "MULTI_ZZCX", "P/L_ZZCX"
                             ])


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
KO_BACKUP_MAX_AGE_SECONDS = 180
KO_KEEP_AFTER_SCHEDULE_MINUTES = 20
KO_POST_BOUNDARY_SECONDS = 8
KO_BOUNDARY_RECONCILE_SECONDS = 30
KO_LIVE_DISCOVERY_MAX_AFTER_SCHEDULE_SECONDS = 120
KO_LIVE_ELAPSED_MAX_MINUTES = 3
FORENSIC_MAX_SNAPSHOTS = 8
HT_FOCUS_AFTER_FIRST_HALF_MINUTES = 0
HT_MARKET_REOPEN_MINUTES = 12
HT_BOUNDARY_CAPTURE_SECONDS = 3
HT_REPLENISH_POLL_SECONDS = 5
HT_REPLENISH_WINDOW_SECONDS = 20
RECOVERY_RETRIES = 1
RECOVERY_WAIT = 0.5
TIMELINE_BATCH_SIZE = 50
TIMELINE_RETRY_BATCH_SIZE = 10
HT_SIGNAL_FRESH_SECONDS = 20
HT_SIGNAL_MINUTE_MIN = 45
HT_SIGNAL_MINUTE_MAX = 48
FOCUSED_MINUTE_WINDOWS = []  # e.g. [(50, 2, 2), (55, 2, 2)]

PRICE_HISTORY = {}
CLEAN_PRICE_HISTORY = {}
CAPTURE_EVIDENCE = {}
FIRST_HALF_START_TIMES = {}
FIRST_HALF_START_SOURCE = {}
FIRST_HALF_END_TIMES = {}
FIRST_HALF_END_SCORES = {}
SECOND_HALF_START_TIMES = {}
SECOND_HALF_START_SOURCE = {}
HT_REPLENISH_LAST_ATTEMPT = {}
NEAR_START_CATALOGUE = {}
CURRENT_INPLAY_CATALOGUE = {}
LATEST_TIMELINES = {}
KO_MISSING = set()
KO_CAPTURE_STATE = {}
CATALOGUE_MISSING = set()
TIMELINE_MISSING = set()
LAST_CATALOGUE_SEEN = {}
LAST_TIMELINE_SEEN = {}
HT_CLEAN_SEEN = set()
HT_UNAVAILABLE_COUNTS = {}
HT_LAST_UNAVAILABLE_TIMES = {}
FINALIZED_MARKETS = set()
RESULT_KEYS = {}
LOG_CODES = {}
STATE_DIRTY = False


def markStateDirty():
    global STATE_DIRTY
    STATE_DIRTY = True


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


def currentUKDay(offset_days=0):
    now = betfairAPI.datetime.datetime.now(ZoneInfo('Europe/London')) + betfairAPI.datetime.timedelta(days=offset_days)
    return now.strftime('%Y%m%d')


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


def isMatchOddsEntry(entry):
    if not isinstance(entry, dict):
        return False
    market_type = str(entry.get('description', {}).get('marketType', '')).upper()
    market_name = str(entry.get('marketName', '')).strip().lower()
    return market_type == 'MATCH_ODDS' or market_name == 'match odds'


def scheduledStart(entry):
    if not isinstance(entry, dict):
        return None
    return parseBetfairTimestamp(entry.get('description', {}).get('marketTime') or entry.get('event', {}).get('openDate'))


def eventElapsedMinutes(event):
    values = []
    if not isinstance(event, dict):
        return None
    try:
        value = event.get('elapsedRegularTime')
        if value not in [None, '']:
            values.append(float(value))
    except Exception:
        pass
    for detail in event.get('updateDetails', []) or []:
        try:
            value = detail.get('elapsedRegularTime')
            if value in [None, '']:
                value = detail.get('matchTime')
            if value not in [None, '']:
                values.append(float(value))
        except Exception:
            pass
    return max(values) if values else None


def snapshotIsKosher(snapshot, history=None):
    if snapshot is None or not collection.book_is_plausible(snapshot.get('back', [])):
        return False
    history = history or []
    if not collection.recent_clean(history):
        return True
    return collection.snapshot_is_strong(snapshot, history)


def collectorStamp():
    return betfairAPI.datetime.datetime.now(betfairAPI.datetime.timezone.utc).isoformat(timespec='seconds')


def resultFilenameForEntry(entry):
    when = scheduledStart(entry)
    if when is None:
        return None
    date = betfairAPI.datetime.datetime.fromtimestamp(when, betfairAPI.datetime.timezone.utc).strftime('%Y%m%d')
    return f"{date}_results.csv"


def entryAlreadyFinalized(entry):
    if not isinstance(entry, dict):
        return False
    market_id = getMarketID(entry)
    if market_id and market_id in FINALIZED_MARKETS:
        return True
    filename = resultFilenameForEntry(entry)
    if filename is None:
        return False
    home, away = getHomeAway(entry)
    key = (entry.get('event', {}).get('openDate', ''), home, away)
    return key in resultKeys(filename)


def ensureKOState(team, start, source, phase='RECOVERY'):
    if team is None or start is None:
        return
    event_id = getEventID(team)
    market_id = getMarketID(team)
    if event_id not in FIRST_HALF_START_TIMES:
        FIRST_HALF_START_TIMES[event_id] = start
        FIRST_HALF_START_SOURCE[event_id] = source
    state = KO_CAPTURE_STATE.get(market_id, {})
    if state.get('phase') not in ['FROZEN', 'MISSING']:
        actual_start = FIRST_HALF_START_TIMES.get(event_id, start)
        state.update({
            'event_id': event_id,
            'start': actual_start,
            'source': FIRST_HALF_START_SOURCE.get(event_id, source),
            'phase': phase,
            'deadline': actual_start + KO_BOUNDARY_RECONCILE_SECONDS,
            'observed_at': time.time()
        })
        KO_CAPTURE_STATE[market_id] = state
    markStateDirty()


def observedKickoffTime(event, now_epoch=None):
    now_epoch = now_epoch or time.time()
    exact = transitionTime(event, 'KickOff')
    if exact is not None:
        return exact, 'explicit_time'
    elapsed = eventElapsedMinutes(event)
    if hasTransition(event, 'KickOff') and elapsed is not None and 0 <= elapsed <= KO_LIVE_ELAPSED_MAX_MINUTES:
        return now_epoch - (elapsed * 60), 'explicit_observed'
    status = event.get('inPlayMatchStatus', '') if isinstance(event, dict) else ''
    if status == 'KickOff' and (elapsed is None or elapsed <= KO_LIVE_ELAPSED_MAX_MINUTES):
        return now_epoch - ((elapsed or 0) * 60), 'status_observed'
    return None, None

def findTeamByEvent(event_id):
    return next((team for team in DA_TEAMS if collection.same_id(team.get('event', {}).get('id'), event_id)), None)


def findCatalogueByEvent(event_id):
    event_id = collection.normalise_id(event_id)
    return CURRENT_INPLAY_CATALOGUE.get(event_id) or NEAR_START_CATALOGUE.get(event_id)


def initialiseTeam(entry, event_details=None):
    existing = findTeamByEvent(getEventID(entry))
    if existing is not None:
        return existing
    if entryAlreadyFinalized(entry):
        return None
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
    markStateDirty()
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
        date = currentUKDay()

    filename = f"{date}_log.txt"
    file_exists = os.path.isfile(filename)
    code = LOG_CODES.get(key, key)
    with open(filename, mode='a', encoding='utf-8', newline='') as outfile:
        writer = csv.writer(outfile, lineterminator='\n')
        if not file_exists:
            writer.writerow(['Timestamp', 'Home', 'Away', 'Code', 'Point', 'Details'])
        writer.writerow([timestamp, home, away, code, point, detail])
    print(f"{timestamp},{home},{away},{code},{point},{detail}")


def transitionDetail(event_details, event_type):
    for detail in event_details.get('updateDetails', []):
        if detail.get('updateType') == event_type or detail.get('type') == event_type:
            return detail
    return None


def transitionTime(event_details, event_type):
    detail = transitionDetail(event_details, event_type)
    if detail is None:
        return None
    epoch = parseBetfairTimestamp(detail.get('updateTime'))
    if epoch is not None and epoch > 86400:
        return epoch
    return None


def hasTransition(event_details, event_type):
    if event_details.get('inPlayMatchStatus') == event_type:
        return True
    return transitionDetail(event_details, event_type) is not None


def _scoreValue(value):
    if value is None or value == '':
        return None
    try:
        return int(value)
    except Exception:
        return None


def explicitHalfTimeScore(event):
    score = event.get('score', {}) if isinstance(event, dict) else {}
    home = _scoreValue(score.get('home', {}).get('halfTimeScore'))
    away = _scoreValue(score.get('away', {}).get('halfTimeScore'))
    if home is not None and away is not None:
        return [home, away]
    return None


def reconstructHalfTimeScore(event):
    home = 0
    away = 0
    boundary_seen = False
    for detail in event.get('updateDetails', []):
        event_type = detail.get('updateType') or detail.get('type')
        if event_type in ['FirstHalfEnd', 'SecondHalfKickOff']:
            boundary_seen = True
            break
        try:
            elapsed = float(detail.get('elapsedRegularTime') or 0)
        except Exception:
            elapsed = 0
        if elapsed >= 46:
            boundary_seen = True
            break
        if event_type != 'Goal':
            continue
        team = detail.get('team')
        if team == 'home':
            home += 1
        elif team == 'away':
            away += 1
    return [home, away] if boundary_seen else None


def currentScore(event):
    score = event.get('score', {}) if isinstance(event, dict) else {}
    home = _scoreValue(score.get('home', {}).get('score'))
    away = _scoreValue(score.get('away', {}).get('score'))
    if home is not None and away is not None:
        return [home, away]
    return None


def firstHalfScore(event_id, event):
    explicit = explicitHalfTimeScore(event)
    if explicit is not None:
        return explicit
    saved = FIRST_HALF_END_SCORES.get(event_id)
    if saved is not None:
        return list(saved)
    reconstructed = reconstructHalfTimeScore(event)
    if reconstructed is not None:
        return reconstructed
    return None


def estimatedLegacyTransitionTime(team, event_type):
    event = {
        'eventId': getEventID(team),
        'score': team.get('score', {}),
        'updateDetails': team.get('updateDetails', [])
    }
    exact = transitionTime(event, event_type)
    if exact is not None:
        return exact

    open_time = parseBetfairTimestamp(team.get('event', {}).get('openDate'))
    kickoff = transitionTime(event, 'KickOff') or open_time
    detail = transitionDetail(event, event_type)
    if kickoff is None or detail is None:
        return None

    if event_type == 'SecondHalfKickOff':
        first_end = estimatedLegacyTransitionTime(team, 'FirstHalfEnd')
        if first_end is not None:
            return first_end + (15 * 60)
        return kickoff + (60 * 60)

    match_time = detail.get('matchTime') or detail.get('elapsedRegularTime')
    try:
        return kickoff + (float(match_time) * 60)
    except Exception:
        return None


def restoreLegacyOperationalState():
    for team in DA_TEAMS:
        event_id = getEventID(team)
        market_id = getMarketID(team)
        event = {
            'eventId': event_id,
            'score': team.get('score', {}),
            'updateDetails': team.get('updateDetails', [])
        }
        LATEST_TIMELINES[event_id] = event

        kickoff = estimatedLegacyTransitionTime(team, 'KickOff')
        if kickoff is not None:
            FIRST_HALF_START_TIMES[event_id] = kickoff
            FIRST_HALF_START_SOURCE[event_id] = 'legacy_restore'

        if hasTransition(event, 'FirstHalfEnd'):
            FIRST_HALF_END_TIMES[event_id] = estimatedLegacyTransitionTime(team, 'FirstHalfEnd') or time.time()
            score = explicitHalfTimeScore(event) or reconstructHalfTimeScore(event)
            if score is not None:
                FIRST_HALF_END_SCORES[event_id] = score

        if hasTransition(event, 'SecondHalfKickOff'):
            second_start = estimatedLegacyTransitionTime(team, 'SecondHalfKickOff') or time.time()
            SECOND_HALF_START_TIMES[event_id] = second_start
            SECOND_HALF_START_SOURCE[event_id] = 'legacy_restore'
            if event_id not in FIRST_HALF_END_TIMES:
                FIRST_HALF_END_TIMES[event_id] = second_start - (15 * 60)
            score = explicitHalfTimeScore(event) or reconstructHalfTimeScore(event)
            if score is not None:
                FIRST_HALF_END_SCORES[event_id] = score

        if not any(team.get('output', {}).get(key, 0) for key in ['KO_1', 'KO_2', 'KO_X']) and kickoff is not None:
            if time.time() <= kickoff + KO_BOUNDARY_RECONCILE_SECONDS:
                ensureKOState(team, kickoff, FIRST_HALF_START_SOURCE.get(event_id, 'legacy_restore'))
            else:
                KO_MISSING.add(market_id)
                KO_CAPTURE_STATE[market_id] = {'event_id': event_id, 'start': kickoff,
                                               'source': FIRST_HALF_START_SOURCE.get(event_id, 'legacy_restore'),
                                               'phase': 'MISSING'}


def compactHistorySnapshot(snapshot):
    return {
        'event_id': snapshot.get('event_id', ''),
        'market_id': snapshot.get('market_id', ''),
        'back': list(snapshot.get('back', [])),
        'lay': list(snapshot.get('lay', [])),
        'book': snapshot.get('book'),
        'inplay': snapshot.get('inplay'),
        'status': snapshot.get('status'),
        'time': snapshot.get('time', time.time())
    }


def addPriceHistory(entry, snapshot):
    if snapshot is None:
        return
    market_id = getMarketID(entry)
    record = compactHistorySnapshot(snapshot)
    PRICE_HISTORY.setdefault(market_id, []).append(record)
    PRICE_HISTORY[market_id] = PRICE_HISTORY[market_id][-30:]
    markStateDirty()


def referencePriceHistory(market_id):
    clean = CLEAN_PRICE_HISTORY.get(market_id, [])
    return list(clean) if clean else list(PRICE_HISTORY.get(market_id, []))


def addCleanPriceHistory(entry, snapshot, reference=None):
    if snapshot is None:
        return
    market_id = getMarketID(entry)
    reference = list(reference if reference is not None else CLEAN_PRICE_HISTORY.get(market_id, []))
    if not snapshotIsKosher(snapshot, reference):
        return
    record = compactHistorySnapshot(snapshot)
    CLEAN_PRICE_HISTORY.setdefault(market_id, []).append(record)
    CLEAN_PRICE_HISTORY[market_id] = CLEAN_PRICE_HISTORY[market_id][-12:]
    markStateDirty()


def rememberCaptureEvidence(team, point, result=None):
    market_id = getMarketID(team)
    event_id = getEventID(team)
    history = list(PRICE_HISTORY.get(market_id, []))

    if point == 'KO':
        start = FIRST_HALF_START_TIMES.get(event_id)
        if start is not None:
            history = [item for item in history
                       if start - KO_BACKUP_MAX_AGE_SECONDS <= item.get('time', 0) <= start + KO_BOUNDARY_RECONCILE_SECONDS]
    elif point == 'HT':
        start = SECOND_HALF_START_TIMES.get(event_id)
        if start is not None:
            lower = FIRST_HALF_END_TIMES.get(event_id, start - (HT_FOCUS_AFTER_FIRST_HALF_MINUTES * 60))
            lower += HT_FOCUS_AFTER_FIRST_HALF_MINUTES * 60 if event_id in FIRST_HALF_END_TIMES else 0
            history = [item for item in history
                       if lower <= item.get('time', 0) <= start + HT_REPLENISH_WINDOW_SECONDS]

    if len(history) > FORENSIC_MAX_SNAPSHOTS:
        left = FORENSIC_MAX_SNAPSHOTS // 2
        right = FORENSIC_MAX_SNAPSHOTS - left
        history = history[:left] + history[-right:]

    selected = (result or {}).get('selected') or (result or {}).get('raw')
    evidence = {
        'method': (result or {}).get('method', 'MISS'),
        'selected': compactHistorySnapshot(selected) if selected else None,
        'history': copy.deepcopy(history)
    }
    inferred = (result or {}).get('inferred') or []
    if inferred:
        evidence['inferred'] = copy.deepcopy(inferred)
    CAPTURE_EVIDENCE.setdefault(market_id, {})[point] = evidence
    markStateDirty()

def extractSnapshot(entry, marketbook):
    event_id = getEventID(entry)
    event_node = next((item for item in marketbook if collection.same_id(item.get('eventId'), event_id)), None)
    if event_node is None:
        return None
    snapshot = collection.market_snapshot(event_node, entry.get('marketId'), selectionIDs(entry))
    if snapshot is not None:
        snapshot['time'] = time.time()
    return snapshot


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

    history_before = {market_id: referencePriceHistory(market_id) for market_id in entries_by_market}
    candidates = {market_id: [] for market_id in entries_by_market}
    marketbook = getCleanExchangePricesfromWebsite(list(entries_by_market.keys()))

    for market_id, entry in entries_by_market.items():
        snapshot = extractSnapshot(entry, marketbook)
        if snapshot is not None:
            candidates[market_id].append(snapshot)
            addPriceHistory(entry, snapshot)
            addCleanPriceHistory(entry, snapshot, history_before[market_id])

    bad = [market_id for market_id, values in candidates.items() if not values or not snapshotIsKosher(values[-1], history_before[market_id])]
    initial_bad = set(bad)

    source_problem = len(entries_by_market) >= 2 and len(bad) / len(entries_by_market) >= 0.75
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
                    addCleanPriceHistory(entry, snapshot, history_before[market_id])
                if snapshot is None or not snapshotIsKosher(snapshot, history_before[market_id]):
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
                if isMatchOddsEntry(entry):
                    fixed = collection.repair_match_odds_boundary(snapshot, history_before[market_id])
                else:
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

        current_raw = values[-1] if values else None
        if chosen is None:
            results[market_id] = {
                'back': [0.0, 0.0, 0.0],
                'lay': list(current_raw.get('lay', [None, None, None])) if current_raw else [None, None, None],
                'book': None, 'method': 'MISS',
                'raw': current_raw, 'selected': current_raw, 'inferred': [],
                'current_raw': current_raw, 'source_problem': source_problem
            }
            if not source_problem and (aggressive or market_id in initial_bad):
                logIssue(entry, 'missing_price', point, '')
            continue

        raw = chosen.get('raw_snapshot') if isinstance(chosen, dict) else None
        if raw is None and values:
            raw = min(values, key=lambda item: abs((item.get('book') or 99) - (chosen.get('book') or collection.BOOK_TARGET)))

        inferred = list(chosen.get('inferred', [])) if isinstance(chosen, dict) else []
        selected = copy.deepcopy(raw) if raw is not None else None
        result_back = list(chosen['back'])
        result_lay = list(raw.get('lay', [None, None, None])) if raw is not None else [None, None, None]

        if selected is not None:
            selected['back'] = list(result_back)
            selected['book'] = chosen.get('book')
            if isMatchOddsEntry(entry) and method != 'LAST':
                boundary = collection.repair_match_odds_boundary(selected, history_before[market_id])
                if boundary is not None:
                    result_back = list(boundary['back'])
                    result_lay = list(boundary['lay'])
                    selected['back'] = list(result_back)
                    selected['lay'] = list(result_lay)
                    selected['book'] = boundary.get('book')
                    for item in boundary.get('inferred', []):
                        if item not in inferred:
                            inferred.append(item)
                    if boundary.get('inferred'):
                        method = 'INF'

        results[market_id] = {
            'back': result_back, 'lay': result_lay,
            'book': selected.get('book') if selected is not None else chosen.get('book'), 'method': method,
            'raw': raw, 'selected': selected, 'inferred': inferred,
            'current_raw': current_raw, 'source_problem': source_problem
        }
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


def _checkpointState():
    return {
        'version': 6,
        'saved_at': betfairAPI.datetime.datetime.now(betfairAPI.datetime.timezone.utc).isoformat(),
        'DA_TEAMS': DA_TEAMS,
        'PRICE_HISTORY': PRICE_HISTORY,
        'CLEAN_PRICE_HISTORY': CLEAN_PRICE_HISTORY,
        'CAPTURE_EVIDENCE': CAPTURE_EVIDENCE,
        'FIRST_HALF_START_TIMES': FIRST_HALF_START_TIMES,
        'FIRST_HALF_START_SOURCE': FIRST_HALF_START_SOURCE,
        'FIRST_HALF_END_TIMES': FIRST_HALF_END_TIMES,
        'FIRST_HALF_END_SCORES': FIRST_HALF_END_SCORES,
        'SECOND_HALF_START_TIMES': SECOND_HALF_START_TIMES,
        'SECOND_HALF_START_SOURCE': SECOND_HALF_START_SOURCE,
        'HT_REPLENISH_LAST_ATTEMPT': HT_REPLENISH_LAST_ATTEMPT,
        'NEAR_START_CATALOGUE': NEAR_START_CATALOGUE,
        'CURRENT_INPLAY_CATALOGUE': CURRENT_INPLAY_CATALOGUE,
        'LATEST_TIMELINES': LATEST_TIMELINES,
        'KO_MISSING': sorted(KO_MISSING),
        'KO_CAPTURE_STATE': KO_CAPTURE_STATE,
        'CATALOGUE_MISSING': sorted(CATALOGUE_MISSING),
        'TIMELINE_MISSING': sorted(TIMELINE_MISSING),
        'LAST_CATALOGUE_SEEN': LAST_CATALOGUE_SEEN,
        'LAST_TIMELINE_SEEN': LAST_TIMELINE_SEEN,
        'HT_CLEAN_SEEN': sorted(HT_CLEAN_SEEN),
        'HT_UNAVAILABLE_COUNTS': HT_UNAVAILABLE_COUNTS,
        'HT_LAST_UNAVAILABLE_TIMES': HT_LAST_UNAVAILABLE_TIMES,
        'FINALIZED_MARKETS': sorted(FINALIZED_MARKETS)
    }


def saveCheckpoint(force=False):
    global STATE_DIRTY
    if not force and not STATE_DIRTY:
        return
    filename = f"{currentUKDay()}_checkpoint.json"
    lib.saveToJSONWithBackup(_checkpointState(), filename)
    STATE_DIRTY = False


def saveRunDump():
    if DA_TEAMS:
        lib.saveToJSON(DA_TEAMS, f"{currentUKDay()}_run_dump.json")


def persistState(force=False):
    saveRunDump()
    saveCheckpoint(force=force)


def _restoreDict(target, data):
    target.clear()
    if isinstance(data, dict):
        target.update(data)


def restoreCheckpoint(data):
    global DA_TEAMS
    DA_TEAMS = data.get('DA_TEAMS', []) if isinstance(data.get('DA_TEAMS', []), list) else []
    _restoreDict(PRICE_HISTORY, data.get('PRICE_HISTORY', {}))
    _restoreDict(CLEAN_PRICE_HISTORY, data.get('CLEAN_PRICE_HISTORY', {}))
    if not CLEAN_PRICE_HISTORY:
        for market_id, history in PRICE_HISTORY.items():
            clean = collection.recent_clean(history)
            if clean:
                CLEAN_PRICE_HISTORY[market_id] = clean[-12:]
    _restoreDict(CAPTURE_EVIDENCE, data.get('CAPTURE_EVIDENCE', {}))
    _restoreDict(FIRST_HALF_START_TIMES, data.get('FIRST_HALF_START_TIMES', {}))
    _restoreDict(FIRST_HALF_START_SOURCE, data.get('FIRST_HALF_START_SOURCE', {}))
    _restoreDict(FIRST_HALF_END_TIMES, data.get('FIRST_HALF_END_TIMES', {}))
    _restoreDict(FIRST_HALF_END_SCORES, data.get('FIRST_HALF_END_SCORES', {}))
    _restoreDict(SECOND_HALF_START_TIMES, data.get('SECOND_HALF_START_TIMES', {}))
    _restoreDict(SECOND_HALF_START_SOURCE, data.get('SECOND_HALF_START_SOURCE', {}))
    _restoreDict(HT_REPLENISH_LAST_ATTEMPT, data.get('HT_REPLENISH_LAST_ATTEMPT', {}))
    _restoreDict(NEAR_START_CATALOGUE, data.get('NEAR_START_CATALOGUE', {}))
    _restoreDict(CURRENT_INPLAY_CATALOGUE, data.get('CURRENT_INPLAY_CATALOGUE', {}))
    _restoreDict(LATEST_TIMELINES, data.get('LATEST_TIMELINES', {}))
    _restoreDict(LAST_CATALOGUE_SEEN, data.get('LAST_CATALOGUE_SEEN', {}))
    _restoreDict(LAST_TIMELINE_SEEN, data.get('LAST_TIMELINE_SEEN', {}))
    _restoreDict(HT_UNAVAILABLE_COUNTS, data.get('HT_UNAVAILABLE_COUNTS', {}))
    _restoreDict(HT_LAST_UNAVAILABLE_TIMES, data.get('HT_LAST_UNAVAILABLE_TIMES', {}))
    _restoreDict(KO_CAPTURE_STATE, data.get('KO_CAPTURE_STATE', {}))

    KO_MISSING.clear(); KO_MISSING.update(data.get('KO_MISSING', []))
    CATALOGUE_MISSING.clear(); CATALOGUE_MISSING.update(data.get('CATALOGUE_MISSING', []))
    TIMELINE_MISSING.clear(); TIMELINE_MISSING.update(data.get('TIMELINE_MISSING', []))
    HT_CLEAN_SEEN.clear(); HT_CLEAN_SEEN.update(data.get('HT_CLEAN_SEEN', []))
    FINALIZED_MARKETS.clear(); FINALIZED_MARKETS.update(data.get('FINALIZED_MARKETS', []))


def _stateCandidates(suffix):
    names = []
    for day in [currentUKDay(), currentUKDay(-1)]:
        for ending in [suffix, suffix + '.bak']:
            filename = f"{day}_{ending}"
            if os.path.isfile(filename):
                names.append(filename)
    return sorted(names, key=lambda item: os.path.getmtime(item), reverse=True)


def repairRestoredKOState():
    now_epoch = time.time()
    for team in DA_TEAMS:
        market_id = getMarketID(team)
        event_id = getEventID(team)
        if any(team.get('output', {}).get(key, 0) for key in ['KO_1', 'KO_2', 'KO_X']):
            KO_CAPTURE_STATE.setdefault(market_id, {}).update({'event_id': event_id, 'phase': 'FROZEN'})
            KO_MISSING.discard(market_id)
            continue

        start = FIRST_HALF_START_TIMES.get(event_id)
        source = FIRST_HALF_START_SOURCE.get(event_id, 'restored')

        # A restart may happen after the boundary-reconciliation period. If the
        # checkpoint already contains a valid pre-in-play KO snapshot, freeze it
        # immediately rather than losing it simply because wall-clock time moved on.
        if start is not None:
            boundary_result, _ = selectKOBoundary(team, start, now_epoch)
            if boundary_result is not None:
                freezeKO(team, boundary_result)
                continue

        event = LATEST_TIMELINES.get(event_id, {})
        elapsed = eventElapsedMinutes(event)
        safe_to_reopen = start is not None and now_epoch <= start + KO_BOUNDARY_RECONCILE_SECONDS
        if source in {'timeline_fallback', 'catalogue_inplay'} and (elapsed is None or elapsed > KO_LIVE_ELAPSED_MAX_MINUTES):
            safe_to_reopen = False

        if market_id in KO_MISSING and safe_to_reopen:
            KO_MISSING.discard(market_id)
        if market_id in KO_MISSING:
            KO_CAPTURE_STATE.setdefault(market_id, {}).update({
                'event_id': event_id, 'start': start, 'source': source, 'phase': 'MISSING'
            })
        elif start is not None:
            ensureKOState(team, start, source)


LEGACY_UNRELIABLE_HT_SOURCES = {
    'explicit_observed_estimated',
    'fallback_elapsed',
    'fallback_elapsed_no_fhe',
    'fallback_elapsed_observed',
    'fallback_elapsed_observed_no_fhe'
}


def repairRestoredHTState():
    for team in DA_TEAMS:
        if htIsFilled(team):
            continue
        event_id = getEventID(team)
        source = SECOND_HALF_START_SOURCE.get(event_id)
        if source in LEGACY_UNRELIABLE_HT_SOURCES:
            SECOND_HALF_START_TIMES.pop(event_id, None)
            SECOND_HALF_START_SOURCE.pop(event_id, None)
            markStateDirty()


def restoreState():
    global DA_TEAMS
    for filename in _stateCandidates('checkpoint.json'):
        data = lib.readFromJSON(filename)
        if isinstance(data, dict) and isinstance(data.get('DA_TEAMS'), list):
            restoreCheckpoint(data)
            repairRestoredKOState()
            repairRestoredHTState()
            print(f"RESTORE: {len(DA_TEAMS)} tracked match(es) from {filename}")
            return

    for filename in _stateCandidates('run_dump.json'):
        data = lib.readFromJSON(filename)
        if isinstance(data, list):
            DA_TEAMS = data
            restoreLegacyOperationalState()
            repairRestoredKOState()
            repairRestoredHTState()
            markStateDirty()
            print(f"RESTORE: {len(DA_TEAMS)} tracked match(es) from legacy {filename}")
            return


def _resultKey(output):
    return (output.get('Date', ''), output.get('Home', ''), output.get('Away', ''))


def resultKeys(filename):
    if filename in RESULT_KEYS:
        return RESULT_KEYS[filename]
    keys = set()
    if os.path.isfile(filename):
        try:
            with open(filename, mode='r', encoding='utf-8') as infile:
                for row in csv.DictReader(infile):
                    keys.add(_resultKey(row))
        except Exception as err:
            print(f"Could not read {filename}: {err}")
    RESULT_KEYS[filename] = keys
    return keys


def requestTrackedTimelines(event_ids):
    event_ids = list(dict.fromkeys(collection.normalise_id(item) for item in event_ids if item))
    by_event = {}
    for index in range(0, len(event_ids), TIMELINE_BATCH_SIZE):
        batch = event_ids[index:index + TIMELINE_BATCH_SIZE]
        if index > 0:
            time.sleep(0.1)
        result = requestEventTimelines(batch)
        if isinstance(result, list):
            for item in result:
                event_id = collection.normalise_id(item.get('eventId'))
                if event_id:
                    by_event[event_id] = item

        returned = {event_id for event_id in by_event if event_id in batch}
        missing = [event_id for event_id in batch if event_id not in returned]
        # A successful but partial timeline response is not evidence that the
        # missing events had no transition. Retry only those IDs once in smaller batches.
        if missing and ENDPOINT_LAST_ERROR.get('timeline') is None:
            for retry_index in range(0, len(missing), TIMELINE_RETRY_BATCH_SIZE):
                retry_batch = missing[retry_index:retry_index + TIMELINE_RETRY_BATCH_SIZE]
                retry = requestEventTimelines(retry_batch, force=True)
                if isinstance(retry, list):
                    for item in retry:
                        event_id = collection.normalise_id(item.get('eventId'))
                        if event_id:
                            by_event[event_id] = item
    return [by_event[event_id] for event_id in event_ids if event_id in by_event]


def watchedEventIDs(current_catalogue=None, near_start_catalogue=None):
    event_ids = set()
    for entry in current_catalogue or []:
        if getEventID(entry) and not entryAlreadyFinalized(entry):
            event_ids.add(getEventID(entry))
    for entry in near_start_catalogue or []:
        if getEventID(entry) and not entryAlreadyFinalized(entry):
            event_ids.add(getEventID(entry))
    event_ids.update(event_id for event_id in NEAR_START_CATALOGUE if event_id)
    event_ids.update(getEventID(team) for team in DA_TEAMS if getEventID(team))
    return sorted(event_ids)


def updatePresence(current_catalogue, near_start_catalogue, timelines):
    fresh_catalogue_ids = {getEventID(entry) for entry in current_catalogue + near_start_catalogue if getEventID(entry)}
    timeline_ids = {collection.normalise_id(item.get('eventId')) for item in timelines}
    now_epoch = time.time()

    tracked_entries = {getEventID(team): team for team in DA_TEAMS}
    for event_id, entry in NEAR_START_CATALOGUE.items():
        market_time = parseBetfairTimestamp(entry.get('description', {}).get('marketTime') or entry.get('event', {}).get('openDate'))
        if market_time is not None and market_time - (KO_FOCUS_BEFORE_MINUTES * 60) <= now_epoch:
            tracked_entries.setdefault(event_id, entry)

    for event_id, entry in tracked_entries.items():
        if event_id in fresh_catalogue_ids:
            LAST_CATALOGUE_SEEN[event_id] = now_epoch
            if event_id in CATALOGUE_MISSING:
                CATALOGUE_MISSING.remove(event_id)
                logIssue(entry, 'catalogue_returned', 'WATCH', '')
                markStateDirty()
        elif event_id not in CATALOGUE_MISSING:
            CATALOGUE_MISSING.add(event_id)
            logIssue(entry, 'catalogue_missing', 'WATCH', '')
            markStateDirty()

        if event_id in timeline_ids:
            LAST_TIMELINE_SEEN[event_id] = now_epoch
            if event_id in TIMELINE_MISSING:
                TIMELINE_MISSING.remove(event_id)
                logIssue(entry, 'timeline_returned', 'WATCH', '')
                markStateDirty()
        elif findTeamByEvent(event_id) is not None and event_id not in TIMELINE_MISSING:
            TIMELINE_MISSING.add(event_id)
            logIssue(entry, 'timeline_missing', 'WATCH', '')
            markStateDirty()



def _detailIdentity(detail):
    if not isinstance(detail, dict):
        return None
    update_id = detail.get('updateId')
    if update_id is not None:
        return ('id', str(update_id))
    return (
        detail.get('updateType') or detail.get('type'),
        detail.get('updateTime'),
        detail.get('matchTime'),
        detail.get('elapsedRegularTime'),
        detail.get('team')
    )


def detectLivePhaseSignals(timelines):
    now_epoch = time.time()
    phases = {'KickOff', 'FirstHalfEnd', 'SecondHalfKickOff'}
    signals = {}
    for event in timelines:
        event_id = collection.normalise_id(event.get('eventId'))
        previous = LATEST_TIMELINES.get(event_id, {})
        previous_status = previous.get('inPlayMatchStatus')
        current_status = event.get('inPlayMatchStatus')
        minute = eventElapsedMinutes(event)
        event_signals = {}

        if current_status in phases and current_status != previous_status:
            live = False
            if current_status == 'KickOff':
                live = minute is None or minute <= KO_LIVE_ELAPSED_MAX_MINUTES
            elif current_status == 'FirstHalfEnd':
                live = True
            elif current_status == 'SecondHalfKickOff':
                live = minute is not None and HT_SIGNAL_MINUTE_MIN <= minute <= HT_SIGNAL_MINUTE_MAX
            if live:
                event_signals[current_status] = {
                    'source': 'STATUS', 'observed_at': now_epoch, 'bf_minute': minute
                }

        previous_details = {_detailIdentity(item) for item in previous.get('updateDetails', []) or []}
        for detail in event.get('updateDetails', []) or []:
            phase = detail.get('updateType') or detail.get('type')
            if phase not in phases or _detailIdentity(detail) in previous_details:
                continue
            exact = parseBetfairTimestamp(detail.get('updateTime'))
            if exact is not None and exact <= 86400:
                exact = None
            recent = exact is not None and 0 <= now_epoch - exact <= HT_SIGNAL_FRESH_SECONDS
            live = recent
            if exact is None:
                if phase == 'KickOff':
                    live = minute is None or minute <= KO_LIVE_ELAPSED_MAX_MINUTES
                elif phase == 'FirstHalfEnd':
                    live = current_status == 'FirstHalfEnd'
                elif phase == 'SecondHalfKickOff':
                    live = minute is not None and HT_SIGNAL_MINUTE_MIN <= minute <= HT_SIGNAL_MINUTE_MAX
            if live and phase not in event_signals:
                event_signals[phase] = {
                    'source': 'UPDATE_DETAIL', 'observed_at': now_epoch, 'bf_minute': minute,
                    'detail_time': exact
                }

        if event_signals:
            signals[event_id] = event_signals
    return signals


def rememberTimelineStates(timelines, live_signals=None):
    now_epoch = time.time()
    for event in timelines:
        event_id = collection.normalise_id(event.get('eventId'))
        if LATEST_TIMELINES.get(event_id) != event:
            LATEST_TIMELINES[event_id] = copy.deepcopy(event)
            markStateDirty()

        if hasTransition(event, 'KickOff') and event_id not in FIRST_HALF_START_TIMES:
            kickoff, source = observedKickoffTime(event, now_epoch)
            if kickoff is not None:
                FIRST_HALF_START_TIMES[event_id] = kickoff
                FIRST_HALF_START_SOURCE[event_id] = source
                team = findTeamByEvent(event_id)
                if team is not None and not koIsFilled(team):
                    ensureKOState(team, kickoff, source)
                markStateDirty()

        if hasTransition(event, 'FirstHalfEnd') and event_id not in FIRST_HALF_END_TIMES:
            first_end = transitionTime(event, 'FirstHalfEnd')
            signal = (live_signals or {}).get(event_id, {}).get('FirstHalfEnd')
            if first_end is None and signal is not None:
                first_end = signal.get('observed_at', now_epoch)
            elif first_end is None and event.get('inPlayMatchStatus') == 'FirstHalfEnd':
                first_end = now_epoch
            if first_end is not None:
                FIRST_HALF_END_TIMES[event_id] = first_end
                score = explicitHalfTimeScore(event) or reconstructHalfTimeScore(event)
                if score is None and event.get('inPlayMatchStatus') == 'FirstHalfEnd':
                    score = currentScore(event)
                if score is not None:
                    FIRST_HALF_END_SCORES[event_id] = score
                markStateDirty()

        team = findTeamByEvent(event_id)
        if team is not None:
            changed = team.get('score') != event.get('score') or team.get('updateDetails') != event.get('updateDetails')
            team['score'] = event.get('score', team.get('score', ''))
            team['updateDetails'] = event.get('updateDetails', team.get('updateDetails', ''))
            if changed:
                markStateDirty()

def matchHasStarted(event):
    if hasTransition(event, 'KickOff'):
        return True
    status = event.get('inPlayMatchStatus', '')
    if status in ['FirstHalfEnd', 'SecondHalfKickOff', 'Finished']:
        return True
    try:
        if float(event.get('elapsedRegularTime', 0) or 0) >= 1:
            return True
    except Exception:
        pass
    return any((detail.get('elapsedRegularTime') or detail.get('matchTime') or 0) >= 1 for detail in event.get('updateDetails', []))


def processKOEvents(timelines):
    now_epoch = time.time()
    for event in timelines:
        if not matchHasStarted(event):
            continue

        event_id = collection.normalise_id(event.get('eventId'))
        entry = findCatalogueByEvent(event_id)
        if entry is not None and entryAlreadyFinalized(entry):
            continue
        team = findTeamByEvent(event_id)
        if team is None and entry is not None:
            team = initialiseTeam(entry, event)
        if team is None or koIsFilled(team):
            continue

        start = FIRST_HALF_START_TIMES.get(event_id)
        source = FIRST_HALF_START_SOURCE.get(event_id)
        if start is None:
            start, source = observedKickoffTime(event, now_epoch)
        if start is None:
            scheduled = scheduledStart(team)
            if scheduled is not None:
                start = scheduled
                source = 'late_rediscovery'
        if start is not None:
            ensureKOState(team, start, source or 'timeline')

def processCatalogueKickOffFallback(current_catalogue):
    now_epoch = time.time()
    for entry in current_catalogue:
        if entryAlreadyFinalized(entry):
            continue
        event_id = getEventID(entry)
        team = findTeamByEvent(event_id)
        if team is None:
            team = initialiseTeam(entry, LATEST_TIMELINES.get(event_id, {}))
        if team is None or koIsFilled(team):
            continue

        start = FIRST_HALF_START_TIMES.get(event_id)
        source = FIRST_HALF_START_SOURCE.get(event_id)
        if start is None:
            event = LATEST_TIMELINES.get(event_id, {})
            start, source = observedKickoffTime(event, now_epoch)

        if start is None:
            scheduled = scheduledStart(entry)
            if scheduled is not None and now_epoch <= scheduled + KO_LIVE_DISCOVERY_MAX_AFTER_SCHEDULE_SECONDS:
                start = now_epoch
                source = 'catalogue_inplay_live'
                logIssue(team, 'first_half_fallback', 'KO', f'catalogue_inplay_live|obs={collectorStamp()}')
            elif scheduled is not None:
                start = scheduled
                source = 'catalogue_inplay_late'

        if start is not None:
            ensureKOState(team, start, source or 'catalogue_inplay')

KO_SYNTHETIC_START_SOURCES = {
    'catalogue_inplay_live', 'catalogue_inplay_late', 'late_rediscovery', 'catalogue_inplay'
}


def _recoverBoundarySnapshot(team, snapshot, reference):
    if snapshot is None:
        return None
    repaired = (collection.repair_match_odds_boundary(snapshot, reference)
                if isMatchOddsEntry(team) else collection.repair_missing_back(snapshot, reference))
    if repaired is not None:
        selected = copy.deepcopy(snapshot)
        selected['back'] = list(repaired['back'])
        selected['lay'] = list(repaired.get('lay', snapshot.get('lay', [None, None, None])))
        selected['book'] = repaired.get('book')
        return {
            'back': list(repaired['back']),
            'lay': list(repaired.get('lay', snapshot.get('lay', [None, None, None]))),
            'book': repaired.get('book'),
            'raw': snapshot,
            'selected': selected,
            'inferred': list(repaired.get('inferred', []))
        }
    if snapshotIsKosher(snapshot, reference):
        return {
            'back': list(snapshot['back']),
            'lay': list(snapshot.get('lay', [None, None, None])),
            'book': snapshot.get('book'),
            'raw': snapshot,
            'selected': copy.deepcopy(snapshot),
            'inferred': []
        }
    return None


def _koPreCandidates(team, start, source):
    market_id = getMarketID(team)
    history = sorted(PRICE_HISTORY.get(market_id, []), key=lambda item: item.get('time', 0))
    lower = start - KO_BACKUP_MAX_AGE_SECONDS
    candidates = []
    entered_play = False
    for item in history:
        when = item.get('time', 0) or 0
        if when < lower or when > start + KO_BOUNDARY_RECONCILE_SECONDS:
            continue
        inplay = item.get('inplay')
        if inplay is True:
            entered_play = True
            continue
        if entered_play:
            continue
        if inplay is False:
            candidates.append(item)
        elif inplay is None and source not in KO_SYNTHETIC_START_SOURCES and when <= start:
            candidates.append(item)
    return candidates


def _koFirstPostCandidate(team, start):
    market_id = getMarketID(team)
    history = sorted(PRICE_HISTORY.get(market_id, []), key=lambda item: item.get('time', 0))
    return next((item for item in history
                 if start <= (item.get('time', 0) or 0) <= start + KO_POST_BOUNDARY_SECONDS
                 and item.get('inplay') is True), None)


def selectKOBoundary(team, start, now_epoch=None):
    now_epoch = now_epoch or time.time()
    event_id = getEventID(team)
    market_id = getMarketID(team)
    source = FIRST_HALF_START_SOURCE.get(event_id, 'unknown')
    clean_reference = [item for item in CLEAN_PRICE_HISTORY.get(market_id, [])
                       if (item.get('time', 0) or 0) <= start]

    pre_result = None
    for item in _koPreCandidates(team, start, source):
        recovered = _recoverBoundarySnapshot(team, item, clean_reference)
        if recovered is not None:
            pre_result = recovered
            if snapshotIsKosher(recovered['selected'], clean_reference):
                clean_reference.append(recovered['selected'])

    post_raw = _koFirstPostCandidate(team, start)
    post_result = _recoverBoundarySnapshot(team, post_raw, clean_reference) if post_raw is not None else None

    if pre_result is not None and post_result is not None:
        if collection.boundary_snapshots_close(pre_result['selected'], post_result['selected']):
            post_result['method'] = 'BOUNDARY_POST'
            return post_result, True
        pre_result['method'] = 'BOUNDARY_PRE'
        return pre_result, True

    if post_result is not None:
        # A post-kick-off price can stand alone only when the kick-off boundary
        # came from a real timeline observation rather than a late/synthetic rediscovery.
        if source not in KO_SYNTHETIC_START_SOURCES:
            post_result['method'] = 'BOUNDARY_POST_ONLY'
            return post_result, True

    if pre_result is not None and now_epoch >= start + KO_POST_BOUNDARY_SECONDS:
        pre_result['method'] = 'BOUNDARY_PRE'
        return pre_result, True

    return None, now_epoch > start + KO_BOUNDARY_RECONCILE_SECONDS


def firstKosherKO(team, start):
    result, ready = selectKOBoundary(team, start)
    if result is None:
        return None, None
    selected = result.get('selected') or result.get('raw')
    return selected, result.get('method')


def applyPendingKO(timelines, results):
    now_epoch = time.time()
    for team in list(DA_TEAMS):
        if koIsFilled(team):
            continue
        market_id = getMarketID(team)
        event_id = getEventID(team)
        start = FIRST_HALF_START_TIMES.get(event_id)
        if start is None:
            continue

        result, ready = selectKOBoundary(team, start, now_epoch)
        if result is not None:
            freezeKO(team, result)
            continue

        if ready:
            state = KO_CAPTURE_STATE.setdefault(market_id, {})
            state.update({'event_id': event_id, 'start': start,
                          'source': FIRST_HALF_START_SOURCE.get(event_id, state.get('source', 'unknown')),
                          'phase': 'MISSING', 'deadline': start + KO_BOUNDARY_RECONCILE_SECONDS})
            rememberCaptureEvidence(team, 'KO', {'method': 'MISS', 'raw': None})
            KO_MISSING.add(market_id)
            logIssue(team, 'late_start', 'KO', f"{state.get('source', 'unknown')}|obs={collectorStamp()}")
            markStateDirty()


def secondHalfGoalRecorded(event):
    restart_seen = False
    for detail in event.get('updateDetails', []) or []:
        event_type = detail.get('updateType') or detail.get('type')
        if event_type == 'SecondHalfKickOff':
            restart_seen = True
            continue
        if event_type != 'Goal':
            continue
        try:
            elapsed = float(detail.get('elapsedRegularTime') or detail.get('matchTime') or 0)
        except Exception:
            elapsed = 0
        if restart_seen or elapsed >= 46:
            return True
    return False


def htBoundarySafety(event_id, event, require_recorded_score=False):
    ht_score = FIRST_HALF_END_SCORES.get(event_id)
    if ht_score is None:
        ht_score = explicitHalfTimeScore(event)
    if require_recorded_score and ht_score is None:
        return False, 'HT_SCORE_NOT_RECORDED', None
    live_score = currentScore(event)
    if ht_score is not None and live_score is not None and list(live_score) != list(ht_score):
        return False, 'SCORE_CHANGED_AFTER_HT', list(ht_score)
    if secondHalfGoalRecorded(event):
        return False, 'SECOND_HALF_GOAL_ALREADY_RECORDED', list(ht_score) if ht_score is not None else None
    return True, '', list(ht_score) if ht_score is not None else None


def secondHalfSignal(event, event_id, live_signals=None):
    now_epoch = time.time()
    minute = eventElapsedMinutes(event)
    live = (live_signals or {}).get(event_id, {}).get('SecondHalfKickOff')
    if live is not None:
        return live.get('source'), live.get('observed_at', now_epoch), live.get('bf_minute', minute)

    # A valid persistent update timestamp may have arrived in a previous response.
    # It is usable only while still very close to the actual restart boundary.
    detail = transitionDetail(event, 'SecondHalfKickOff')
    if detail is not None:
        exact = parseBetfairTimestamp(detail.get('updateTime'))
        if exact is not None and 0 <= now_epoch - exact <= HT_SIGNAL_FRESH_SECONDS:
            return 'UPDATE_DETAIL', exact, minute

    # If current status itself is still the restart state, observation time is
    # the practical boundary. This also handles Betfair's 1970 update timestamp.
    if event.get('inPlayMatchStatus') == 'SecondHalfKickOff':
        if minute is not None and HT_SIGNAL_MINUTE_MIN <= minute <= HT_SIGNAL_MINUTE_MAX:
            return 'STATUS', now_epoch, minute

    # Narrow recovery for a literal restart signal that was missed. It is only
    # allowed after a definitely observed FirstHalfEnd, at minute 46-48, with
    # the score still exactly equal to the recorded half-time score and no goal.
    if event_id in FIRST_HALF_END_TIMES and minute is not None and 46 <= minute <= HT_SIGNAL_MINUTE_MAX:
        safe, _, ht_score = htBoundarySafety(event_id, event, require_recorded_score=True)
        if safe and ht_score is not None:
            return 'ELAPSED_FALLBACK', now_epoch, minute

    return None, None, minute


def recoverPostStartSnapshot(team, snapshot, reference):
    if snapshot is None:
        return None

    repaired = (collection.repair_match_odds_boundary(snapshot, reference)
                if isMatchOddsEntry(team) else collection.repair_missing_back(snapshot, reference))
    if repaired is not None:
        selected = copy.deepcopy(snapshot)
        selected['back'] = list(repaired['back'])
        selected['lay'] = list(repaired.get('lay', snapshot.get('lay', [None, None, None])))
        selected['book'] = repaired.get('book')
        inferred = list(repaired.get('inferred', []))
        method = 'INF' if inferred else 'OBS'
        return {
            'back': list(repaired['back']),
            'lay': list(repaired.get('lay', snapshot.get('lay', [None, None, None]))),
            'book': repaired.get('book'),
            'method': method,
            'raw': snapshot,
            'selected': selected,
            'inferred': inferred,
            'request_time': snapshot.get('request_time'),
            'response_time': snapshot.get('response_time')
        }

    if snapshotIsKosher(snapshot, reference):
        return {
            'back': list(snapshot['back']),
            'lay': list(snapshot.get('lay', [None, None, None])),
            'book': snapshot.get('book'),
            'method': 'OBS',
            'raw': snapshot,
            'selected': copy.deepcopy(snapshot),
            'inferred': [],
            'request_time': snapshot.get('request_time'),
            'response_time': snapshot.get('response_time')
        }
    return None


def _formatHTScore(score):
    if score is None:
        return ''
    return f"{score[0]}-{score[1]}"


def recordHTDiagnostic(team, source, observed_at, bf_minute, ht_score,
                       request_time, response_time, captured, reason):
    detail = (
        f"event_id={getEventID(team)};source={source or ''};"
        f"signal_observed_at={observed_at or ''};bf_minute={bf_minute if bf_minute is not None else ''};"
        f"ht_score={_formatHTScore(ht_score)};price_request_time={request_time or ''};"
        f"price_response_time={response_time or ''};captured={'YES' if captured else 'NO'};reason={reason}"
    )
    logIssue(team, 'ht_capture_diagnostic', 'HT', detail)


def captureHTBoundaryPrice(team, event, source, observed_at, bf_minute):
    event_id = getEventID(team)
    market_id = getMarketID(team)
    safe, reason, ht_score = htBoundarySafety(
        event_id, event, require_recorded_score=(source == 'ELAPSED_FALLBACK'))
    if not safe:
        recordHTDiagnostic(team, source, observed_at, bf_minute, ht_score,
                           None, None, False, reason)
        return None

    reference = referencePriceHistory(market_id)
    request_time = time.time()
    HT_REPLENISH_LAST_ATTEMPT[event_id] = request_time
    marketbook = getCleanExchangePricesfromWebsite([market_id], force=True)
    response_time = time.time()
    snapshot = extractSnapshot(team, marketbook)
    if snapshot is None:
        reason = 'PRICE_ENDPOINT_' + str(ENDPOINT_LAST_ERROR.get('price') or 'NO_MARKET')
        recordHTDiagnostic(team, source, observed_at, bf_minute, ht_score,
                           request_time, response_time, False, reason)
        markStateDirty()
        return None

    snapshot['request_time'] = request_time
    snapshot['response_time'] = response_time
    addPriceHistory(team, snapshot)
    addCleanPriceHistory(team, snapshot, reference)
    recovered = recoverPostStartSnapshot(team, snapshot, reference)
    if recovered is None:
        recordHTDiagnostic(team, source, observed_at, bf_minute, ht_score,
                           request_time, response_time, False, 'FRESH_PRICE_REJECTED')
        markStateDirty()
        return None

    # The restart boundary stays fixed. A later replenish poll is accepted only
    # while the score still matches HT and no second-half goal is recorded.
    safe_after, reason_after, ht_score_after = htBoundarySafety(
        event_id, event, require_recorded_score=(source == 'ELAPSED_FALLBACK'))
    if not safe_after:
        recordHTDiagnostic(team, source, observed_at, bf_minute, ht_score_after,
                           request_time, response_time, False, reason_after)
        markStateDirty()
        return None

    recordHTDiagnostic(team, source, observed_at, bf_minute, ht_score_after,
                       request_time, response_time, True, recovered.get('method', 'OBS'))
    markStateDirty()
    return recovered


def firstKosherPostStart(team, start):
    # Restart recovery may use only snapshots from the tiny boundary interval.
    market_id = getMarketID(team)
    history = sorted(PRICE_HISTORY.get(market_id, []), key=lambda item: item.get('time', 0))
    reference = [item for item in CLEAN_PRICE_HISTORY.get(market_id, []) if item.get('time', 0) < start]
    boundary = [item for item in history if start <= (item.get('time', 0) or 0) <= start + HT_BOUNDARY_CAPTURE_SECONDS]
    for item in boundary:
        recovered = recoverPostStartSnapshot(team, item, reference)
        if recovered is not None:
            return recovered
    return None


def processSecondHalfStarts(timelines, live_signals=None):
    attempted = set()
    now_epoch = time.time()
    for event in timelines:
        event_id = collection.normalise_id(event.get('eventId'))
        team = findTeamByEvent(event_id)
        if team is None or htIsFilled(team):
            continue

        existing = SECOND_HALF_START_TIMES.get(event_id)
        source, evidence_time, bf_minute = secondHalfSignal(event, event_id, live_signals)
        if source is None:
            if existing is None or now_epoch - existing > HT_REPLENISH_WINDOW_SECONDS:
                continue
            source = SECOND_HALF_START_SOURCE.get(event_id, 'UPDATE_DETAIL')
            evidence_time = existing
            bf_minute = eventElapsedMinutes(event)

        market_id = getMarketID(team)
        attempted.add(market_id)

        # Existing boundaries are retried by the 5-second replenish cycle.
        if existing is not None:
            continue

        SECOND_HALF_START_TIMES[event_id] = evidence_time
        SECOND_HALF_START_SOURCE[event_id] = source
        if source == 'ELAPSED_FALLBACK':
            logIssue(team, 'second_half_fallback', 'HT', source)
        markStateDirty()

        # One immediate request at the observed restart. A bad response stays
        # pending instead of permanently freezing HT to zero.
        result = captureHTBoundaryPrice(team, event, source, evidence_time, bf_minute)
        if result is not None:
            freezeHT(team, result, event)
        else:
            logIssue(team, 'missing_price', 'HT', 'boundary_price_pending')
    return attempted


def _rawUnavailable(snapshot):
    if snapshot is None:
        return True
    status = str(snapshot.get('status') or '').upper()
    if status in {'SUSPENDED', 'CLOSED'}:
        return True
    prices = snapshot.get('back', [])
    return len(prices) != 3 or all(price is None or price <= 1.0 for price in prices)


def _rawStrong(snapshot, history):
    return snapshot is not None and snapshotIsKosher(snapshot, history)


def _rawMarketAvailable(snapshot):
    if snapshot is None:
        return False
    backs = snapshot.get('back', [])
    lays = snapshot.get('lay', [])
    if len(backs) != 3 or len(lays) != 3:
        return False
    return all(((backs[index] or 0) > 1.0) or ((lays[index] or 0) > 1.0) for index in range(3))

def freezeKO(team, result):
    prices = result['back']
    market_id = getMarketID(team)
    event_id = getEventID(team)
    KO_MISSING.discard(market_id)
    state = KO_CAPTURE_STATE.setdefault(market_id, {})
    state.update({'event_id': event_id, 'start': FIRST_HALF_START_TIMES.get(event_id),
                  'source': FIRST_HALF_START_SOURCE.get(event_id, state.get('source', 'unknown')),
                  'phase': 'FROZEN'})
    rememberCaptureEvidence(team, 'KO', result)
    team['output']['KO_1'] = prices[0]
    team['output']['KO_2'] = prices[1]
    team['output']['KO_X'] = prices[2]
    updateTeamExchange(team, result.get('raw'))
    markStateDirty()
    print(f"KO: {team['output']['Home']} - {team['output']['Away']} {prices}")
    persistState(force=True)

def freezeHT(team, result, event_details):
    prices = result['back']
    rememberCaptureEvidence(team, 'HT', result)
    team['output']['HT_1'] = prices[0]
    team['output']['HT_2'] = prices[1]
    team['output']['HT_X'] = prices[2]
    team['score'] = event_details.get('score', team.get('score', ''))

    event_id = getEventID(team)
    scores = firstHalfScore(event_id, event_details)
    if scores is not None:
        team['output']['HT_Home'] = str(scores[0])
        team['output']['HT_Away'] = str(scores[1])
    else:
        team['output']['HT_Home'] = '-1'
        team['output']['HT_Away'] = '-1'

    team['output']['HT_1/X'] = lib.doubleChance(team['output']['HT_1'], team['output']['HT_X']) if team['output']['HT_1'] and team['output']['HT_X'] else 0.0
    team['output']['HT_2/X'] = lib.doubleChance(team['output']['HT_2'], team['output']['HT_X']) if team['output']['HT_2'] and team['output']['HT_X'] else 0.0
    team['output']['HT_1/2'] = lib.doubleChance(team['output']['HT_1'], team['output']['HT_2']) if team['output']['HT_1'] and team['output']['HT_2'] else 0.0
    team['output']['MODEL_DT1'] = applyModel__DT1(team)
    team['output']['MODEL_ZZCX'] = applyModel__ZZCX(team)
    team['output']['STAKE'] = config['Bet_Size']
    roundOutputDecimals(team['output'])
    updateTeamExchange(team, result.get('raw'))
    markStateDirty()
    print(f"HT: {team['output']['Home']} - {team['output']['Away']} {prices}")
    persistState(force=True)


def koIsFilled(team):
    return getMarketID(team) in KO_MISSING or any(team['output'].get(key, 0) for key in ['KO_1', 'KO_2', 'KO_X'])


def htIsFilled(team):
    return team['output'].get('HT_Home', '') != ''


def preKOFocusEntries():
    now_epoch = time.time()
    entries = {}
    for entry in NEAR_START_CATALOGUE.values():
        if entryAlreadyFinalized(entry):
            continue
        market_time = scheduledStart(entry)
        if market_time is None:
            continue
        team = findTeamByEvent(getEventID(entry))
        if team is not None and koIsFilled(team):
            continue

        event_id = getEventID(entry)
        actual_start = FIRST_HALF_START_TIMES.get(event_id)
        if actual_start is None:
            # Keep polling around a delayed kick-off until we actually observe
            # the start, rather than stopping just after the scheduled time.
            in_window = market_time - (KO_FOCUS_BEFORE_MINUTES * 60) <= now_epoch <= market_time + (KO_KEEP_AFTER_SCHEDULE_MINUTES * 60)
        else:
            in_window = now_epoch <= actual_start + KO_BOUNDARY_RECONCILE_SECONDS

        if in_window:
            target = team or entry
            entries[getMarketID(target)] = target

    for team in DA_TEAMS:
        if koIsFilled(team):
            continue
        event_id = getEventID(team)
        start = FIRST_HALF_START_TIMES.get(event_id)
        if start is not None and start - (KO_FOCUS_BEFORE_MINUTES * 60) <= now_epoch <= start + KO_BOUNDARY_RECONCILE_SECONDS:
            entries[getMarketID(team)] = team
    return list(entries.values())

def htFocusEntries():
    now_epoch = time.time()
    entries = []
    for team in DA_TEAMS:
        if htIsFilled(team):
            continue
        event_id = getEventID(team)
        first_half_end = FIRST_HALF_END_TIMES.get(event_id)
        if first_half_end is not None:
            focus_start = first_half_end + (HT_FOCUS_AFTER_FIRST_HALF_MINUTES * 60)
        else:
            kickoff = FIRST_HALF_START_TIMES.get(event_id)
            if kickoff is None:
                continue
            focus_start = kickoff + (55 * 60)

        if now_epoch < focus_start:
            continue
        second_half_start = SECOND_HALF_START_TIMES.get(event_id)
        if second_half_start is not None and now_epoch > second_half_start + HT_BOUNDARY_CAPTURE_SECONDS:
            continue
        if first_half_end is None and second_half_start is None and now_epoch > focus_start + (20 * 60):
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
        market_id = getMarketID(entry)
        if market_id:
            result[market_id] = entry
    return list(result.values())


def pendingHTMarketIDs():
    return {getMarketID(team) for team in DA_TEAMS
            if not htIsFilled(team) and getEventID(team) in SECOND_HALF_START_TIMES}


def retryPendingHT(timelines):
    by_event = {collection.normalise_id(event.get('eventId')): event for event in timelines}
    now_epoch = time.time()
    for team in list(DA_TEAMS):
        if htIsFilled(team):
            continue
        event_id = getEventID(team)
        start = SECOND_HALF_START_TIMES.get(event_id)
        if start is None or now_epoch > start + HT_REPLENISH_WINDOW_SECONDS:
            continue

        # No fresh timeline means no price request: a stale score must never
        # allow a post-goal price to be labelled HT.
        event = by_event.get(event_id)
        if event is None:
            continue

        source = SECOND_HALF_START_SOURCE.get(event_id, 'UPDATE_DETAIL')
        safe, reason, score = htBoundarySafety(
            event_id, event, require_recorded_score=(source == 'ELAPSED_FALLBACK'))
        if not safe:
            recordHTDiagnostic(team, source, start, eventElapsedMinutes(event), score,
                               None, None, False, reason)
            freezeHT(team, {'back': [0.0, 0.0, 0.0], 'lay': [0.0, 0.0, 0.0],
                            'book': None, 'method': 'MISS', 'raw': None}, event)
            HT_REPLENISH_LAST_ATTEMPT.pop(event_id, None)
            logIssue(team, 'missing_price', 'HT', reason.lower())
            continue

        last_attempt = HT_REPLENISH_LAST_ATTEMPT.get(event_id, start)
        if now_epoch - last_attempt < HT_REPLENISH_POLL_SECONDS:
            continue

        result = captureHTBoundaryPrice(team, event, source, start, eventElapsedMinutes(event))
        if result is not None:
            freezeHT(team, result, event)
            HT_REPLENISH_LAST_ATTEMPT.pop(event_id, None)


def applyPendingHT(timelines, results=None):
    by_event = {collection.normalise_id(event.get('eventId')): event for event in timelines}
    now_epoch = time.time()
    for team in list(DA_TEAMS):
        if htIsFilled(team):
            continue
        event_id = getEventID(team)
        start = SECOND_HALF_START_TIMES.get(event_id)
        if start is None or now_epoch <= start + HT_REPLENISH_WINDOW_SECONDS:
            continue
        event = by_event.get(event_id) or LATEST_TIMELINES.get(event_id, {})
        score = firstHalfScore(event_id, event)
        recordHTDiagnostic(team, SECOND_HALF_START_SOURCE.get(event_id, ''), start,
                           eventElapsedMinutes(event), score, None, None, False,
                           'REPLENISH_WINDOW_EXPIRED')
        freezeHT(team, {'back': [0.0, 0.0, 0.0], 'lay': [0.0, 0.0, 0.0],
                        'book': None, 'method': 'MISS', 'raw': None}, event)
        HT_REPLENISH_LAST_ATTEMPT.pop(event_id, None)
        logIssue(team, 'missing_price', 'HT', 'replenish_window_expired')


def eventFinished(event):
    if event.get('inPlayMatchStatus') == 'Finished' or hasTransition(event, 'Finished'):
        return True
    score = event.get('score', {})
    return score.get('home', {}).get('fullTimeScore') not in [None, ''] and score.get('away', {}).get('fullTimeScore') not in [None, '']


def cleanupEventState(team):
    event_id = getEventID(team)
    market_id = getMarketID(team)
    PRICE_HISTORY.pop(market_id, None)
    CLEAN_PRICE_HISTORY.pop(market_id, None)
    CAPTURE_EVIDENCE.pop(market_id, None)
    KO_CAPTURE_STATE.pop(market_id, None)
    FIRST_HALF_START_TIMES.pop(event_id, None)
    FIRST_HALF_START_SOURCE.pop(event_id, None)
    FIRST_HALF_END_TIMES.pop(event_id, None)
    FIRST_HALF_END_SCORES.pop(event_id, None)
    SECOND_HALF_START_TIMES.pop(event_id, None)
    SECOND_HALF_START_SOURCE.pop(event_id, None)
    HT_REPLENISH_LAST_ATTEMPT.pop(event_id, None)
    LATEST_TIMELINES.pop(event_id, None)
    NEAR_START_CATALOGUE.pop(event_id, None)
    CURRENT_INPLAY_CATALOGUE.pop(event_id, None)
    KO_MISSING.discard(market_id)
    CATALOGUE_MISSING.discard(event_id)
    TIMELINE_MISSING.discard(event_id)
    LAST_CATALOGUE_SEEN.pop(event_id, None)
    LAST_TIMELINE_SEEN.pop(event_id, None)
    HT_CLEAN_SEEN.discard(event_id)
    HT_UNAVAILABLE_COUNTS.pop(event_id, None)
    HT_LAST_UNAVAILABLE_TIMES.pop(event_id, None)

def finaliseTeam(team, event):
    team['score'] = event.get('score', team.get('score', ''))
    team['updateDetails'] = event.get('updateDetails', team.get('updateDetails', ''))
    score = team.get('score', {})
    ht_scores = firstHalfScore(getEventID(team), event)
    if ht_scores is not None:
        team['output']['HT_Home'] = str(ht_scores[0])
        team['output']['HT_Away'] = str(ht_scores[1])
    team['output']['FT_Home'] = score.get('home', {}).get('fullTimeScore') or score.get('home', {}).get('score', '')
    team['output']['FT_Away'] = score.get('away', {}).get('fullTimeScore') or score.get('away', {}).get('score', '')
    team['output']['STAKE'] = config['Bet_Size']
    team['output']['FINAL'] = getFINAL(team['output'])
    team['output']['MULTI_DT1'] = getMULTI(team['output'], 'MODEL_DT1')
    team['output']['MULTI_ZZCX'] = getMULTI(team['output'], 'MODEL_ZZCX')
    team['output']['P/L_DT1'] = getPL(team['output'], 'MULTI_DT1')
    team['output']['P/L_ZZCX'] = getPL(team['output'], 'MULTI_ZZCX')
    roundOutputDecimals(team['output'])

    date_epoch = parseBetfairTimestamp(team['output']['Date'])
    date = betfairAPI.datetime.datetime.fromtimestamp(date_epoch, betfairAPI.datetime.timezone.utc) if date_epoch is not None else betfairAPI.datetime.datetime.now()
    filename = f"{date.strftime('%Y%m%d')}_results.csv"
    key = _resultKey(team['output'])
    keys = resultKeys(filename)

    saved = key in keys
    if not saved:
        saved = saveDictArrayToCSV(filename, [team['output']], 'a')
        if saved:
            keys.add(key)

    if saved:
        if captureNeedsForensicState(team):
            mergeDumpStateRecords(date.strftime('%Y%m%d'), [teamStateRecord(team, 'finalized_problematic')])
        FINALIZED_MARKETS.add(getMarketID(team))
        if team in DA_TEAMS:
            DA_TEAMS.remove(team)
        cleanupEventState(team)
        markStateDirty()
        persistState(force=True)


def processFinished(timelines):
    for event in timelines:
        if not eventFinished(event):
            continue

        event_id = collection.normalise_id(event.get('eventId'))
        team = findTeamByEvent(event_id)
        if team is None:
            entry = findCatalogueByEvent(event_id)
            if entry is None or getMarketID(entry) in FINALIZED_MARKETS:
                continue
            team = initialiseTeam(entry, event)
        finaliseTeam(team, event)


def refreshCatalogueCaches(current_catalogue, near_start_catalogue):
    current = {getEventID(entry): entry for entry in current_catalogue
               if getEventID(entry) and not entryAlreadyFinalized(entry)}
    if CURRENT_INPLAY_CATALOGUE != current:
        CURRENT_INPLAY_CATALOGUE.clear()
        CURRENT_INPLAY_CATALOGUE.update(current)
        markStateDirty()

    for entry in near_start_catalogue:
        event_id = getEventID(entry)
        if not event_id:
            continue
        if entryAlreadyFinalized(entry):
            if event_id in NEAR_START_CATALOGUE:
                NEAR_START_CATALOGUE.pop(event_id, None)
                markStateDirty()
            continue
        if NEAR_START_CATALOGUE.get(event_id) != entry:
            NEAR_START_CATALOGUE[event_id] = entry
            markStateDirty()

    cutoff = time.time() - (KO_KEEP_AFTER_SCHEDULE_MINUTES * 60 * 2)
    expired = []
    for event_id, entry in NEAR_START_CATALOGUE.items():
        market_time = scheduledStart(entry)
        team = findTeamByEvent(event_id)
        if entryAlreadyFinalized(entry) or (team is None and market_time is not None and market_time < cutoff):
            expired.append(event_id)
    for event_id in expired:
        NEAR_START_CATALOGUE.pop(event_id, None)
        markStateDirty()

def essentialTimeline(event):
    if not isinstance(event, dict):
        return {}
    keep_types = {'KickOff', 'FirstHalfEnd', 'SecondHalfKickOff', 'Finished', 'Goal'}
    details = []
    for item in event.get('updateDetails', []) or []:
        event_type = item.get('updateType') or item.get('type')
        if event_type not in keep_types:
            continue
        details.append({key: item.get(key) for key in
                        ['updateTime', 'matchTime', 'elapsedRegularTime', 'elapsedAddedTime',
                         'type', 'updateType', 'team', 'teamName'] if key in item})
    score = event.get('score', {}) or {}
    return {
        'status': event.get('inPlayMatchStatus', ''),
        'elapsed': event.get('elapsedRegularTime'),
        'score': {
            'home': {key: score.get('home', {}).get(key, '') for key in ['score', 'halfTimeScore', 'fullTimeScore']},
            'away': {key: score.get('away', {}).get(key, '') for key in ['score', 'halfTimeScore', 'fullTimeScore']}
        },
        'events': details
    }


def boundedHistory(history):
    history = list(history or [])
    if len(history) <= FORENSIC_MAX_SNAPSHOTS:
        return copy.deepcopy(history)
    left = FORENSIC_MAX_SNAPSHOTS // 2
    right = FORENSIC_MAX_SNAPSHOTS - left
    return copy.deepcopy(history[:left] + history[-right:])


def forensicPriceContext(market_id):
    clean = list(CLEAN_PRICE_HISTORY.get(market_id, []))[-4:]
    raw = list(PRICE_HISTORY.get(market_id, []))[-4:]
    merged = {}
    for item in clean + raw:
        merged[item.get('time', 0)] = item
    return boundedHistory([merged[key] for key in sorted(merged)])


def compactEvidence(evidence):
    result = {}
    if not isinstance(evidence, dict):
        return result
    for point in ['KO', 'HT']:
        item = evidence.get(point)
        if not isinstance(item, dict):
            continue
        result[point] = {
            'method': item.get('method'),
            'selected': item.get('selected'),
            'history': boundedHistory(item.get('history', []))
        }
        if item.get('inferred'):
            result[point]['inferred'] = copy.deepcopy(item.get('inferred'))
    return result

def teamStateRecord(team, reason='unresolved_dump'):
    event_id = getEventID(team)
    market_id = getMarketID(team)
    output = team.get('output', {})
    home, away = getHomeAway(team)
    timeline = LATEST_TIMELINES.get(event_id) or {
        'score': team.get('score', {}), 'updateDetails': team.get('updateDetails', [])
    }
    evidence = compactEvidence(CAPTURE_EVIDENCE.get(market_id, {}))
    ko_missing = not all(float(output.get(key, 0) or 0) > 0 for key in ['KO_1', 'KO_2', 'KO_X'])
    ht_missing = not all(float(output.get(key, 0) or 0) > 0 for key in ['HT_1', 'HT_2', 'HT_X'])
    need_context = (ko_missing and 'KO' not in evidence) or (ht_missing and 'HT' not in evidence)
    price_context = forensicPriceContext(market_id) if need_context else []
    return {
        'state_reason': reason,
        'event_id': event_id,
        'market_id': market_id,
        'fixture': {
            'Date': output.get('Date', team.get('event', {}).get('openDate', '')),
            'Competition': output.get('Competition', team.get('competition', {}).get('name', '')),
            'Home': output.get('Home', home),
            'Away': output.get('Away', away)
        },
        'observed': {key: output.get(key) for key in
                     ['HT_Home', 'HT_Away', 'FT_Home', 'FT_Away',
                      'KO_1', 'KO_2', 'KO_X', 'HT_1', 'HT_2', 'HT_X']},
        'capture_evidence': evidence,
        'price_context': price_context,
        'transitions': {
            'first_half_start': FIRST_HALF_START_TIMES.get(event_id),
            'first_half_start_source': FIRST_HALF_START_SOURCE.get(event_id),
            'first_half_end': FIRST_HALF_END_TIMES.get(event_id),
            'first_half_end_score': FIRST_HALF_END_SCORES.get(event_id),
            'second_half_start': SECOND_HALF_START_TIMES.get(event_id),
            'second_half_start_source': SECOND_HALF_START_SOURCE.get(event_id),
            'ko_state': copy.deepcopy(KO_CAPTURE_STATE.get(market_id, {}))
        },
        'timeline': essentialTimeline(timeline),
        'flags': {
            'ko_missing': market_id in KO_MISSING,
            'catalogue_missing': event_id in CATALOGUE_MISSING,
            'timeline_missing': event_id in TIMELINE_MISSING
        }
    }

def dumpStateForTeams(teams, reason='unresolved_dump'):
    return [teamStateRecord(team, reason) for team in teams]


def compactLegacyForensicRecord(record):
    if not isinstance(record, dict) or 'team' not in record:
        return record
    team = record.get('team') or {}
    event_id = record.get('event_id') or getEventID(team)
    market_id = record.get('market_id') or getMarketID(team)
    output = team.get('output', {})
    home, away = getHomeAway(team) if team else ('', '')
    timeline = record.get('latest_timeline') or {'score': team.get('score', {}), 'updateDetails': team.get('updateDetails', [])}
    evidence = compactEvidence(record.get('capture_evidence', {}))
    observed_ko_missing = not all(float(output.get(key, 0) or 0) > 0 for key in ['KO_1', 'KO_2', 'KO_X'])
    observed_ht_missing = not all(float(output.get(key, 0) or 0) > 0 for key in ['HT_1', 'HT_2', 'HT_X'])
    need_context = (observed_ko_missing and 'KO' not in evidence) or (observed_ht_missing and 'HT' not in evidence)
    old_context = record.get('price_context', []) or record.get('price_history', [])
    price_context = boundedHistory(old_context) if need_context else boundedHistory(record.get('price_context', []))
    return {
        'state_reason': record.get('state_reason', 'legacy'),
        'event_id': event_id,
        'market_id': market_id,
        'fixture': {
            'Date': output.get('Date', team.get('event', {}).get('openDate', '')),
            'Competition': output.get('Competition', team.get('competition', {}).get('name', '')),
            'Home': output.get('Home', home),
            'Away': output.get('Away', away)
        },
        'observed': {key: output.get(key) for key in
                     ['HT_Home', 'HT_Away', 'FT_Home', 'FT_Away',
                      'KO_1', 'KO_2', 'KO_X', 'HT_1', 'HT_2', 'HT_X']},
        'capture_evidence': evidence,
        'price_context': price_context,
        'transitions': {
            'first_half_start': record.get('first_half_start_time'),
            'first_half_start_source': record.get('first_half_start_source'),
            'first_half_end': record.get('first_half_end_time'),
            'first_half_end_score': record.get('first_half_end_score'),
            'second_half_start': record.get('second_half_start_time'),
            'second_half_start_source': record.get('second_half_start_source'),
            'ko_state': {}
        },
        'timeline': essentialTimeline(timeline),
        'flags': {
            'ko_missing': bool(record.get('ko_missing')),
            'catalogue_missing': bool(record.get('catalogue_missing')),
            'timeline_missing': bool(record.get('timeline_missing'))
        }
    }


def forensicScore(record):
    observed = record.get('observed', {}) if isinstance(record, dict) else {}
    score = sum(1 for key in ['KO_1', 'KO_2', 'KO_X', 'HT_1', 'HT_2', 'HT_X']
                if float(observed.get(key, 0) or 0) > 0)
    evidence = record.get('capture_evidence', {}) if isinstance(record, dict) else {}
    for point in ['KO', 'HT']:
        item = evidence.get(point, {}) if isinstance(evidence, dict) else {}
        score += min(len(item.get('history', []) or []), FORENSIC_MAX_SNAPSHOTS)
        if item.get('selected'):
            score += 2
    score += min(len(record.get('price_context', []) or []), FORENSIC_MAX_SNAPSHOTS)
    return score

def mergeDumpStateRecords(day, records):
    if not records:
        return
    filename = f"{day}_dump_state.json"
    existing = lib.readFromJSON(filename) if os.path.isfile(filename) else []
    if not isinstance(existing, list):
        existing = []

    merged = {}
    for raw_record in existing + records:
        record = compactLegacyForensicRecord(raw_record)
        if not isinstance(record, dict):
            continue
        key = (record.get('event_id', ''), record.get('market_id', ''))
        previous = merged.get(key)
        if previous is None or forensicScore(record) >= forensicScore(previous):
            merged[key] = record
    lib.saveToJSON(list(merged.values()), filename)


def compactDumpStateFile(day):
    filename = f"{day}_dump_state.json"
    if not os.path.isfile(filename):
        return
    existing = lib.readFromJSON(filename)
    if not isinstance(existing, list):
        return
    merged = {}
    changed = False
    for raw_record in existing:
        record = compactLegacyForensicRecord(raw_record)
        if record is not raw_record or 'team' in raw_record or 'price_history' in raw_record:
            changed = True
        if not isinstance(record, dict):
            continue
        key = (record.get('event_id', ''), record.get('market_id', ''))
        previous = merged.get(key)
        if previous is not None:
            changed = True
        if previous is None or forensicScore(record) >= forensicScore(previous):
            merged[key] = record
    if changed:
        lib.saveToJSON(list(merged.values()), filename)
        print(f"Compacted forensic state: {filename} ({len(existing)} -> {len(merged)} records)")

def captureNeedsForensicState(team):
    output = team.get('output', {})
    ko_missing = not all(float(output.get(key, 0) or 0) > 0 for key in ['KO_1', 'KO_2', 'KO_X'])
    ht_missing = not all(float(output.get(key, 0) or 0) > 0 for key in ['HT_1', 'HT_2', 'HT_X'])
    score_missing = output.get('HT_Home', '') in ['', '-1'] or output.get('HT_Away', '') in ['', '-1']

    evidence = CAPTURE_EVIDENCE.get(getMarketID(team), {})
    suspect_methods = {'MIX', 'INF', 'MISS'}
    ko_method = evidence.get('KO', {}).get('method')
    ht_method = evidence.get('HT', {}).get('method')
    inferred = bool(evidence.get('KO', {}).get('inferred') or evidence.get('HT', {}).get('inferred'))
    reconstructed = ko_method in suspect_methods or ht_method in suspect_methods or inferred
    fallback_ht = SECOND_HALF_START_SOURCE.get(getEventID(team), '') == 'ELAPSED_FALLBACK'
    return ko_missing or ht_missing or score_missing or reconstructed or fallback_ht

def closedDayTransientFiles(day):
    return [
        f"{day}_checkpoint.json",
        f"{day}_checkpoint.json.bak",
        f"{day}_checkpoint.json.tmp",
        f"{day}_run_dump.json",
        f"{day}_run_dump.json.tmp"
    ]


def removeClosedDayRuntimeFiles(day):
    if day == currentUKDay():
        return
    removed = []
    for filename in closedDayTransientFiles(day):
        if os.path.isfile(filename):
            os.remove(filename)
            removed.append(filename)
    if removed:
        print(f"Removed closed-day runtime files for {day}: {', '.join(removed)}")


def purgeTeams(teams):
    for team in list(teams):
        cleanupEventState(team)
        if team in DA_TEAMS:
            DA_TEAMS.remove(team)
    markStateDirty()


def focusedCycle():
    entries = focusEntries()
    if not entries:
        return

    print(f"Focused capture: {len(entries)} market(s)")
    event_ids = list({getEventID(entry) for entry in entries if getEventID(entry)})
    timelines = requestTrackedTimelines(event_ids) if event_ids else []
    live_signals = detectLivePhaseSignals(timelines)
    rememberTimelineStates(timelines, live_signals)
    processKOEvents(timelines)
    attempted = processSecondHalfStarts(timelines, live_signals)
    retryPendingHT(timelines)

    pending_ht = pendingHTMarketIDs()
    entries = [entry for entry in focusEntries()
               if getMarketID(entry) not in attempted and getMarketID(entry) not in pending_ht]
    ht_focus_ids = {getMarketID(entry) for entry in htFocusEntries()}
    ht_ids = ht_focus_ids - pending_ht
    ht_entries = [entry for entry in entries if getMarketID(entry) in ht_ids]
    other_entries = [entry for entry in entries if getMarketID(entry) not in ht_ids]

    results = pollEntries(other_entries, aggressive=True, point='WIN') if other_entries else {}
    if ht_entries:
        results.update(pollEntries(ht_entries, aggressive=True, point='HT', allow_history_fallback=False))

    applyPendingKO(timelines, results)
    applyPendingHT(timelines, results)
    processFinished(timelines)
    persistState()


def htReplenishCycle():
    pending = [team for team in DA_TEAMS
               if not htIsFilled(team) and getEventID(team) in SECOND_HALF_START_TIMES]
    if not pending:
        return

    # During a pending HT boundary, watch other half-time events too so a new
    # SecondHalfKickOff is not missed. Prices are requested only for a new or
    # already-pending HT boundary, never for every watched market.
    watch = {getEventID(team): team for team in pending if getEventID(team)}
    for team in htFocusEntries():
        event_id = getEventID(team)
        if event_id:
            watch[event_id] = team

    timelines = requestTrackedTimelines(list(watch.keys())) if watch else []
    live_signals = detectLivePhaseSignals(timelines)
    rememberTimelineStates(timelines, live_signals)
    processSecondHalfStarts(timelines, live_signals)
    retryPendingHT(timelines)
    applyPendingHT(timelines)
    processFinished(timelines)
    persistState()


def main():
    global todays_threshold, filename

    now = betfairAPI.datetime.datetime.today()
    teamsToDump = [team for team in DA_TEAMS if lib.expiredMatch(team, now, timeDeltaHours)]
    if teamsToDump:
        listOfOutputs = list(map(lambda item: item['output'], teamsToDump))
        df = pd.json_normalize(listOfOutputs)
        print(tabulate(df, headers='keys', tablefmt='psql'))

    if todays_threshold < now:
        yesterday = now - betfairAPI.datetime.timedelta(days=1)
        closed_day = yesterday.strftime('%Y%m%d')
        filename = f"{closed_day}_dump"
        df = pd.json_normalize(teamsToDump)
        df.to_csv(filename + ".csv")
        lib.saveToJSON(teamsToDump, filename + ".json")
        mergeDumpStateRecords(closed_day, dumpStateForTeams(teamsToDump))

        thePL = getPL_API(yesterday)
        print(f"{yesterday.strftime('%d/%m/%Y')} PL is {thePL}")

        todays_threshold = betfairAPI.datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + betfairAPI.datetime.timedelta(hours=(24 + timeDeltaHours))
        purgeTeams(teamsToDump)
        FINALIZED_MARKETS.clear()
        markStateDirty()
        persistState(force=True)
        removeClosedDayRuntimeFiles(closed_day)

    current_catalogue = betfairAPI.getMarketCatalogueByEventTypeId(soccerEventTypeID) or []
    near_start_catalogue = betfairAPI.getMarketCatalogueNearStartByEventTypeId(soccerEventTypeID, minutes_before=KO_KEEP_AFTER_SCHEDULE_MINUTES, minutes_after=KO_FOCUS_BEFORE_MINUTES) or []
    refreshCatalogueCaches(current_catalogue, near_start_catalogue)

    event_ids = watchedEventIDs(current_catalogue, near_start_catalogue)
    timelines = requestTrackedTimelines(event_ids) if event_ids else []
    updatePresence(current_catalogue, near_start_catalogue, timelines)

    returned_timeline_ids = [collection.normalise_id(item.get('eventId')) for item in timelines]
    inplay_event_ids = [getEventID(entry) for entry in current_catalogue if getEventID(entry)]
    missing_timeline = len([item for item in inplay_event_ids if item not in returned_timeline_ids])
    reportMarketCatalogue(current_catalogue, [int(item) for item in returned_timeline_ids if item.isdigit()])
    if timelines:
        reportTimeLines(timelines, all=True)
    print(f"MarketCatalogue: {len(current_catalogue)} | NearKO: {len(near_start_catalogue)} | Watched: {len(event_ids)} | Timelines: {len(timelines)} | Missing: {missing_timeline}")

    live_signals = detectLivePhaseSignals(timelines)
    rememberTimelineStates(timelines, live_signals)
    processKOEvents(timelines)
    processCatalogueKickOffFallback(current_catalogue)
    attempted = processSecondHalfStarts(timelines, live_signals)
    retryPendingHT(timelines)

    pending_ht = pendingHTMarketIDs()
    entries = [entry for entry in focusEntries()
               if getMarketID(entry) not in attempted and getMarketID(entry) not in pending_ht]
    ht_focus_ids = {getMarketID(entry) for entry in htFocusEntries()}
    ht_ids = ht_focus_ids - pending_ht
    ht_entries = [entry for entry in entries if getMarketID(entry) in ht_ids]
    other_entries = [entry for entry in entries if getMarketID(entry) not in ht_ids]

    results = pollEntries(other_entries, aggressive=True, point='WIN') if other_entries else {}
    if ht_entries:
        results.update(pollEntries(ht_entries, aggressive=True, point='HT', allow_history_fallback=False))

    applyPendingKO(timelines, results)
    applyPendingHT(timelines, results)
    processFinished(timelines)
    persistState()

    print(f"Tracked: {len(DA_TEAMS)} | Catalogue missing: {len(CATALOGUE_MISSING)} | Timeline missing: {len(TIMELINE_MISSING)} | KO focus: {len(preKOFocusEntries())} | HT focus: {len(htFocusEntries())}")
    print(betfairAPI.datetime.datetime.now())


def stopAndSave(signum=None, frame=None):
    print("Saving collector state before exit...")
    try:
        persistState(force=True)
    except Exception as err:
        print(f"State save error: {err}")
    raise KeyboardInterrupt


def runCollector():
    restoreState()
    compactDumpStateFile(currentUKDay())
    compactDumpStateFile(currentUKDay(-1))
    persistState(force=True)

    try:
        import signal
        signal.signal(signal.SIGTERM, stopAndSave)
    except Exception:
        pass

    while True:
        try:
            main()

            # A bad first HT response remains pending for a fixed 20-second
            # boundary window. Replenish at 5-second spacing rather than making
            # a tight retry burst. Every third replenish tick keeps the normal
            # 15-second focused cycle cadence for unrelated KO/HT work.
            replenish_tick = 0
            while pendingHTMarketIDs():
                time.sleep(HT_REPLENISH_POLL_SECONDS)
                replenish_tick += 1
                if replenish_tick % max(int(FOCUSED_DELAY / HT_REPLENISH_POLL_SECONDS), 1) == 0 and focusEntries():
                    focusedCycle()
                else:
                    htReplenishCycle()

            if focusEntries():
                time.sleep(FOCUSED_DELAY)
                focusedCycle()
                time.sleep(max(NORMAL_DELAY - FOCUSED_DELAY, 0))
            else:
                time.sleep(NORMAL_DELAY)
        except KeyboardInterrupt:
            try:
                persistState(force=True)
            except Exception as err:
                print(f"State save error: {err}")
            break
        except Exception as e:
            print(f"An error occurred: {e}")
            traceback.print_exc()
            try:
                persistState(force=True)
            except Exception as dump_err:
                print(f"State save error: {dump_err}")
            time.sleep(NORMAL_DELAY)


if __name__ == '__main__':
    runCollector()
