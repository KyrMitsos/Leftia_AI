import json  # EXAMPLES: https://stackabuse.com/reading-and-writing-json-to-a-file-in-python/
import requests
import datetime
from requests.exceptions import HTTPError
import os
import src.ufuncs as lib

my_timeout = 10

"""
make a call API-NG
"""


def _setSessionToken(newSessionToken):
    global headers, sessionToken
    sessionToken = newSessionToken
    headers = {
        'X-Application': creds["DelayAppKey"],
        'X-Authentication': sessionToken,
        'content-type': 'application/json',
        'accept': 'application/json'
    }


def callAping(url, request, safe_to_retry=True):
    global headers

    for attempt in range(2):
        try:
            response = requests.post(url, data=request, headers=headers, timeout=my_timeout)
            response.raise_for_status()
            print('Success!')
            return response.text
        except HTTPError as http_err:
            status = http_err.response.status_code if http_err.response is not None else None
            print(f'HTTP error occurred: {http_err}')

            if status in [401, 403]:
                newSessionToken = getNewSessionToken()
                if newSessionToken:
                    _setSessionToken(newSessionToken)
                    if safe_to_retry and attempt == 0:
                        continue
                return "{}"

            if not safe_to_retry or attempt > 0:
                return "{}"
            if status == 429:
                return "{}"
            if status is not None and status >= 500:
                continue

            return "{}"
        except requests.RequestException as err:
            print(f'Other error occurred: {err}')
            if safe_to_retry and attempt == 0:
                continue
            return "{}"
        except Exception as err:
            print(f'Other error occurred: {err}')
            return "{}"

    return "{}"


def getNewSessionToken():
    sessionToken = ''
    resp_json = {}
    resp = None
    print("Inside getNewSessionToken()")
    try:
        headers = {'X-Application': creds["ApplicationName"], 'Content-Type': 'application/x-www-form-urlencoded'}
        payload = f'username={creds["un"]}&password={creds["ps"]}'
        crt_path = os.path.join(script_dir, 'client-2048.crt')
        key_path = os.path.join(script_dir, 'client-2048.key')
        resp = requests.post('https://identitysso-cert.betfair.com/api/certlogin', data=payload, cert=(crt_path, key_path), headers=headers)

        if resp.status_code == 200:
            resp_json = resp.json()
            sessionToken = resp_json['sessionToken']
    except Exception as err:
        print("error " + str(err))
        if ((resp is not None) & (hasattr(resp, 'text'))):
            print(resp.text)

    print("Leaving getNewSessionToken()")
    return sessionToken


"""
calling getEventTypes operation
"""


def getEventTypes():
    endPoint = 'https://api.betfair.com/exchange/betting/rest/v1.0/listEventTypes/'
    event_type_req = '{"filter":{ }}'
    print('Calling listEventTypes to get event Type ID')
    eventTypesResponse = callAping(endPoint, event_type_req)
    """
    print eventTypesResponse
    """
    eventTypeLoads = json.loads(eventTypesResponse)
    """
    print eventTypeLoads
    """
    return eventTypeLoads


"""
Extraction eventypeId for eventTypeName from evetypeResults

    Example:
    eventTypesResult = getEventTypes()
    soccerEventTypeID = getEventTypeIDFromName(eventTypesResult, 'Soccer')
    print('Eventype Id for Soccer is :' + str(soccerEventTypeID))
"""


def getEventTypeIDFromName(eventTypesResult, requestedEventTypeName):
    if(eventTypesResult is not None):
        for event in eventTypesResult:
            eventTypeName = event['eventType']['name']
            if (eventTypeName == requestedEventTypeName):
                return event['eventType']['id']


"""
calling "listEvents" operation
    Description:
    listEvents - use "Starts After", "Starts Before", InPlay, and EventTypeID = 1 to get what EventID is currently in play

    Example:
    allEvents = betfairAPI.getEvents(soccerEventTypeID)  # get today's in-play events (unordered)
    print('Event Ids returned were :' + str(len(allEvents)))
"""


