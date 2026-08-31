from decimal import Decimal
import statistics

BOOK_MIN = 0.80
BOOK_MAX = 1.50
BOOK_TARGET = 1.025
HISTORY_LIMIT = 8
MIN_SPREAD_SAMPLES = 3


def normalise_id(value):
    try:
        return str(int(str(value).strip()))
    except Exception:
        return str(value).strip()


def same_id(a, b):
    return normalise_id(a) == normalise_id(b)


def book_sum(prices):
    if len(prices) != 3 or any(price is None or price <= 1.0 for price in prices):
        return None
    return sum(1.0 / price for price in prices)


def book_is_plausible(prices, low=BOOK_MIN, high=BOOK_MAX):
    value = book_sum(prices)
    return value is not None and low <= value <= high


def _classic_ladder():
    bands = [
        (Decimal('1.01'), Decimal('2.00'), Decimal('0.01')),
        (Decimal('2.00'), Decimal('3.00'), Decimal('0.02')),
        (Decimal('3.00'), Decimal('4.00'), Decimal('0.05')),
        (Decimal('4.00'), Decimal('6.00'), Decimal('0.10')),
        (Decimal('6.00'), Decimal('10.00'), Decimal('0.20')),
        (Decimal('10.00'), Decimal('20.00'), Decimal('0.50')),
        (Decimal('20.00'), Decimal('30.00'), Decimal('1.00')),
        (Decimal('30.00'), Decimal('50.00'), Decimal('2.00')),
        (Decimal('50.00'), Decimal('100.00'), Decimal('5.00')),
        (Decimal('100.00'), Decimal('1000.00'), Decimal('10.00')),
    ]
    values = []
    for start, end, step in bands:
        value = start
        while value < end:
            values.append(float(value))
            value += step
    values.append(1000.0)
    return values


CLASSIC_LADDER = _classic_ladder()
LADDER_INDEX = {round(value, 2): index for index, value in enumerate(CLASSIC_LADDER)}


def _ladder_index(price):
    if price is None:
        return None
    return LADDER_INDEX.get(round(float(price), 2))


def move_ticks(price, ticks):
    index = _ladder_index(price)
    if index is None:
        return None
    target = min(max(index + int(ticks), 0), len(CLASSIC_LADDER) - 1)
    return CLASSIC_LADDER[target]


def spread_ticks(back, lay):
    back_index = _ladder_index(back)
    lay_index = _ladder_index(lay)
    if back_index is None or lay_index is None or lay_index < back_index:
        return None
    return lay_index - back_index


def best_price(exchange, side):
    offers = exchange.get(side, []) if isinstance(exchange, dict) else []
    if not offers:
        return None
    price = offers[0].get('price')
    try:
        return float(price)
    except Exception:
        return None


def market_snapshot(event_node, market_id, selection_ids):
    markets = event_node.get('marketNodes', []) if isinstance(event_node, dict) else []
    market = next((item for item in markets if same_id(item.get('marketId'), market_id)), None)
    if market is None:
        return None

    runners = {normalise_id(item.get('selectionId')): item for item in market.get('runners', [])}
    back = []
    lay = []
    exchanges = []
    for selection_id in selection_ids:
        runner = runners.get(normalise_id(selection_id), {})
        exchange = runner.get('exchange', {})
        exchanges.append(exchange)
        back.append(best_price(exchange, 'availableToBack'))
        lay.append(best_price(exchange, 'availableToLay'))

    return {
        'event_id': normalise_id(event_node.get('eventId')),
        'market_id': normalise_id(market_id),
        'back': back,
        'lay': lay,
        'exchanges': exchanges,
        'book': book_sum(back),
    }


def expected_book(history):
    books = [entry.get('book') for entry in history if entry.get('book') is not None and BOOK_MIN <= entry.get('book') <= BOOK_MAX]
    if not books:
        return BOOK_TARGET
    return statistics.median(books[-HISTORY_LIMIT:])


def recent_clean(history):
    return [entry for entry in history if book_is_plausible(entry.get('back', []))][-HISTORY_LIMIT:]


def snapshot_is_strong(snapshot, history):
    if snapshot is None or not book_is_plausible(snapshot.get('back', [])):
        return False
    target = expected_book(history)
    return abs(snapshot['book'] - target) <= 0.12


def choose_complete_snapshot(candidates, history):
    target = expected_book(history)
    valid = [entry for entry in candidates if book_is_plausible(entry.get('back', []))]
    if not valid:
        return None
    return min(valid, key=lambda entry: abs(entry['book'] - target))


