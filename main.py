import requests
import os.path
import csv
from requests.structures import CaseInsensitiveDict
import src.betfairAPI.betfairAPI as betfairAPI
import src.ufuncs as lib
import src.collection as collection
import src.state_store as state_store
from functools import reduce
import io
import time
import copy  # for copy.deepcopy
import traceback
import statistics
import math
from zoneinfo import ZoneInfo

# OPERATIONAL VISIBILITY / REGRESSION GUARD (2026-10-08):
# Keep the original successful-request and catalogue/timeline console output.
# Leftia is run directly with `python3 main.py`, so normal stdout is useful live
# diagnostics and is not made into /var/log files by Python itself. Do not remove
# these prints merely as an efficiency cleanup; change them only if the runtime
# deployment model or the user's logging requirements deliberately change.

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
            keys = list(RESULT_FIELDS)

            if file_exists and 'a' in mode:
                with io.open(filename, 'r', encoding='utf-8', newline='') as infile:
                    existing_header = next(csv.reader(infile), [])

                # One-time schema migration for a results file created by <=v0.2.3:
                # drop only the obsolete STAKE column, without altering any values.
                legacy_header = list(lib.eventTemplateKeys)
                if existing_header == legacy_header and 'STAKE' in existing_header:
                    temp_name = filename + '.stake_schema.tmp'
                    with io.open(filename, 'r', encoding='utf-8', newline='') as infile:
                        old_rows = list(csv.DictReader(infile))
                    with io.open(temp_name, 'w', encoding='utf-8', newline='') as outfile:
                        writer = csv.DictWriter(outfile, fieldnames=keys, extrasaction='ignore', lineterminator='\r')
                        writer.writeheader()
                        for old_row in old_rows:
                            migrated = {key: old_row.get(key, '') for key in keys}
                            for pl_key in [key for key in keys if key.startswith('P/L_')]:
                                multi_key = 'MULTI_' + pl_key[4:]
                                try:
                                    multi = float(old_row.get(multi_key, ''))
                                    migrated[pl_key] = round(multi - 1.0, 2)
                                except Exception:
                                    pass
                            writer.writerow(migrated)
                    os.replace(temp_name, filename)
                    existing_header = keys

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


def _firstHalfRedCards(details):
    """Return red-card events that were known by half time only.

    Models are evaluated at HT. Re-evaluating them at full time must not let a
    second-half dismissal retroactively alter the original HT decision.
    """
    cards = []
    boundary_seen = False
    for item in _safeDetails(details):
        event_type = str(item.get('type') or item.get('updateType') or '')
        normalised = event_type.lower().replace('_', '')
        if event_type in {'FirstHalfEnd', 'SecondHalfKickOff'}:
            boundary_seen = True
            continue
        if normalised not in {'redcard', 'sendingoff', 'dismissal'}:
            continue
        elapsed = None
        try:
            raw = item.get('elapsedRegularTime')
            if raw in [None, '']:
                raw = item.get('matchTime')
            if raw not in [None, '']:
                elapsed = float(raw)
        except Exception:
            elapsed = None
        if elapsed is not None:
            if elapsed <= 45:
                cards.append(item)
        elif not boundary_seen:
            cards.append(item)
    return cards


def _strategyPriceAvailable(output, selection):
    if not selection or selection == 'NO':
        return selection == 'NO'
    try:
        return float(output.get(f"HT_{selection}") or 0) > 1.0
    except Exception:
        return False


def applyModel__DT1(data):
    output = data.get('output', {}) if isinstance(data, dict) else {}
    details = _safeDetails(data.get('updateDetails')) if isinstance(data, dict) else []
    red_cards = _firstHalfRedCards(details)
    home_reds = [item for item in red_cards if item.get('team') == 'home']
    away_reds = [item for item in red_cards if item.get('team') == 'away']

    home = _scoreValue(output.get('HT_Home'))
    away = _scoreValue(output.get('HT_Away'))
    if home is None or away is None:
        return 'NO'

    if home > away:
        selection = '1' if not home_reds else 'NO'
    elif home < away:
        selection = '2' if not away_reds else 'NO'
    else:
        try:
            ko_1 = float(output.get('KO_1') or 0)
            ko_2 = float(output.get('KO_2') or 0)
        except Exception:
            return 'NO'
        if ko_1 <= 1.0 or ko_2 <= 1.0:
            return 'NO'
        if ko_1 >= 2.1 and ko_2 < 1.9:
            selection = '2/X' if not away_reds else 'NO'
        else:
            selection = '1/X' if not home_reds else 'NO'

    # A theoretical selection without a real HT price is not an executable bet.
    # Record it as NO rather than leaving MODEL_* blank or implying a bet existed.
    return selection if _strategyPriceAvailable(output, selection) else 'NO'


def applyModel__ZZCX(data):
    output = data.get('output', {}) if isinstance(data, dict) else {}
    home = _scoreValue(output.get('HT_Home'))
    away = _scoreValue(output.get('HT_Away'))
    if home is None or away is None:
        return 'NO'
    selection = 'X' if home == away and home in {0, 1} else 'NO'
    return selection if _strategyPriceAvailable(output, selection) else 'NO'

def getFINAL(data):
    home = _scoreValue(data.get('FT_Home')) if isinstance(data, dict) else None
    away = _scoreValue(data.get('FT_Away')) if isinstance(data, dict) else None
    if home is None or away is None:
        return ''
    if home > away:
        return '1'
    if home < away:
        return '2'
    return 'X'

def getMULTI(data, model):
    selection = str(data.get(model, '') or '').strip()
    if not selection or selection == 'NO':
        return 1.0
    final = str(data.get('FINAL', '') or '').strip()
    if not final:
        return 1.0
    if final not in selection:
        return 0.0
    key = f"HT_{selection}"
    try:
        price = float(data.get(key) or 0)
    except Exception:
        return 1.0
    return price if price > 1.0 else 1.0

def getPL(data, multi):
    """Return strategy profit/loss in staking units (1 SU risked)."""
    return float(data[multi]) - 1.0




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
                             0.0, "",           # legacy "STAKE", "FINAL" slots in lib.render
                             "", 0.0, 0.0,    # "MODEL_DT1", "MULTI_DT1", "P/L_DT1"
                             "", 0.0, 0.0,    # "MODEL_ZZCX", "MULTI_ZZCX", "P/L_ZZCX"
                             ])
outputTemplate.pop('STAKE', None)

# STAKE is no longer a results field. Strategy P/L is stored in staking units.
RESULT_FIELDS = [key for key in lib.eventTemplateKeys if key != 'STAKE']


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


LEFTIA_AI_VERSION = '0.2.12'

# Betfair API sessions can become unusable after a long sleep/hibernation.
# listMarketCatalogue should always return a list; the legacy API wrapper
# returns {} when an HTTP/API call fails. Use that distinction to refresh the
# session once and retry without treating a failed catalogue as an empty one.
CATALOGUE_SESSION_REFRESH_COOLDOWN_SECONDS = 60
LAST_CATALOGUE_SESSION_REFRESH = 0.0
CATALOGUE_API_UNAVAILABLE = False
STANDARD_INTERVAL = 30
NORMAL_DELAY = STANDARD_INTERVAL
RECOVERY_INTERVAL = 15
# One immediate post-boundary request plus six 15-second retries.
POST_RECOVERY_RETRIES = 6
POST_RECOVERY_TOTAL_POLLS = POST_RECOVERY_RETRIES + 1
BOUNDARY_RECOVERY_SECONDS = RECOVERY_INTERVAL * POST_RECOVERY_RETRIES  # 90 seconds
# Allow tiny scheduler drift so the T+90s final slot is not lost by milliseconds.
BOUNDARY_FINAL_SLOT_GRACE_SECONDS = 2
ODDS_BOOK_TARGET = 1.03
ODDS_BOOK_TOLERANCE = 0.05
ODDS_BOOK_LOW = ODDS_BOOK_TARGET - ODDS_BOOK_TOLERANCE
ODDS_BOOK_HIGH = ODDS_BOOK_TARGET + ODDS_BOOK_TOLERANCE
# Fresh SHKO discovery is intentionally conservative.  Betfair's top-level
# elapsedRegularTime is the same live-position field used to render the website
# minute; only 45/46 is accepted as a *new* SHKO whiff.
SHKO_FRESH_MINUTE_MIN = 45.0
SHKO_FRESH_MINUTE_MAX = 46.0

# ---------------------------------------------------------------------------
# CAPTURE DESIGN / REGRESSION GUARDS
# ---------------------------------------------------------------------------
# Keep these comments with the implementation until the behaviour they explain
# is deliberately superseded.  They record failures seen in live collection so
# that a later clean-up does not remove a line that looks redundant but protects
# a real edge case.
#
# 1) Odds come from Betfair's WEBSITE readonly JSON endpoint, not from delayed
#    Exchange API price calls.  The API catalogue is trusted for market identity
#    and whether Betfair still considers a match active/relevant.
#
# 2) PRE insurance is intentionally simple: every normal 30-second heartbeat,
#    KO from scheduled KO-2m to scheduled KO; HT from FirstHalfEnd+13m until the
#    restart is observed.  Keep the best real observation; do not numerically
#    repair odds.  PRE exists so a suspended/corrupt POST window does not leave a
#    match empty.
#
# 3) POST capture is the same mechanism for KO and HT: immediate T+0 website
#    price request, then at most six 15-second retries (+15..+90).  First
#    acceptable book wins.  A later goal/red card stops future polling but must
#    NEVER erase a safe POST observation captured before that event.
#
# 4) v0.2.11 regression: a market newly entering Betfair's active catalogue was
#    logged as a KO hint but did not actually arm POST recovery.  AL Sadd U20 v
#    Al-Arabi U20 (2026-10-08) therefore kept a horrible PRE book and made zero
#    POST attempts.  A NEWLY_ACTIVE catalogue transition is therefore a genuine
#    KO "whiff" and MUST immediately arm the same POST scheduler as timeline KO.
#    This also protects unexpectedly early/delayed KOs (e.g. Slovenia U19 v
#    Serbia U19) when the catalogue sees the live transition before the timeline.
#
# 5) v0.2.11 regression: no-timestamp SecondHalfKickOff required the immediately
#    previous website status to be FirstHalfEnd.  Betfair sometimes omits FHE or
#    supplies a literal 1970-01-01 updateTime, causing valid HT restarts to be
#    ignored.  A literal 1970 updateTime means "timestamp unavailable"; ignore
#    that timestamp only, not the whole event.  The top-level/bulk
#    elapsedRegularTime that drives Betfair's website minute is checked on every
#    timeline response and is the preferred live-position indicator.
#
# 6) A newly observed SHKO may start HT capture only while the bulk website minute
#    is 45 or 46.  Minute 47+ is deliberately too late for a *new* HT boundary,
#    even if a persistent SHKO status is still visible.  Once an HT boundary was
#    legitimately caught at 45/46, its already-started +15..+90 recovery may of
#    course continue according to the normal recovery clock.  This conservative
#    guard prevents minute-50 (or later) prices being mislabeled as HT.
#
# 7) If an explicit transition detail is missing, bulk elapsedRegularTime may
#    still reveal movement.  A fresh minute 0/1 can provide a KO whiff; a fresh
#    minute 45/46 can provide an SHKO whiff only when half-time was already known
#    (stored FirstHalfEnd / previous FHE).  Do NOT infer SHKO from minute 46 alone:
#    first-half stoppage time can also reach that number.
#
# 8) Persist only recovery-relevant changes (new/better PRE or POST evidence,
#    boundary, material event, freeze/finalise).  Ordinary minute changes and
#    retry-clock movement alone must not turn live_state.json into a 15-second
#    write loop.
# ---------------------------------------------------------------------------
KO_FOCUS_BEFORE_MINUTES = 2
KO_BACKUP_MAX_AGE_SECONDS = 120
KO_CATALOGUE_LOOKBACK_MINUTES = 20
# KO prices are sampled every 30 seconds. The pre-KO book is locked at the
# scheduled start. A post-KO book is acceptable only when the website's live
# timer/status says we are still right at the start.
KO_POST_BOUNDARY_SECONDS = STANDARD_INTERVAL + 10
KO_BOUNDARY_RECONCILE_SECONDS = KO_POST_BOUNDARY_SECONDS + 5
KO_POST_WEBSITE_MAX_MINUTES = 1
KO_POST_CONFIRM_WAIT_SECONDS = STANDARD_INTERVAL + 10
KO_LIVE_DISCOVERY_MAX_AFTER_SCHEDULE_SECONDS = 120
KO_LIVE_ELAPSED_MAX_MINUTES = BOUNDARY_RECOVERY_SECONDS / 60.0
KO_SYNTHETIC_START_SOURCES = {
    'catalogue_inplay_live', 'catalogue_inplay_late', 'late_rediscovery', 'catalogue_inplay'
}
KO_START_SOURCE_PRIORITY = {
    'catalogue_inplay_late': 0,
    'late_rediscovery': 0,
    'catalogue_inplay': 0,
    'catalogue_inplay_live': 1,
    'status_observed': 2,
    'website_status': 3,
    'explicit_observed': 3,
    'website_elapsed': 4,
    'explicit_time': 4,
}
FORENSIC_MAX_SNAPSHOTS = 8
HT_FOCUS_AFTER_FIRST_HALF_MINUTES = 13
HT_REPLENISH_WINDOW_SECONDS = BOUNDARY_RECOVERY_SECONDS
DAY_CLOSE_GRACE_HOURS = 4
FINAL_RECOVERY_AFTER_START_SECONDS = 3 * 60 * 60
FINAL_RECOVERY_MAX_ATTEMPTS = 2
RECOVERY_RETRIES = 2
TIMELINE_BATCH_SIZE = 50
TIMELINE_RETRY_BATCH_SIZE = 10
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
# Best real pre-restart snapshot observed from FirstHalfEnd +13 minutes.
# It is persisted as HT insurance and is used if a usable post-restart triplet
# cannot be obtained.
HT_RECESS_STATE = {}
HT_CAPTURE_STATE = {}
NEAR_START_CATALOGUE = {}
CURRENT_INPLAY_CATALOGUE = {}
# The successful Betfair catalogue call is authoritative for which matches are
# currently active.  We only use *transitions into* that list as a KO hint; the
# first catalogue after process start establishes a baseline so a mid-match
# restart cannot mislabel current odds as KO.
NEWLY_ACTIVE_CATALOGUE_IDS = set()
CATALOGUE_ACTIVE_BASELINE_READY = False
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