def getEvents(eventTypeID):
    endPoint = 'https://api.betfair.com/exchange/betting/rest/v1.0/listEvents/'

    today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start = today.strftime('%Y-%m-%dT%H:%M:%SZ')
    end = (today + datetime.timedelta(1)).strftime('%Y-%m-%dT%H:%M:%SZ')

    events_req = f'''
    {{
        "filter" : {{
            "eventTypeIds" : ["{eventTypeID}"],
            "marketStartTime" : {{
                "from" : "{start}",
                "to" : "{end}"
            }},
            "inPlayOnly" : "true"
        }}
    }}
    '''
    print('Calling listEvents to get today\'s EventIDs')
    eventsResponse = callAping(endPoint, events_req)
    """
    print eventsResponse
    """
    eventsLoads = json.loads(eventsResponse)
    """
    print eventsLoads
    """
    return eventsLoads


"""
calling "listMarketTypes" operation
    Description:
    listMarketTypes - lists Market Types (we are interested in MATCH_ODDS) given an EventID or MarketID
    Notes:
    This is currently not used as it only returns the number of events that support the given MarketTypeCode.
    getMarketCatalogue() below supersedes this function.
"""


def getMarketTypes(eventIDs):
    endPoint = 'https://api.betfair.com/exchange/betting/rest/v1.0/listMarketTypes/'

    _eventIDs = '","'.join([event_type_object['event']['id'] for event_type_object in eventIDs])

    events_req = f'''
    {{
        "filter" : {{
            "eventIds" : ["{_eventIDs}"],
            "marketTypeCodes" : ["MATCH_ODDS"]
        }}
    }}
    '''
    print('Calling listMarketTypes to get MarketIDs associated with today\'s EventIDs')
    marketTypesResponse = callAping(endPoint, events_req)
    """
    print marketTypesResponse
    """
    marketTypesLoads = json.loads(marketTypesResponse)
    """
    print marketTypesLoads
    """
    return marketTypesLoads


"""
calling "listMarketCatalogue" operation
    Description: listMarketCatalogue - lists the MarketIDs of a specific EventID (we can use
    MarketName = "Match Odds" to know the MarketID. Bear in mind we need to set "Max Results" to
    something big >20 to show all MarketIDs. Can further filter using MarketTypes = MATCH_ODDS to show
    only the match odds MarketID. With Additional Data: RUNNER_METADATA we get the SelectionID for Home,
     Away, Draw selections
"""


def getMarketCatalogueByEventId(eventIDs, today=None):
    if(eventIDs is not None):
        print('Calling listMarketCatalogue Operation to get MarketID and selectionId by eventIDs')
        endPoint = 'https://api.betfair.com/exchange/betting/rest/v1.0/listMarketCatalogue/'

        if (today is None):
            today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        start = today.strftime('%Y-%m-%dT%H:%M:%SZ')
        end = (today + datetime.timedelta(1)).strftime('%Y-%m-%dT%H:%M:%SZ')

        market_catalogue_req = f'''
        {{
            "filter" : {{
                "eventIds" : ["{eventIDs}"],
                "marketStartTime" : {{
                    "from" : "{start}",
                    "to" : "{end}"
                }},
                "marketTypeCodes" : ["MATCH_ODDS"],
                "inPlayOnly" : "true"
            }},
            "sort" : "FIRST_TO_START",
            "maxResults" : "1000",
            "marketProjection" : ["COMPETITION", "EVENT", "MARKET_DESCRIPTION", "RUNNER_DESCRIPTION"]
        }}
        '''

        """
        print  market_catalogue_req
        """
        market_catalogue_response = callAping(endPoint, market_catalogue_req)
        """
        print market_catalogue_response
        """
        market_catalogue_loads = json.loads(market_catalogue_response)
        return market_catalogue_loads