def _runner_anchor(history, runner_index):
    values = [entry['back'][runner_index] for entry in recent_clean(history) if entry['back'][runner_index] is not None]
    return statistics.median(values) if values else None


def _tick_distance(a, b):
    ai = _ladder_index(a)
    bi = _ladder_index(b)
    if ai is None or bi is None:
        return 9999
    return abs(ai - bi)


def mix_candidates(candidates, history):
    target = expected_book(history)
    pools = []
    for runner_index in range(3):
        values = []
        for entry in candidates:
            price = entry.get('back', [None, None, None])[runner_index]
            if price is not None and price > 1.0 and price not in values:
                values.append(price)
        anchor = _runner_anchor(history, runner_index)
        if anchor is not None:
            values.sort(key=lambda value: _tick_distance(value, anchor))
        pools.append(values[:5])

    if any(not pool for pool in pools):
        return None

    anchors = [_runner_anchor(history, index) for index in range(3)]
    best = None
    for home in pools[0]:
        for away in pools[1]:
            for draw in pools[2]:
                prices = [home, away, draw]
                book = book_sum(prices)
                if book is None or not BOOK_MIN <= book <= BOOK_MAX:
                    continue
                anchor_penalty = 0
                for index, price in enumerate(prices):
                    if anchors[index] is not None:
                        anchor_penalty += min(_tick_distance(price, anchors[index]), 50) / 50.0
                score = abs(book - target) + (0.10 * anchor_penalty)
                if best is None or score < best['score']:
                    best = {'back': prices, 'book': book, 'score': score}
    return best


def stable_spread(history, runner_index):
    spreads = []
    for entry in recent_clean(history):
        back = entry.get('back', [None, None, None])[runner_index]
        lay = entry.get('lay', [None, None, None])[runner_index]
        spread = spread_ticks(back, lay)
        if spread is not None:
            spreads.append(spread)
    if len(spreads) < MIN_SPREAD_SAMPLES:
        return None
    recent = spreads[-HISTORY_LIMIT:]
    median = int(round(statistics.median(recent)))
    if max(recent) - min(recent) > max(3, median):
        return None
    return median


def infer_back_from_lay(lay, history, runner_index):
    spread = stable_spread(history, runner_index)
    if lay is None or spread is None:
        return None
    return move_ticks(lay, -spread)


def repair_missing_back(snapshot, history):
    if snapshot is None:
        return None
    prices = list(snapshot.get('back', []))
    if len(prices) != 3:
        return None
    changed = []
    for runner_index in range(3):
        if prices[runner_index] is None:
            inferred = infer_back_from_lay(snapshot.get('lay', [None, None, None])[runner_index], history, runner_index)
            if inferred is not None:
                prices[runner_index] = inferred
                changed.append((runner_index, inferred))
    book = book_sum(prices)
    if book is None or not BOOK_MIN <= book <= BOOK_MAX:
        return None
    return {'back': prices, 'book': book, 'inferred': changed}


def repair_suspect_back(prices, candidates, history):
    clean = recent_clean(history)
    if not clean or len(prices) != 3:
        return None

    anchors = [_runner_anchor(history, index) for index in range(3)]
    if any(anchor is None for anchor in anchors):
        return None

    suspect = max(range(3), key=lambda index: _tick_distance(prices[index], anchors[index]))
    lay = None
    for snapshot in reversed(candidates):
        value = snapshot.get('lay', [None, None, None])[suspect]
        if value is not None:
            lay = value
            break

    inferred = infer_back_from_lay(lay, history, suspect)
    if inferred is None:
        return None

    repaired = list(prices)
    repaired[suspect] = inferred
    book = book_sum(repaired)
    if book is None or not BOOK_MIN <= book <= BOOK_MAX:
        return None

    target = expected_book(history)
    old_book = book_sum(prices)
    if old_book is not None and abs(book - target) >= abs(old_book - target):
        return None
    return {'back': repaired, 'book': book, 'inferred': [(suspect, inferred)]}


def latest_consistent(history):
    clean = recent_clean(history)
    if not clean:
        return None
    if len(clean) == 1:
        return clean[-1]

    target = expected_book(clean)
    for entry in reversed(clean):
        if abs(entry['book'] - target) <= 0.12:
            return entry
    return min(clean, key=lambda entry: abs(entry['book'] - target))