def bulkElapsedMinutes(event):
    """Return Betfair's top-level live match minute, if supplied.

    This is deliberately separate from updateDetails.  The top-level
    elapsedRegularTime is the current per-game value used by the live website
    display (e.g. 43', 46', 63') and is therefore the best cheap answer to
    "where is this match now?".  Historical detail rows can have missing or
    1970 timestamps and must not override this live-position value.
    """
    if not isinstance(event, dict):
        return None
    try:
        value = event.get('elapsedRegularTime')
        if value not in [None, '']:
            return float(value)
    except Exception:
        pass
    return None


def eventElapsedMinutes(event):
    """Return current minute, preferring the top-level website value.

    Detail-level elapsed/matchTime is only a fallback for payloads/restored state
    that do not contain the bulk elapsedRegularTime field.  Do not take the max
    of historical detail rows when a current top-level minute is available.
    """
    bulk = bulkElapsedMinutes(event)
    if bulk is not None:
        return bulk
    values = []
    if not isinstance(event, dict):
        return None
    for detail in _safeDetails(event.get('updateDetails')):
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
    """Legacy quality check used outside the KO/HT raw recorder path."""
    if snapshot is None or not collection.book_is_plausible(snapshot.get('back', [])):
        return False
    history = history or []
    if not collection.recent_clean(history):
        return True
    return collection.snapshot_is_strong(snapshot, history)


def _realBackCount(snapshot):
    if not isinstance(snapshot, dict):
        return 0
    prices = list(snapshot.get('back', []))
    return sum(1 for value in prices[:3]
               if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 1.0)


def _completeRealBack(snapshot):
    return _realBackCount(snapshot) == 3 and len(list(snapshot.get('back', []))) >= 3


def _snapshotBook(snapshot):
    if not _completeRealBack(snapshot):
        return None
    value = collection.book_sum(list(snapshot.get('back', []))[:3])
    if value is not None:
        snapshot['book'] = value
    return value


def _bookDistanceToAcceptable(book):
    if book is None:
        return float('inf')
    if ODDS_BOOK_LOW <= book <= ODDS_BOOK_HIGH:
        return 0.0
    return min(abs(book - ODDS_BOOK_LOW), abs(book - ODDS_BOOK_HIGH))


def _snapshotAcceptable(snapshot):
    if not _completeRealBack(snapshot):
        return False
    status = str(snapshot.get('status') or '').upper()
    if status in {'SUSPENDED', 'CLOSED'}:
        return False
    book = _snapshotBook(snapshot)
    return book is not None and ODDS_BOOK_LOW <= book <= ODDS_BOOK_HIGH


def _snapshotQualityKey(snapshot):
    """Higher is better. Complete real triplets always beat partial ones.

    Acceptability is only a stop condition. Outside the accepted band, the best
    observation is the one closest to the nearest band edge. Inside the band,
    closeness to the 1.03 target breaks ties for pre-boundary insurance.
    """
    if not isinstance(snapshot, dict):
        return (-1, float('-inf'), float('-inf'), float('-inf'))
    count = _realBackCount(snapshot)
    when = float(snapshot.get('time') or 0)
    if count == 3:
        book = _snapshotBook(snapshot)
        band_distance = _bookDistanceToAcceptable(book)
        target_distance = abs(book - ODDS_BOOK_TARGET) if book is not None else float('inf')
        return (3, -band_distance, -target_distance, when)
    return (count, float('-inf'), float('-inf'), when)


def _betterRealSnapshot(current, candidate):
    if not isinstance(candidate, dict) or _realBackCount(candidate) == 0:
        return current
    if not isinstance(current, dict):
        return copy.deepcopy(candidate)
    return copy.deepcopy(candidate) if _snapshotQualityKey(candidate) > _snapshotQualityKey(current) else current


def _rawBoundaryResult(snapshot, method='RAW'):
    if not isinstance(snapshot, dict):
        return None
    back = list(snapshot.get('back', []))[:3]
    while len(back) < 3:
        back.append(None)
    lay = list(snapshot.get('lay', []))[:3]
    while len(lay) < 3:
        lay.append(None)
    selected = copy.deepcopy(snapshot)
    selected['back'] = back
    selected['lay'] = lay
    selected['book'] = _snapshotBook(selected)
    return {
        'back': back,
        'lay': lay,
        'book': selected.get('book'),
        'method': method,
        'raw': copy.deepcopy(snapshot),
        'selected': selected,
        'inferred': []
    }


def _outputTriplet(prices):
    """Convert raw BACK prices to output values without altering raw evidence.

    Narrow sparse-market exception: when exactly two of the three Match Odds
    BACK prices are genuinely present (>1.0), export the single missing runner
    as 1.01 rather than 0.0.  This is only a recorder placeholder for the
    near-certain outcome case; it is never applied when zero, one, or all three
    real BACK prices are present.

    Returns (values, inferred) so the forensic evidence can explicitly record
    that 1.01 was not an observed BACK price.
    """
    values = list(prices or [])[:3]
    while len(values) < 3:
        values.append(None)

    result = []
    present = []
    for index, value in enumerate(values):
        try:
            value = float(value)
            valid = value > 1.0
        except Exception:
            valid = False
            value = 0.0
        result.append(value if valid else 0.0)
        if valid:
            present.append(index)

    inferred = []
    if len(present) == 2:
        missing_index = next(index for index in range(3) if index not in present)
        result[missing_index] = 1.01
        inferred.append({
            'runner_index': missing_index,
            'value': 1.01,
            'reason': 'single_missing_back_placeholder'
        })

    return result, inferred


def pollBoundaryEntriesRaw(entries, point='RAW'):
    """Poll KO/HT markets without repairing, mixing or synthesising BACK odds."""
    by_market = {getMarketID(entry): entry for entry in entries if getMarketID(entry)}
    if not by_market:
        return {}
    marketbook = getCleanExchangePricesfromWebsite(list(by_market.keys()))
    results = {}
    for market_id, entry in by_market.items():
        snapshot = extractSnapshot(entry, marketbook)
        if snapshot is not None:
            addPriceHistory(entry, snapshot)
            results[market_id] = _rawBoundaryResult(snapshot, 'RAW')
            results[market_id]['current_raw'] = snapshot
            results[market_id]['source_problem'] = False
        else:
            results[market_id] = {
                'back': [None, None, None], 'lay': [None, None, None], 'book': None,
                'method': 'MISS', 'raw': None, 'selected': None, 'inferred': [],
                'current_raw': None, 'source_problem': ENDPOINT_LAST_ERROR.get('price') is not None
            }
    return results


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
    """Create/update KO recovery state only when meaningful state changed.

    The old implementation refreshed an ``observed_at`` value every ordinary
    cycle, which made live_state.json look changed even when nothing important
    had happened.  Boundary/fallback state is persisted; heartbeat noise is not.
    """
    if team is None or start is None:
        return
    event_id = getEventID(team)
    market_id = getMarketID(team)
    changed = False
    if event_id not in FIRST_HALF_START_TIMES:
        FIRST_HALF_START_TIMES[event_id] = start
        FIRST_HALF_START_SOURCE[event_id] = source
        changed = True

    state = KO_CAPTURE_STATE.get(market_id)
    if not isinstance(state, dict):
        state = {}
    if state.get('phase') not in ['FROZEN', 'MISSING']:
        actual_start = FIRST_HALF_START_TIMES.get(event_id, start)
        desired = {
            'event_id': event_id,
            'start': actual_start,
            'source': FIRST_HALF_START_SOURCE.get(event_id, source),
            'phase': phase,
            'deadline': actual_start + KO_BOUNDARY_RECONCILE_SECONDS,
        }
        for key, value in desired.items():
            if state.get(key) != value:
                state[key] = value
                changed = True
        if 'observed_at' not in state:
            state['observed_at'] = time.time()
            changed = True
        KO_CAPTURE_STATE[market_id] = state
    if changed:
        markStateDirty()

def observedKickoffTime(event, now_epoch=None):
    """Identify the KO boundary from the website timeline.

    Prefer a sane KickOff updateTime.  Otherwise estimate from the displayed
    live minute, and finally fall back to the instant we observe the KickOff
    status.  Scheduled KO is never substituted for an actually delayed KO.
    """
    now_epoch = now_epoch or time.time()
    event = _safeDict(event)

    exact = transitionTime(event, 'KickOff')
    if exact is not None and exact <= now_epoch + 60:
        return exact, 'explicit_time'

    elapsed = eventElapsedMinutes(event)
    started = hasTransition(event, 'KickOff') or event.get('inPlayMatchStatus') in {
        'KickOff', 'FirstHalfEnd', 'SecondHalfKickOff', 'Finished'
    }
    if started and elapsed is not None and elapsed >= 0:
        return now_epoch - (elapsed * 60), 'website_elapsed'
    if event.get('inPlayMatchStatus') == 'KickOff':
        return now_epoch, 'website_status'
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


def _safeDict(value):
    return value if isinstance(value, dict) else {}


def _safeDetails(value):
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def normaliseTimelineEvent(event):
    """Keep external/restored timeline payloads structurally safe."""
    if not isinstance(event, dict):
        return {}
    result = copy.deepcopy(event)
    score = _safeDict(result.get('score'))
    score['home'] = _safeDict(score.get('home'))
    score['away'] = _safeDict(score.get('away'))
    result['score'] = score
    result['updateDetails'] = _safeDetails(result.get('updateDetails'))
    return result


def transitionDetail(event_details, event_type):
    event_details = _safeDict(event_details)
    for detail in _safeDetails(event_details.get('updateDetails')):
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
    event_details = _safeDict(event_details)
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
    score = _safeDict(event.get('score')) if isinstance(event, dict) else {}
    home = _scoreValue(_safeDict(score.get('home')).get('halfTimeScore'))
    away = _scoreValue(_safeDict(score.get('away')).get('halfTimeScore'))
    if home is not None and away is not None:
        return [home, away]
    return None


def reconstructHalfTimeScore(event):
    home = 0
    away = 0
    boundary_seen = False
    for detail in _safeDetails(_safeDict(event).get('updateDetails')):
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
    score = _safeDict(event.get('score')) if isinstance(event, dict) else {}
    home = _scoreValue(_safeDict(score.get('home')).get('score'))
    away = _scoreValue(_safeDict(score.get('away')).get('score'))
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
    """Keep short forensic history in RAM without forcing a disk checkpoint."""
    if snapshot is None:
        return
    market_id = getMarketID(entry)
    record = compactHistorySnapshot(snapshot)
    PRICE_HISTORY.setdefault(market_id, []).append(record)
    PRICE_HISTORY[market_id] = PRICE_HISTORY[market_id][-30:]


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


def pollEntries(entries, point='', allow_history_fallback=True):
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
            if not source_problem and market_id in initial_bad:
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


def _usableBoundarySnapshot(result):
    """Return the fresh raw snapshot, even when its overround is poor."""
    if not isinstance(result, dict):
        return None
    for key in ['current_raw', 'selected', 'raw']:
        snapshot = result.get(key)
        if isinstance(snapshot, dict) and _realBackCount(snapshot) > 0:
            return snapshot
    return None

def _priceResultCorrupt(result):
    """Recovery-worthy means no acceptable complete real triplet was observed."""
    snapshot = _usableBoundarySnapshot(result)
    return not _snapshotAcceptable(snapshot)

def _refreshRecoveryTimelines(entries):
    event_ids = [getEventID(entry) for entry in entries if getEventID(entry)]
    if not event_ids:
        return []
    timelines = requestTrackedTimelines(event_ids)
    if timelines:
        live_signals = detectLivePhaseSignals(timelines)
        rememberTimelineStates(timelines, live_signals)
        processFinished(timelines)
        processKOEvents(timelines)
    return timelines


def recoverCorruptPriceResults(entries, results, point='RECOVERY'):
    """Deprecated compatibility helper: one immediate batched retry, never sleep.

    KO/HT use the shared recovery scheduler. Keeping this helper non-blocking
    prevents a future caller from accidentally starving all other matches.
    """
    pending = [entry for entry in entries
               if getMarketID(entry) and _priceResultCorrupt(results.get(getMarketID(entry)))]
    if not pending:
        return results
    retry = pollBoundaryEntriesRaw(pending, point=point)
    for entry in pending:
        market_id = getMarketID(entry)
        old = _usableBoundarySnapshot(results.get(market_id))
        new = _usableBoundarySnapshot(retry.get(market_id))
        chosen = _betterRealSnapshot(old, new)
        if isinstance(chosen, dict):
            results[market_id] = _rawBoundaryResult(chosen, 'RAW_BEST')
            results[market_id]['current_raw'] = chosen
            results[market_id]['source_problem'] = False
        elif market_id in retry:
            results[market_id] = retry[market_id]
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


