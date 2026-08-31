import json  # EXAMPLES: https://stackabuse.com/reading-and-writing-json-to-a-file-in-python/
import os
import src.betfairAPI.betfairAPI as betfairAPI

# Writing to json file


def saveToJSON(data, filename, mode='w'):
    if mode != 'w':
        with open(filename, mode) as outfile:
            json.dump(data, outfile, indent=4)
        return

    temp_filename = filename + ".tmp"
    with open(temp_filename, 'w') as outfile:
        json.dump(data, outfile, indent=4)
    os.replace(temp_filename, filename)

# Reading from json file


def readFromJSON(filename):
    try:
        with open(filename) as json_file:
            return json.load(json_file)
    except Exception as err:
        print(f'{err}')


eventTemplateKeys = [
    "Date", "Competition", "Home", "Away",
    "HT_Home", "HT_Away", "FT_Home", "FT_Away",
    "KO_1", "KO_2", "KO_X", "HT_1", "HT_2", "HT_X",
    "HT_1/X", "HT_2/X", "HT_1/2",
    "STAKE", "FINAL",
    "MODEL_DT1", "MULTI_DT1", "P/L_DT1",
    "MODEL_ZZCX", "MULTI_ZZCX", "P/L_ZZCX"
]


def render(values):
    return dict(zip(eventTemplateKeys, values))


def doubleChance(a, b):
    return (a * b) / (a + b)


class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def expiredMatch(match, today_datetime, delta_hours):
    match_datetime = betfairAPI.datetime.datetime.strptime(match['output']['Date'], '%Y-%m-%dT%H:%M:%S.%fZ')
    threshold_datetime = (match_datetime + betfairAPI.datetime.timedelta(hours=delta_hours))
    return threshold_datetime < today_datetime