def getMarketCatalogueByEventTypeId(eventTypeID, today=None):
    if(eventTypeID is not None):
        print('Calling listMarketCatalogue Operation to get MarketID and selectionId by eventTypeID')
        endPoint = 'https://api.betfair.com/exchange/betting/rest/v1.0/listMarketCatalogue/'

        if (today is None):
            today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        start = today.strftime('%Y-%m-%dT%H:%M:%SZ')
        end = (today + datetime.timedelta(1)).strftime('%Y-%m-%dT%H:%M:%SZ')

        market_catalogue_req = f'''
        {{
            "filter" : {{
                "eventTypeIds" : ["{eventTypeID}"],
                "marketTypeCodes" : ["MATCH_ODDS"],
                "inPlayOnly" : "true",
                "turnInPlayEnabled" : "true"
            }},
            "sort" : "FIRST_TO_START",
            "maxResults" : "1000",
            "marketProjection" : ["COMPETITION", "EVENT", "MARKET_DESCRIPTION", "RUNNER_DESCRIPTION"]
        }}
        '''

        """
        print  market_catalogue_req
        """
        market_catalogue_response = callAping(endPoint, market_catalogue_req)
        """
        print market_catalogue_response
        """
        market_catalogue_loads = json.loads(market_catalogue_response)
        return market_catalogue_loads


def getMarketCatalogueNearStartByEventTypeId(eventTypeID, minutes_before=15, minutes_after=5):
    if(eventTypeID is not None):
        print('Calling listMarketCatalogue Operation to get near-start MarketIDs')
        endPoint = 'https://api.betfair.com/exchange/betting/rest/v1.0/listMarketCatalogue/'

        now = datetime.datetime.now(datetime.timezone.utc)
        start = (now - datetime.timedelta(minutes=minutes_before)).strftime('%Y-%m-%dT%H:%M:%SZ')
        end = (now + datetime.timedelta(minutes=minutes_after)).strftime('%Y-%m-%dT%H:%M:%SZ')

        market_catalogue_req = f'''
        {{
            "filter" : {{
                "eventTypeIds" : ["{eventTypeID}"],
                "marketTypeCodes" : ["MATCH_ODDS"],
                "marketStartTime" : {{
                    "from" : "{start}",
                    "to" : "{end}"
                }},
                "turnInPlayEnabled" : "true"
            }},
            "sort" : "FIRST_TO_START",
            "maxResults" : "1000",
            "marketProjection" : ["COMPETITION", "EVENT", "MARKET_DESCRIPTION", "RUNNER_DESCRIPTION"]
        }}
        '''

        market_catalogue_response = callAping(endPoint, market_catalogue_req)
        return json.loads(market_catalogue_response)


def getMarketId(marketCatalogueResult):
    if(marketCatalogueResult is not None):
        for market in marketCatalogueResult:
            return market['marketId']


def getSelectionId(marketCatalogueResult):
    if(marketCatalogueResult is not None):
        for market in marketCatalogueResult:
            return market['runners'][0]['selectionId']


"""
calling "listMarketBook" operation
    Description: listMarketBook - Lists Odds (Price, Size) input
    a) MarketID of the MATCH_ODDS market,
    b) Price Data: EX_ALL_OFFERS or EX_BEST_OFFERS. Under 'Runners' we should find the SelectionID of
    what we want to bet on.
"""


def getMarketBook(marketIDs):
    if(marketIDs is not None):
        print(f'Calling listMarketBook to read prices for the Market(s) with ID : {marketIDs}')

        # market_book_req = '{"marketIds":["' + marketId + \
        #     '"],"priceProjection":{"priceData":["EX_BEST_OFFERS"]}}'

        market_book_req = f'''
        {{
            "marketIds" : ["{marketIDs}"],
            "priceProjection": {{
                "priceData" : ["EX_BEST_OFFERS"],
                "virtualise" : "true"
            }},
            "orderProjection" : "EXECUTABLE",
            "matchProjection" : "ROLLED_UP_BY_AVG_PRICE"
        }}
        '''

        """
        print  market_book_req
        """
        endPoint = 'https://api.betfair.com/exchange/betting/rest/v1.0/listMarketBook/'

        market_book_response = callAping(endPoint, market_book_req)
        """
        print market_book_response
        """
        market_book_loads = json.loads(market_book_response)
        return market_book_loads


def getMarketPrices(marketIDs):
    if(marketIDs is not None):
        print(f'Calling listMarketBook to read prices for the Market(s) with ID : {marketIDs}')
        market_book_req = f'''
        {{
            "marketIds" : ["{marketIDs}"],
            "priceProjection": {{
                "priceData" : ["EX_BEST_OFFERS"],
                "virtualise" : "true"
            }}
        }}
        '''
        endPoint = 'https://api.betfair.com/exchange/betting/rest/v1.0/listMarketBook/'
        market_book_response = callAping(endPoint, market_book_req)
        return json.loads(market_book_response)


