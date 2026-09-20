import requests
import os.path
import csv
import pandas as pd
from requests.structures import CaseInsensitiveDict
import src.betfairAPI.betfairAPI as betfairAPI
import src.ufuncs as lib
import src.collection as collection
import src.state_store as state_store
from functools import reduce
from tabulate import tabulate
import io
import time
import copy  # for copy.deepcopy
import traceback
import statistics
import math
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
    requested_count = len(eventIDs)
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
            print(f'Timeline GET {event_time_lines_response.status_code}: requested={requested_count}')
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
    requested_count = len([item for item in str(marketIDs).split(',') if item])
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
        print(f'Price GET {exchange_prices_response.status_code}: markets={requested_count}')
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

        if dictArray is not None:
            # Results CSV column order is part of the file format. Never derive it
            # from a restored/migrated dictionary because JSON key order may differ.
            keys = list(lib.eventTemplateKeys)

            if file_exists and 'a' in mode:
                with io.open(filename, 'r', encoding='utf-8', newline='') as infile:
                    existing_header = next(csv.reader(infile), [])
                if existing_header != keys:
                    raise ValueError(
                        f"results header mismatch in {filename}; refusing unsafe append"
                    )

            with io.open(filename, mode, encoding="utf-8", newline='') as f_object:
                dictwriter_object = csv.DictWriter(
                    f_object, fieldnames=keys, extrasaction='ignore', lineterminator='\r'
                )

                if not file_exists or 'w' in mode:
                    dictwriter_object.writeheader()

                for item in dictArray:
                    source = roundOutputDecimals(canonicalOutput(item))
                    row = {key: source.get(key, '') for key in keys}
                    dictwriter_object.writerow(row)

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


RESULT_FIELDS = list(lib.eventTemplateKeys)


def canonicalOutput(source):
    """Return the 25 result fields in the one authoritative order.

    This is structural normalisation for live/in-memory state and new writes only.
    It does not inspect, rewrite or repair historical results CSV files.
    """
    source = source if isinstance(source, dict) else {}
    return {key: copy.deepcopy(source.get(key, outputTemplate.get(key, ''))) for key in RESULT_FIELDS}


def normaliseTeamOutput(team):
    if not isinstance(team, dict):
        return False
    current = team.get('output', {})
    canonical = canonicalOutput(current)
    changed = not isinstance(current, dict) or list(current.keys()) != RESULT_FIELDS or current != canonical
    team['output'] = canonical
    return changed


def normaliseMatchRecordOutput(record):
    if not isinstance(record, dict):
        return record
    record['o'] = canonicalOutput(record.get('o', {}))
    return record


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


STANDARD_INTERVAL = 30
INTERMEDIATE_INTERVAL = 10
NORMAL_DELAY = STANDARD_INTERVAL
FOCUSED_DELAY = INTERMEDIATE_INTERVAL
KO_FOCUS_BEFORE_MINUTES = 3
KO_BACKUP_MAX_AGE_SECONDS = 180
KO_KEEP_AFTER_SCHEDULE_MINUTES = 20
# Price collection remains on the ordinary 30-second cadence. Allow enough
# time for the first standard cycle after a real kick-off observation.
KO_POST_BOUNDARY_SECONDS = STANDARD_INTERVAL + 10
KO_BOUNDARY_RECONCILE_SECONDS = KO_POST_BOUNDARY_SECONDS + 5
KO_LIVE_DISCOVERY_MAX_AFTER_SCHEDULE_SECONDS = 120
KO_LIVE_ELAPSED_MAX_MINUTES = 3
KO_SYNTHETIC_START_SOURCES = {
    'catalogue_inplay_live', 'catalogue_inplay_late', 'late_rediscovery', 'catalogue_inplay'
}
KO_START_SOURCE_PRIORITY = {
    'catalogue_inplay_late': 0,
    'late_rediscovery': 0,
    'catalogue_inplay': 0,
    'catalogue_inplay_live': 1,
    'status_observed': 2,
    'explicit_observed': 3,
    'explicit_time': 4,
}
FORENSIC_MAX_SNAPSHOTS = 8
HT_FOCUS_AFTER_FIRST_HALF_MINUTES = 0
HT_MARKET_REOPEN_MINUTES = 12
HT_BOUNDARY_CAPTURE_SECONDS = 3
HT_REPLENISH_POLL_SECONDS = INTERMEDIATE_INTERVAL
HT_REPLENISH_WINDOW_SECONDS = 21
DAY_CLOSE_GRACE_HOURS = 4
FINAL_RECOVERY_AFTER_START_SECONDS = 3 * 60 * 60
FINAL_RECOVERY_MAX_ATTEMPTS = 2
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
# Latest complete/plausible 30-second snapshot observed during the half-time recess.
# This is reference/forensic state only; HT output still requires a post-restart capture.
HT_RECESS_STATE = {}
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
FINAL_RECOVERY_STATE = {}
FINALIZED_MARKETS = set()
RESULT_KEYS = {}
LOG_CODES = {}
STATE_DIRTY = False
LIVE_STATE_FILE = 'live_state.json'
LIVE_STATE_SCHEMA = 2
LAST_SAVED_STATE_HASH = None
LIVE_STATE_RESTORED_FROM_BACKUP = False
LOG_LAST_STATE = {}


def markStateDirty():
    global STATE_DIRTY
    STATE_DIRTY = True


def loadLogCodes():
    codes = {}
    try:
        legend = 'codes.csv' if os.path.isfile('codes.csv') else 'log_codes.csv'
        with open(legend, mode='r', encoding='utf-8') as infile:
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


def currentUTCDay(offset_days=0):
    now = betfairAPI.datetime.datetime.now(betfairAPI.datetime.timezone.utc) + betfairAPI.datetime.timedelta(days=offset_days)
    return now.strftime('%Y%m%d')


def matchStartDay(team):
    if not isinstance(team, dict):
        return None
    values = [
        team.get('output', {}).get('Date'),
        team.get('event', {}).get('openDate'),
        team.get('description', {}).get('marketTime')
    ]
    for value in values:
        epoch = parseBetfairTimestamp(value)
        if epoch is not None:
            return betfairAPI.datetime.datetime.fromtimestamp(
                epoch, betfairAPI.datetime.timezone.utc).strftime('%Y%m%d')
    return None


def dayCloseEpoch(day):
    try:
        start = betfairAPI.datetime.datetime.strptime(day, '%Y%m%d').replace(
            tzinfo=betfairAPI.datetime.timezone.utc)
    except Exception:
        return None
    return (start + betfairAPI.datetime.timedelta(
        days=1, hours=DAY_CLOSE_GRACE_HOURS)).timestamp()


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


def koStartSourceReliable(source):
    return bool(source) and source not in KO_SYNTHETIC_START_SOURCES