def _compactHTCaptureState(event_id):
    state = copy.deepcopy(HT_CAPTURE_STATE.get(event_id, {}) or {})
    if isinstance(state.get('post'), dict):
        state['post'] = _compactSnapshotForState(state.get('post'))
    return state


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
    event = normaliseTimelineEvent(event)
    if not event:
        return {}
    score = _safeDict(event.get('score'))
    home = _safeDict(score.get('home'))
    away = _safeDict(score.get('away'))
    events = []
    code_map = {
        'KickOff': 'K',
        'FirstHalfEnd': 'F',
        'SecondHalfKickOff': 'S',
        'Finished': 'E',
        'SecondHalfEnd': 'E',
        'Goal': 'G',
        'RedCard': 'R',
        'SendingOff': 'R',
        'Dismissal': 'R'
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
    timeline = _safeDict(record.get('tl')) if isinstance(record, dict) else {}
    packed_scores = timeline.get('sc', [])
    score_values = list(packed_scores) + [''] * 6 if isinstance(packed_scores, (list, tuple)) else [''] * 6
    home_name = record.get('h', '')
    away_name = record.get('a', '')
    reverse_map = {'K': 'KickOff', 'F': 'FirstHalfEnd', 'S': 'SecondHalfKickOff', 'E': 'Finished', 'G': 'Goal', 'R': 'RedCard'}
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
            'ht': _compactHTCaptureState(event_id),
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
        restored_ko = copy.deepcopy(runtime.get('ko'))
        restored_ko.pop('pre_retry_due', None)
        KO_CAPTURE_STATE[market_id] = restored_ko
    restored_recess = _expandSnapshotFromState(runtime.get('hr'), event_id, market_id)
    if restored_recess is not None:
        HT_RECESS_STATE[event_id] = restored_recess
    if isinstance(runtime.get('ht'), dict) and runtime.get('ht'):
        restored_ht = copy.deepcopy(runtime.get('ht'))
        restored_ht.pop('pre_retry_due', None)
        if isinstance(restored_ht.get('post'), dict):
            restored_ht['post'] = _expandSnapshotFromState(restored_ht.get('post'), event_id, market_id)
        HT_CAPTURE_STATE[event_id] = restored_ht
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


def saveLiveState(force=False, sync_backup=False):
    global STATE_DIRTY, LAST_SAVED_STATE_HASH, LIVE_STATE_RESTORED_FROM_BACKUP
    if not force and not STATE_DIRTY and not sync_backup:
        return False
    payload = _liveStatePayload()
    current_hash = state_store.state_hash(payload)
    if (LAST_SAVED_STATE_HASH == current_hash and os.path.isfile(LIVE_STATE_FILE)
            and not LIVE_STATE_RESTORED_FROM_BACKUP and not sync_backup):
        STATE_DIRTY = False
        return False

    if sync_backup:
        # Day-close housekeeping must leave both live-state files on the same
        # current-day-only snapshot. Never rotate stale previous-day matches
        # into the backup while closing an old day.
        LAST_SAVED_STATE_HASH = state_store.atomic_write_json(
            payload, LIVE_STATE_FILE, backup=False
        )
        state_store.atomic_write_json(payload, LIVE_STATE_FILE + '.bak', backup=False)
    else:
        # If the main file was unreadable and state came from .bak, do not rotate
        # the unreadable main file over the good backup.
        keep_backup = not LIVE_STATE_RESTORED_FROM_BACKUP
        LAST_SAVED_STATE_HASH = state_store.atomic_write_json(
            payload, LIVE_STATE_FILE, backup=keep_backup
        )

    LIVE_STATE_RESTORED_FROM_BACKUP = False
    STATE_DIRTY = False
    return True


def persistState(force=False, sync_backup=False):
    return saveLiveState(force=force, sync_backup=sync_backup)


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
    restored = _loadNewLiveState()
    if not restored:
        restored = _loadLegacyActiveState()
    # Always normalise existing dumps, even when live_state.json restored
    # successfully. This is what catches an old dump containing several days.
    migrateLegacyDumpFiles()
    persistState(force=True)
    return restored


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
                item = normaliseTimelineEvent(item)
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
                        item = normaliseTimelineEvent(item)
                        event_id = collection.normalise_id(item.get('eventId'))
                        if event_id:
                            by_event[event_id] = item
    return [by_event[event_id] for event_id in event_ids if event_id in by_event]


def watchedEventIDs(current_catalogue=None, near_start_catalogue=None):
    """Events worth asking the website timeline service about this cycle.

    Before KO, Betfair's successful catalogue/near-start lists decide relevance;
    we do not keep hammering an unresolved fixture merely because its scheduled
    KO was hours ago.  Once a match has genuinely started, its tracked state is
    kept until finalisation so HT/FT collection cannot be lost if the catalogue
    drops it near the end.
    """
    event_ids = set()
    fresh_ids = set()
    for entry in current_catalogue or []:
        event_id = getEventID(entry)
        if event_id and not entryAlreadyFinalized(entry):
            event_ids.add(event_id)
            fresh_ids.add(event_id)
    for entry in near_start_catalogue or []:
        event_id = getEventID(entry)
        if event_id and not entryAlreadyFinalized(entry):
            event_ids.add(event_id)
            fresh_ids.add(event_id)

    for team in DA_TEAMS:
        event_id = getEventID(team)
        if not event_id:
            continue
        timeline = _safeDict(LATEST_TIMELINES.get(event_id))
        started = event_id in FIRST_HALF_START_TIMES or matchHasStarted(timeline)
        if started or event_id in fresh_ids:
            event_ids.add(event_id)

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


def _freshObservedSecondHalfStatus(previous, previous_status, current_status, bulk_minute):
    """Whether a no-timestamp SHKO status edge is safe to treat as fresh HT.

    Betfair can omit FirstHalfEnd and can attach a literal 1970 timestamp to a
    genuine SecondHalfKickOff.  The live website still exposes a top-level
    elapsedRegularTime, so use that as the primary freshness gate.  Per the
    capture policy, only minute 45 or 46 is fresh enough to *start* HT capture;
    47+ is too late.  If the bulk minute is absent, an immediately preceding
    FirstHalfEnd remains the only safe fallback.
    """
    if current_status != 'SecondHalfKickOff' or current_status == previous_status:
        return False
    try:
        if bulk_minute is not None:
            minute = float(bulk_minute)
            return SHKO_FRESH_MINUTE_MIN <= minute <= SHKO_FRESH_MINUTE_MAX
    except Exception:
        pass
    return previous_status == 'FirstHalfEnd'

def _isLiteral1970UpdateTime(value):
    """Betfair occasionally emits 1970-01-01 as a missing timestamp sentinel."""
    return isinstance(value, str) and value.strip().startswith('1970-01-01')


def _bulkMinuteMovedForward(previous, current):
    """True when the per-game website minute has newly advanced."""
    if current is None:
        return False
    if previous is None:
        return True
    try:
        return float(current) > float(previous)
    except Exception:
        return False


def detectLivePhaseSignals(timelines):
    """Detect KO/FHE/SHKO using live website position plus transition details.

    The top-level elapsedRegularTime is checked for every game first because it
    is Betfair's current website minute.  A valid transition updateTime gives a
    more precise boundary epoch when available; a literal 1970-01-01 timestamp
    is treated as missing, not as evidence that the transition did not happen.

    New SHKO capture is intentionally restricted to bulk minute 45/46.  A valid
    SHKO caught earlier can continue its existing recovery into later minutes,
    but a collector that first notices the match at minute 47+ must use PRE
    insurance rather than relabel current prices as HT.
    """
    now_epoch = time.time()
    phases = {'KickOff', 'FirstHalfEnd', 'SecondHalfKickOff'}
    signals = {}

    for event in timelines:
        event = normaliseTimelineEvent(event)
        event_id = collection.normalise_id(event.get('eventId'))
        previous = _safeDict(LATEST_TIMELINES.get(event_id))
        previous_status = previous.get('inPlayMatchStatus')
        current_status = event.get('inPlayMatchStatus')
        previous_bulk_minute = bulkElapsedMinutes(previous)
        bulk_minute = bulkElapsedMinutes(event)
        minute = bulk_minute if bulk_minute is not None else eventElapsedMinutes(event)
        event_signals = {}

        previous_details = {_detailIdentity(item) for item in _safeDetails(previous.get('updateDetails'))}
        for detail in _safeDetails(event.get('updateDetails')):
            phase = detail.get('updateType') or detail.get('type')
            if phase not in phases or _detailIdentity(detail) in previous_details:
                continue

            raw_update_time = detail.get('updateTime')
            exact = None if _isLiteral1970UpdateTime(raw_update_time) else parseBetfairTimestamp(raw_update_time)

            if exact is not None:
                # A real timestamp is retained even if discovered later; the
                # recovery layer decides whether its +90s window is still open.
                # For SHKO, however, first discovery at bulk minute 47+ is
                # intentionally too late to start a new HT capture.
                shko_minute_ok = True
                if phase == 'SecondHalfKickOff' and bulk_minute is not None:
                    shko_minute_ok = SHKO_FRESH_MINUTE_MIN <= float(bulk_minute) <= SHKO_FRESH_MINUTE_MAX
                if shko_minute_ok:
                    event_signals[phase] = {
                        'source': 'UPDATE_DETAIL',
                        'observed_at': now_epoch,
                        'bf_minute': minute,
                        'detail_time': exact,
                        'stale': phase in {'KickOff', 'SecondHalfKickOff'}
                                 and now_epoch - exact > BOUNDARY_RECOVERY_SECONDS,
                    }
                continue

            # Missing/1970 timestamp: the transition may still be genuine.  Use
            # current website state and, crucially, the bulk live minute rather
            # than requiring the broken timestamp.
            live = False
            if phase == 'KickOff':
                live = (current_status == 'KickOff' and current_status != previous_status
                        and (bulk_minute is None or bulk_minute <= 2))
            elif phase == 'FirstHalfEnd':
                live = current_status == 'FirstHalfEnd'
            elif phase == 'SecondHalfKickOff':
                live = _freshObservedSecondHalfStatus(
                    previous, previous_status, current_status, bulk_minute)

            if live and phase not in event_signals:
                event_signals[phase] = {
                    'source': 'STATUS', 'observed_at': now_epoch, 'bf_minute': minute,
                    'detail_time': None, 'stale': False
                }

        # Some payloads expose only the current status and no transition detail.
        if current_status in phases and current_status != previous_status and current_status not in event_signals:
            live = False
            if current_status == 'KickOff':
                live = bulk_minute is None or bulk_minute <= 2
            elif current_status == 'FirstHalfEnd':
                live = True
            elif current_status == 'SecondHalfKickOff':
                live = _freshObservedSecondHalfStatus(
                    previous, previous_status, current_status, bulk_minute)
            if live:
                event_signals[current_status] = {
                    'source': 'STATUS', 'observed_at': now_epoch, 'bf_minute': minute,
                    'detail_time': None, 'stale': False
                }

        # REGRESSION GUARD / independent live-position fallback: even if a
        # transition detail/status edge is absent, a newly advanced bulk minute
        # can tell us that the match moved.  Keep this conservative:
        #   * minute 0/1 may establish a KO whiff;
        #   * minute 45/46 may establish SHKO only if half-time was already
        #     known.  Minute 46 alone is NOT enough because first-half stoppage
        #     time can also show 46.
        moved_forward = _bulkMinuteMovedForward(previous_bulk_minute, bulk_minute)
        if moved_forward and bulk_minute is not None:
            try:
                bulk_value = float(bulk_minute)
            except Exception:
                bulk_value = None

            if (bulk_value is not None and 0.0 <= bulk_value <= 1.0
                    and 'KickOff' not in event_signals
                    and event_id not in FIRST_HALF_START_TIMES
                    and current_status not in {'FirstHalfEnd', 'SecondHalfKickOff', 'Finished'}):
                event_signals['KickOff'] = {
                    'source': 'BULK_ELAPSED', 'observed_at': now_epoch,
                    'bf_minute': bulk_value, 'detail_time': None, 'stale': False
                }

            half_time_known = (
                event_id in FIRST_HALF_END_TIMES
                or previous_status == 'FirstHalfEnd'
            )
            if (bulk_value is not None
                    and SHKO_FRESH_MINUTE_MIN <= bulk_value <= SHKO_FRESH_MINUTE_MAX
                    and half_time_known
                    and 'SecondHalfKickOff' not in event_signals
                    and event_id not in SECOND_HALF_START_TIMES):
                event_signals['SecondHalfKickOff'] = {
                    'source': 'BULK_ELAPSED', 'observed_at': now_epoch,
                    'bf_minute': bulk_value, 'detail_time': None, 'stale': False
                }

        if event_signals:
            signals[event_id] = event_signals
    return signals

def rememberTimelineStates(timelines, live_signals=None):
    now_epoch = time.time()
    for event in timelines:
        event = normaliseTimelineEvent(event)
        if not event:
            continue
        event_id = collection.normalise_id(event.get('eventId'))

        # Always keep the freshest timeline in RAM, including Betfair's
        # top-level elapsedRegularTime.  That bulk field is the live website
        # minute and is deliberately used by detectLivePhaseSignals even when a
        # transition detail is missing or carries the 1970 timestamp sentinel.
        # Dirty the persisted state only when the compact recovery
        # information changes (phase, score, or material/phase events).  This
        # avoids a live_state.json write merely because 31' became 32'.
        previous = _safeDict(LATEST_TIMELINES.get(event_id))
        previous_persisted = _compactTimelineForState(previous) if previous else {}
        current_persisted = _compactTimelineForState(event)
        LATEST_TIMELINES[event_id] = copy.deepcopy(event)
        if previous_persisted != current_persisted:
            markStateDirty()

        if hasTransition(event, 'KickOff'):
            reconcileTimelineKickOff(event, now_epoch)
            kickoff = FIRST_HALF_START_TIMES.get(event_id)
            source = FIRST_HALF_START_SOURCE.get(event_id)
            team = findTeamByEvent(event_id)
            if team is not None and kickoff is not None and not koIsFilled(team):
                ensureKOState(team, kickoff, source or 'timeline')

        if hasTransition(event, 'FirstHalfEnd') and event_id not in FIRST_HALF_END_TIMES:
            signal = (live_signals or {}).get(event_id, {}).get('FirstHalfEnd')
            first_end = signal.get('detail_time') if signal is not None else None
            if first_end is None:
                first_end = transitionTime(event, 'FirstHalfEnd')
            if first_end is None and signal is not None:
                first_end = signal.get('observed_at', now_epoch)
            if first_end is None and event.get('inPlayMatchStatus') == 'FirstHalfEnd':
                first_end = now_epoch
            if first_end is not None:
                FIRST_HALF_END_TIMES[event_id] = first_end
                score = explicitHalfTimeScore(event) or reconstructHalfTimeScore(event)
                if score is None and event.get('inPlayMatchStatus') == 'FirstHalfEnd':
                    score = currentScore(event)
                if score is not None:
                    FIRST_HALF_END_SCORES[event_id] = score
                markStateDirty()

        # Record the observed restart *before* routine HT pre-price selection.
        # This ensures a price fetched after the transition can never be
        # mislabelled as a pre-restart fallback.
        sh_signal = (live_signals or {}).get(event_id, {}).get('SecondHalfKickOff')
        if sh_signal is not None and event_id not in SECOND_HALF_START_TIMES:
            SECOND_HALF_START_TIMES[event_id] = (sh_signal.get('detail_time')
                                                  or sh_signal.get('observed_at', now_epoch))
            SECOND_HALF_START_SOURCE[event_id] = sh_signal.get('source', 'STATUS')
            state = HT_CAPTURE_STATE.setdefault(event_id, {})
            state['boundary_observed_at'] = SECOND_HALF_START_TIMES[event_id]
            state['source'] = SECOND_HALF_START_SOURCE[event_id]
            markStateDirty()

        team = findTeamByEvent(event_id)
        if team is not None:
            new_score = event.get('score', team.get('score', ''))
            new_details = event.get('updateDetails', team.get('updateDetails', ''))
            changed = team.get('score') != new_score or team.get('updateDetails') != new_details
            team['score'] = new_score
            team['updateDetails'] = new_details
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
    return any((detail.get('elapsedRegularTime') or detail.get('matchTime') or 0) >= 1 for detail in _safeDetails(event.get('updateDetails')))


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
    """Turn a *new* Betfair active-catalogue transition into a real KO whiff.

    The API catalogue is not used for odds; it is trusted only for the fact that
    Betfair now regards this market as active.  v0.2.11 recorded this transition
    but then waited for the timeline before arming price recovery, which meant a
    missing/late timeline could produce zero POST attempts.  Arm the shared POST
    scheduler immediately here; the actual prices still come from the website
    JSON endpoint in ``runBoundaryRecoveryTick``.
    """
    now_epoch = time.time()
    activated = False
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

        newly_active = event_id in NEWLY_ACTIVE_CATALOGUE_IDS
        if start is None and newly_active:
            start = now_epoch
            source = 'catalogue_inplay_live'
            logIssue(team, 'first_half_fallback', 'KO', f'catalogue_active_transition|obs={collectorStamp()}')

        if start is not None:
            ensureKOState(team, start, source or 'catalogue_inplay')

        # REGRESSION GUARD (2026-10-08): catalogue activation itself is enough
        # to start T+0 POST capture.  Do not require a timeline event as well.
        # This fixes AL Sadd U20 and gives unexpectedly early KOs (such as
        # Slovenia U19 v Serbia U19) a chance to capture while the 90s window is
        # still open.  ``_activateKORecovery`` is non-blocking and only schedules
        # the website price request; it does not call the Exchange price API.
        if newly_active and start is not None:
            if _activateKORecovery(team, now_epoch):
                activated = True
    return activated

def _recoverBoundarySnapshot(team, snapshot, reference=None):
    """Return only actually observed BACK prices; never numerically repair them."""
    result = _rawBoundaryResult(snapshot, 'RAW')
    if result is None or _realBackCount(result.get('selected')) == 0:
        return None
    return result

def _koPreCandidates(team, scheduled, source=None):
    """Legacy/history fallback: only pre-KO prices at or before scheduled KO."""
    market_id = getMarketID(team)
    history = sorted(PRICE_HISTORY.get(market_id, []), key=lambda item: item.get('time', 0))
    lower = scheduled - KO_BACKUP_MAX_AGE_SECONDS
    return [item for item in history
            if lower <= (item.get('time', 0) or 0) <= scheduled
            and item.get('inplay') is False]


def _storedPreKOSnapshot(team):
    state = KO_CAPTURE_STATE.get(getMarketID(team), {}) or {}
    snapshot = state.get('pre')
    return copy.deepcopy(snapshot) if isinstance(snapshot, dict) else None


def _storedPostKOSnapshot(team):
    state = KO_CAPTURE_STATE.get(getMarketID(team), {}) or {}
    snapshot = state.get('post')
    return copy.deepcopy(snapshot) if isinstance(snapshot, dict) else None


def _legacyFirstPostCandidate(team, scheduled):
    """Compatibility for state made before the dedicated one-shot post slot."""
    history = sorted(PRICE_HISTORY.get(getMarketID(team), []), key=lambda item: item.get('time', 0))
    return next((item for item in history
                 if (item.get('time', 0) or 0) >= scheduled
                 and item.get('inplay') is True
                 and collection.book_is_plausible(item.get('back', []))), None)


def _websiteMaterialEvent(event):
    for detail in _safeDetails(_safeDict(event).get('updateDetails')):
        kind = str(detail.get('updateType') or detail.get('type') or '').lower().replace('_', '')
        if kind in {'goal', 'redcard', 'sendingoff', 'dismissal'}:
            return str(detail.get('updateType') or detail.get('type') or 'MATERIAL_EVENT').upper()
    return None


def _koPostSafety(team, post_snapshot, scheduled, now_epoch=None):
    """Classify the one post-KO candidate using Betfair website live state.

    SAFE means the website timer/status still shows the match right at KO and no
    goal/red card has appeared. WAIT gives the website a short chance to catch
    up with the price feed. UNSAFE means use the locked scheduled-time pre-KO.
    """
    now_epoch = now_epoch or time.time()
    if not isinstance(post_snapshot, dict):
        return 'UNSAFE', 'NO_POST'

    event_id = getEventID(team)
    post_time = post_snapshot.get('time') or now_epoch
    timeline_fresh = event_id not in TIMELINE_MISSING and bool(LATEST_TIMELINES.get(event_id))

    if not timeline_fresh:
        # Without the website timer, accept only a post price that arrived on the
        # first ordinary 30-second cycle around the theoretical KO. A delayed
        # in-play wake-up must never replace the locked pre-KO book.
        if post_time <= scheduled + KO_POST_BOUNDARY_SECONDS:
            return 'SAFE', 'NO_TIMELINE_NEAR_SCHEDULE'
        return 'UNSAFE', 'NO_TIMELINE_LATE'

    event = _safeDict(LATEST_TIMELINES.get(event_id))
    material = _websiteMaterialEvent(event)
    if material:
        return 'UNSAFE', material

    elapsed = eventElapsedMinutes(event)
    status = str(event.get('inPlayMatchStatus') or '')
    started = matchHasStarted(event)

    if started:
        if elapsed is not None:
            if 0 <= elapsed <= KO_POST_WEBSITE_MAX_MINUTES:
                return 'SAFE', f'WEB_{elapsed:g}M'
            return 'UNSAFE', f'WEB_{elapsed:g}M_LATE'
        # Website says live but has no usable minute. Give the status feed one
        # short cycle to populate its timer, then fall back to pre-KO.
        if now_epoch - post_time <= KO_POST_CONFIRM_WAIT_SECONDS:
            return 'WAIT', 'WEB_STARTED_NO_MINUTE'
        return 'UNSAFE', 'WEB_STARTED_NO_MINUTE_LATE'

    # Price feed can flip in-play just before the website status response catches
    # up. Preserve this first post snapshot but never replace it with a later one.
    if now_epoch - post_time <= KO_POST_CONFIRM_WAIT_SECONDS:
        return 'WAIT', f'WEB_NOT_STARTED_{status or "NONE"}'
    return 'UNSAFE', 'WEB_NOT_STARTED_LATE'


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
    """Log pre/post KO only when the boundary move is unusually large."""
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


def _koUsePreWhenPostWindowGone(team, scheduled, now_epoch=None):
    """Return True once a future post-KO observation would be too late to trust."""
    now_epoch = now_epoch or time.time()
    event_id = getEventID(team)
    timeline_fresh = event_id not in TIMELINE_MISSING and bool(LATEST_TIMELINES.get(event_id))
    if not timeline_fresh:
        return now_epoch > scheduled + KO_POST_BOUNDARY_SECONDS

    event = _safeDict(LATEST_TIMELINES.get(event_id))
    if _websiteMaterialEvent(event):
        return True
    if not matchHasStarted(event):
        # Genuine delayed kick-off: keep watching. The saved pre-KO book remains
        # locked at the scheduled start and will not be replaced.
        return False
    elapsed = eventElapsedMinutes(event)
    return elapsed is not None and elapsed > KO_POST_WEBSITE_MAX_MINUTES


def selectKOBoundary(team, start=None, now_epoch=None):
    """Select already-captured KO evidence without synthesising odds."""
    now_epoch = now_epoch or time.time()
    state = KO_CAPTURE_STATE.get(getMarketID(team), {}) or {}
    pre = state.get('pre') if isinstance(state.get('pre'), dict) else None
    post = state.get('post') if isinstance(state.get('post'), dict) else None
    event = _safeDict(LATEST_TIMELINES.get(getEventID(team)))
    elapsed = eventElapsedMinutes(event)
    material = _websiteMaterialEvent(event) if event else None

    if material and isinstance(pre, dict):
        result = _rawBoundaryResult(pre, 'KO_PRE_MATERIAL_EVENT')
        return result, True
    if isinstance(post, dict):
        result = _rawBoundaryResult(post, state.get('post_method') or 'KO_POST_BEST')
        return result, True
    if elapsed is not None and elapsed > KO_LIVE_ELAPSED_MAX_MINUTES:
        if isinstance(pre, dict):
            return _rawBoundaryResult(pre, 'KO_PRE_LATE_FALLBACK'), True
        return None, True
    return None, False

def firstKosherKO(team, start):
    result, ready = selectKOBoundary(team, start)
    if result is None:
        return None, None
    selected = result.get('selected') or result.get('raw')
    return selected, result.get('method')



def _boundaryScoreChanged(state, event):
    baseline = state.get('boundary_score') if isinstance(state, dict) else None
    current = currentScore(event) if isinstance(event, dict) else None
    if baseline is None or current is None:
        return False
    return list(current) != list(baseline)


def _postPollAllowed(state, now_epoch):
    """Whether another post-boundary website price request is still allowed."""
    if not isinstance(state, dict):
        return False
    count = int(state.get('post_poll_count') or 0)
    if count >= POST_RECOVERY_TOTAL_POLLS:
        return False
    deadline = float(state.get('recovery_deadline') or 0)
    if not deadline:
        return True
    if now_epoch <= deadline:
        return True
    # The scheduler may wake a fraction late for the final T+90 slot.  Permit
    # only that already-scheduled final slot, never a genuinely late recovery.
    retry = state.get('next_retry')
    return (retry is not None and float(retry) <= deadline
            and now_epoch <= deadline + BOUNDARY_FINAL_SLOT_GRACE_SECONDS)


def _scheduleNextPostPoll(state, now_epoch):
    count = int(state.get('post_poll_count') or 0)
    deadline = float(state.get('recovery_deadline') or 0)
    if count >= POST_RECOVERY_TOTAL_POLLS or (deadline and now_epoch >= deadline):
        return False
    due = now_epoch + RECOVERY_INTERVAL
    if deadline:
        due = min(due, deadline)
    state['next_retry'] = due
    return True


def _activateKORecovery(team, now_epoch=None):
    """Start/resume the shared non-blocking POST capture for KickOff."""
    now_epoch = time.time() if now_epoch is None else now_epoch
    event_id = getEventID(team)
    market_id = getMarketID(team)
    state = KO_CAPTURE_STATE.setdefault(market_id, {})
    if state.get('phase') in {'FROZEN', 'MISSING'}:
        return False

    boundary = FIRST_HALF_START_TIMES.get(event_id)
    if boundary is None:
        return False

    changed = False
    desired = {
        'phase': 'POST_RECOVERY',
        'event_id': event_id,
        'capture_started_at': state.get('capture_started_at') or now_epoch,
        'boundary_observed_at': boundary,
        'source': FIRST_HALF_START_SOURCE.get(event_id, state.get('source', 'timeline')),
        'recovery_deadline': boundary + BOUNDARY_RECOVERY_SECONDS,
    }
    event = _safeDict(LATEST_TIMELINES.get(event_id))
    if state.get('boundary_score') is None:
        desired['boundary_score'] = [0, 0]
    if state.get('post_poll_count') is None:
        desired['post_poll_count'] = 0
    if state.get('next_retry') is None:
        desired['next_retry'] = now_epoch

    for key, value in desired.items():
        if state.get(key) != value:
            state[key] = value
            changed = True
    if changed:
        markStateDirty()
    return True

def captureKOBoundaryPrice(team, initial_result=None):
    """Compatibility wrapper: KO recovery is scheduled, never blocking."""
    if not _activateKORecovery(team):
        return None
    state = KO_CAPTURE_STATE.get(getMarketID(team), {}) or {}
    snapshot = _usableBoundarySnapshot(initial_result)
    if isinstance(snapshot, dict):
        current = state.get('post') if isinstance(state.get('post'), dict) else None
        chosen = _betterRealSnapshot(current, snapshot)
        if chosen is not current:
            state['post'] = compactHistorySnapshot(chosen)
            state['post_method'] = 'KO_POST_CANDIDATE'
            markStateDirty()
        if _snapshotAcceptable(snapshot):
            return _rawBoundaryResult(snapshot, 'KO_POST_ACCEPTABLE')
    return None


def applyPendingKO(timelines, results=None):
    """Turn a genuine KickOff into the unified non-blocking POST capture."""
    results = results or {}
    now_epoch = time.time()
    for team in list(DA_TEAMS):
        if koIsFilled(team):
            continue
        market_id = getMarketID(team)
        event_id = getEventID(team)
        event = _safeDict(LATEST_TIMELINES.get(event_id))
        if not event or not matchHasStarted(event):
            continue

        if not _activateKORecovery(team, now_epoch):
            continue
        state = KO_CAPTURE_STATE.setdefault(market_id, {})
        if _websiteMaterialEvent(event) or _boundaryScoreChanged(state, event):
            _finaliseKORecovery(team, reason='MATERIAL_EVENT')
            continue

        # If the ordinary 30-second pre-window request happened after KickOff in
        # this same cycle, it is already our immediate POST attempt.  Do not make
        # a duplicate T+0 call; schedule the first retry for +15s if necessary.
        if market_id in results and int(state.get('post_poll_count') or 0) == 0:
            state['post_poll_count'] = 1
            snapshot = _usableBoundarySnapshot(results.get(market_id))
            if isinstance(snapshot, dict):
                current = state.get('post') if isinstance(state.get('post'), dict) else None
                chosen = _betterRealSnapshot(current, snapshot)
                if chosen is not current:
                    state['post'] = compactHistorySnapshot(chosen)
                    state['post_method'] = 'KO_POST_CANDIDATE'
                    markStateDirty()
                if _snapshotAcceptable(snapshot):
                    state['phase'] = 'FROZEN'
                    _clearRecoveryTiming(state)
                    markStateDirty()
                    freezeKO(team, _rawBoundaryResult(snapshot, 'KO_POST_ACCEPTABLE'))
                    continue
            _scheduleNextPostPoll(state, time.time())

def secondHalfGoalRecorded(event):
    return secondHalfMaterialEventRecorded(event) is not None


def secondHalfMaterialEventRecorded(event):
    restart_seen = False
    for detail in _safeDetails(_safeDict(event).get('updateDetails')):
        event_type = str(detail.get('updateType') or detail.get('type') or '')
        if event_type == 'SecondHalfKickOff':
            restart_seen = True
            continue
        normalised = event_type.lower().replace('_', '')
        if normalised not in {'goal', 'redcard', 'sendingoff', 'dismissal'}:
            continue
        try:
            elapsed = float(detail.get('elapsedRegularTime') or detail.get('matchTime') or 0)
        except Exception:
            elapsed = 0
        if restart_seen or elapsed >= 46:
            return event_type.upper() or 'MATERIAL_EVENT'
    return None

def htBoundarySafety(event_id, event, require_recorded_score=False):
    ht_score = FIRST_HALF_END_SCORES.get(event_id)
    if ht_score is None:
        ht_score = explicitHalfTimeScore(event)
    if require_recorded_score and ht_score is None:
        return False, 'HT_SCORE_NOT_RECORDED', None
    live_score = currentScore(event)
    if ht_score is not None and live_score is not None and list(live_score) != list(ht_score):
        return False, 'SCORE_CHANGED_AFTER_HT', list(ht_score)
    material = secondHalfMaterialEventRecorded(event)
    if material:
        return False, material, list(ht_score) if ht_score is not None else None
    return True, '', list(ht_score) if ht_score is not None else None

def secondHalfSignal(event, event_id, live_signals=None):
    """Return an SHKO signal already validated by the 45/46 live-minute gate."""
    now_epoch = time.time()
    event = normaliseTimelineEvent(event)
    minute = eventElapsedMinutes(event)
    live = (live_signals or {}).get(event_id, {}).get('SecondHalfKickOff')
    if live is not None:
        return (live.get('source'), live.get('detail_time') or live.get('observed_at', now_epoch),
                live.get('bf_minute', minute))

    # If the boundary was already persisted (e.g. crash during recovery), allow
    # recovery to resume from it.  Do not manufacture a fresh boundary merely
    # because the persistent second-half status is visible.
    if event_id in SECOND_HALF_START_TIMES:
        return (SECOND_HALF_START_SOURCE.get(event_id, 'RESTORED'),
                SECOND_HALF_START_TIMES.get(event_id), minute)
    return None, None, minute

def recoverPostStartSnapshot(team, snapshot, reference=None):
    """Post-boundary snapshots are recorded raw; no BACK reconstruction."""
    return _recoverBoundarySnapshot(team, snapshot, reference)

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



def _activateHTRecovery(team, source, observed_at, now_epoch=None):
    """Start/resume the shared non-blocking POST capture for SecondHalfKickOff."""
    now_epoch = time.time() if now_epoch is None else now_epoch
    event_id = getEventID(team)
    state = HT_CAPTURE_STATE.setdefault(event_id, {})
    if htIsFilled(team) or state.get('phase') in {'FROZEN', 'MISSING'}:
        return False

    boundary = observed_at or SECOND_HALF_START_TIMES.get(event_id)
    if boundary is None:
        return False

    changed = False
    desired = {
        'phase': 'POST_RECOVERY',
        'boundary_observed_at': boundary,
        'source': source or SECOND_HALF_START_SOURCE.get(event_id, 'STATUS'),
        'capture_started_at': state.get('capture_started_at') or now_epoch,
        'recovery_deadline': boundary + BOUNDARY_RECOVERY_SECONDS,
    }
    if state.get('boundary_score') is None:
        score = FIRST_HALF_END_SCORES.get(event_id)
        if score is None:
            score = currentScore(_safeDict(LATEST_TIMELINES.get(event_id)))
        if score is not None:
            desired['boundary_score'] = list(score)
    if state.get('post_poll_count') is None:
        desired['post_poll_count'] = 0
    if state.get('next_retry') is None:
        desired['next_retry'] = now_epoch

    for key, value in desired.items():
        if state.get(key) != value:
            state[key] = value
            changed = True
    if changed:
        markStateDirty()
    return True

def captureHTBoundaryPrice(team, event, source, observed_at, bf_minute, initial_result=None):
    """Compatibility wrapper: HT recovery is scheduled, never blocking."""
    if not _activateHTRecovery(team, source, observed_at):
        return None
    state = HT_CAPTURE_STATE.get(getEventID(team), {}) or {}
    snapshot = _usableBoundarySnapshot(initial_result)
    if isinstance(snapshot, dict):
        current = state.get('post') if isinstance(state.get('post'), dict) else None
        chosen = _betterRealSnapshot(current, snapshot)
        if chosen is not current:
            state['post'] = compactHistorySnapshot(chosen)
            markStateDirty()
        if _snapshotAcceptable(snapshot):
            return _rawBoundaryResult(snapshot, 'HT_POST_ACCEPTABLE')
    return None

def _htRecessFallbackResult(team):
    snapshot = HT_RECESS_STATE.get(getEventID(team))
    if not isinstance(snapshot, dict):
        return None
    result = _rawBoundaryResult(snapshot, 'HT_PRE_FALLBACK')
    return result if result is not None and _realBackCount(result.get('selected')) > 0 else None


def processSecondHalfStarts(timelines, live_signals=None, results=None):
    """SecondHalfKickOff starts the same POST mechanism used for KO."""
    results = results or {}
    now_epoch = time.time()
    for event in timelines:
        event = normaliseTimelineEvent(event)
        event_id = collection.normalise_id(event.get('eventId'))
        team = findTeamByEvent(event_id)
        if team is None or htIsFilled(team):
            continue

        source, evidence_time, bf_minute = secondHalfSignal(event, event_id, live_signals)
        if source is None and event_id not in SECOND_HALF_START_TIMES:
            continue

        if event_id not in SECOND_HALF_START_TIMES:
            SECOND_HALF_START_TIMES[event_id] = evidence_time or now_epoch
            SECOND_HALF_START_SOURCE[event_id] = source or 'STATUS'
            markStateDirty()
        else:
            evidence_time = SECOND_HALF_START_TIMES[event_id]
            source = SECOND_HALF_START_SOURCE.get(event_id, source or 'STATUS')

        if not _activateHTRecovery(team, source, evidence_time, now_epoch):
            continue
        state = HT_CAPTURE_STATE.setdefault(event_id, {})
        market_id = getMarketID(team)
        if secondHalfMaterialEventRecorded(event) or _boundaryScoreChanged(state, event):
            _finaliseHTRecovery(team, reason='MATERIAL_EVENT')
            continue

        if market_id in results and int(state.get('post_poll_count') or 0) == 0:
            state['post_poll_count'] = 1
            snapshot = _usableBoundarySnapshot(results.get(market_id))
            if isinstance(snapshot, dict):
                current = state.get('post') if isinstance(state.get('post'), dict) else None
                chosen = _betterRealSnapshot(current, snapshot)
                if chosen is not current:
                    state['post'] = compactHistorySnapshot(chosen)
                    markStateDirty()
                if _snapshotAcceptable(snapshot):
                    state['phase'] = 'FROZEN'
                    _clearRecoveryTiming(state)
                    markStateDirty()
                    freezeHT(team, _rawBoundaryResult(snapshot, 'HT_POST_ACCEPTABLE'), event)
                    continue
            _scheduleNextPostPoll(state, time.time())

def _chooseBoundaryFallback(post, pre):
    """Choose boundary evidence using the agreed simple hierarchy.

    An acceptable POST always wins, even if PRE was fractionally prettier.  If
    no acceptable POST exists, an acceptable PRE is the insurance.  When neither
    side ever produced an acceptable book, retain the best complete real book by
    overround quality, then the best partial evidence rather than invent prices.
    """
    if _snapshotAcceptable(post):
        return post, 'POST'
    if _snapshotAcceptable(pre):
        return pre, 'PRE'

    post_complete = _completeRealBack(post)
    pre_complete = _completeRealBack(pre)
    if post_complete and pre_complete:
        if _snapshotQualityKey(post) > _snapshotQualityKey(pre):
            return post, 'POST'
        return pre, 'PRE'
    if post_complete:
        return post, 'POST'
    if pre_complete:
        return pre, 'PRE'

    if isinstance(post, dict) and _realBackCount(post) > 0:
        if isinstance(pre, dict) and _realBackCount(pre) > 0:
            if _snapshotQualityKey(post) > _snapshotQualityKey(pre):
                return post, 'POST_PARTIAL'
            return pre, 'PRE_PARTIAL'
        return post, 'POST_PARTIAL'
    if isinstance(pre, dict) and _realBackCount(pre) > 0:
        return pre, 'PRE_PARTIAL'
    return None, 'MISS'

def _clearRecoveryTiming(state):
    changed = False
    for key in ['next_retry', 'recovery_deadline', 'pre_retry_due']:
        if key in state:
            state.pop(key, None)
            changed = True
    return changed


def _finaliseKORecovery(team, reason='DEADLINE'):
    if team is None or koIsFilled(team):
        return
    market_id = getMarketID(team)
    state = KO_CAPTURE_STATE.setdefault(market_id, {})
    post = state.get('post') if isinstance(state.get('post'), dict) else None
    pre = state.get('pre') if isinstance(state.get('pre'), dict) else None
    chosen, source = _chooseBoundaryFallback(post, pre)

    if chosen is not None:
        if source == 'POST':
            method = 'KO_POST_BEST'
            if reason == 'MATERIAL_EVENT':
                method = 'KO_POST_BEFORE_MATERIAL_EVENT'
        elif source == 'PRE':
            method = {
                'MATERIAL_EVENT': 'KO_PRE_MATERIAL_EVENT',
                'LATE': 'KO_PRE_LATE_FALLBACK',
            }.get(reason, 'KO_PRE_FALLBACK')
        elif source == 'POST_PARTIAL':
            method = 'KO_POST_PARTIAL'
        elif source == 'PRE_PARTIAL':
            method = 'KO_PRE_PARTIAL_FALLBACK'
        else:
            method = 'KO_BEST_PARTIAL'
        state['phase'] = 'FROZEN'
        _clearRecoveryTiming(state)
        markStateDirty()
        freezeKO(team, _rawBoundaryResult(chosen, method))
        return

    state['phase'] = 'MISSING'
    _clearRecoveryTiming(state)
    KO_MISSING.add(market_id)
    rememberCaptureEvidence(team, 'KO', {'method': 'MISS', 'raw': None})
    if reason == 'LATE':
        event = _safeDict(LATEST_TIMELINES.get(getEventID(team)))
        elapsed = eventElapsedMinutes(event)
        logIssue(team, 'late_start', 'KO', f'first_seen={elapsed:g}m' if elapsed is not None else 'late')
    markStateDirty()


def _finaliseHTRecovery(team, reason='DEADLINE'):
    if team is None or htIsFilled(team):
        return
    event_id = getEventID(team)
    state = HT_CAPTURE_STATE.setdefault(event_id, {})
    post = state.get('post') if isinstance(state.get('post'), dict) else None
    pre = HT_RECESS_STATE.get(event_id)
    chosen, source = _chooseBoundaryFallback(post, pre)
    event = normaliseTimelineEvent(LATEST_TIMELINES.get(event_id, {
        'eventId': event_id,
        'score': team.get('score', {}),
        'updateDetails': team.get('updateDetails', [])
    }))

    if chosen is not None:
        if source == 'POST':
            method = 'HT_POST_BEST'
            if reason == 'MATERIAL_EVENT':
                method = 'HT_POST_BEFORE_MATERIAL_EVENT'
        elif source == 'PRE':
            method = 'HT_PRE_FALLBACK'
        elif source == 'POST_PARTIAL':
            method = 'HT_POST_PARTIAL'
        elif source == 'PRE_PARTIAL':
            method = 'HT_PRE_PARTIAL_FALLBACK'
        else:
            method = 'HT_BEST_PARTIAL'
        state['phase'] = 'FROZEN'
        _clearRecoveryTiming(state)
        HT_REPLENISH_LAST_ATTEMPT.pop(event_id, None)
        markStateDirty()
        freezeHT(team, _rawBoundaryResult(chosen, method), event)
        return

    state['phase'] = 'MISSING'
    _clearRecoveryTiming(state)
    HT_REPLENISH_LAST_ATTEMPT.pop(event_id, None)
    markStateDirty()
    freezeHT(team, {
        'back': [0.0, 0.0, 0.0],
        'lay': [0.0, 0.0, 0.0],
        'book': None,
        'method': 'MISS',
        'raw': None
    }, event)
    logIssue(team, 'missing_price', 'HT', 'no_real_pre_or_post_odds')


def _activeBoundaryRecoveryDue(now_epoch=None):
    now_epoch = time.time() if now_epoch is None else now_epoch
    due = []
    for team in DA_TEAMS:
        if team is None:
            continue
        market_id = getMarketID(team)
        event_id = getEventID(team)

        if not koIsFilled(team):
            state = KO_CAPTURE_STATE.get(market_id, {}) or {}
            if state.get('phase') == 'POST_RECOVERY':
                if state.get('next_retry') is not None:
                    due.append(float(state.get('next_retry')))
                if state.get('recovery_deadline') is not None:
                    due.append(float(state.get('recovery_deadline')))

        if not htIsFilled(team):
            state = HT_CAPTURE_STATE.get(event_id, {}) or {}
            if state.get('phase') == 'POST_RECOVERY':
                if state.get('next_retry') is not None:
                    due.append(float(state.get('next_retry')))
                if state.get('recovery_deadline') is not None:
                    due.append(float(state.get('recovery_deadline')))
    return min(due) if due else None

def _dueRecoveryJobs(now_epoch=None):
    """Return due POST jobs keyed by market; KO/HT share one scheduler."""
    now_epoch = time.time() if now_epoch is None else now_epoch
    jobs = {}
    for team in list(DA_TEAMS):
        if team is None:
            continue
        market_id = getMarketID(team)
        event_id = getEventID(team)
        if not market_id or not event_id:
            continue

        if not koIsFilled(team):
            state = KO_CAPTURE_STATE.get(market_id, {}) or {}
            if state.get('phase') == 'POST_RECOVERY':
                deadline = float(state.get('recovery_deadline') or 0)
                retry = float(state.get('next_retry') or 0)
                if deadline <= now_epoch or retry <= now_epoch:
                    jobs[market_id] = (team, 'KO_POST')

        if not htIsFilled(team):
            state = HT_CAPTURE_STATE.get(event_id, {}) or {}
            if state.get('phase') == 'POST_RECOVERY':
                deadline = float(state.get('recovery_deadline') or 0)
                retry = float(state.get('next_retry') or 0)
                if deadline <= now_epoch or retry <= now_epoch:
                    jobs[market_id] = (team, 'HT_POST')
    return jobs

def runBoundaryRecoveryTick(refresh_timelines=True):
    """Service all due KO/HT POST captures together, without blocking.

    Each boundary gets one immediate price request and at most six further calls
    at 15-second intervals, ending at T+90 seconds.  Before every retry we refresh
    the timeline and stop immediately if the score changed or a red card/goal was
    recorded.  Earlier safe POST evidence is never erased by a later event.
    """
    now_epoch = time.time()
    jobs = _dueRecoveryJobs(now_epoch)
    if not jobs:
        return False

    event_ids = sorted({getEventID(team) for team, _ in jobs.values() if getEventID(team)})
    if refresh_timelines and event_ids:
        refreshed = requestTrackedTimelines(event_ids)
        if refreshed:
            live_signals = detectLivePhaseSignals(refreshed)
            rememberTimelineStates(refreshed, live_signals)
            processFinished(refreshed)
            processKOEvents(refreshed)
            applyPendingKO(refreshed, {})
            processSecondHalfStarts(refreshed, live_signals, {})

    now_epoch = time.time()
    jobs = _dueRecoveryJobs(now_epoch)
    if not jobs:
        persistState()
        return True

    poll = {}
    finalise_ko = []
    finalise_ht = []

    for market_id, (team, kind) in list(jobs.items()):
        event_id = getEventID(team)
        event = _safeDict(LATEST_TIMELINES.get(event_id))

        if kind == 'KO_POST':
            state = KO_CAPTURE_STATE.get(market_id, {}) or {}
            material = _websiteMaterialEvent(event)
            if material or _boundaryScoreChanged(state, event):
                finalise_ko.append((team, 'MATERIAL_EVENT'))
                continue
            if not _postPollAllowed(state, now_epoch):
                finalise_ko.append((team, 'DEADLINE'))
                continue
            poll[market_id] = (team, kind)

        elif kind == 'HT_POST':
            state = HT_CAPTURE_STATE.get(event_id, {}) or {}
            material = secondHalfMaterialEventRecorded(event)
            if material or _boundaryScoreChanged(state, event):
                finalise_ht.append((team, 'MATERIAL_EVENT'))
                continue
            if not _postPollAllowed(state, now_epoch):
                finalise_ht.append((team, 'DEADLINE'))
                continue
            poll[market_id] = (team, kind)

    for team, reason in finalise_ko:
        _finaliseKORecovery(team, reason)
    for team, reason in finalise_ht:
        _finaliseHTRecovery(team, reason)

    if poll:
        market_ids = list(poll.keys())
        marketbook = getCleanExchangePricesfromWebsite(market_ids, force=True)
        response_time = time.time()

        for market_id, (team, kind) in poll.items():
            event_id = getEventID(team)
            snapshot = extractSnapshot(team, marketbook)
            if snapshot is not None:
                snapshot['request_time'] = now_epoch
                snapshot['response_time'] = response_time

            if kind == 'KO_POST':
                state = KO_CAPTURE_STATE.setdefault(market_id, {})
                state['post_poll_count'] = int(state.get('post_poll_count') or 0) + 1
                if isinstance(snapshot, dict) and _realBackCount(snapshot) > 0:
                    current = state.get('post') if isinstance(state.get('post'), dict) else None
                    chosen = _betterRealSnapshot(current, snapshot)
                    if chosen is not current:
                        state['post'] = compactHistorySnapshot(chosen)
                        state['post_method'] = 'KO_POST_CANDIDATE'
                        markStateDirty()
                    if _snapshotAcceptable(snapshot):
                        state['phase'] = 'FROZEN'
                        _clearRecoveryTiming(state)
                        markStateDirty()
                        freezeKO(team, _rawBoundaryResult(snapshot, 'KO_POST_ACCEPTABLE'))
                        continue

                if not _scheduleNextPostPoll(state, response_time):
                    _finaliseKORecovery(team, 'DEADLINE')

            elif kind == 'HT_POST':
                state = HT_CAPTURE_STATE.setdefault(event_id, {})
                state['post_poll_count'] = int(state.get('post_poll_count') or 0) + 1
                HT_REPLENISH_LAST_ATTEMPT[event_id] = now_epoch
                if isinstance(snapshot, dict) and _realBackCount(snapshot) > 0:
                    current = state.get('post') if isinstance(state.get('post'), dict) else None
                    chosen = _betterRealSnapshot(current, snapshot)
                    if chosen is not current:
                        state['post'] = compactHistorySnapshot(chosen)
                        markStateDirty()
                    if _snapshotAcceptable(snapshot):
                        state['phase'] = 'FROZEN'
                        _clearRecoveryTiming(state)
                        HT_REPLENISH_LAST_ATTEMPT.pop(event_id, None)
                        markStateDirty()
                        event = normaliseTimelineEvent(LATEST_TIMELINES.get(event_id, {}))
                        freezeHT(team, _rawBoundaryResult(snapshot, 'HT_POST_ACCEPTABLE'), event)
                        continue

                if not _scheduleNextPostPoll(state, response_time):
                    _finaliseHTRecovery(team, 'DEADLINE')

    persistState()
    return True

def _rawMarketAvailable(snapshot):
    if snapshot is None:
        return False
    backs = snapshot.get('back', [])
    lays = snapshot.get('lay', [])
    if len(backs) != 3 or len(lays) != 3:
        return False
    return all(((backs[index] or 0) > 1.0) or ((lays[index] or 0) > 1.0) for index in range(3))

def freezeKO(team, result):
    prices, inferred = _outputTriplet(result.get('back', []))
    result = copy.deepcopy(result)
    if inferred:
        result['inferred'] = list(result.get('inferred', []) or []) + inferred
    market_id = getMarketID(team)
    event_id = getEventID(team)
    KO_MISSING.discard(market_id)
    state = KO_CAPTURE_STATE.setdefault(market_id, {})
    state.update({'event_id': event_id, 'start': FIRST_HALF_START_TIMES.get(event_id),
                  'source': FIRST_HALF_START_SOURCE.get(event_id, state.get('source', 'unknown')),
                  'phase': 'FROZEN'})
    rememberCaptureEvidence(team, 'KO', result)
    team['output']['KO_1'], team['output']['KO_2'], team['output']['KO_X'] = prices
    updateTeamExchange(team, result.get('raw'))
    markStateDirty()
    print(f"KO: {team['output']['Home']} - {team['output']['Away']} {prices}")
    # Persisted by the enclosing normal/recovery cycle.

def freezeHT(team, result, event_details):
    prices, inferred = _outputTriplet(result.get('back', []))
    result = copy.deepcopy(result)
    if inferred:
        result['inferred'] = list(result.get('inferred', []) or []) + inferred
    rememberCaptureEvidence(team, 'HT', result)
    team['output']['HT_1'], team['output']['HT_2'], team['output']['HT_X'] = prices
    team['score'] = _safeDict(event_details.get('score'))

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
    roundOutputDecimals(team['output'])
    updateTeamExchange(team, result.get('raw'))
    markStateDirty()
    print(f"HT: {team['output']['Home']} - {team['output']['Away']} {prices}")
    # Persisted by the enclosing normal/recovery cycle.

def koIsFilled(team):
    if any(team['output'].get(key, 0) for key in ['KO_1', 'KO_2', 'KO_X']):
        return True
    return getMarketID(team) in KO_MISSING

def htIsFilled(team):
    return team['output'].get('HT_Home', '') != ''


def preKOFocusEntries():
    """Unresolved KO matches that still need website/timeline watching."""
    now_epoch = time.time()
    entries = {}
    for entry in NEAR_START_CATALOGUE.values():
        if entryAlreadyFinalized(entry):
            continue
        market_time = scheduledStart(entry)
        if market_time is None or now_epoch < market_time - (KO_FOCUS_BEFORE_MINUTES * 60):
            continue
        team = findTeamByEvent(getEventID(entry))
        if team is not None and koIsFilled(team):
            continue
        target = team or entry
        entries[getMarketID(target)] = target

    for team in DA_TEAMS:
        if koIsFilled(team):
            continue
        market_time = scheduledStart(team)
        if market_time is None or now_epoch < market_time - (KO_FOCUS_BEFORE_MINUTES * 60):
            continue
        entries[getMarketID(team)] = team
    return list(entries.values())


def koStandardPriceEntries():
    """Routine 30-second KO prices only in the scheduled -2 minute pre-window.

    Post-KO prices are requested from the KickOff boundary handler, not by an
    indefinite in-play watcher. This prevents a delayed market wake-up many
    minutes into a match from being treated as KO.
    """
    now_epoch = time.time()
    entries = {}
    for entry in NEAR_START_CATALOGUE.values():
        if entryAlreadyFinalized(entry):
            continue
        market_time = scheduledStart(entry)
        if market_time is None or not (market_time - KO_BACKUP_MAX_AGE_SECONDS <= now_epoch <= market_time):
            continue
        event_id = getEventID(entry)
        team = findTeamByEvent(event_id)
        if team is None:
            team = initialiseTeam(entry, LATEST_TIMELINES.get(event_id, {}))
        if team is not None and not koIsFilled(team) and event_id not in FIRST_HALF_START_TIMES:
            entries[getMarketID(team)] = team
    for team in DA_TEAMS:
        if koIsFilled(team) or getEventID(team) in FIRST_HALF_START_TIMES:
            continue
        market_time = scheduledStart(team)
        if market_time is None or not (market_time - KO_BACKUP_MAX_AGE_SECONDS <= now_epoch <= market_time):
            continue
        entries[getMarketID(team)] = team
    return list(entries.values())

def htRecessPriceEntries():
    """Pre-restart HT insurance on the ordinary 30-second heartbeat.

    It begins 13 minutes after the observed FirstHalfEnd and ends the instant we
    first observe SecondHalfKickOff.  It does not depend on Betfair continuing
    to label the current status exactly ``FirstHalfEnd``.
    """
    return [team for team in htFocusEntries()
            if getEventID(team) not in SECOND_HALF_START_TIMES]

def rememberLatestPreKO(entries, results):
    """Keep the best real PRE observation from scheduled KO -2 min to scheduled KO."""
    now_epoch = time.time()
    for entry in entries:
        market_id = getMarketID(entry)
        result = results.get(market_id) or {}
        snapshot = _usableBoundarySnapshot(result)
        if snapshot is None:
            continue
        team = findTeamByEvent(getEventID(entry)) or entry
        scheduled = scheduledStart(team)
        current_time = snapshot.get('time', now_epoch) or now_epoch
        boundary = FIRST_HALF_START_TIMES.get(getEventID(team))
        if scheduled is None or current_time < scheduled - KO_BACKUP_MAX_AGE_SECONDS or current_time > scheduled:
            continue
        if boundary is not None and current_time >= boundary:
            continue

        state = KO_CAPTURE_STATE.setdefault(market_id, {})
        state['event_id'] = getEventID(team)
        previous = state.get('pre') if isinstance(state.get('pre'), dict) else None
        chosen = _betterRealSnapshot(previous, snapshot)
        if chosen is previous:
            continue
        if isinstance(previous, dict):
            movement = _koTripletTickMove(previous.get('back', []), snapshot.get('back', []))
            if movement is not None:
                moves = list(state.get('pm') or [])
                moves.append(int(movement))
                state['pm'] = moves[-6:]
        state['pre'] = compactHistorySnapshot(chosen)
        state['pre_observed_at'] = chosen.get('time', current_time)
        if state.get('phase') not in {'FROZEN', 'MISSING'}:
            state['phase'] = 'PREWATCH'
        markStateDirty()

def rememberFirstPostKO(entries, results):
    """Deprecated compatibility hook: KickOff event now drives post-KO capture."""
    return None

def rememberLatestHTRecess(entries, results):
    """Keep the best real pre-restart book seen after FirstHalfEnd +13 minutes."""
    now_epoch = time.time()
    for team in entries:
        event_id = getEventID(team)
        boundary = SECOND_HALF_START_TIMES.get(event_id)
        first_end = FIRST_HALF_END_TIMES.get(event_id)
        if first_end is None or now_epoch < first_end + (HT_FOCUS_AFTER_FIRST_HALF_MINUTES * 60):
            continue
        result = results.get(getMarketID(team)) or {}
        snapshot = _usableBoundarySnapshot(result)
        if snapshot is None:
            continue
        observed = snapshot.get('time', now_epoch) or now_epoch
        # Observation time relative to the boundary is what matters.  Never
        # require a particular persistent status label here.
        if boundary is not None and observed >= boundary:
            continue
        current = HT_RECESS_STATE.get(event_id)
        chosen = _betterRealSnapshot(current, snapshot)
        if chosen is not current:
            HT_RECESS_STATE[event_id] = compactHistorySnapshot(chosen)
            markStateDirty()

def htFocusEntries():
    now_epoch = time.time()
    entries = []
    for team in DA_TEAMS:
        if htIsFilled(team):
            continue
        event_id = getEventID(team)
        first_half_end = FIRST_HALF_END_TIMES.get(event_id)
        if first_half_end is None:
            continue
        focus_start = first_half_end + (HT_FOCUS_AFTER_FIRST_HALF_MINUTES * 60)
        if now_epoch < focus_start:
            continue
        second_half_start = SECOND_HALF_START_TIMES.get(event_id)
        if second_half_start is not None:
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


def eventFinished(event):
    event = _safeDict(event)
    score = _safeDict(event.get('score'))
    home = _safeDict(score.get('home'))
    away = _safeDict(score.get('away'))

    # Explicit FT scores are definitive even if the status lags. Conversely a
    # Finished status without any usable score must not create a fabricated row.
    if (home.get('fullTimeScore') not in [None, ''] and
            away.get('fullTimeScore') not in [None, '']):
        return True

    finished_signal = (
        event.get('inPlayMatchStatus') == 'Finished' or
        hasTransition(event, 'Finished') or
        hasTransition(event, 'SecondHalfEnd')
    )
    return (finished_signal and
            home.get('score') not in [None, ''] and
            away.get('score') not in [None, ''])


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
    HT_CAPTURE_STATE.pop(event_id, None)
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
    event = normaliseTimelineEvent(event)
    event_score = _safeDict(event.get('score'))
    if event_score:
        team['score'] = event_score
    else:
        team['score'] = _safeDict(team.get('score'))
    event_details = _safeDetails(event.get('updateDetails'))
    if event_details:
        team['updateDetails'] = event_details
    else:
        team['updateDetails'] = _safeDetails(team.get('updateDetails'))
    score = _safeDict(team.get('score'))
    home_score = _safeDict(score.get('home'))
    away_score = _safeDict(score.get('away'))
    ht_scores = firstHalfScore(getEventID(team), event)
    if ht_scores is not None:
        team['output']['HT_Home'] = str(ht_scores[0])
        team['output']['HT_Away'] = str(ht_scores[1])

    # If Betfair never delivered a usable SecondHalfKickOff signal, a valid
    # pre-restart book collected from FirstHalfEnd +13 minutes must not be lost.
    # Use it at finalisation when the recorded HT triplet is absent/incomplete.
    current_ht_count = 0
    for key in ['HT_1', 'HT_2', 'HT_X']:
        try:
            if float(team['output'].get(key) or 0) > 1.0:
                current_ht_count += 1
        except Exception:
            pass
    if current_ht_count < 3:
        pre_result = _htRecessFallbackResult(team)
        pre_snapshot = pre_result.get('selected') if isinstance(pre_result, dict) else None
        if _completeRealBack(pre_snapshot):
            freezeHT(team, pre_result, event)

    team['output']['FT_Home'] = home_score.get('fullTimeScore') or home_score.get('score', '')
    team['output']['FT_Away'] = away_score.get('fullTimeScore') or away_score.get('score', '')
    team['output']['FINAL'] = getFINAL(team['output'])

    # Always evaluate the strategies from the final preserved HT state. This
    # fixes rows where HT score arrived only at finalisation and MODEL_* was
    # previously left blank. Missing/non-executable HT odds are recorded as NO.
    team['output']['MODEL_DT1'] = applyModel__DT1(team)
    team['output']['MODEL_ZZCX'] = applyModel__ZZCX(team)
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


def refreshCatalogueCaches(current_catalogue, near_start_catalogue, current_catalogue_ok=True):
    """Refresh Betfair's discovery caches.

    A successful current-catalogue response is authoritative for which football
    markets Betfair still regards as active.  No local four-hour (or similar)
    delayed-KO lifetime is imposed.  Near-start cache ageing is only discovery
    housekeeping; an active market returned by Betfair remains in the current
    catalogue regardless of its originally scheduled KO.
    """
    global CATALOGUE_ACTIVE_BASELINE_READY

    current = {getEventID(entry): entry for entry in current_catalogue
               if getEventID(entry) and not entryAlreadyFinalized(entry)}
    old_ids = set(CURRENT_INPLAY_CATALOGUE)
    new_ids = set(current)
    NEWLY_ACTIVE_CATALOGUE_IDS.clear()
    if current_catalogue_ok:
        if CATALOGUE_ACTIVE_BASELINE_READY:
            NEWLY_ACTIVE_CATALOGUE_IDS.update(new_ids - old_ids)
        else:
            # Never call every in-play match a fresh KO merely because the process
            # has just started in the middle of a match.
            CATALOGUE_ACTIVE_BASELINE_READY = True

        if CURRENT_INPLAY_CATALOGUE != current:
            CURRENT_INPLAY_CATALOGUE.clear()
            CURRENT_INPLAY_CATALOGUE.update(current)

    for entry in near_start_catalogue:
        event_id = getEventID(entry)
        if not event_id:
            continue
        if entryAlreadyFinalized(entry):
            NEAR_START_CATALOGUE.pop(event_id, None)
            continue
        NEAR_START_CATALOGUE[event_id] = entry

    # This only trims stale near-start discovery metadata.  It does not expire a
    # match which Betfair still returns in CURRENT_INPLAY_CATALOGUE, nor does it
    # remove an already tracked team/state fallback.
    cutoff = time.time() - (KO_CATALOGUE_LOOKBACK_MINUTES * 60 * 2)
    expired = []
    for event_id, entry in NEAR_START_CATALOGUE.items():
        market_time = scheduledStart(entry)
        team = findTeamByEvent(event_id)
        active = event_id in CURRENT_INPLAY_CATALOGUE
        if entryAlreadyFinalized(entry) or (
                not active and team is None and market_time is not None and market_time < cutoff):
            expired.append(event_id)
    for event_id in expired:
        NEAR_START_CATALOGUE.pop(event_id, None)

def essentialTimeline(event):
    event = normaliseTimelineEvent(event)
    if not event:
        return {}
    keep_types = {'KickOff', 'FirstHalfEnd', 'SecondHalfKickOff', 'Finished', 'Goal', 'RedCard', 'SendingOff', 'Dismissal'}
    details = []
    for item in _safeDetails(event.get('updateDetails')):
        event_type = item.get('updateType') or item.get('type')
        if event_type not in keep_types:
            continue
        details.append({key: item.get(key) for key in
                        ['updateTime', 'matchTime', 'elapsedRegularTime', 'elapsedAddedTime',
                         'type', 'updateType', 'team', 'teamName'] if key in item})
    score = _safeDict(event.get('score'))
    home_score = _safeDict(score.get('home'))
    away_score = _safeDict(score.get('away'))
    return {
        'status': event.get('inPlayMatchStatus', ''),
        'elapsed': event.get('elapsedRegularTime'),
        'score': {
            'home': {key: home_score.get(key, '') for key in ['score', 'halfTimeScore', 'fullTimeScore']},
            'away': {key: away_score.get(key, '') for key in ['score', 'halfTimeScore', 'fullTimeScore']}
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
    timeline = normaliseTimelineEvent(timeline)
    if not timeline:
        return {}
    score = _safeDict(timeline.get('score'))
    home = _safeDict(score.get('home'))
    away = _safeDict(score.get('away'))
    code_map = {'KickOff': 'K', 'FirstHalfEnd': 'F', 'SecondHalfKickOff': 'S',
                'Finished': 'E', 'SecondHalfEnd': 'E', 'Goal': 'G'}
    events = []
    for item in (_safeDetails(timeline.get('events')) or _safeDetails(timeline.get('updateDetails'))):
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


def _recordMatchDay(record, fallback_day=None):
    if isinstance(record, dict):
        for value in [record.get('dt'), (record.get('o', {}) or {}).get('Date')]:
            epoch = parseBetfairTimestamp(value)
            if epoch is not None:
                return betfairAPI.datetime.datetime.fromtimestamp(
                    epoch, betfairAPI.datetime.timezone.utc).strftime('%Y%m%d')
    if isinstance(fallback_day, str) and len(fallback_day) == 8 and fallback_day.isdigit():
        return fallback_day
    return None


def _dumpRecordKey(record):
    return record.get('id') or f"{record.get('dt')}|{record.get('h')}|{record.get('a')}"


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
    # A daily dump is a natural persistent file, not a rotating runtime state.
    # Atomic replacement is enough; do not leave a per-day .bak behind.
    state_store.atomic_write_json(payload, filename, backup=False)
    return True


def saveDayDump(day, teams=None, archive_reason='U'):
    records = _readDumpRecords(day)
    for team in teams or []:
        record = matchRecordFromTeam(team, archive_reason=archive_reason)
        key = record.get('id') or f"{record.get('dt')}|{record.get('h')}|{record.get('a')}"
        records[key] = _mergeMatchRecords(records.get(key), record)
    # Deliberately write an empty schema-v2 dump when there are no records.
    # This keeps every closed day JSON-readable without special cases.
    _writeDumpRecords(day, records)


def saveProblemRecord(day, team, archive_reason='P'):
    saveDayDump(day, [team], archive_reason=archive_reason)


def migrateLegacyDumpFiles():
    """Normalise all dump material and split any mixed-day file by fixture day.

    Old checkpoint/dump variants could contain matches from more than one day.
    The filename is therefore only a fallback; the fixture timestamp is authoritative.
    """
    source_days = set()
    for filename in os.listdir('.'):
        if len(filename) >= 18 and filename[:8].isdigit() and (
                filename.endswith('_dump.json') or filename.endswith('_dump_state.json')):
            source_days.add(filename[:8])
    if not source_days:
        return False

    # Never overwrite a dump we cannot read. It is better to leave an old file
    # untouched than lose forensic material while trying to repartition it.
    raw_dumps = {}
    raw_states = {}
    for day in sorted(source_days):
        dump_name = f"{day}_dump.json"
        if os.path.isfile(dump_name):
            data = state_store.read_json(dump_name)
            if not (isinstance(data, list) or (isinstance(data, dict) and
                    data.get('v') == LIVE_STATE_SCHEMA and isinstance(data.get('matches'), dict))):
                print(f"DUMP MIGRATE deferred: unreadable/unknown {dump_name}")
                return False
            raw_dumps[day] = data
        state_name = f"{day}_dump_state.json"
        if os.path.isfile(state_name):
            data = state_store.read_json(state_name)
            if not isinstance(data, list):
                print(f"DUMP MIGRATE deferred: unreadable/unknown {state_name}")
                return False
            raw_states[day] = data

    buckets = {}

    def add_record(record, source_day):
        if record is None:
            return
        target_day = _recordMatchDay(record, source_day)
        if target_day is None:
            return
        normaliseMatchRecordOutput(record)
        key = _dumpRecordKey(record)
        target = buckets.setdefault(target_day, {})
        target[key] = _mergeMatchRecords(target.get(key), record)

    for source_day, data in raw_dumps.items():
        if isinstance(data, dict):
            for record in (data.get('matches', {}) or {}).values():
                add_record(copy.deepcopy(record), source_day)
        else:
            for raw in data:
                record = _legacyTeamToRecord(raw, 'U')
                if record is None:
                    record = _legacyForensicToRecord(raw, source_day, 'U')
                add_record(record, source_day)

    for source_day, rows in raw_states.items():
        for raw in rows:
            reason = 'P' if str(raw.get('state_reason', '')).lower() == 'finalized_problematic' else 'U'
            add_record(_legacyForensicToRecord(raw, source_day, reason), source_day)

    changed = False
    # Keep every original source day as a valid JSON dump even when all of its
    # records actually belong to another day. New target days are created too.
    for day in sorted(source_days | set(buckets)):
        records = buckets.get(day, {})
        if _writeDumpRecords(day, records):
            changed = True
            print(f"DUMP NORMALISE: {day} ({len(records)} match(es))")
    return changed


def captureNeedsForensicState(team):
    output = team.get('output', {})
    ko_missing = not all(float(output.get(key, 0) or 0) > 0 for key in ['KO_1', 'KO_2', 'KO_X'])
    ht_missing = not all(float(output.get(key, 0) or 0) > 0 for key in ['HT_1', 'HT_2', 'HT_X'])
    score_missing = output.get('HT_Home', '') in ['', '-1'] or output.get('HT_Away', '') in ['', '-1']
    evidence = CAPTURE_EVIDENCE.get(getMarketID(team), {})
    ko_method = str(evidence.get('KO', {}).get('method') or '')
    ht_method = str(evidence.get('HT', {}).get('method') or '')
    nonideal = {
        'MISS', 'KO_POST_BEST', 'KO_POST_PARTIAL', 'KO_PRE_FALLBACK',
        'KO_PRE_LATE_FALLBACK', 'KO_PRE_MATERIAL_EVENT', 'HT_POST_BEST',
        'HT_POST_PARTIAL', 'HT_PRE_FALLBACK'
    }
    fallback_or_poor = ko_method in nonideal or ht_method in nonideal
    fallback_ht = SECOND_HALF_START_SOURCE.get(getEventID(team), '') == 'ELAPSED_FALLBACK'
    return ko_missing or ht_missing or score_missing or fallback_or_poor or fallback_ht

def finaliseRestoredMatchesFromState():
    # A restored state may already contain a definitive end-of-match signal.
    # Finalise these rows before any fresh network call or day-close decision.
    for team in list(DA_TEAMS):
        event_id = getEventID(team)
        event = LATEST_TIMELINES.get(event_id)
        if event is None:
            event = {
                'eventId': event_id,
                'score': _safeDict(team.get('score')),
                'updateDetails': _safeDetails(team.get('updateDetails'))
            }
        else:
            event = normaliseTimelineEvent(event)
        if eventFinished(event):
            finaliseTeam(team, event)


def finalRecoveryNeeded(team, now_epoch=None):
    now_epoch = time.time() if now_epoch is None else now_epoch
    day = matchStartDay(team)
    close_epoch = dayCloseEpoch(day) if day else None
    if close_epoch is not None and now_epoch >= close_epoch:
        # Closed days are archived immediately by closeDueMatchDays(). Do not
        # keep yesterday's records alive merely to spend recovery requests.
        return False, ''

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


def _closedDayEvent(team):
    event_id = getEventID(team)
    event = LATEST_TIMELINES.get(event_id)
    if isinstance(event, dict) and event:
        return event
    return {
        'eventId': event_id,
        'score': team.get('score', {}) if isinstance(team, dict) else {},
        'updateDetails': team.get('updateDetails', []) if isinstance(team, dict) else []
    }


def closedDayLimitationDetail(team):
    event = _closedDayEvent(team)
    minute = eventElapsedMinutes(event)
    if minute is None:
        if getEventID(team) in SECOND_HALF_START_TIMES:
            up_to = '2H'
        elif getEventID(team) in FIRST_HALF_END_TIMES:
            up_to = 'HT'
        elif getEventID(team) in FIRST_HALF_START_TIMES:
            up_to = 'KO'
        else:
            up_to = '?'
    else:
        up_to = str(int(minute)) if float(minute).is_integer() else f"{minute:.1f}"

    output = team.get('output', {}) if isinstance(team, dict) else {}
    missing = []
    if not all(float(output.get(key, 0) or 0) > 0 for key in ['KO_1', 'KO_2', 'KO_X']):
        missing.append('KO')
    if output.get('HT_Home', '') in ['', '-1', None] or output.get('HT_Away', '') in ['', '-1', None]:
        missing.append('HT_SCORE')
    if not all(float(output.get(key, 0) or 0) > 0 for key in ['HT_1', 'HT_2', 'HT_X']):
        missing.append('HT_ODDS')
    if output.get('FT_Home', '') in ['', '-1', None] or output.get('FT_Away', '') in ['', '-1', None]:
        missing.append('FT')

    detail = f"up_to={up_to}"
    if minute is not None:
        detail += "'"
    if missing:
        detail += ';missing=' + ','.join(missing)
    return detail


def logClosedDayPartial(team):
    logIssue(team, 'closed_partial', 'DUMP', closedDayLimitationDetail(team))


def closedDayTransientFiles(day):
    return [
        f"{day}_checkpoint.json", f"{day}_checkpoint.json.bak", f"{day}_checkpoint.json.tmp",
        f"{day}_run_dump.json", f"{day}_run_dump.json.bak", f"{day}_run_dump.json.tmp",
        f"{day}_dump_state.json", f"{day}_dump_state.json.bak", f"{day}_dump_state.json.tmp",
        f"{day}_dump.json.bak", f"{day}_dump.json.tmp",
        f"{day}_results.csv.pre_repair.bak"
    ]


def removeClosedDayRuntimeFiles(day):
    removed = []
    for filename in closedDayTransientFiles(day):
        if os.path.isfile(filename):
            os.remove(filename)
            removed.append(filename)
    if removed:
        print(f"Closed {day}: removed {len(removed)} transient file(s)")
    return bool(removed)


def dueMatchDayGroups(now_epoch=None):
    now_epoch = time.time() if now_epoch is None else now_epoch
    groups = {}
    for team in DA_TEAMS:
        day = matchStartDay(team)
        close_epoch = dayCloseEpoch(day) if day else None
        if close_epoch is not None and now_epoch >= close_epoch:
            groups.setdefault(day, []).append(team)
    return groups


def storedMatchDays():
    suffixes = (
        '_results.csv', '_dump.json', '_log.txt', '_checkpoint.json',
        '_checkpoint.json.bak', '_run_dump.json', '_run_dump.json.bak',
        '_dump_state.json', '_dump_state.json.bak', '_dump.json.bak',
        '_results.csv.pre_repair.bak'
    )
    days = set()
    for filename in os.listdir('.'):
        if len(filename) < 9 or not filename[:8].isdigit():
            continue
        if any(filename.endswith(suffix) for suffix in suffixes):
            days.add(filename[:8])
    return days


def _liveStateFileHasClosedMatches(filename, now_epoch):
    data = state_store.read_json(filename) if os.path.isfile(filename) else None
    if not isinstance(data, dict) or not isinstance(data.get('matches'), dict):
        return False
    for record in data['matches'].values():
        date_text = (record or {}).get('dt', '')
        epoch = parseBetfairTimestamp(date_text)
        if epoch is None:
            continue
        day = betfairAPI.datetime.datetime.fromtimestamp(
            epoch, betfairAPI.datetime.timezone.utc).strftime('%Y%m%d')
        close_epoch = dayCloseEpoch(day)
        if close_epoch is not None and now_epoch >= close_epoch:
            return True
    return False


def closeDueMatchDays(now_epoch=None, restored=False):
    now_epoch = time.time() if now_epoch is None else now_epoch

    # First promote anything already known to be Finished into results.csv.
    # Everything else from a closed day is intentionally preserved as partial
    # forensic data rather than left in live state past the 04:00 boundary.
    finaliseRestoredMatchesFromState()
    groups = dueMatchDayGroups(now_epoch)

    days = set(groups) | storedMatchDays()
    closed_days = {day for day in days
                   if dayCloseEpoch(day) is not None and now_epoch >= dayCloseEpoch(day)}

    state_needs_sync = (
        _liveStateFileHasClosedMatches(LIVE_STATE_FILE, now_epoch) or
        _liveStateFileHasClosedMatches(LIVE_STATE_FILE + '.bak', now_epoch)
    )
    changed = False

    for day in sorted(closed_days):
        teams = list(groups.get(day, []))
        if teams:
            for team in teams:
                logClosedDayPartial(team)
            saveDayDump(day, teams, archive_reason='R' if restored else 'U')
            purgeTeams(teams)
            print(f"DAY CLOSE: {len(teams)} partial match(es) -> {day}_dump.json")
            changed = True
        else:
            # The dump file exists for every closed day even when there was
            # nothing unresolved to archive.
            before = os.path.isfile(f"{day}_dump.json")
            saveDayDump(day, [])
            changed = changed or not before

        changed = removeClosedDayRuntimeFiles(day) or changed

    if changed or state_needs_sync:
        # Both recovery files must contain only still-live current-day matches.
        persistState(force=True, sync_backup=True)

    return changed or state_needs_sync


def archiveExhaustedClosedRecoveries(now_epoch=None):
    # Compatibility wrapper for older call sites. Day closure is now deterministic
    # and does not depend on recovery-attempt counters.
    return closeDueMatchDays(now_epoch=now_epoch)

def purgeTeams(teams):
    for team in list(teams):
        cleanupEventState(team)
        if team in DA_TEAMS:
            DA_TEAMS.remove(team)
    markStateDirty()


def _catalogueResultValid(result):
    """Betfair listMarketCatalogue returns a JSON array on every valid call."""
    return isinstance(result, list)


def _refreshBetfairSessionForCatalogue():
    """Refresh the Betfair session at most once per cooldown window."""
    global LAST_CATALOGUE_SESSION_REFRESH
    now_epoch = time.time()
    if now_epoch - LAST_CATALOGUE_SESSION_REFRESH < CATALOGUE_SESSION_REFRESH_COOLDOWN_SECONDS:
        return False

    # Set the timestamp before login so a failed login cannot be hammered every
    # 30-second collector cycle.
    LAST_CATALOGUE_SESSION_REFRESH = now_epoch
    try:
        token = betfairAPI.getNewSessionToken()
        if not token:
            return False
        setter = getattr(betfairAPI, '_setSessionToken', None)
        if not callable(setter):
            return False
        setter(token)
        print('Betfair session refreshed')
        return True
    except Exception as err:
        print(f'Betfair session refresh failed: {err}')
        return False


def _catalogueCallWithRecovery(call, *args, **kwargs):
    """Run one catalogue call, refreshing an unusable session once if needed.

    A genuine no-match response is [] and is therefore considered successful.
    The legacy betfairAPI wrapper returns {} after HTTP/API failures, including
    the repeated 400 response seen after some Windows hibernation resumes.
    """
    try:
        result = call(*args, **kwargs)
    except Exception:
        result = None

    if _catalogueResultValid(result):
        return result, True

    if _refreshBetfairSessionForCatalogue():
        try:
            result = call(*args, **kwargs)
        except Exception:
            result = None
        if _catalogueResultValid(result):
            return result, True

    return [], False


def _reportCatalogueAvailability(current_ok, near_ok):
    """Print only state changes; do not spam every 30-second cycle."""
    global CATALOGUE_API_UNAVAILABLE
    unavailable = not current_ok or not near_ok
    if unavailable and not CATALOGUE_API_UNAVAILABLE:
        print('Betfair catalogue unavailable; retaining cached markets')
    elif not unavailable and CATALOGUE_API_UNAVAILABLE:
        print('Betfair catalogue recovered')
    CATALOGUE_API_UNAVAILABLE = unavailable


def routineCorruptRecoveryEntries(ko_entries, ht_entries, results):
    """Routine pre-boundary samples stay on 30 seconds; fast recovery is boundary-only."""
    return []

def main():
    global filename

    current_catalogue, current_catalogue_ok = _catalogueCallWithRecovery(
        betfairAPI.getMarketCatalogueByEventTypeId, soccerEventTypeID
    )
    near_start_catalogue, near_start_catalogue_ok = _catalogueCallWithRecovery(
        betfairAPI.getMarketCatalogueNearStartByEventTypeId,
        soccerEventTypeID,
        minutes_before=KO_CATALOGUE_LOOKBACK_MINUTES,
        minutes_after=KO_FOCUS_BEFORE_MINUTES
    )
    _reportCatalogueAvailability(current_catalogue_ok, near_start_catalogue_ok)

    # Never interpret a failed API call as an authoritative empty catalogue.
    # Keep the previous cache so tracked matches survive a transient session or
    # network failure and continue normally once the API recovers.
    if not current_catalogue_ok:
        current_catalogue = list(CURRENT_INPLAY_CATALOGUE.values())
    if not near_start_catalogue_ok:
        near_start_catalogue = list(NEAR_START_CATALOGUE.values())

    refreshCatalogueCaches(current_catalogue, near_start_catalogue, current_catalogue_ok)
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
    processKOEvents(timelines)
    catalogue_ko_activated = processCatalogueKickOffFallback(current_catalogue)

    # A NEWLY_ACTIVE catalogue transition is an actual KO whiff, not merely a
    # note for later.  Service its T+0 website-price request in this same cycle
    # before any routine PRE work.  This is deliberately non-blocking: if the
    # book is poor the normal +15..+90 scheduler takes over.
    if catalogue_ko_activated:
        runBoundaryRecoveryTick(refresh_timelines=False)

    # Routine pre-boundary insurance uses only the 30-second heartbeat: KO from
    # scheduled -2 minutes to scheduled KO, HT from FirstHalfEnd +13 minutes.
    ko_entries = koStandardPriceEntries()
    ht_entries = htRecessPriceEntries()
    boundary_by_market = {}
    for entry in ko_entries + ht_entries:
        market_id = getMarketID(entry)
        if market_id:
            boundary_by_market[market_id] = entry
    boundary_entries = list(boundary_by_market.values())
    results = pollBoundaryEntriesRaw(boundary_entries, point='30S_RAW') if boundary_entries else {}
    rememberLatestPreKO(ko_entries, results)
    rememberLatestHTRecess(ht_entries, results)

    # KickOff / SecondHalfKickOff trigger the same POST capture mechanism.
    # T+0 is immediate; only unresolved markets are then retried at +15 seconds,
    # up to six retries / 90 seconds total.  PRE remains ordinary 30-second work.
    applyPendingKO(timelines, results)
    processSecondHalfStarts(timelines, live_signals, results)
    runBoundaryRecoveryTick(refresh_timelines=False)

    # Any optional minute-window feature remains legacy/independent of KO/HT.
    minute_entries = minuteFocusEntries()
    if minute_entries:
        pollEntries(minute_entries, point='WIN')
    standard_entries = boundary_entries + minute_entries
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
    print(f"Leftia_AI v{LEFTIA_AI_VERSION}")
    restored = restoreState()
    if restored:
        finaliseRestoredMatchesFromState()

    # A machine may wake after sleeping through the 04:00 day boundary. Close
    # every expired day before any fresh current-day collection starts.
    closeDueMatchDays(restored=restored)
    scheduleFinalRecoveryJobs(restored=restored)
    persistState(force=True)

    try:
        import signal
        signal.signal(signal.SIGTERM, stopAndSave)
    except Exception:
        pass

    # Normal discovery/timeline/PRE work remains on a 30-second heartbeat.
    # Only unresolved POST capture wakes at 15-second intervals, and all due
    # markets are serviced together: no per-match sleep loops or blocking.
    next_normal = time.time()

    while True:
        try:
            now_epoch = time.time()

            # After hibernation do one normal cycle, never replay missed slots.
            if now_epoch >= next_normal:
                main()
                next_normal = time.time() + STANDARD_INTERVAL
                continue

            recovery_due = _activeBoundaryRecoveryDue(now_epoch)
            if recovery_due is not None and recovery_due <= now_epoch:
                runBoundaryRecoveryTick(refresh_timelines=True)
                continue

            wake_at = next_normal
            if recovery_due is not None:
                wake_at = min(wake_at, recovery_due)
            time.sleep(max(0.05, wake_at - time.time()))

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
            # Brief backoff only. A transient exception must not silence every
            # boundary market for another full 30-second heartbeat.
            time.sleep(min(5, NORMAL_DELAY))
            next_normal = time.time()

if __name__ == '__main__':
    runCollector()