"""
calling "listClearedOrders" operation
    Description:
    listClearedOrders - use "Starts After", "Starts Before", betStatus = SETTLED and EventTypeID = 1 to get P/L
"""


def getClearedOrders(eventTypeID, today):
    endPoint = 'https://api.betfair.com/exchange/betting/rest/v1.0/listClearedOrders/'

    # today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start = today.strftime('%Y-%m-%dT%H:%M:%SZ')
    end = (today + datetime.timedelta(1)).strftime('%Y-%m-%dT%H:%M:%SZ')

    cleared_orders_req = f'''
    {{
        "betStatus" : "SETTLED",
        "eventTypeIds" : ["{eventTypeID}"],
        "settledDateRange" : {{
            "from" : "{start}",
            "to" : "{end}"
        }}
    }}
    '''
    print('Calling listEvents to get today\'s EventIDs')
    eventsResponse = callAping(endPoint, cleared_orders_req)
    """
    print eventsResponse
    """
    eventsLoads = json.loads(eventsResponse)
    """
    print eventsLoads
    """
    return eventsLoads


def printPriceInfo(market_book_result):
    print('Please find Best three available prices for the runners')
    for marketBook in market_book_result:
        try:
            runners = marketBook['runners']
            for runner in runners:
                print('Selection id is ' + str(runner['selectionId']))
                if (runner['status'] == 'ACTIVE'):
                    print('Available to back price :' + str(runner['ex']['availableToBack']))
                    print('Available to lay price :' + str(runner['ex']['availableToLay']))
                else:
                    print('This runner is not active')
        except Exception:
            print('No runners available for this market')


"""
calling "placeOrders" operation
    Description:
    placeOrders - use marketId, selectionId, side: "BACK"/"LAY", size (Stake), price (Odds), customerRef (optional)
"""


def placeBet(marketId, selectionId, side, size, price, customerRef=""):
    if(marketId is not None and selectionId is not None):
        print('Calling placeOrder for marketId :' + marketId + ' with selection id :' + str(selectionId))
        place_order_req = f'''
        {{
            "marketId" : "{marketId}",
            "instructions" : ["
                "selectionId" : "{selectionId}",
                "handicap" : "0",
                "side" : "{side}",
                "orderType" : "LIMIT",
                "limitOrder" : {{
                    "size" : "{size}",
                    "price" : "{price}",
                    "persistenceType" : "LAPSE"
                }}
            "],
            "customerRef" : "{customerRef}"
        }}
        '''
        # place_order_Req = '{"marketId":"' + marketId + '","instructions":'\
        #                                                '[{"selectionId":"' + str(
        #                                                    selectionId) + '","handicap":"0","side":"BACK","orderType":"LIMIT","limitOrder":{"size":"0.01","price":"1.50","persistenceType":"LAPSE"}}],"customerRef":"test12121212121"}'
        endPoint = 'https://beta-api.betfair.com/rest/v1.0/placeOrders/'
        """
        print place_order_Req
        """
        place_order_Response = callAping(endPoint, place_order_req, safe_to_retry=False)
        place_order_load = json.loads(place_order_Response)
        print('Place order status is ' + place_order_load['status'])
        """
        print 'Place order error status is ' + place_order_load['errorCode']
        """
        print('Reason for Place order failure is ' + place_order_load['instructionReports'][0]['errorCode'])
        """
        print place_order_Response
        """


script_dir = os.path.dirname(__file__)  # <-- absolute dir the script is in
rel_path = "creds.json"
abs_file_path = os.path.join(script_dir, rel_path)
creds = lib.readFromJSON(abs_file_path)  # load in BetFair Account creds
sessionToken = getNewSessionToken()
"""
headers = { 'X-Application' : 'xxxxxxx', 'X-Authentication' : 'xxxxxxxxx', 'content-type' : 'application/json', 'Accept': 'application/json'}
"""
headers = {
    'X-Application': creds["DelayAppKey"],
    'X-Authentication': sessionToken,
    'content-type': 'application/json',
    'accept': 'application/json'
}