def reconcileTimelineKickOff(event, now_epoch=None):
    """Replace a synthetic/approximate KO boundary when better timeline evidence arrives.

    This is deliberately allowed to reopen a KO previously marked MISSING. A
    temporary catalogue fallback must never make a later exact KickOff timestamp
    unusable (the delayed-kick-off failure seen in Ascoli v Avellino).
    """
    now_epoch = now_epoch or time.time()
    event_id = collection.normalise_id(event.get('eventId')) if isinstance(event, dict) else ''
    if not event_id:
        return False

    observed_start, observed_source = observedKickoffTime(event, now_epoch)
    if observed_start is None or not observed_source:
        return False

    current_start = FIRST_HALF_START_TIMES.get(event_id)
    current_source = FIRST_HALF_START_SOURCE.get(event_id)
    current_rank = KO_START_SOURCE_PRIORITY.get(current_source, 1 if koStartSourceReliable(current_source) else 0)
    observed_rank = KO_START_SOURCE_PRIORITY.get(observed_source, 1 if koStartSourceReliable(observed_source) else 0)

    replace = current_start is None
    if not replace and observed_rank > current_rank:
        replace = True
    if not replace and current_source in KO_SYNTHETIC_START_SOURCES and observed_source not in KO_SYNTHETIC_START_SOURCES:
        replace = True

    if not replace:
        return False

    previous_source = current_source
    FIRST_HALF_START_TIMES[event_id] = observed_start
    FIRST_HALF_START_SOURCE[event_id] = observed_source

    team = findTeamByEvent(event_id)
    if team is not None:
        market_id = getMarketID(team)
        state = KO_CAPTURE_STATE.setdefault(market_id, {})
        previous_phase = state.get('phase')
        state.update({
            'event_id': event_id,
            'start': observed_start,
            'source': observed_source,
            'deadline': observed_start + KO_BOUNDARY_RECONCILE_SECONDS,
            'observed_at': now_epoch,
        })

        # A synthetic boundary may have expired before Betfair's timeline became
        # available. Reopen that MISS and re-run selection against the stored
        # 30-second price history around the real boundary.
        if previous_phase == 'MISSING' and (
                previous_source in KO_SYNTHETIC_START_SOURCES or observed_rank > current_rank):
            KO_MISSING.discard(market_id)
            state['phase'] = 'RECOVERY'
            evidence = CAPTURE_EVIDENCE.get(market_id)
            if isinstance(evidence, dict):
                ko_evidence = evidence.get('KO')
                if isinstance(ko_evidence, dict) and ko_evidence.get('method') == 'MISS':
                    evidence.pop('KO', None)

        # Compatibility with a state produced by the older collector: if a KO
        # was already frozen against a synthetic scheduled/catalogue boundary,
        # replace it only when the stored price history can prove a valid boundary
        # around the newly observed real kick-off. Otherwise retain the old value.
        elif previous_phase == 'FROZEN' and previous_source in KO_SYNTHETIC_START_SOURCES:
            corrected, _ = selectKOBoundary(team, observed_start, now_epoch)
            if corrected is not None:
                freezeKO(team, corrected)

    markStateDirty()
    return True

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
        match_date = entry['output'].get('Date', '')
        home = entry['output'].get('Home', '')
        away = entry['output'].get('Away', '')
    else:
        match_date = entry.get('event', {}).get('openDate', '')
        home, away = getHomeAway(entry)

    date_epoch = parseBetfairTimestamp(match_date)
    if date_epoch is not None:
        date = betfairAPI.datetime.datetime.fromtimestamp(date_epoch, betfairAPI.datetime.timezone.utc).strftime('%Y%m%d')
    else:
        date = currentUTCDay()

    code = LOG_CODES.get(key, key)
    event_id = getEventID(entry) if isinstance(entry, dict) else ''
    state_key = (event_id, point)
    state_value = (code, str(detail))
    if LOG_LAST_STATE.get(state_key) == state_value:
        return
    LOG_LAST_STATE[state_key] = state_value

    filename = f"{date}_log.txt"
    file_exists = os.path.isfile(filename)
    at_utc = betfairAPI.datetime.datetime.now(betfairAPI.datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    with open(filename, mode='a', encoding='utf-8', newline='') as outfile:
        writer = csv.writer(outfile, lineterminator='\n')
        if not file_exists:
            writer.writerow(['AtUTC', 'MatchDate', 'Home', 'Away', 'Code', 'Point', 'Details'])
        writer.writerow([at_utc, match_date, home, away, code, point, detail])
    print(f"{at_utc},{match_date},{home},{away},{code},{point},{detail}")


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


def _compactSnapshotForState(snapshot):
    if not isinstance(snapshot, dict):
        return None
    result = {
        't': snapshot.get('time'),
        'b': list(snapshot.get('back', [])),
        'l': list(snapshot.get('lay', [])),
        'q': snapshot.get('book'),
        'ip': snapshot.get('inplay'),
        'st': snapshot.get('status')
    }
    if snapshot.get('request_time') is not None:
        result['rq'] = snapshot.get('request_time')
    if snapshot.get('response_time') is not None:
        result['rs'] = snapshot.get('response_time')
    return result


def _expandSnapshotFromState(snapshot, event_id='', market_id=''):
    if not isinstance(snapshot, dict):
        return None
    return {
        'event_id': event_id,
        'market_id': market_id,
        'back': list(snapshot.get('b', [])),
        'lay': list(snapshot.get('l', [])),
        'book': snapshot.get('q'),
        'inplay': snapshot.get('ip'),
        'status': snapshot.get('st'),
        'time': snapshot.get('t') or time.time(),
        'request_time': snapshot.get('rq'),
        'response_time': snapshot.get('rs')
    }


def _compactTimelineForState(event):
    if not isinstance(event, dict):
        return {}
    score = event.get('score', {}) or {}
    home = score.get('home', {}) or {}
    away = score.get('away', {}) or {}
    events = []
    code_map = {
        'KickOff': 'K',
        'FirstHalfEnd': 'F',
        'SecondHalfKickOff': 'S',
        'Finished': 'E',
        'SecondHalfEnd': 'E',
        'Goal': 'G'
    }
    for item in event.get('updateDetails', []) or []:
        kind = item.get('updateType') or item.get('type')
        code = code_map.get(kind)
        if code is None:
            continue
        match_time = item.get('matchTime')
        if match_time in [None, '']:
            match_time = item.get('elapsedRegularTime')
        added = item.get('elapsedAddedTime')
        side = item.get('team', '')
        update_time = item.get('updateTime', '')
        events.append([code, match_time, added, side, update_time])
    return {
        'ph': event.get('inPlayMatchStatus', ''),
        'sc': [
            home.get('score', ''), away.get('score', ''),
            home.get('halfTimeScore', ''), away.get('halfTimeScore', ''),
            home.get('fullTimeScore', ''), away.get('fullTimeScore', '')
        ],
        'ev': events
    }


def _expandTimelineFromState(record):
    timeline = record.get('tl', {}) if isinstance(record, dict) else {}
    score_values = list(timeline.get('sc', [])) + [''] * 6
    home_name = record.get('h', '')
    away_name = record.get('a', '')
    reverse_map = {'K': 'KickOff', 'F': 'FirstHalfEnd', 'S': 'SecondHalfKickOff', 'E': 'Finished', 'G': 'Goal'}
    details = []
    for packed in timeline.get('ev', []) or []:
        if not isinstance(packed, list) or not packed:
            continue
        code = packed[0]
        kind = reverse_map.get(code)
        if kind is None:
            continue
        match_time = packed[1] if len(packed) > 1 else None
        added = packed[2] if len(packed) > 2 else None
        side = packed[3] if len(packed) > 3 else ''
        update_time = packed[4] if len(packed) > 4 else ''
        item = {'type': kind, 'updateType': kind}
        if match_time not in [None, '']:
            item['matchTime'] = match_time
            item['elapsedRegularTime'] = match_time
        if added not in [None, '']:
            item['elapsedAddedTime'] = added
        if side:
            item['team'] = side
            if side == 'home':
                item['teamName'] = home_name
            elif side == 'away':
                item['teamName'] = away_name
        if update_time:
            item['updateTime'] = update_time
        details.append(item)
    return {
        'eventId': record.get('id', ''),
        'inPlayMatchStatus': timeline.get('ph', ''),
        'elapsedRegularTime': timeline.get('el'),
        'score': {
            'home': {'name': home_name, 'score': score_values[0], 'halfTimeScore': score_values[2], 'fullTimeScore': score_values[4]},
            'away': {'name': away_name, 'score': score_values[1], 'halfTimeScore': score_values[3], 'fullTimeScore': score_values[5]}
        },
        'updateDetails': details
    }


def _compactEvidencePoint(item):
    if not isinstance(item, dict):
        return None
    selected = item.get('selected')
    if selected is None:
        history = item.get('history', []) or []
        selected = history[-1] if history else None
    result = {
        'm': item.get('method', 'MISS'),
        's': _compactSnapshotForState(selected)
    }
    if item.get('inferred'):
        result['i'] = copy.deepcopy(item.get('inferred'))
    return result


def _compactPriceState(market_id):
    clean = list(CLEAN_PRICE_HISTORY.get(market_id, []) or [])
    result = {}
    if clean:
        result['c'] = _compactSnapshotForState(clean[-1])
    return result


def matchRecordFromTeam(team, archive_reason=None):
    event_id = getEventID(team)
    market_id = getMarketID(team)
    output = canonicalOutput(team.get('output', {}))
    home, away = getHomeAway(team)
    runners = []
    for runner in orderedCatalogueRunners(team):
        runners.append([runner.get('selectionId'), runner.get('runnerName', ''), runner.get('sortPriority')])
    timeline = LATEST_TIMELINES.get(event_id) or {
        'eventId': event_id,
        'score': team.get('score', {}),
        'updateDetails': team.get('updateDetails', [])
    }
    evidence = CAPTURE_EVIDENCE.get(market_id, {}) or {}
    flags = []
    if market_id in KO_MISSING:
        flags.append('K0')
    if not all(float(output.get(key, 0) or 0) > 0 for key in ['HT_1', 'HT_2', 'HT_X']):
        flags.append('H0')
    if output.get('HT_Home', '') in ['', '-1'] or output.get('HT_Away', '') in ['', '-1']:
        flags.append('S0')
    if event_id in CATALOGUE_MISSING:
        flags.append('CM')
    if event_id in TIMELINE_MISSING:
        flags.append('TM')

    record = {
        'v': LIVE_STATE_SCHEMA,
        'id': event_id,
        'mid': market_id,
        'sid': runners,
        'dt': output.get('Date') or team.get('event', {}).get('openDate', ''),
        'cp': output.get('Competition') or team.get('competition', {}).get('name', ''),
        'h': output.get('Home') or home,
        'a': output.get('Away') or away,
        'o': output,
        'tl': _compactTimelineForState(timeline),
        'tr': {
            'k': [FIRST_HALF_START_TIMES.get(event_id), FIRST_HALF_START_SOURCE.get(event_id)],
            'f': [FIRST_HALF_END_TIMES.get(event_id), FIRST_HALF_END_SCORES.get(event_id)],
            's': [SECOND_HALF_START_TIMES.get(event_id), SECOND_HALF_START_SOURCE.get(event_id)]
        },
        'od': {
            'ko': _compactEvidencePoint(evidence.get('KO')),
            'ht': _compactEvidencePoint(evidence.get('HT'))
        },
        'px': _compactPriceState(market_id),
        'fl': flags,
        'rt': {
            'ko': copy.deepcopy(KO_CAPTURE_STATE.get(market_id, {})),
            'hr': _compactSnapshotForState(HT_RECESS_STATE.get(event_id)),
            'hla': HT_REPLENISH_LAST_ATTEMPT.get(event_id),
            'fr': copy.deepcopy(FINAL_RECOVERY_STATE.get(event_id))
        }
    }
    if archive_reason:
        record['ar'] = archive_reason
    return record


def teamFromMatchRecord(record):
    if not isinstance(record, dict):
        return None
    home = record.get('h', '')
    away = record.get('a', '')
    dt = record.get('dt', '')
    runners = []
    for index, packed in enumerate(record.get('sid', []) or []):
        if not isinstance(packed, list) or not packed:
            continue
        selection_id = packed[0]
        runner_name = packed[1] if len(packed) > 1 else ''
        sort_priority = packed[2] if len(packed) > 2 else index + 1
        runners.append({'selectionId': selection_id, 'runnerName': runner_name, 'sortPriority': sort_priority})
    if not runners and home and away:
        runners = [
            {'selectionId': None, 'runnerName': home, 'sortPriority': 1},
            {'selectionId': None, 'runnerName': away, 'sortPriority': 2},
            {'selectionId': None, 'runnerName': 'The Draw', 'sortPriority': 3}
        ]
    timeline = _expandTimelineFromState(record)
    team = {
        'marketId': record.get('mid', ''),
        'marketName': 'Match Odds',
        'event': {'id': record.get('id', ''), 'openDate': dt, 'name': f"{home} v {away}"},
        'competition': {'name': record.get('cp', '')},
        'description': {'marketTime': dt, 'marketType': 'MATCH_ODDS'},
        'runners': runners,
        'score': timeline.get('score', {}),
        'updateDetails': timeline.get('updateDetails', []),
        'output': canonicalOutput(record.get('o', {}))
    }
    team['output']['Date'] = team['output'].get('Date') or dt
    team['output']['Competition'] = team['output'].get('Competition') or record.get('cp', '')
    team['output']['Home'] = team['output'].get('Home') or home
    team['output']['Away'] = team['output'].get('Away') or away
    return team


def _restoreMatchRecord(record):
    team = teamFromMatchRecord(record)
    if team is None:
        return None
    event_id = getEventID(team)
    market_id = getMarketID(team)
    timeline = _expandTimelineFromState(record)
    LATEST_TIMELINES[event_id] = timeline

    transitions = record.get('tr', {}) or {}
    k = transitions.get('k') or [None, None]
    f = transitions.get('f') or [None, None]
    sh = transitions.get('s') or [None, None]
    if len(k) > 0 and k[0] is not None:
        FIRST_HALF_START_TIMES[event_id] = k[0]
        if len(k) > 1 and k[1]:
            FIRST_HALF_START_SOURCE[event_id] = k[1]
    if len(f) > 0 and f[0] is not None:
        FIRST_HALF_END_TIMES[event_id] = f[0]
        if len(f) > 1 and f[1] is not None:
            FIRST_HALF_END_SCORES[event_id] = f[1]
    if len(sh) > 0 and sh[0] is not None:
        SECOND_HALF_START_TIMES[event_id] = sh[0]
        if len(sh) > 1 and sh[1]:
            SECOND_HALF_START_SOURCE[event_id] = sh[1]

    evidence = {}
    for point, key in [('KO', 'ko'), ('HT', 'ht')]:
        packed = (record.get('od', {}) or {}).get(key)
        if not isinstance(packed, dict):
            continue
        selected = _expandSnapshotFromState(packed.get('s'), event_id, market_id)
        item = {'method': packed.get('m', 'MISS'), 'selected': selected, 'history': [selected] if selected else []}
        if packed.get('i'):
            item['inferred'] = copy.deepcopy(packed.get('i'))
        evidence[point] = item
    if evidence:
        CAPTURE_EVIDENCE[market_id] = evidence

    price_items = []
    clean_items = []
    px = record.get('px', {}) or {}
    for key in ['r', 'c']:
        expanded = _expandSnapshotFromState(px.get(key), event_id, market_id)
        if expanded:
            price_items.append(expanded)
            if key == 'c':
                clean_items.append(expanded)
    for point in evidence.values():
        selected = point.get('selected')
        if selected:
            price_items.append(selected)
            if collection.book_is_plausible(selected.get('back', [])):
                clean_items.append(selected)
    if price_items:
        unique = {item.get('time', index): item for index, item in enumerate(price_items)}
        PRICE_HISTORY[market_id] = [unique[key] for key in sorted(unique, key=lambda x: str(x))][-4:]
    if clean_items:
        unique = {item.get('time', index): item for index, item in enumerate(clean_items)}
        CLEAN_PRICE_HISTORY[market_id] = [unique[key] for key in sorted(unique, key=lambda x: str(x))][-4:]

    flags = set(record.get('fl', []) or [])
    if 'K0' in flags:
        KO_MISSING.add(market_id)
    if 'CM' in flags:
        CATALOGUE_MISSING.add(event_id)
    if 'TM' in flags:
        TIMELINE_MISSING.add(event_id)
    runtime = record.get('rt', {}) or {}
    if isinstance(runtime.get('ko'), dict) and runtime.get('ko'):
        KO_CAPTURE_STATE[market_id] = copy.deepcopy(runtime.get('ko'))
    restored_recess = _expandSnapshotFromState(runtime.get('hr'), event_id, market_id)
    if restored_recess is not None:
        HT_RECESS_STATE[event_id] = restored_recess
    if runtime.get('hla') is not None:
        HT_REPLENISH_LAST_ATTEMPT[event_id] = runtime.get('hla')
    if isinstance(runtime.get('fr'), dict) and runtime.get('fr'):
        FINAL_RECOVERY_STATE[event_id] = copy.deepcopy(runtime.get('fr'))
    return team


def _liveStatePayload():
    records = {}
    for team in DA_TEAMS:
        event_id = getEventID(team)
        if not event_id:
            raise RuntimeError('Active match has no event id; refusing unsafe live-state save')
        if event_id in records:
            raise RuntimeError(f'Duplicate active event id {event_id}; refusing unsafe live-state save')
        records[event_id] = matchRecordFromTeam(team)
    return {'v': LIVE_STATE_SCHEMA, 'matches': records}


def saveLiveState(force=False):
    global STATE_DIRTY, LAST_SAVED_STATE_HASH, LIVE_STATE_RESTORED_FROM_BACKUP
    if not force and not STATE_DIRTY:
        return False
    payload = _liveStatePayload()
    current_hash = state_store.state_hash(payload)
    if (LAST_SAVED_STATE_HASH == current_hash and os.path.isfile(LIVE_STATE_FILE)
            and not LIVE_STATE_RESTORED_FROM_BACKUP):
        STATE_DIRTY = False
        return False

    # If the main file was unreadable and state came from .bak, do not rotate the
    # unreadable main file over the good backup. Rebuild live_state.json in place
    # and keep the known-good .bak until the next normal state change.
    keep_backup = not LIVE_STATE_RESTORED_FROM_BACKUP
    LAST_SAVED_STATE_HASH = state_store.atomic_write_json(
        payload, LIVE_STATE_FILE, backup=keep_backup
    )
    LIVE_STATE_RESTORED_FROM_BACKUP = False
    STATE_DIRTY = False
    return True


def persistState(force=False):
    return saveLiveState(force=force)


def _restoreDict(target, data):
    target.clear()
    if isinstance(data, dict):
        target.update(data)


def restoreCheckpoint(data):
    global DA_TEAMS
    DA_TEAMS = data.get('DA_TEAMS', []) if isinstance(data.get('DA_TEAMS', []), list) else []
    for team in DA_TEAMS:
        normaliseTeamOutput(team)
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


def _legacyStateFiles():
    checkpoints = []
    run_dumps = []
    for filename in os.listdir('.'):
        target = None
        if filename.endswith('_checkpoint.json'):
            target = checkpoints
        elif filename.endswith('_run_dump.json'):
            target = run_dumps
        if target is None:
            continue
        try:
            target.append((os.path.getmtime(filename), filename))
        except OSError:
            pass
    # Checkpoints carry richer operational state and are therefore authoritative.
    # run_dump is only a compatibility fallback when no usable checkpoint exists.
    return ([name for _, name in sorted(checkpoints, reverse=True)] +
            [name for _, name in sorted(run_dumps, reverse=True)])


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
        if source in KO_SYNTHETIC_START_SOURCES and market_id in KO_MISSING:
            KO_MISSING.discard(market_id)
            KO_CAPTURE_STATE.setdefault(market_id, {}).update({
                'event_id': event_id, 'start': start, 'source': source, 'phase': 'RECOVERY'
            })
            markStateDirty()
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


def _loadNewLiveState():
    global DA_TEAMS, LAST_SAVED_STATE_HASH, LIVE_STATE_RESTORED_FROM_BACKUP
    for filename in [LIVE_STATE_FILE, LIVE_STATE_FILE + '.bak']:
        if not os.path.isfile(filename):
            continue
        data = state_store.read_json(filename)
        if not isinstance(data, dict) or data.get('v') != LIVE_STATE_SCHEMA or not isinstance(data.get('matches'), dict):
            continue
        DA_TEAMS = []
        for event_id, record in data['matches'].items():
            team = _restoreMatchRecord(record)
            if team is not None:
                DA_TEAMS.append(team)
        LAST_SAVED_STATE_HASH = state_store.state_hash(data)
        LIVE_STATE_RESTORED_FROM_BACKUP = filename.endswith('.bak')
        if state_store.state_hash(_liveStatePayload()) != LAST_SAVED_STATE_HASH:
            markStateDirty()
        print(f"RESTORE: {len(DA_TEAMS)} tracked match(es) from {filename}")
        return True
    return False


def _archiveClosedRestoredMatches(reason='R'):
    now_epoch = time.time()
    groups = {}
    for team in list(DA_TEAMS):
        day = matchStartDay(team)
        close_epoch = dayCloseEpoch(day) if day else None
        if close_epoch is not None and now_epoch >= close_epoch:
            groups.setdefault(day, []).append(team)
    for day, teams in sorted(groups.items()):
        saveDayDump(day, teams, archive_reason=reason)
        purgeTeams(teams)
        print(f"RESTORE ARCHIVE: {len(teams)} stale match(es) -> {day}_dump.json")


def _loadLegacyActiveState():
    global DA_TEAMS
    files = _legacyStateFiles()
    for filename in files:
        data = lib.readFromJSON(filename)
        if filename.endswith('_checkpoint.json') and isinstance(data, dict) and isinstance(data.get('DA_TEAMS'), list):
            restoreCheckpoint(data)
            repairRestoredKOState()
            repairRestoredHTState()
            print(f"LEGACY RESTORE: {len(DA_TEAMS)} tracked match(es) from {filename}")
            return True
        if filename.endswith('_run_dump.json') and isinstance(data, list):
            DA_TEAMS = data
            for team in DA_TEAMS:
                normaliseTeamOutput(team)
            restoreLegacyOperationalState()
            repairRestoredKOState()
            repairRestoredHTState()
            markStateDirty()
            print(f"LEGACY RESTORE: {len(DA_TEAMS)} tracked match(es) from {filename}")
            return True
    return False


def restoreState():
    if _loadNewLiveState():
        persistState(force=True)
        return True
    if _loadLegacyActiveState():
        migrateLegacyDumpFiles()
        persistState(force=True)
        return True
    migrateLegacyDumpFiles()
    persistState(force=True)
    return False


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

        if hasTransition(event, 'KickOff'):
            changed_boundary = reconcileTimelineKickOff(event, now_epoch)
            kickoff = FIRST_HALF_START_TIMES.get(event_id)
            source = FIRST_HALF_START_SOURCE.get(event_id)
            team = findTeamByEvent(event_id)
            if team is not None and kickoff is not None and not koIsFilled(team):
                ensureKOState(team, kickoff, source or 'timeline')

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


def _storedPreKOSnapshot(team):
    state = KO_CAPTURE_STATE.get(getMarketID(team), {}) or {}
    snapshot = state.get('pre')
    return copy.deepcopy(snapshot) if isinstance(snapshot, dict) else None


def _koMaterialEventBeforePost(team, post_snapshot):
    """Return a reason only when a material event predates the post-KO snapshot."""
    if not isinstance(post_snapshot, dict):
        return None
    event_id = getEventID(team)
    if event_id in TIMELINE_MISSING:
        return 'TIMELINE_MISSING'

    event = LATEST_TIMELINES.get(event_id, {}) or {}
    post_time = post_snapshot.get('time') or time.time()
    start = FIRST_HALF_START_TIMES.get(event_id)
    untimed_material = False

    for detail in event.get('updateDetails', []) or []:
        event_type = str(detail.get('updateType') or detail.get('type') or '')
        kind = event_type.lower().replace('_', '')
        if kind not in {'goal', 'redcard', 'sendingoff', 'dismissal'}:
            continue

        event_time = parseBetfairTimestamp(detail.get('updateTime'))
        if event_time is not None and event_time <= 86400:
            event_time = None
        if event_time is None and start is not None:
            try:
                elapsed = detail.get('elapsedRegularTime')
                if elapsed in [None, '']:
                    elapsed = detail.get('matchTime')
                if elapsed not in [None, '']:
                    event_time = start + float(elapsed) * 60
            except Exception:
                event_time = None

        if event_time is None:
            untimed_material = True
            continue
        if event_time <= post_time:
            return event_type.upper() or 'MATERIAL_EVENT'

    # Only use the current score as a conservative fallback when material event
    # timing itself is unavailable. A later goal must not invalidate a clean
    # post-KO snapshot during restore/recovery.
    if untimed_material:
        score = currentScore(event)
        if score is not None and (score[0] > 0 or score[1] > 0):
            return f"GOAL_SCORE_{score[0]}-{score[1]}"
    return None


def _fmtOdds(prices):
    labels = ['1', '2', 'X']
    values = []
    for label, value in zip(labels, prices or []):
        if value is None:
            values.append(f"{label}:NA")
        else:
            values.append(f"{label}:{float(value):.2f}")
    return '|'.join(values)


def _koTripletTickMove(first, second):
    """Total absolute Betfair-tick movement across 1/2/X."""
    if not isinstance(first, (list, tuple)) or not isinstance(second, (list, tuple)):
        return None
    if len(first) != 3 or len(second) != 3:
        return None
    distances = []
    for before, after in zip(first, second):
        if before is None or after is None or before <= 1.0 or after <= 1.0:
            return None
        distance = collection._tick_distance(before, after)
        if distance >= 9999:
            return None
        distances.append(int(distance))
    return sum(distances)


def logKOBoundaryMovement(team, pre_result, post_result):
    """Log pre/post KO only when the boundary move is unusually large.

    The baseline is the sequence of valid 30-second pre-KO triplet movements
    collected during the final three minutes. A boundary move is logged only
    when it is clearly above both the typical and the largest recent move.
    """
    if pre_result is None or post_result is None:
        return
    pre = list(pre_result.get('back', []))
    post = list(post_result.get('back', []))
    final_move = _koTripletTickMove(pre, post)
    if final_move is None:
        return

    state = KO_CAPTURE_STATE.get(getMarketID(team), {}) or {}
    recent = [int(value) for value in (state.get('pm') or [])
              if isinstance(value, (int, float)) and value >= 0]
    if len(recent) < 2:
        return

    expected = statistics.median(recent)
    recent_peak = max(recent)
    threshold = max(4, math.ceil(expected * 2.5), recent_peak + 2)
    if final_move < threshold:
        return

    logIssue(team, 'ko_boundary_move', 'KO_MOVE',
             f"pre={_fmtOdds(pre)};post={_fmtOdds(post)}")


def selectKOBoundary(team, start, now_epoch=None):
    now_epoch = now_epoch or time.time()
    event_id = getEventID(team)
    market_id = getMarketID(team)
    source = FIRST_HALF_START_SOURCE.get(event_id, 'unknown')
    clean_reference = [item for item in CLEAN_PRICE_HISTORY.get(market_id, [])
                       if (item.get('time', 0) or 0) <= start]

    # The explicit saved pre-KO snapshot is authoritative as the fallback. It is
    # collected only on the ordinary 30-second cycle during the final 3 minutes.
    pre_result = None
    stored_pre = _storedPreKOSnapshot(team)
    if stored_pre is not None:
        pre_result = _recoverBoundarySnapshot(team, stored_pre, clean_reference)

    # Compatibility with state created before the explicit pre-KO slot existed.
    if pre_result is None:
        for item in _koPreCandidates(team, start, source):
            recovered = _recoverBoundarySnapshot(team, item, clean_reference)
            if recovered is not None:
                pre_result = recovered
                if snapshotIsKosher(recovered['selected'], clean_reference):
                    clean_reference.append(recovered['selected'])

    post_raw = _koFirstPostCandidate(team, start)
    post_result = _recoverBoundarySnapshot(team, post_raw, clean_reference) if post_raw is not None else None

    # Catalogue/scheduled-time fallbacks do not define the real KO boundary.
    # Keep collecting 30-second evidence and timeline updates until a genuine
    # KickOff observation replaces the synthetic start.
    if source in KO_SYNTHETIC_START_SOURCES:
        return None, False

    if pre_result is not None and post_result is not None:
        event_reason = _koMaterialEventBeforePost(team, post_result.get('selected'))
        if event_reason:
            pre_result['method'] = 'BOUNDARY_PRE_EVENT'
            return pre_result, True

        # Normal case: use the first clean post-KO price even if it moved from
        # the pre-KO market. Only unusually large boundary moves are logged.
        logKOBoundaryMovement(team, pre_result, post_result)
        post_result['method'] = 'BOUNDARY_POST'
        return post_result, True

    if post_result is not None:
        # A post-kick-off price can stand alone only when the kick-off boundary
        # came from a real timeline observation and the same cycle has no sign
        # that a goal/red card already contaminated that first post-KO price.
        if source not in KO_SYNTHETIC_START_SOURCES:
            event_reason = _koMaterialEventBeforePost(team, post_result.get('selected'))
            if event_reason is None:
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
            source = FIRST_HALF_START_SOURCE.get(event_id, state.get('source', 'unknown'))
            if source in KO_SYNTHETIC_START_SOURCES:
                state.update({'event_id': event_id, 'start': start, 'source': source,
                              'phase': 'RECOVERY',
                              'deadline': start + KO_BOUNDARY_RECONCILE_SECONDS})
                KO_MISSING.discard(market_id)
                markStateDirty()
                continue
            state.update({'event_id': event_id, 'start': start,
                          'source': source, 'phase': 'MISSING',
                          'deadline': start + KO_BOUNDARY_RECONCILE_SECONDS})
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

        # Existing boundaries are retried at the next 10-second scheduler opportunity.
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
    if any(team['output'].get(key, 0) for key in ['KO_1', 'KO_2', 'KO_X']):
        return True
    market_id = getMarketID(team)
    if market_id not in KO_MISSING:
        return False
    event_id = getEventID(team)
    source = FIRST_HALF_START_SOURCE.get(event_id) or (KO_CAPTURE_STATE.get(market_id, {}) or {}).get('source')
    return source not in KO_SYNTHETIC_START_SOURCES


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
        start_source = FIRST_HALF_START_SOURCE.get(event_id)
        if actual_start is None or not koStartSourceReliable(start_source):
            # A scheduled/catalogue fallback is not the real KO boundary. Keep
            # timeline watching through delayed starts until reliable evidence arrives.
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
        source = FIRST_HALF_START_SOURCE.get(event_id)
        if start is not None and koStartSourceReliable(source):
            if start - (KO_FOCUS_BEFORE_MINUTES * 60) <= now_epoch <= start + KO_BOUNDARY_RECONCILE_SECONDS:
                entries[getMarketID(team)] = team
        elif not koStartSourceReliable(source):
            market_time = scheduledStart(team)
            if market_time is not None and market_time - (KO_FOCUS_BEFORE_MINUTES * 60) <= now_epoch <= market_time + (KO_KEEP_AFTER_SCHEDULE_MINUTES * 60):
                entries[getMarketID(team)] = team
    return list(entries.values())

def koStandardPriceEntries():
    """KO price work for the ordinary 30-second cycle only.

    Start three minutes before scheduled KO, retain the latest complete/plausible
    pre-KO book and make one first post-KO observation on the first standard
    cycle after the real start has been detected.
    """
    now_epoch = time.time()
    entries = {}

    for entry in NEAR_START_CATALOGUE.values():
        if entryAlreadyFinalized(entry):
            continue
        market_time = scheduledStart(entry)
        if market_time is None:
            continue
        event_id = getEventID(entry)
        team = findTeamByEvent(event_id)
        actual_start = FIRST_HALF_START_TIMES.get(event_id)
        start_source = FIRST_HALF_START_SOURCE.get(event_id)

        if actual_start is None or not koStartSourceReliable(start_source):
            in_window = (market_time - (KO_FOCUS_BEFORE_MINUTES * 60)
                         <= now_epoch
                         <= market_time + (KO_KEEP_AFTER_SCHEDULE_MINUTES * 60))
        else:
            in_window = now_epoch <= actual_start + KO_POST_BOUNDARY_SECONDS

        if not in_window:
            continue
        if team is None:
            team = initialiseTeam(entry, LATEST_TIMELINES.get(event_id, {}))
        if team is not None and not koIsFilled(team):
            entries[getMarketID(team)] = team

    # A pre-KO team is deliberately created during the final three minutes so
    # its latest valid snapshot survives a process restart in live_state.json.
    for team in DA_TEAMS:
        if koIsFilled(team):
            continue
        event_id = getEventID(team)
        actual_start = FIRST_HALF_START_TIMES.get(event_id)
        start_source = FIRST_HALF_START_SOURCE.get(event_id)
        if actual_start is not None and koStartSourceReliable(start_source):
            if now_epoch <= actual_start + KO_POST_BOUNDARY_SECONDS:
                entries[getMarketID(team)] = team
            continue
        market_time = scheduledStart(team)
        if market_time is not None and (market_time - (KO_FOCUS_BEFORE_MINUTES * 60)
                                        <= now_epoch
                                        <= market_time + (KO_KEEP_AFTER_SCHEDULE_MINUTES * 60)):
            entries[getMarketID(team)] = team

    return list(entries.values())


def htRecessPriceEntries():
    """Half-time recess prices sampled only on the ordinary 30-second cycle."""
    entries = []
    for team in htFocusEntries():
        if getEventID(team) in SECOND_HALF_START_TIMES:
            continue
        entries.append(team)
    return entries


def rememberLatestPreKO(entries, results):
    now_epoch = time.time()
    for entry in entries:
        market_id = getMarketID(entry)
        result = results.get(market_id) or {}
        # LAST is an older fallback, not a new 30-second observation.
        if result.get('method') in {'LAST', 'MISS'}:
            continue
        snapshot = result.get('current_raw')
        if snapshot is None or snapshot.get('inplay') is True:
            continue
        if not collection.book_is_plausible(snapshot.get('back', [])):
            continue

        team = findTeamByEvent(getEventID(entry)) or entry
        event_id = getEventID(team)
        start = FIRST_HALF_START_TIMES.get(event_id)
        start_source = FIRST_HALF_START_SOURCE.get(event_id)
        # Only a genuine timeline KO boundary can close the pre-KO slot. A
        # scheduled/catalogue fallback must not discard valid delayed pre-KO books.
        if start is not None and koStartSourceReliable(start_source) and (snapshot.get('time', now_epoch) or now_epoch) >= start:
            continue

        state = KO_CAPTURE_STATE.setdefault(market_id, {})
        state['event_id'] = getEventID(team)

        # Keep only tiny movement statistics, not every pre-KO snapshot. Each
        # value is the total 1/2/X Betfair-tick movement from one valid 30-second
        # observation to the next during the final three minutes.
        previous = state.get('pre')
        previous_time = (previous or {}).get('time') if isinstance(previous, dict) else None
        current_time = snapshot.get('time', now_epoch)
        if isinstance(previous, dict) and previous_time != current_time:
            movement = _koTripletTickMove(previous.get('back', []), snapshot.get('back', []))
            if movement is not None:
                moves = list(state.get('pm') or [])
                moves.append(int(movement))
                state['pm'] = moves[-6:]

        state['pre'] = compactHistorySnapshot(snapshot)
        state['pre_observed_at'] = current_time
        if state.get('phase') not in {'FROZEN', 'MISSING'}:
            state['phase'] = 'PREWATCH'
        markStateDirty()


def rememberLatestHTRecess(entries, results):
    for team in entries:
        event_id = getEventID(team)
        if event_id in SECOND_HALF_START_TIMES:
            continue
        result = results.get(getMarketID(team)) or {}
        if result.get('method') in {'LAST', 'MISS'}:
            continue
        snapshot = result.get('current_raw')
        if snapshot is None or not collection.book_is_plausible(snapshot.get('back', [])):
            continue
        # Store only a confirmed/reconstructed recess, not the broad 55-minute
        # fallback watch used when FirstHalfEnd itself is missing.
        event = LATEST_TIMELINES.get(event_id, {}) or {}
        if event_id not in FIRST_HALF_END_TIMES and event.get('inPlayMatchStatus') != 'FirstHalfEnd':
            continue
        HT_RECESS_STATE[event_id] = compactHistorySnapshot(snapshot)
        markStateDirty()


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
    if (event.get('inPlayMatchStatus') == 'Finished' or hasTransition(event, 'Finished') or
            hasTransition(event, 'SecondHalfEnd')):
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
    HT_RECESS_STATE.pop(event_id, None)
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
    FINAL_RECOVERY_STATE.pop(event_id, None)

def finaliseTeam(team, event):
    normaliseTeamOutput(team)
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

    day = matchStartDay(team)
    if day is None:
        day = currentUTCDay()
        logIssue(team, 'date_route_fallback', 'FINAL', 'missing_start_date')
    filename = f"{day}_results.csv"
    key = _resultKey(team['output'])
    keys = resultKeys(filename)

    saved = key in keys
    if not saved:
        saved = saveDictArrayToCSV(filename, [team['output']], 'a')
        if saved:
            keys.add(key)

    if saved:
        if captureNeedsForensicState(team):
            saveProblemRecord(day, team, 'P')
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

def _legacyTimelineToCompact(timeline):
    if not isinstance(timeline, dict):
        return {}
    score = timeline.get('score', {}) or {}
    home = score.get('home', {}) or {}
    away = score.get('away', {}) or {}
    code_map = {'KickOff': 'K', 'FirstHalfEnd': 'F', 'SecondHalfKickOff': 'S',
                'Finished': 'E', 'SecondHalfEnd': 'E', 'Goal': 'G'}
    events = []
    for item in timeline.get('events', []) or timeline.get('updateDetails', []) or []:
        kind = item.get('updateType') or item.get('type')
        code = code_map.get(kind)
        if code is None:
            continue
        mt = item.get('matchTime')
        if mt in [None, '']:
            mt = item.get('elapsedRegularTime')
        events.append([code, mt, item.get('elapsedAddedTime'), item.get('team', ''), item.get('updateTime', '')])
    return {
        'ph': timeline.get('status', timeline.get('inPlayMatchStatus', '')),
        'el': timeline.get('elapsed', timeline.get('elapsedRegularTime')),
        'sc': [home.get('score', ''), away.get('score', ''),
               home.get('halfTimeScore', ''), away.get('halfTimeScore', ''),
               home.get('fullTimeScore', ''), away.get('fullTimeScore', '')],
        'ev': events
    }


def _legacyForensicToRecord(raw, day='', archive_reason='U'):
    if not isinstance(raw, dict):
        return None
    if raw.get('v') == LIVE_STATE_SCHEMA and raw.get('id'):
        result = copy.deepcopy(raw)
        result['ar'] = result.get('ar') or archive_reason
        return result

    if 'team' in raw:
        raw = compactLegacyForensicRecord(raw)
    if 'fixture' not in raw:
        return None
    fixture = raw.get('fixture', {}) or {}
    observed = raw.get('observed', {}) or {}
    output = outputTemplate.copy()
    output['Date'] = fixture.get('Date', '')
    output['Competition'] = fixture.get('Competition', '')
    output['Home'] = fixture.get('Home', '')
    output['Away'] = fixture.get('Away', '')
    for key, value in observed.items():
        if key in output:
            output[key] = value
    transitions = raw.get('transitions', {}) or {}
    evidence = raw.get('capture_evidence', {}) or {}
    od = {}
    for point, key in [('KO', 'ko'), ('HT', 'ht')]:
        item = evidence.get(point)
        if isinstance(item, dict):
            od[key] = _compactEvidencePoint(item)
        else:
            od[key] = None
    flags = raw.get('flags', {}) or {}
    fl = []
    if flags.get('ko_missing'):
        fl.append('K0')
    if flags.get('catalogue_missing'):
        fl.append('CM')
    if flags.get('timeline_missing'):
        fl.append('TM')
    if not all(float(output.get(key, 0) or 0) > 0 for key in ['HT_1', 'HT_2', 'HT_X']):
        fl.append('H0')
    price_context = raw.get('price_context', []) or []
    px = {}
    if price_context:
        px['r'] = _compactSnapshotForState(price_context[-1])
        clean = [item for item in price_context if collection.book_is_plausible(item.get('back', []))]
        if clean:
            px['c'] = _compactSnapshotForState(clean[-1])
    return {
        'v': LIVE_STATE_SCHEMA,
        'id': collection.normalise_id(raw.get('event_id', '')),
        'mid': collection.normalise_id(raw.get('market_id', '')),
        'sid': [],
        'dt': fixture.get('Date', ''),
        'cp': fixture.get('Competition', ''),
        'h': fixture.get('Home', ''),
        'a': fixture.get('Away', ''),
        'o': output,
        'tl': _legacyTimelineToCompact(raw.get('timeline', {})),
        'tr': {
            'k': [transitions.get('first_half_start'), transitions.get('first_half_start_source')],
            'f': [transitions.get('first_half_end'), transitions.get('first_half_end_score')],
            's': [transitions.get('second_half_start'), transitions.get('second_half_start_source')]
        },
        'od': od,
        'px': px,
        'fl': sorted(set(fl)),
        'rt': {'ko': copy.deepcopy(transitions.get('ko_state', {})), 'hla': None},
        'ar': archive_reason
    }


def _legacyTeamToRecord(team, archive_reason='U'):
    if not isinstance(team, dict):
        return None
    if team.get('v') == LIVE_STATE_SCHEMA and team.get('id'):
        result = copy.deepcopy(team)
        result['ar'] = result.get('ar') or archive_reason
        return result
    if 'output' not in team:
        return None
    # Temporarily use the normal serializer. It naturally emits an empty/minimal
    # forensic section when the old dump did not contain those global structures.
    return matchRecordFromTeam(team, archive_reason=archive_reason)


def _recordRichness(record):
    if not isinstance(record, dict):
        return -1
    score = 0
    output = record.get('o', {}) or {}
    score += sum(1 for key in ['HT_Home', 'HT_Away', 'FT_Home', 'FT_Away',
                               'KO_1', 'KO_2', 'KO_X', 'HT_1', 'HT_2', 'HT_X']
                 if output.get(key) not in ['', None, 0, 0.0, '-1'])
    score += len((record.get('tl', {}) or {}).get('ev', []) or [])
    for key in ['ko', 'ht']:
        point = (record.get('od', {}) or {}).get(key)
        if isinstance(point, dict) and point.get('s'):
            score += 4
    score += len(record.get('fl', []) or [])
    return score


def _mergeMatchRecords(base, incoming):
    if base is None:
        return copy.deepcopy(incoming)
    if incoming is None:
        return copy.deepcopy(base)
    primary, secondary = (incoming, base) if _recordRichness(incoming) >= _recordRichness(base) else (base, incoming)
    result = copy.deepcopy(primary)
    for key in ['id', 'mid', 'dt', 'cp', 'h', 'a']:
        if not result.get(key) and secondary.get(key):
            result[key] = copy.deepcopy(secondary.get(key))
    if not result.get('sid') and secondary.get('sid'):
        result['sid'] = copy.deepcopy(secondary.get('sid'))
    result.setdefault('o', {})
    for key, value in (secondary.get('o', {}) or {}).items():
        if result['o'].get(key) in ['', None, 0, 0.0, '-1'] and value not in ['', None, 0, 0.0, '-1']:
            result['o'][key] = copy.deepcopy(value)
    if len((secondary.get('tl', {}) or {}).get('ev', []) or []) > len((result.get('tl', {}) or {}).get('ev', []) or []):
        result['tl'] = copy.deepcopy(secondary.get('tl'))
    result.setdefault('od', {})
    for key in ['ko', 'ht']:
        if not result['od'].get(key) and (secondary.get('od', {}) or {}).get(key):
            result['od'][key] = copy.deepcopy(secondary['od'][key])
    result.setdefault('px', {})
    for key in ['r', 'c']:
        if not result['px'].get(key) and (secondary.get('px', {}) or {}).get(key):
            result['px'][key] = copy.deepcopy(secondary['px'][key])
    result['fl'] = sorted(set((result.get('fl', []) or []) + (secondary.get('fl', []) or [])))
    result['ar'] = result.get('ar') or secondary.get('ar')
    return result


def _readDumpRecords(day):
    filename = f"{day}_dump.json"
    data = state_store.read_json(filename) if os.path.isfile(filename) else None
    records = {}
    if isinstance(data, dict) and data.get('v') == LIVE_STATE_SCHEMA and isinstance(data.get('matches'), dict):
        records = copy.deepcopy(data['matches'])
        for record in records.values():
            normaliseMatchRecordOutput(record)
        return records
    if isinstance(data, list):
        for raw in data:
            record = _legacyTeamToRecord(raw, 'U')
            if record is None:
                record = _legacyForensicToRecord(raw, day, 'U')
            if record is None:
                continue
            key = record.get('id') or f"{record.get('dt')}|{record.get('h')}|{record.get('a')}"
            records[key] = _mergeMatchRecords(records.get(key), record)
    return records


def _writeDumpRecords(day, records):
    for record in records.values():
        normaliseMatchRecordOutput(record)
    payload = {'v': LIVE_STATE_SCHEMA, 'day': day, 'matches': records}
    filename = f"{day}_dump.json"
    old = state_store.read_json(filename) if os.path.isfile(filename) else None
    if isinstance(old, dict) and old.get('v') == LIVE_STATE_SCHEMA and state_store.state_hash(old) == state_store.state_hash(payload):
        return False
    state_store.atomic_write_json(payload, filename, backup=True)
    return True


def saveDayDump(day, teams, archive_reason='U'):
    if not teams:
        return
    records = _readDumpRecords(day)
    for team in teams:
        record = matchRecordFromTeam(team, archive_reason=archive_reason)
        key = record.get('id') or f"{record.get('dt')}|{record.get('h')}|{record.get('a')}"
        records[key] = _mergeMatchRecords(records.get(key), record)
    _writeDumpRecords(day, records)


def saveProblemRecord(day, team, archive_reason='P'):
    saveDayDump(day, [team], archive_reason=archive_reason)


def migrateLegacyDumpFiles():
    days = set()
    for filename in os.listdir('.'):
        if len(filename) >= 18 and filename[:8].isdigit() and (filename.endswith('_dump.json') or filename.endswith('_dump_state.json')):
            days.add(filename[:8])
    for day in sorted(days):
        dump_name = f"{day}_dump.json"
        current = state_store.read_json(dump_name) if os.path.isfile(dump_name) else None
        if isinstance(current, dict) and current.get('v') == LIVE_STATE_SCHEMA and isinstance(current.get('matches'), dict):
            continue
        records = _readDumpRecords(day)
        state_name = f"{day}_dump_state.json"
        legacy_state = lib.readFromJSON(state_name) if os.path.isfile(state_name) else []
        if isinstance(legacy_state, list):
            for raw in legacy_state:
                reason = 'P' if str(raw.get('state_reason', '')).lower() == 'finalized_problematic' else 'U'
                record = _legacyForensicToRecord(raw, day, reason)
                if record is None:
                    continue
                key = record.get('id') or f"{record.get('dt')}|{record.get('h')}|{record.get('a')}"
                records[key] = _mergeMatchRecords(records.get(key), record)
        if records:
            _writeDumpRecords(day, records)
            print(f"MIGRATE: {day} dump -> schema v{LIVE_STATE_SCHEMA} ({len(records)} match(es))")


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


def finaliseRestoredMatchesFromState():
    # A restored state may already contain a definitive end-of-match signal.
    # Finalise these rows before any fresh network call or day-close decision.
    for team in list(DA_TEAMS):
        event_id = getEventID(team)
        event = LATEST_TIMELINES.get(event_id)
        if event is None:
            event = {
                'eventId': event_id,
                'score': team.get('score', {}),
                'updateDetails': team.get('updateDetails', [])
            }
        if eventFinished(event):
            finaliseTeam(team, event)


def finalRecoveryNeeded(team, now_epoch=None):
    now_epoch = time.time() if now_epoch is None else now_epoch
    day = matchStartDay(team)
    close_epoch = dayCloseEpoch(day) if day else None
    if close_epoch is not None and now_epoch >= close_epoch:
        return True, 'CLOSED_DAY'

    start = scheduledStart(team)
    if start is None:
        start = parseBetfairTimestamp(team.get('output', {}).get('Date'))
    if start is not None and now_epoch >= start + FINAL_RECOVERY_AFTER_START_SECONDS:
        return True, 'ELAPSED'
    return False, ''


def scheduleFinalRecoveryJobs(now_epoch=None, restored=False):
    now_epoch = time.time() if now_epoch is None else now_epoch
    changed = False
    for team in DA_TEAMS:
        event_id = getEventID(team)
        if not event_id or event_id in FINAL_RECOVERY_STATE:
            continue
        needed, reason = finalRecoveryNeeded(team, now_epoch)
        if not needed:
            continue
        state = {'a': 0, 'r': reason}
        day = matchStartDay(team)
        close_epoch = dayCloseEpoch(day) if day else None
        if close_epoch is not None and now_epoch >= close_epoch:
            state['ar'] = 'R' if restored else 'U'
        FINAL_RECOVERY_STATE[event_id] = state
        changed = True
    if changed:
        markStateDirty()


def finalRecoveryEntries():
    result = []
    for team in DA_TEAMS:
        event_id = getEventID(team)
        state = FINAL_RECOVERY_STATE.get(event_id)
        if not isinstance(state, dict):
            continue
        if int(state.get('a', 0) or 0) < FINAL_RECOVERY_MAX_ATTEMPTS:
            result.append(team)
    return result


def recordFinalRecoveryAttempts(requested_event_ids):
    if ENDPOINT_LAST_ERROR.get('timeline') is not None:
        return
    changed = False
    for event_id in {collection.normalise_id(item) for item in requested_event_ids if item}:
        state = FINAL_RECOVERY_STATE.get(event_id)
        if not isinstance(state, dict) or findTeamByEvent(event_id) is None:
            continue
        attempts = int(state.get('a', 0) or 0)
        if attempts >= FINAL_RECOVERY_MAX_ATTEMPTS:
            continue
        state['a'] = attempts + 1
        changed = True
    if changed:
        markStateDirty()


def archiveExhaustedClosedRecoveries(now_epoch=None):
    now_epoch = time.time() if now_epoch is None else now_epoch
    groups = {}
    for team in list(DA_TEAMS):
        event_id = getEventID(team)
        state = FINAL_RECOVERY_STATE.get(event_id)
        if not isinstance(state, dict):
            continue
        if int(state.get('a', 0) or 0) < FINAL_RECOVERY_MAX_ATTEMPTS:
            continue
        day = matchStartDay(team)
        close_epoch = dayCloseEpoch(day) if day else None
        if close_epoch is None or now_epoch < close_epoch:
            continue
        groups.setdefault((day, state.get('ar', 'U')), []).append(team)

    for (day, archive_reason), teams in sorted(groups.items()):
        saveDayDump(day, teams, archive_reason=archive_reason or 'U')
        print(f"FINAL RECOVERY: {len(teams)} unresolved match(es) -> {day}_dump.json")
        purgeTeams(teams)
        removeClosedDayRuntimeFiles(day)
    if groups:
        persistState(force=True)


def closedDayTransientFiles(day):
    return [
        f"{day}_checkpoint.json", f"{day}_checkpoint.json.bak", f"{day}_checkpoint.json.tmp",
        f"{day}_run_dump.json", f"{day}_run_dump.json.tmp"
    ]


def removeClosedDayRuntimeFiles(day):
    # Legacy runtime files are no longer written. Remove only after their day is
    # safely represented in the new dump/results structures.
    removed = []
    for filename in closedDayTransientFiles(day):
        if os.path.isfile(filename):
            os.remove(filename)
            removed.append(filename)
    if removed:
        print(f"Removed legacy runtime files for {day}: {', '.join(removed)}")


def dueMatchDayGroups(now_epoch=None):
    now_epoch = time.time() if now_epoch is None else now_epoch
    groups = {}
    for team in DA_TEAMS:
        day = matchStartDay(team)
        close_epoch = dayCloseEpoch(day) if day else None
        if close_epoch is not None and now_epoch >= close_epoch:
            groups.setdefault(day, []).append(team)
    return groups


def closeDueMatchDays(now_epoch=None):
    groups = dueMatchDayGroups(now_epoch)
    if not groups:
        return

    # A due day is not dumped merely because the clock crossed 04:00 UTC.
    # The current Standard cycle is the first dedicated final-recovery attempt;
    # a remaining match gets one more scheduler opportunity before archival.
    if ENDPOINT_LAST_ERROR.get('timeline') is not None:
        print('Closed-day housekeeping deferred: timeline endpoint unavailable')
        return

    scheduleFinalRecoveryJobs(now_epoch=now_epoch)
    archiveExhaustedClosedRecoveries(now_epoch=now_epoch)
    persistState()


def purgeTeams(teams):
    for team in list(teams):
        cleanupEventState(team)
        if team in DA_TEAMS:
            DA_TEAMS.remove(team)
    markStateDirty()


def focusedCycle():
    ko_watch = preKOFocusEntries()
    ht_watch = htFocusEntries()
    pending_market_ids = pendingHTMarketIDs()
    pending_teams = [team for team in DA_TEAMS if getMarketID(team) in pending_market_ids]
    recovery_teams = finalRecoveryEntries()
    minute_watch = minuteFocusEntries()

    watched = {}
    for entry in ko_watch + ht_watch + pending_teams + recovery_teams + minute_watch:
        event_id = getEventID(entry)
        if event_id:
            watched[event_id] = entry
    if not watched:
        return

    print(
        f"Intermediate timeline watch: {len(watched)} event(s) "
        f"[KO={len(ko_watch)}, HT={len(ht_watch)}, HT-pending={len(pending_teams)}, "
        f"recovery={len(recovery_teams)}]"
    )
    timelines = requestTrackedTimelines(list(watched.keys())) if watched else []
    live_signals = detectLivePhaseSignals(timelines)
    rememberTimelineStates(timelines, live_signals)
    processFinished(timelines)
    recordFinalRecoveryAttempts(watched.keys())
    archiveExhaustedClosedRecoveries()
    processKOEvents(timelines)

    # No blanket 10-second odds polling. HT prices are requested only when a
    # restart is actually detected or while a just-detected boundary is pending.
    processSecondHalfStarts(timelines, live_signals)
    retryPendingHT(timelines)
    applyPendingHT(timelines)
    persistState()

def intermediateWorkNeeded():
    return bool(focusEntries() or pendingHTMarketIDs() or finalRecoveryEntries())


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
    processFinished(timelines)
    processSecondHalfStarts(timelines, live_signals)
    retryPendingHT(timelines)
    applyPendingHT(timelines)
    persistState()


def main():
    global filename

    current_catalogue = betfairAPI.getMarketCatalogueByEventTypeId(soccerEventTypeID) or []
    near_start_catalogue = betfairAPI.getMarketCatalogueNearStartByEventTypeId(
        soccerEventTypeID,
        minutes_before=KO_KEEP_AFTER_SCHEDULE_MINUTES,
        minutes_after=KO_FOCUS_BEFORE_MINUTES
    ) or []
    refreshCatalogueCaches(current_catalogue, near_start_catalogue)
    scheduleFinalRecoveryJobs()

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
    processFinished(timelines)
    recordFinalRecoveryAttempts(event_ids)
    archiveExhaustedClosedRecoveries()
    processKOEvents(timelines)
    processCatalogueKickOffFallback(current_catalogue)
    processSecondHalfStarts(timelines, live_signals)
    retryPendingHT(timelines)

    # Ordinary 30-second price sampling only. KO starts three minutes before the
    # scheduled start and keeps the latest valid pre-KO book. Half-time recess
    # likewise keeps the latest valid reference without any 10-second price loop.
    ko_entries = koStandardPriceEntries()
    ht_entries = htRecessPriceEntries()
    minute_entries = minuteFocusEntries()
    standard_by_market = {}
    for entry in ko_entries + ht_entries + minute_entries:
        market_id = getMarketID(entry)
        if market_id:
            standard_by_market[market_id] = entry
    standard_entries = list(standard_by_market.values())

    results = pollEntries(standard_entries, aggressive=False, point='30S') if standard_entries else {}
    rememberLatestPreKO(ko_entries, results)
    rememberLatestHTRecess(ht_entries, results)

    # KO is frozen from the first clean post-KO snapshot on this 30-second cycle.
    # If the timeline already shows an early goal/red card, the saved pre-KO book
    # is used instead. Only unusually large pre->post movement is logged.
    applyPendingKO(timelines, results)
    applyPendingHT(timelines, results)
    closeDueMatchDays()
    persistState()

    print(
        f"Tracked: {len(DA_TEAMS)} | Catalogue missing: {len(CATALOGUE_MISSING)} | "
        f"Timeline missing: {len(TIMELINE_MISSING)} | KO watch: {len(preKOFocusEntries())} | "
        f"HT watch: {len(htFocusEntries())} | 30s prices: {len(standard_entries)}"
    )
    print(betfairAPI.datetime.datetime.now())

def stopAndSave(signum=None, frame=None):
    print("Saving collector state before exit...")
    try:
        persistState(force=True)
    except Exception as err:
        print(f"State save error: {err}")
    raise KeyboardInterrupt


def runCollector():
    restored = restoreState()
    if restored:
        finaliseRestoredMatchesFromState()
        scheduleFinalRecoveryJobs(restored=True)
    persistState(force=True)

    try:
        import signal
        signal.signal(signal.SIGTERM, stopAndSave)
    except Exception:
        pass

    anchor = time.monotonic()
    slot = 0
    while True:
        try:
            target = anchor + (slot * INTERMEDIATE_INTERVAL)
            now = time.monotonic()
            if target > now:
                time.sleep(target - now)
            elif now - target >= INTERMEDIATE_INTERVAL:
                # Never fire a burst of catch-up requests after a slow or stalled
                # cycle. Skip missed opportunities and resume at the next slot.
                slot = int((now - anchor) // INTERMEDIATE_INTERVAL) + 1
                target = anchor + (slot * INTERMEDIATE_INTERVAL)
                time.sleep(max(target - time.monotonic(), 0))

            if slot % (STANDARD_INTERVAL // INTERMEDIATE_INTERVAL) == 0:
                main()
            elif intermediateWorkNeeded():
                focusedCycle()

            slot += 1
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
            anchor = time.monotonic()
            slot = 0


if __name__ == '__main__':
    runCollector()
